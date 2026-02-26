"""Deploy tools — wrappers for Vercel and Docker Compose deployment."""

import subprocess
import os
from typing import Optional

from loguru import logger
from src.models.reports import DeployResult


def deploy_vercel(
    repo_path: str,
    token: Optional[str] = None,
    prod: bool = True,
) -> DeployResult:
    """
    Deploy to Vercel using the Vercel CLI.

    Args:
        repo_path: Absolute path to the project.
        token: Vercel API token (falls back to AFTERBURNER_VERCEL_TOKEN env).
        prod: Whether to deploy to production.

    Returns:
        DeployResult with URL and status.
    """
    token = token or os.environ.get("AFTERBURNER_VERCEL_TOKEN")

    cmd = ["vercel"]
    if prod:
        cmd.append("--prod")
    cmd.append("--yes")  # Skip confirmation prompts

    if token:
        cmd.extend(["--token", token])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180,
            cwd=repo_path,
        )

        if result.returncode == 0:
            # Vercel prints the deployment URL as last line of stdout
            url = result.stdout.strip().split("\n")[-1].strip()
            logger.info("Deployed to Vercel: {}", url)
            return DeployResult(
                target="vercel",
                url=url,
                status="success",
                logs=result.stdout[:1000],
            )
        else:
            logger.error("Vercel deploy failed: {}", result.stderr[:500])
            return DeployResult(
                target="vercel",
                status="failed",
                logs=(result.stdout + "\n" + result.stderr)[:1000],
            )

    except FileNotFoundError:
        return DeployResult(
            target="vercel",
            status="failed",
            logs="Vercel CLI not found. Install with: npm i -g vercel",
        )
    except subprocess.TimeoutExpired:
        return DeployResult(
            target="vercel",
            status="failed",
            logs="Vercel deploy timed out after 180s",
        )


def deploy_docker_compose(
    repo_path: str,
    compose_file: str = "docker-compose.yml",
    build: bool = True,
    detach: bool = True,
) -> DeployResult:
    """
    Deploy using Docker Compose for local staging.

    Args:
        repo_path: Absolute path to the project.
        compose_file: Docker Compose file name.
        build: Whether to rebuild images.
        detach: Whether to run in detached mode.

    Returns:
        DeployResult with status.
    """
    compose_path = os.path.join(repo_path, compose_file)
    if not os.path.exists(compose_path):
        logger.warning("No {} found at {}", compose_file, repo_path)
        return DeployResult(
            target="docker",
            status="failed",
            logs=f"No {compose_file} found in project root",
        )

    cmd = ["docker", "compose", "-f", compose_file, "up"]
    if build:
        cmd.append("--build")
    if detach:
        cmd.append("-d")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            cwd=repo_path,
        )

        if result.returncode == 0:
            logger.info("Docker Compose deployment successful")
            return DeployResult(
                target="docker",
                url="http://localhost",
                status="success",
                logs=result.stdout[:1000],
            )
        else:
            logger.error("Docker Compose failed: {}", result.stderr[:500])
            return DeployResult(
                target="docker",
                status="failed",
                logs=(result.stdout + "\n" + result.stderr)[:1000],
            )

    except FileNotFoundError:
        return DeployResult(
            target="docker",
            status="failed",
            logs="Docker not found. Install Docker Desktop.",
        )
    except subprocess.TimeoutExpired:
        return DeployResult(
            target="docker",
            status="failed",
            logs="Docker Compose timed out after 300s",
        )


def generate_github_actions_workflow(repo_path: str) -> str:
    """
    Generate a GitHub Actions CI/CD workflow file.

    Creates .github/workflows/afterburner.yml if it doesn't exist.

    Args:
        repo_path: Absolute path to the repository.

    Returns:
        Path to the generated workflow file.
    """
    workflow_dir = os.path.join(repo_path, ".github", "workflows")
    workflow_path = os.path.join(workflow_dir, "afterburner.yml")

    if os.path.exists(workflow_path):
        logger.debug("GitHub Actions workflow already exists, skipping generation")
        return workflow_path

    os.makedirs(workflow_dir, exist_ok=True)

    workflow_content = """name: Afterburner CI/CD

on:
  push:
    branches: [main, master, develop]
  pull_request:
    branches: [main, master]

jobs:
  afterburner:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          if [ -f requirements.txt ]; then pip install -r requirements.txt; fi
          pip install bandit semgrep

      - name: Security Scan — Bandit
        run: bandit -r . -f json -o bandit-report.json || true

      - name: Security Scan — Semgrep
        run: semgrep scan --json --quiet . > semgrep-report.json || true

      - name: Run Tests
        run: python -m pytest --tb=short -q || true

      - name: Upload Reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: afterburner-reports
          path: |
            bandit-report.json
            semgrep-report.json
"""

    with open(workflow_path, "w") as f:
        f.write(workflow_content)

    logger.info("Generated GitHub Actions workflow: {}", workflow_path)
    return workflow_path
