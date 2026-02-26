"""AfterburnerState — shared state flowing through the LangGraph workflow."""

from typing import TypedDict, List, Optional, Annotated, Dict, Any
from langgraph.graph import add_messages


# ──────────────────────────── Custom Reducers ────────────────────────────


def merge_lists(existing: List[str] | None, new: List[str] | None) -> List[str]:
    """Concatenate two lists (used for changed_files, test_results, etc.)."""
    if existing is None:
        existing = []
    if new is None:
        new = []
    return existing + new


def merge_errors(existing: List[str] | None, new: List[str] | None) -> List[str]:
    """Concatenate error message lists from potentially parallel agents."""
    if existing is None:
        existing = []
    if new is None:
        new = []
    return existing + new


# ──────────────────────────── State Schema ────────────────────────────


class AfterburnerState(TypedDict):
    """
    Central state that flows through every node in the Afterburner graph.

    Convention follows the user's existing LangGraph projects:
    - Annotated fields with custom reducers for list accumulation
    - add_messages for LLM conversation history
    """

    # ===== Input =====
    repo_path: str
    """Absolute path to the repository being processed."""

    changed_files: Annotated[List[str], merge_lists]
    """List of file paths changed since last commit."""

    diff_summary: Optional[str]
    """Human-readable git diff --stat output."""

    trigger_source: str
    """How Afterburner was invoked: 'mcp' | 'cli' | 'hook'."""

    file_types: Optional[Dict[str, List[str]]]
    """Changed files grouped by type: {'python': [...], 'javascript': [...], ...}."""

    # ===== Security =====
    security_report: Optional[Dict[str, Any]]
    """Serialised SecurityReport (dict form for LangGraph compatibility)."""

    security_passed: bool
    """Whether the security gate passed."""

    security_issues_count: int
    """Total number of security findings."""

    # ===== Testing =====
    test_results: Annotated[List[Dict[str, Any]], merge_lists]
    """Serialised TestRun objects (list of dicts)."""

    tests_passed: bool
    """Whether all tests passed."""

    test_debug_iterations: int
    """Current self-debug loop iteration count (max from settings)."""

    # ===== Git & PR =====
    branch_name: Optional[str]
    commit_sha: Optional[str]
    pr_url: Optional[str]
    pr_number: Optional[int]

    # ===== Deployment =====
    deployment_url: Optional[str]
    deployment_status: Optional[str]
    """Deployment status: 'success' | 'failed' | 'skipped'."""

    monitoring_configured: bool

    # ===== Workflow Control =====
    current_stage: str
    """Current pipeline stage name (for status tracking)."""

    reflection_count: int
    """Global reflection-loop retry counter (max from settings)."""

    hard_fail: bool
    """True if the pipeline hit max retries and must abort."""

    skip_deploy: bool
    """User opt-out of deployment."""

    # ===== Error Handling =====
    errors: Annotated[List[str], merge_errors]
    """Accumulated error messages from all agents."""

    # ===== Summary =====
    final_summary: Optional[str]
    """Generated Markdown report for IDE display."""

    # ===== Messages (LLM conversation context) =====
    messages: Annotated[list, add_messages]
    """LangChain message history for agent reasoning."""
