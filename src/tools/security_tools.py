"""Security tools — wrappers for Semgrep, Bandit, cargo audit, npm audit."""

import json
import subprocess
import time
from typing import List, Optional

from loguru import logger
from src.models.reports import SecurityFinding, SecurityReport


def run_semgrep(repo_path: str, files: Optional[List[str]] = None) -> List[SecurityFinding]:
    """
    Run Semgrep SAST scanner on changed files.

    Args:
        repo_path: Absolute path to the repository.
        files: Specific files to scan. If None, scans the entire repo.

    Returns:
        List of SecurityFinding objects.
    """
    cmd = ["semgrep", "scan", "--json", "--quiet"]

    if files:
        for f in files:
            cmd.extend(["--include", f])

    cmd.append(repo_path)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=repo_path,
        )
        return _parse_semgrep_output(result.stdout)
    except FileNotFoundError:
        logger.warning("Semgrep not installed — skipping. Install with: pip install semgrep")
        return []
    except subprocess.TimeoutExpired:
        logger.error("Semgrep timed out after 120s")
        return [SecurityFinding(
            tool="semgrep",
            severity="warning",
            file="<timeout>",
            message="Semgrep scan timed out after 120 seconds",
        )]


def _parse_semgrep_output(raw_json: str) -> List[SecurityFinding]:
    """Parse Semgrep JSON output into SecurityFinding objects."""
    findings = []
    try:
        data = json.loads(raw_json) if raw_json.strip() else {"results": []}
        for r in data.get("results", []):
            severity_map = {"ERROR": "critical", "WARNING": "warning", "INFO": "info"}
            findings.append(SecurityFinding(
                tool="semgrep",
                severity=severity_map.get(r.get("extra", {}).get("severity", "INFO"), "info"),
                file=r.get("path", "unknown"),
                line=r.get("start", {}).get("line"),
                message=r.get("extra", {}).get("message", r.get("check_id", "unknown")),
                rule_id=r.get("check_id"),
            ))
    except json.JSONDecodeError:
        logger.warning("Failed to parse Semgrep JSON output")

    return findings


def run_bandit(repo_path: str, files: Optional[List[str]] = None) -> List[SecurityFinding]:
    """
    Run Bandit Python security scanner on changed Python files.

    Args:
        repo_path: Absolute path to the repository.
        files: Specific .py files to scan. If None, scans all Python files.

    Returns:
        List of SecurityFinding objects.
    """
    # Filter to Python files only
    if files:
        py_files = [f for f in files if f.endswith(".py")]
        if not py_files:
            logger.debug("No Python files in changeset — skipping Bandit")
            return []
    else:
        py_files = None

    cmd = ["bandit", "-f", "json", "-q"]

    if py_files:
        cmd.extend(py_files)
    else:
        cmd.extend(["-r", repo_path])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=repo_path,
        )
        return _parse_bandit_output(result.stdout)
    except FileNotFoundError:
        logger.warning("Bandit not installed — skipping. Install with: pip install bandit")
        return []
    except subprocess.TimeoutExpired:
        logger.error("Bandit timed out after 120s")
        return [SecurityFinding(
            tool="bandit",
            severity="warning",
            file="<timeout>",
            message="Bandit scan timed out after 120 seconds",
        )]


def _parse_bandit_output(raw_json: str) -> List[SecurityFinding]:
    """Parse Bandit JSON output into SecurityFinding objects."""
    findings = []
    try:
        data = json.loads(raw_json) if raw_json.strip() else {"results": []}
        severity_map = {"HIGH": "critical", "MEDIUM": "warning", "LOW": "info"}

        for r in data.get("results", []):
            findings.append(SecurityFinding(
                tool="bandit",
                severity=severity_map.get(r.get("issue_severity", "LOW"), "info"),
                file=r.get("filename", "unknown"),
                line=r.get("line_number"),
                message=r.get("issue_text", "Unknown issue"),
                rule_id=r.get("test_id"),
            ))
    except json.JSONDecodeError:
        logger.warning("Failed to parse Bandit JSON output")

    return findings


