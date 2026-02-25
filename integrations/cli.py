"""Afterburner CLI — Typer-based command-line interface."""

import os
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

app = typer.Typer(
    name="afterburner",
    help="🔥 Afterburner — Post-write companion for shipping production-ready code.",
    no_args_is_help=True,
)
console = Console()


@app.command()
def run(
    repo_path: str = typer.Argument(
        ".",
        help="Path to the git repository to process.",
    ),
    skip_deploy: bool = typer.Option(
        False,
        "--skip-deploy",
        help="Skip deployment step.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose", "-v",
        help="Enable verbose output.",
    ),
):
    """Run the full Afterburner pipeline: detect → security → test → git → deploy."""
    repo_path = os.path.abspath(repo_path)

    if verbose:
        os.environ["AFTERBURNER_VERBOSE"] = "true"

    console.print(Panel.fit(
        "🔥 [bold red]Afterburner[/bold red] — Post-Write Companion\n"
        f"📂 Repo: {repo_path}",
        border_style="red",
    ))

    from src.graph.workflow import run_afterburner

    result = run_afterburner(
        repo_path=repo_path,
        trigger_source="cli",
        skip_deploy=skip_deploy,
    )

    # Display summary
    summary = result.get("final_summary", "No summary generated.")
    console.print()
    console.print(Markdown(summary))

    # Exit code
    if result.get("hard_fail"):
        raise typer.Exit(code=1)


@app.command()
def security(
    repo_path: str = typer.Argument(".", help="Path to the git repository to process."),
):
    """Run only the Security Sentinel (Semgrep + Bandit)."""
    repo_path = os.path.abspath(repo_path)
    console.print("[bold]🛡️ Running security scan only...[/bold]")

    from src.utils.logging import setup_logging
    from src.agents.change_detector import change_detector_node
    from src.agents.security_sentinel import security_sentinel_node

    setup_logging()

    # Minimal state for change detection + security
    state = {
        "repo_path": repo_path,
        "changed_files": [],
        "trigger_source": "cli",
        "reflection_count": 0,
    }

    state.update(change_detector_node(state))
    result = security_sentinel_node(state)

    passed = result.get("security_passed", True)
    count = result.get("security_issues_count", 0)
    icon = "✅" if passed else "❌"

    console.print(f"\n{icon} Security scan: {count} issue(s) found")
    if not passed:
        raise typer.Exit(code=1)


@app.command()
def test(
    repo_path: str = typer.Argument(".", help="Path to the git repository to process."),
    max_retries: int = typer.Option(4, "--max-retries"),
):
    """Run only the Test Pilot (auto-detect framework + self-debug loop)."""
    repo_path = os.path.abspath(repo_path)
    console.print("[bold]🧪 Running tests only...[/bold]")

    from src.utils.logging import setup_logging
    from src.agents.change_detector import change_detector_node
    from src.agents.test_pilot import test_pilot_node

    setup_logging()

    state = {
        "repo_path": repo_path,
        "changed_files": [],
        "trigger_source": "cli",
        "test_debug_iterations": 0,
    }

    state.update(change_detector_node(state))

    # Self-debug loop
    for i in range(max_retries):
        result = test_pilot_node(state)
        state.update(result)

        if result.get("tests_passed", False):
            console.print(f"\n✅ All tests passed (iteration {i + 1})")
            return

        console.print(f"\n⚠️ Tests failed (iteration {i + 1}/{max_retries})")

    console.print("\n❌ Tests still failing after all retries")
    raise typer.Exit(code=1)


@app.command()
def commit(
    repo_path: str = typer.Argument(".", help="Path to the git repository to process."),
    no_pr: bool = typer.Option(False, "--no-pr", help="Skip PR creation."),
):
    """Run only the Git Guardian (commit + optional PR)."""
    repo_path = os.path.abspath(repo_path)
    console.print("[bold]📦 Creating commit...[/bold]")

    from src.utils.logging import setup_logging
    from src.agents.change_detector import change_detector_node
    from src.agents.git_guardian import git_guardian_node

    setup_logging()

    if no_pr:
        os.environ["AFTERBURNER_AUTO_PR"] = "false"

    state = {
        "repo_path": repo_path,
        "changed_files": [],
        "trigger_source": "cli",
        "security_passed": True,
        "tests_passed": True,
    }

    state.update(change_detector_node(state))
    result = git_guardian_node(state)

    sha = result.get("commit_sha")
    pr = result.get("pr_url")

    if sha:
        console.print(f"\n✅ Committed: {sha[:8]}")
    if pr:
        console.print(f"🔗 PR: {pr}")


@app.command()
def deploy(
    repo_path: str = typer.Argument(".", help="Path to the git repository to process."),
    target: str = typer.Option(None, "--target", "-t", help="Deploy target: vercel | docker"),
):
    """Run only the Launch Controller (deploy + monitoring)."""
    repo_path = os.path.abspath(repo_path)
    console.print("[bold]🚀 Deploying...[/bold]")

    if target:
        os.environ["AFTERBURNER_DEPLOY_TARGET"] = target

    from src.utils.logging import setup_logging
    from src.agents.launch_controller import launch_controller_node

    setup_logging()

    state = {
        "repo_path": repo_path,
        "skip_deploy": False,
    }

    result = launch_controller_node(state)

    status = result.get("deployment_status", "unknown")
    url = result.get("deployment_url")
    icon = "✅" if status == "success" else "❌"

    console.print(f"\n{icon} Deploy status: {status}")
    if url:
        console.print(f"🔗 URL: {url}")


@app.command()
def status():
    """Show Afterburner configuration."""
    from src.config import settings

    console.print(Panel.fit(
        f"[bold]LLM Provider:[/bold] {settings.LLM_PROVIDER}\n"
        f"[bold]LLM Model:[/bold] {settings.LLM_MODEL}\n"
        f"[bold]GitHub Repo:[/bold] {settings.GITHUB_REPO or 'Not configured'}\n"
        f"[bold]Auto PR:[/bold] {settings.AUTO_PR}\n"
        f"[bold]Semgrep:[/bold] {settings.ENABLE_SEMGREP}\n"
        f"[bold]Bandit:[/bold] {settings.ENABLE_BANDIT}\n"
        f"[bold]Deploy Target:[/bold] {settings.DEPLOY_TARGET or 'None'}\n"
        f"[bold]Max Test Retries:[/bold] {settings.MAX_TEST_DEBUG_ITERATIONS}\n"
        f"[bold]Max Reflection Retries:[/bold] {settings.MAX_REFLECTION_RETRIES}\n"
        f"[bold]Verbose:[/bold] {settings.VERBOSE}",
        title="🔥 Afterburner Config",
        border_style="red",
    ))


if __name__ == "__main__":
    app()
