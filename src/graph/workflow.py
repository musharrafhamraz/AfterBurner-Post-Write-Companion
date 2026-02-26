"""Afterburner LangGraph workflow — the full pipeline StateGraph definition."""

from typing import Literal
from langgraph.graph import StateGraph, END

from src.graph.state import AfterburnerState
from src.agents.change_detector import change_detector_node
from src.agents.security_sentinel import security_sentinel_node
from src.agents.test_pilot import test_pilot_node
from src.agents.git_guardian import git_guardian_node
from src.agents.launch_controller import (
    launch_controller_node,
    summarize_node,
    hard_fail_node,
)
from src.config import settings

from loguru import logger


# ──────────────────────────── Gate Functions ────────────────────────────


def security_gate(state: AfterburnerState) -> Literal["test_run", "security_review", "hard_fail"]:
    """
    Conditional edge after security review.

    - If security passed → proceed to testing
    - If failed and retries remain → loop back to security review
    - If failed and retries exhausted → hard fail
    """
    if state.get("security_passed", False):
        return "test_run"

    reflection_count = state.get("reflection_count", 0)
    if reflection_count < settings.MAX_REFLECTION_RETRIES:
        logger.info(
            "Security gate: RETRY ({}/{})",
            reflection_count,
            settings.MAX_REFLECTION_RETRIES,
        )
        return "security_review"

    logger.error("Security gate: HARD FAIL after {} retries", reflection_count)
    return "hard_fail"


def test_gate(state: AfterburnerState) -> Literal["git_commit", "test_run", "hard_fail"]:
    """
    Conditional edge after test run.

    - If all tests passed → proceed to git commit
    - If failed and debug iterations remain → loop back to test run
    - If failed and iterations exhausted → hard fail
    """
    if state.get("tests_passed", False):
        return "git_commit"

    iterations = state.get("test_debug_iterations", 0)
    if iterations < settings.MAX_TEST_DEBUG_ITERATIONS:
        logger.info(
            "Test gate: RETRY ({}/{})",
            iterations,
            settings.MAX_TEST_DEBUG_ITERATIONS,
        )
        return "test_run"

    logger.error("Test gate: HARD FAIL after {} iterations", iterations)
    return "hard_fail"


# ──────────────────────────── Workflow Builder ────────────────────────────


def create_afterburner_workflow(checkpointer=None):
    """
    Create the main Afterburner LangGraph workflow.

    Pipeline:
        detect_changes → security_review → [security_gate]
            ↓ pass          ↑ retry (≤3)       ↓ hard_fail
        test_run → [test_gate]
            ↓ pass    ↑ retry (≤4)  ↓ hard_fail
        git_commit → deploy → summarize → END
                                ↑
                 hard_fail ─────┘

    Args:
        checkpointer: Optional LangGraph checkpointer for persistence.

    Returns:
        Compiled LangGraph workflow.
    """
    workflow = StateGraph(AfterburnerState)

    # ── Add Nodes ──
    workflow.add_node("detect_changes", change_detector_node)
    workflow.add_node("security_review", security_sentinel_node)
    workflow.add_node("test_run", test_pilot_node)
    workflow.add_node("git_commit", git_guardian_node)
    workflow.add_node("deploy", launch_controller_node)
    workflow.add_node("summarize", summarize_node)
    workflow.add_node("hard_fail", hard_fail_node)

    # ── Define Edges ──

    # Entry point
    workflow.set_entry_point("detect_changes")

    # detect_changes → security_review
    workflow.add_edge("detect_changes", "security_review")

    # security_review → security_gate (conditional)
    workflow.add_conditional_edges(
        "security_review",
        security_gate,
        {
            "test_run": "test_run",
            "security_review": "security_review",
            "hard_fail": "hard_fail",
        },
    )

    # test_run → test_gate (conditional)
    workflow.add_conditional_edges(
        "test_run",
        test_gate,
        {
            "git_commit": "git_commit",
            "test_run": "test_run",
            "hard_fail": "hard_fail",
        },
    )

    # Linear edges: git_commit → deploy → summarize → END
    workflow.add_edge("git_commit", "deploy")
    workflow.add_edge("deploy", "summarize")
    workflow.add_edge("summarize", END)

    # Hard fail → summarize → END
    workflow.add_edge("hard_fail", "summarize")

    logger.info("Afterburner workflow compiled")
    return workflow.compile(checkpointer=checkpointer)


def run_afterburner(
    repo_path: str,
    trigger_source: str = "cli",
    changed_files: list | None = None,
    skip_deploy: bool = False,
) -> dict:
    """
    Convenience function to run the full Afterburner pipeline.

    Args:
        repo_path: Absolute path to the git repository.
        trigger_source: How the run was triggered: 'cli', 'mcp', or 'hook'.
        changed_files: Optional list of changed files (auto-detected if None).
        skip_deploy: Whether to skip deployment.

    Returns:
        Final AfterburnerState dict with all results.
    """
    from src.utils.logging import setup_logging
    setup_logging()

    workflow = create_afterburner_workflow()

    initial_state = {
        "repo_path": repo_path,
        "changed_files": changed_files or [],
        "diff_summary": None,
        "trigger_source": trigger_source,
        "file_types": None,
        "security_report": None,
        "security_passed": False,
        "security_issues_count": 0,
        "test_results": [],
        "tests_passed": False,
        "test_debug_iterations": 0,
        "branch_name": None,
        "commit_sha": None,
        "pr_url": None,
        "pr_number": None,
        "deployment_url": None,
        "deployment_status": None,
        "monitoring_configured": False,
        "current_stage": "starting",
        "reflection_count": 0,
        "hard_fail": False,
        "skip_deploy": skip_deploy or settings.SKIP_DEPLOY,
        "errors": [],
        "final_summary": None,
        "messages": [],
    }

    logger.info("🔥 Afterburner starting: repo={}, trigger={}", repo_path, trigger_source)
    result = workflow.invoke(initial_state)
    logger.info("🏁 Afterburner complete: stage={}", result.get("current_stage"))

    return result