def run_npm_audit(repo_path: str) -> List[SecurityFinding]:
    """
    Run npm audit for Node.js dependency vulnerabilities.

    Only runs if package.json exists in repo_path.

    Returns:
        List of SecurityFinding objects.
    """
    import os
    if not os.path.exists(os.path.join(repo_path, "package.json")):
        logger.debug("No package.json found — skipping npm audit")
        return []

    cmd = ["npm", "audit", "--json"]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=repo_path,
        )
        return _parse_npm_audit_output(result.stdout)
    except FileNotFoundError:
        logger.warning("npm not installed — skipping npm audit")
        return []
    except subprocess.TimeoutExpired:
        logger.error("npm audit timed out")
        return []


def _parse_npm_audit_output(raw_json: str) -> List[SecurityFinding]:
    """Parse npm audit JSON output."""
    findings = []
    try:
        data = json.loads(raw_json) if raw_json.strip() else {}
        severity_map = {"critical": "critical", "high": "critical", "moderate": "warning", "low": "info"}

        for vuln_id, vuln in data.get("vulnerabilities", {}).items():
            findings.append(SecurityFinding(
                tool="npm_audit",
                severity=severity_map.get(vuln.get("severity", "low"), "info"),
                file="package.json",
                message=f"{vuln_id}: {vuln.get('title', 'Unknown vulnerability')}",
                rule_id=vuln_id,
            ))
    except json.JSONDecodeError:
        logger.warning("Failed to parse npm audit JSON output")

    return findings


def run_cargo_audit(repo_path: str) -> List[SecurityFinding]:
    """
    Run cargo audit for Rust dependency vulnerabilities.

    Only runs if Cargo.toml exists in repo_path.

    Returns:
        List of SecurityFinding objects.
    """
    import os
    if not os.path.exists(os.path.join(repo_path, "Cargo.toml")):
        logger.debug("No Cargo.toml found — skipping cargo audit")
        return []

    cmd = ["cargo", "audit", "--json"]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=repo_path,
        )
        return _parse_cargo_audit_output(result.stdout)
    except FileNotFoundError:
        logger.warning("cargo-audit not installed — skipping")
        return []
    except subprocess.TimeoutExpired:
        logger.error("cargo audit timed out")
        return []


def _parse_cargo_audit_output(raw_json: str) -> List[SecurityFinding]:
    """Parse cargo audit JSON output."""
    findings = []
    try:
        data = json.loads(raw_json) if raw_json.strip() else {}
        for vuln in data.get("vulnerabilities", {}).get("list", []):
            advisory = vuln.get("advisory", {})
            findings.append(SecurityFinding(
                tool="cargo_audit",
                severity="critical",
                file="Cargo.toml",
                message=f"{advisory.get('id', 'UNKNOWN')}: {advisory.get('title', 'Unknown')}",
                rule_id=advisory.get("id"),
            ))
    except json.JSONDecodeError:
        logger.warning("Failed to parse cargo audit JSON output")

    return findings


def aggregate_security_findings(
    findings: List[SecurityFinding],
    block_on: str = "critical",
) -> SecurityReport:
    """
    Aggregate all findings into a SecurityReport with pass/fail determination.

    Args:
        findings: All security findings across tools.
        block_on: Minimum severity that causes a fail: 'critical' or 'warning'.

    Returns:
        SecurityReport with pass/fail status.
    """
    blocking_severities = {"critical"}
    if block_on == "warning":
        blocking_severities.add("warning")

    has_blockers = any(f.severity in blocking_severities for f in findings)

    return SecurityReport(
        findings=findings,
        passed=not has_blockers,
        scan_duration_ms=0.0,  # Caller should set this
    )
