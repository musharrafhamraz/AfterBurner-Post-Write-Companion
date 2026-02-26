"""Afterburner settings — Pydantic BaseSettings driven by environment variables."""

from typing import Optional, List
from pydantic_settings import BaseSettings, SettingsConfigDict


class AfterburnerSettings(BaseSettings):
    """
    All Afterburner configuration.
    Values are loaded from environment variables prefixed with AFTERBURNER_,
    falling back to a .env file in the project root.
    """

    # ===== LLM =====
    LLM_PROVIDER: str = "gemini"
    """LLM provider to use: 'gemini' or 'groq'."""

    GEMINI_API_KEY: Optional[str] = None
    GROQ_API_KEY: Optional[str] = None

    LLM_MODEL: str = "gemini-2.0-flash"
    """Model name. Use 'llama-3.3-70b-versatile' for Groq."""

    # ===== GitHub =====
    GITHUB_TOKEN: Optional[str] = None
    GITHUB_REPO: Optional[str] = None
    """GitHub repo in 'owner/repo' format."""

    GIT_BASE_BRANCH: str = "main"
    """The default branch to merge PRs into (e.g. 'main' or 'master')."""

    AUTO_PR: bool = True
    """Automatically open a Pull Request after committing."""

    PR_REVIEWERS: List[str] = []
    """GitHub usernames to request review from."""

    # ===== Security =====
    ENABLE_SEMGREP: bool = True
    ENABLE_BANDIT: bool = True

    SECURITY_BLOCK_ON: str = "critical"
    """Minimum severity that blocks the pipeline: 'critical' or 'warning'."""

    # ===== Testing =====
    MAX_TEST_DEBUG_ITERATIONS: int = 4
    """Maximum self-debug loop retries for failing tests."""

    ENABLE_PLAYWRIGHT: bool = False
    """Enable Playwright E2E visual regression tests."""

    TEST_TIMEOUT_SECONDS: int = 300
    """Maximum time (seconds) for a single test run."""

    # ===== Deployment =====
    DEPLOY_TARGET: Optional[str] = None
    """Deployment target: 'vercel' or 'docker'. None = skip deployment."""

    SKIP_DEPLOY: bool = False
    """Explicitly skip deployment even if DEPLOY_TARGET is set."""

    VERCEL_TOKEN: Optional[str] = None

    # ===== Monitoring =====
    SENTRY_DSN: Optional[str] = None
    ENABLE_PROMETHEUS: bool = False

    # ===== Workflow =====
    MAX_REFLECTION_RETRIES: int = 3
    """Maximum number of reflection-loop retries (security + test gates)."""

    VERBOSE: bool = False
    """Enable verbose logging output."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="AFTERBURNER_",
        case_sensitive=False,
        extra="ignore",
    )


# Singleton instance — import this everywhere
settings = AfterburnerSettings()
