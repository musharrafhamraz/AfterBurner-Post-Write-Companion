"""Security Sentinel — runs static analysis tools and triages findings via LLM."""

import time
from typing import List

from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger

from src.config import settings
from src.graph.state import AfterburnerState
from src.models.reports import SecurityFinding, SecurityReport
from src.tools.security_tools import (
    run_semgrep,
    run_bandit,
    run_npm_audit,
    run_cargo_audit,
    aggregate_security_findings,
)
from src.utils.llm import get_llm


SECURITY_TRIAGE_PROMPT = """You are a senior security engineer triaging static analysis findings.

Given the following security scan results, classify each finding as:
- "critical" — must be fixed before shipping (SQL injection, RCE, auth bypass, secrets in code)
- "warning" — should be reviewed but not necessarily blocking (weak crypto, missing input validation)
- "info" — informational, low risk (style issues, minor best-practice violations)

Respond with a JSON array of objects: [{"index": 0, "severity": "critical|warning|info", "reason": "..."}]

Only output the JSON array, nothing else.

Findings:
{findings}
"""


def security_sentinel_node(state: AfterburnerState) -> dict:
    """
    LangGraph node: run security scans on changed files and triage results.

    Runs Semgrep, Bandit, npm audit, and cargo audit based on detected file types.
    Uses LLM to re-classify finding severities for more accurate gating.

    Returns state updates for:
        - security_report
        - security_passed
        - security_issues_count
        - current_stage
        - reflection_count (incremented on failure)
    """
    repo_path = state["repo_path"]
    changed_files = state.get("changed_files", [])
    file_types = state.get("file_types", {})
    reflection_count = state.get("reflection_count", 0)

    logger.info("🛡️ Running security analysis (attempt {})", reflection_count + 1)

    start_time = time.time()
    all_findings: List[SecurityFinding] = []

    # Run Semgrep (language-agnostic)
    if settings.ENABLE_SEMGREP:
        logger.debug("Running Semgrep...")
        findings = run_semgrep(repo_path, changed_files)
        all_findings.extend(findings)
        logger.info("Semgrep: {} findings", len(findings))

    # Run Bandit (Python only)
    if settings.ENABLE_BANDIT and "python" in file_types:
        logger.debug("Running Bandit...")
        findings = run_bandit(repo_path, file_types["python"])
        all_findings.extend(findings)
        logger.info("Bandit: {} findings", len(findings))

    # Run npm audit (Node.js projects)
    if "javascript" in file_types or "typescript" in file_types:
        logger.debug("Running npm audit...")
        findings = run_npm_audit(repo_path)
        all_findings.extend(findings)
        logger.info("npm audit: {} findings", len(findings))

    # Run cargo audit (Rust projects)
    if "rust" in file_types:
        logger.debug("Running cargo audit...")
        findings = run_cargo_audit(repo_path)
        all_findings.extend(findings)
        logger.info("cargo audit: {} findings", len(findings))

    # LLM triage — re-classify severities if we have findings
    if all_findings:
        all_findings = _llm_triage(all_findings)

    # Aggregate into report
    elapsed_ms = (time.time() - start_time) * 1000
    report = aggregate_security_findings(all_findings, block_on=settings.SECURITY_BLOCK_ON)
    report.scan_duration_ms = elapsed_ms

    logger.info(
        "Security scan complete: {} findings ({} critical, {} warning) — {}",
        len(report.findings),
        report.critical_count,
        report.warning_count,
        "PASSED" if report.passed else "BLOCKED",
    )

    update = {
        "security_report": report.model_dump(),
        "security_passed": report.passed,
        "security_issues_count": len(report.findings),
        "current_stage": "security_review_complete",
    }

    # Increment reflection count if failed
    if not report.passed:
        update["reflection_count"] = reflection_count + 1
        # Add diagnostic context for the reflection loop
        update["messages"] = [HumanMessage(content=(
            f"Security scan FAILED with {report.critical_count} critical findings. "
            f"Top issues:\n" + "\n".join(
                f"- [{f.tool}] {f.file}:{f.line} — {f.message}"
                for f in report.findings if f.severity == "critical"
            )[:1000]
        ))]

    return update


def _llm_triage(findings: List[SecurityFinding]) -> List[SecurityFinding]:
    """
    Use LLM to re-classify finding severities for more accurate gating.

    Falls back to original severities if LLM call fails.
    """
    try:
        llm = get_llm(temperature=0.0)

        findings_text = "\n".join(
            f"[{i}] tool={f.tool} severity={f.severity} file={f.file}:{f.line} message={f.message}"
            for i, f in enumerate(findings)
        )

        response = llm.invoke([
            SystemMessage(content="You are a security triage expert."),
            HumanMessage(content=SECURITY_TRIAGE_PROMPT.format(findings=findings_text)),
        ])

        import json
        triaged = json.loads(response.content)

        for item in triaged:
            idx = item.get("index")
            new_severity = item.get("severity")
            if idx is not None and 0 <= idx < len(findings) and new_severity in {"critical", "warning", "info"}:
                if findings[idx].severity != new_severity:
                    logger.debug(
                        "LLM re-classified finding {} from {} to {}: {}",
                        idx,
                        findings[idx].severity,
                        new_severity,
                        item.get("reason", ""),
                    )
                    findings[idx].severity = new_severity

    except Exception as e:
        logger.warning("LLM triage failed, using original severities: {}", str(e))

    return findings
