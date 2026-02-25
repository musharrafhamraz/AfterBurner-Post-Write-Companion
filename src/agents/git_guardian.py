"""Git Guardian — creates clean commits, branches, and Pull Requests."""

from datetime import datetime
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger

from src.config import settings
from src.graph.state import AfterburnerState
from src.models.reports import SecurityReport
from src.tools.git_tools import create_branch, commit, push
from src.tools.github_tools import create_pr, get_codeowners, generate_pr_body
from src.utils.llm import get_llm


COMMIT_MSG_PROMPT = """You are a senior developer writing a git commit message.

Rules:
1. Use Conventional Commits format: type(scope): description
2. Types: feat, fix, refactor, docs, style, test, chore, perf, ci
3. Keep the subject line under 72 characters
4. Add a brief body (2-3 lines) explaining WHAT changed and WHY
5. Do NOT include file lists — git tracks that

Context:
- Diff summary: {diff_summary}
- Changed files: {changed_files}
- Security status: {security_status}
- Test status: {test_status}

Output ONLY the commit message, nothing else.
"""


def git_guardian_node(state: AfterburnerState) -> dict:
    """
    LangGraph node: create branch, generate commit message, commit, push, and open PR.

    Uses LLM to generate Conventional Commits-style messages.
    Creates a PR on GitHub if GITHUB_TOKEN and GITHUB_REPO are configured.

    Returns state updates for:
        - branch_name
        - commit_sha
        - pr_url
        - pr_number
        - current_stage
    """
    repo_path = state["repo_path"]
    changed_files = state.get("changed_files", [])
    diff_summary = state.get("diff_summary", "")
    security_passed = state.get("security_passed", True)
    tests_passed = state.get("tests_passed", True)
    security_report_data = state.get("security_report")
    test_results = state.get("test_results", [])

    logger.info("📦 Git Guardian: preparing commit and PR")

    # Generate commit message via LLM
    commit_message = _generate_commit_message(
        diff_summary=diff_summary,
        changed_files=changed_files,
        security_passed=security_passed,
        tests_passed=tests_passed,
    )

    # Create branch if on a protected branch
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    import re
    first_line = commit_message.split("\n")[0]
    commit_type = first_line.split("(")[0].split(":")[0] if ":" in first_line else "feat"
    short_desc = first_line.split(":")[-1].strip()[:30].lower()
    short_desc = re.sub(r'[^a-zA-Z0-9]+', '-', short_desc).strip('-')
    branch_name = f"afterburner/{commit_type}/{short_desc}-{timestamp}"

    try:
        branch_name = create_branch(repo_path, branch_name)
    except Exception as e:
        logger.warning("Branch creation failed (may already be on feature branch): {}", str(e))
        branch_name = None

    # Commit
    try:
        sha = commit(repo_path, changed_files, commit_message)
    except Exception as e:
        logger.error("Commit failed: {}", str(e))
        return {
            "current_stage": "git_complete",
            "errors": [f"Git commit failed: {str(e)}"],
        }

    update = {
        "branch_name": branch_name,
        "commit_sha": sha,
        "current_stage": "git_complete",
    }

    # Push and create PR if GitHub is configured
    if settings.GITHUB_TOKEN and settings.GITHUB_REPO and settings.AUTO_PR:
        # Push
        push_ok = push(repo_path, branch_name)

        if push_ok and branch_name:
            # Build PR body
            security_details = _format_security_details(security_report_data)
            test_summary = _format_test_summary(test_results)

            pr_body = generate_pr_body(
                diff_summary=diff_summary,
                security_passed=security_passed,
                security_details=security_details,
                test_summary=test_summary,
            )

            # Get reviewers
            reviewers = settings.PR_REVIEWERS or get_codeowners(repo_path)

            # Create PR
            pr_result = create_pr(
                repo_name=settings.GITHUB_REPO,
                branch=branch_name,
                title=commit_message.split("\n")[0],
                body=pr_body,
                base=settings.GIT_BASE_BRANCH,
                labels=["afterburner", "auto-generated"],
                reviewers=reviewers if reviewers else None,
                github_token=settings.GITHUB_TOKEN,
            )

            update["pr_url"] = pr_result.get("html_url")
            update["pr_number"] = pr_result.get("number")

            if pr_result.get("html_url"):
                logger.info("PR created: {}", pr_result["html_url"])
            else:
                logger.warning("PR creation returned no URL: {}", pr_result.get("error", "unknown"))
    else:
        logger.info("GitHub not configured — skipping PR creation")

    return update


def _generate_commit_message(
    diff_summary: str,
    changed_files: list,
    security_passed: bool,
    tests_passed: bool,
) -> str:
    """Generate a Conventional Commits message via LLM."""
    try:
        llm = get_llm(temperature=0.2)

        response = llm.invoke([
            SystemMessage(content="You write concise, conventional git commit messages."),
            HumanMessage(content=COMMIT_MSG_PROMPT.format(
                diff_summary=diff_summary[:500],
                changed_files=", ".join(changed_files[:15]),
                security_status="✅ passed" if security_passed else "⚠️ issues found",
                test_status="✅ all passed" if tests_passed else "⚠️ some failures",
            )),
        ])

        msg = response.content.strip().strip("`").strip()
        logger.debug("Generated commit message: {}", msg.split("\n")[0])
        return msg

    except Exception as e:
        logger.warning("LLM commit message failed, using fallback: {}", str(e))
        return f"chore: afterburner automated commit ({len(changed_files)} files changed)"


def _format_security_details(security_report_data: Optional[dict]) -> str:
    """Format security report for PR body."""
    if not security_report_data:
        return "No security scan performed."

    report = SecurityReport(**security_report_data)
    lines = []
    lines.append(f"- **Critical**: {report.critical_count}")
    lines.append(f"- **Warnings**: {report.warning_count}")
    lines.append(f"- **Info**: {report.info_count}")

    if report.critical_count > 0:
        lines.append("\n**Critical Findings:**")
        for f in report.findings:
            if f.severity == "critical":
                lines.append(f"- `{f.file}:{f.line}` — {f.message}")

    return "\n".join(lines)


def _format_test_summary(test_results: list) -> str:
    """Format test results for PR body."""
    if not test_results:
        return "No tests were run."

    lines = []
    for r in test_results:
        icon = "✅" if (r.get("failed", 0) == 0 and not r.get("errors")) else "❌"
        lines.append(
            f"- {icon} **{r.get('framework', 'unknown')}**: "
            f"{r.get('passed', 0)} passed, {r.get('failed', 0)} failed "
            f"({r.get('duration_ms', 0):.0f}ms)"
        )
    return "\n".join(lines)
