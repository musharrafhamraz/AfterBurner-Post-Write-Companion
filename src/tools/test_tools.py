"""Test tools — wrappers for pytest, vitest, cargo test, and Playwright."""

import json
import os
import subprocess
from typing import List, Optional

from loguru import logger
from src.models.reports import TestRun


def detect_test_framework(repo_path: str) -> List[str]:
    """
    Auto-detect which test frameworks are available in the project.

    Args:
        repo_path: Absolute path to the repository.

    Returns:
        List of detected framework names: 'pytest', 'vitest', 'jest', 'cargo', 'playwright'.
    """
    frameworks = []

    # Python — pytest
    if any(
        os.path.exists(os.path.join(repo_path, f))
        for f in ["pytest.ini", "setup.cfg", "conftest.py"]
    ) or _has_pyproject_pytest(repo_path):
        frameworks.append("pytest")
    elif os.path.exists(os.path.join(repo_path, "tests")) or os.path.exists(
        os.path.join(repo_path, "test")
    ):
        frameworks.append("pytest")  # Assume pytest if tests dir exists

    # JavaScript — vitest
    for name in ["vitest.config.ts", "vitest.config.js", "vitest.config.mts"]:
        if os.path.exists(os.path.join(repo_path, name)):
            frameworks.append("vitest")
            break

    # JavaScript — jest (fallback)
    if "vitest" not in frameworks:
        for name in ["jest.config.ts", "jest.config.js", "jest.config.mjs"]:
            if os.path.exists(os.path.join(repo_path, name)):
                frameworks.append("jest")
                break

    # Rust — cargo test
    if os.path.exists(os.path.join(repo_path, "Cargo.toml")):
        frameworks.append("cargo")

    # Playwright
    for name in ["playwright.config.ts", "playwright.config.js"]:
        if os.path.exists(os.path.join(repo_path, name)):
            frameworks.append("playwright")
            break

    logger.info("Detected test frameworks: {}", frameworks or ["none"])
    return frameworks


def _has_pyproject_pytest(repo_path: str) -> bool:
    """Check if pyproject.toml has pytest configuration."""
    pyproject = os.path.join(repo_path, "pyproject.toml")
    if os.path.exists(pyproject):
        try:
            with open(pyproject, "r") as f:
                content = f.read()
                return "[tool.pytest" in content
        except Exception:
            pass
    return False


def run_pytest(
    repo_path: str,
    files: Optional[List[str]] = None,
    timeout: int = 300,
) -> TestRun:
    """
    Run pytest and parse results.

    Args:
        repo_path: Absolute path to the repository.
        files: Specific test files to run. None = run all.
        timeout: Maximum seconds for the test run.

    Returns:
        TestRun with parsed results.
    """
    cmd = ["python", "-m", "pytest", "--tb=short", "-q", "--no-header"]

    if files:
        # Filter to test files only
        test_files = [f for f in files if "test" in f.lower() and f.endswith(".py")]
        if test_files:
            cmd.extend(test_files)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=repo_path,
        )

        return _parse_pytest_output(result.stdout, result.stderr, result.returncode)

    except FileNotFoundError:
        return TestRun(
            framework="pytest",
            errors=["pytest not found. Install with: pip install pytest"],
        )
    except subprocess.TimeoutExpired:
        return TestRun(
            framework="pytest",
            errors=[f"pytest timed out after {timeout}s"],
        )


def _parse_pytest_output(stdout: str, stderr: str, returncode: int) -> TestRun:
    """Parse pytest console output into a TestRun."""
    passed = failed = skipped = 0
    errors = []
    output = stdout + "\n" + stderr

    # Parse the summary line: "5 passed, 2 failed, 1 skipped"
    for line in stdout.split("\n"):
        line = line.strip()
        if "passed" in line or "failed" in line or "error" in line:
            import re
            p = re.search(r"(\d+) passed", line)
            f = re.search(r"(\d+) failed", line)
            s = re.search(r"(\d+) skipped", line)
            e = re.search(r"(\d+) error", line)
            if p:
                passed = int(p.group(1))
            if f:
                failed = int(f.group(1))
            if s:
                skipped = int(s.group(1))
            if e:
                failed += int(e.group(1))

    if returncode != 0 and failed == 0:
        errors.append(f"pytest exited with code {returncode}")
        if stderr.strip():
            errors.append(stderr.strip()[:500])

    # Extract FAILED test names for self-debug context
    for line in stdout.split("\n"):
        if line.startswith("FAILED "):
            errors.append(line.strip())

    return TestRun(
        framework="pytest",
        passed=passed,
        failed=failed,
        skipped=skipped,
        errors=errors,
        output=output[:2000],  # Truncate to avoid bloating state
    )


