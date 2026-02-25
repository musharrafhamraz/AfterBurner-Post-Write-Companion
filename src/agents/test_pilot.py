"""Test Pilot — runs tests, detects failures, and self-debug loops via LLM."""

from typing import Dict, Any, List

from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger

from src.config import settings
from src.graph.state import AfterburnerState
from src.models.reports import TestRun
from src.tools.test_tools import (
    detect_test_framework,
    run_pytest,
    run_vitest,
    run_cargo_test,
    run_playwright,
)
from src.utils.llm import get_llm


SELF_DEBUG_PROMPT = """You are a senior software engineer debugging test failures.

The following tests failed. Analyse the error output and the changed files to determine:
1. Is the test wrong, or is the source code wrong?
2. What is the root cause?
3. Suggest a minimal fix (code patch).

Keep your response concise. Format your fix as a unified diff.

Failed test output:
{test_output}

Changed files:
{changed_files}

Test errors:
{errors}
"""


def test_pilot_node(state: AfterburnerState) -> dict:
    """
    LangGraph node: detect test frameworks, run tests, and self-debug on failure.

    Self-debug loop:
    - If tests fail and iterations < MAX_TEST_DEBUG_ITERATIONS, send error context
      to LLM, get fix suggestions, and add them to messages for next iteration.
    - Each iteration increments test_debug_iterations.

    Returns state updates for:
        - test_results
        - tests_passed
        - test_debug_iterations
        - current_stage
    """
    repo_path = state["repo_path"]
    changed_files = state.get("changed_files", [])
    file_types = state.get("file_types", {})
    iteration = state.get("test_debug_iterations", 0)

    logger.info("🧪 Running tests (iteration {})", iteration + 1)

    # Detect available frameworks
    frameworks = detect_test_framework(repo_path)

    if not frameworks:
        logger.info("No test frameworks detected — skipping")
        return {
            "test_results": [],
            "tests_passed": True,
            "current_stage": "testing_complete",
        }

    # Run each detected framework
    results: List[Dict[str, Any]] = []
    all_passed = True

    for framework in frameworks:
        logger.info("Running {} tests...", framework)

        if framework == "pytest":
            run_result = run_pytest(
                repo_path, changed_files, timeout=settings.TEST_TIMEOUT_SECONDS
            )
        elif framework in ("vitest", "jest"):
            run_result = run_vitest(
                repo_path, changed_files, timeout=settings.TEST_TIMEOUT_SECONDS
            )
        elif framework == "cargo":
            run_result = run_cargo_test(
                repo_path, timeout=settings.TEST_TIMEOUT_SECONDS
            )
        elif framework == "playwright" and settings.ENABLE_PLAYWRIGHT:
            run_result = run_playwright(
                repo_path, timeout=settings.TEST_TIMEOUT_SECONDS
            )
        else:
            logger.debug("Skipping {} (not enabled or unsupported)", framework)
            continue

        results.append(run_result.model_dump())

        if not run_result.all_passed:
            all_passed = False
            logger.warning(
                "{}: {} passed, {} failed",
                framework,
                run_result.passed,
                run_result.failed,
            )
        else:
            logger.info("{}: {} passed ✅", framework, run_result.passed)

    update: dict = {
        "test_results": results,
        "tests_passed": all_passed,
        "test_debug_iterations": iteration + 1,
        "current_stage": "testing_complete",
    }

    # Self-debug loop: if tests failed, send context to LLM
    if not all_passed and iteration < settings.MAX_TEST_DEBUG_ITERATIONS:
        debug_msg = _generate_debug_suggestions(results, changed_files)
        if debug_msg:
            update["messages"] = [HumanMessage(content=debug_msg)]

    return update


def _generate_debug_suggestions(
    results: List[Dict[str, Any]],
    changed_files: List[str],
) -> str:
    """
    Use LLM to analyse test failures and suggest fixes.

    Returns a human-readable debug suggestion string, or empty if LLM fails.
    """
    # Collect all errors from failed test runs
    all_errors = []
    all_output = []
    for r in results:
        if r.get("errors"):
            all_errors.extend(r["errors"])
        if r.get("output"):
            all_output.append(r["output"][:500])

    if not all_errors:
        return ""

    try:
        llm = get_llm(temperature=0.1)

        response = llm.invoke([
            SystemMessage(content="You are a test debugging expert."),
            HumanMessage(content=SELF_DEBUG_PROMPT.format(
                test_output="\n".join(all_output)[:2000],
                changed_files=", ".join(changed_files[:20]),
                errors="\n".join(all_errors)[:1000],
            )),
        ])

        suggestion = response.content
        logger.debug("LLM debug suggestion: {}", suggestion[:200])
        return f"🔧 Self-debug suggestion (iteration):\n{suggestion}"

    except Exception as e:
        logger.warning("LLM debug suggestion failed: {}", str(e))
        return ""
