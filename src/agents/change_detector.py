"""Change Detector — detects what files changed via git diff and classifies them."""

from loguru import logger
from src.graph.state import AfterburnerState
from src.tools.git_tools import get_changed_files, get_diff_summary, classify_file_types


def change_detector_node(state: AfterburnerState) -> dict:
    """
    LangGraph node: detect changed files and produce a diff summary.

    Reads `repo_path` from state, runs git diff, and classifies file types
    for downstream agent routing (e.g. skip Bandit if no Python files).

    Returns state updates for:
        - changed_files
        - diff_summary
        - file_types
        - current_stage
    """
    repo_path = state["repo_path"]
    logger.info("🔍 Detecting changes in {}", repo_path)

    # Get changed files — falls back to staged/untracked
    changed_files = state.get("changed_files", [])
    if not changed_files:
        changed_files = get_changed_files(repo_path)

    if not changed_files:
        logger.warning("No changed files detected — pipeline may produce empty results")
        return {
            "changed_files": [],
            "diff_summary": "No changes detected",
            "file_types": {},
            "current_stage": "change_detection_complete",
        }

    # Get human-readable diff summary
    diff_summary = get_diff_summary(repo_path)

    # Classify file types for agent routing
    file_types = classify_file_types(changed_files)

    logger.info(
        "Detected {} changed files: {}",
        len(changed_files),
        ", ".join(f"{k}({len(v)})" for k, v in file_types.items()),
    )

    return {
        "changed_files": changed_files,
        "diff_summary": diff_summary,
        "file_types": file_types,
        "current_stage": "change_detection_complete",
    }