def run_vitest(
    repo_path: str,
    files: Optional[List[str]] = None,
    timeout: int = 300,
) -> TestRun:
    """
    Run vitest and parse results.

    Args:
        repo_path: Absolute path to the repository.
        files: Specific test files to run.
        timeout: Maximum seconds for the test run.

    Returns:
        TestRun with parsed results.
    """
    cmd = ["npx", "vitest", "run", "--reporter=json"]

    if files:
        test_files = [f for f in files if "test" in f.lower() or "spec" in f.lower()]
        if test_files:
            cmd.extend(test_files)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=repo_path,
        )

        return _parse_vitest_output(result.stdout, result.stderr)

    except FileNotFoundError:
        return TestRun(
            framework="vitest",
            errors=["npx/vitest not found. Install Node.js and run: npm install"],
        )
    except subprocess.TimeoutExpired:
        return TestRun(
            framework="vitest",
            errors=[f"vitest timed out after {timeout}s"],
        )


def _parse_vitest_output(stdout: str, stderr: str) -> TestRun:
    """Parse vitest JSON output."""
    try:
        data = json.loads(stdout) if stdout.strip() else {}
        passed = data.get("numPassedTests", 0)
        failed = data.get("numFailedTests", 0)
        errors = []

        for suite in data.get("testResults", []):
            for test in suite.get("assertionResults", []):
                if test.get("status") == "failed":
                    errors.append(
                        f"{test.get('ancestorTitles', [''])[0]}.{test.get('title', 'unknown')}: "
                        f"{'; '.join(test.get('failureMessages', []))[:200]}"
                    )

        return TestRun(
            framework="vitest",
            passed=passed,
            failed=failed,
            errors=errors,
            output=(stdout + "\n" + stderr)[:2000],
        )
    except json.JSONDecodeError:
        return TestRun(
            framework="vitest",
            errors=["Failed to parse vitest JSON output"],
            output=(stdout + "\n" + stderr)[:2000],
        )


def run_cargo_test(repo_path: str, timeout: int = 300) -> TestRun:
    """
    Run cargo test and parse results.

    Args:
        repo_path: Absolute path to the Rust project.
        timeout: Maximum seconds for the test run.

    Returns:
        TestRun with parsed results.
    """
    cmd = ["cargo", "test", "--", "--test-threads=1", "-q"]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=repo_path,
        )

        return _parse_cargo_test_output(result.stdout, result.stderr, result.returncode)

    except FileNotFoundError:
        return TestRun(
            framework="cargo",
            errors=["cargo not found. Install Rust toolchain."],
        )
    except subprocess.TimeoutExpired:
        return TestRun(
            framework="cargo",
            errors=[f"cargo test timed out after {timeout}s"],
        )


def _parse_cargo_test_output(stdout: str, stderr: str, returncode: int) -> TestRun:
    """Parse cargo test output."""
    import re
    passed = failed = 0
    errors = []

    # Look for "test result: ok. X passed; Y failed"
    for line in (stdout + "\n" + stderr).split("\n"):
        m = re.search(r"(\d+) passed.*?(\d+) failed", line)
        if m:
            passed = int(m.group(1))
            failed = int(m.group(2))

    if returncode != 0 and failed == 0:
        errors.append(f"cargo test exited with code {returncode}")

    return TestRun(
        framework="cargo",
        passed=passed,
        failed=failed,
        errors=errors,
        output=(stdout + "\n" + stderr)[:2000],
    )


def run_playwright(repo_path: str, timeout: int = 300) -> TestRun:
    """
    Run Playwright E2E tests.

    Args:
        repo_path: Absolute path to the project.
        timeout: Maximum seconds for the test run.

    Returns:
        TestRun with parsed results.
    """
    cmd = ["npx", "playwright", "test", "--reporter=json"]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=repo_path,
        )

        return _parse_playwright_output(result.stdout, result.stderr)

    except FileNotFoundError:
        return TestRun(
            framework="playwright",
            errors=["Playwright not found. Install with: npx playwright install"],
        )
    except subprocess.TimeoutExpired:
        return TestRun(
            framework="playwright",
            errors=[f"Playwright timed out after {timeout}s"],
        )


def _parse_playwright_output(stdout: str, stderr: str) -> TestRun:
    """Parse Playwright JSON output."""
    try:
        data = json.loads(stdout) if stdout.strip() else {}
        passed = 0
        failed = 0
        errors = []

        for suite in data.get("suites", []):
            for spec in suite.get("specs", []):
                for test in spec.get("tests", []):
                    for result in test.get("results", []):
                        if result.get("status") == "passed":
                            passed += 1
                        elif result.get("status") in ("failed", "timedOut"):
                            failed += 1
                            errors.append(
                                f"{spec.get('title', 'unknown')}: "
                                f"{result.get('error', {}).get('message', 'unknown error')[:200]}"
                            )

        return TestRun(
            framework="playwright",
            passed=passed,
            failed=failed,
            errors=errors,
            output=(stdout + "\n" + stderr)[:2000],
        )
    except json.JSONDecodeError:
        return TestRun(
            framework="playwright",
            errors=["Failed to parse Playwright JSON output"],
            output=(stdout + "\n" + stderr)[:2000],
        )
