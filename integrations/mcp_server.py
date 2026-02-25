"""Afterburner MCP Server — Model Context Protocol stdio server for Cursor and Antigravity."""

import asyncio
import json
import os
import sys

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from loguru import logger


# Create MCP server instance
server = Server("afterburner")


# ──────────────────────────── Tool Definitions ────────────────────────────


@server.list_tools()
async def list_tools() -> list[Tool]:
    """Return the list of tools exposed by Afterburner."""
    return [
        Tool(
            name="run_afterburner",
            description=(
                "Run the full Afterburner pipeline: detect changes → security scan → "
                "run tests → create git commit + PR → deploy. Returns a Markdown summary."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Absolute path to the git repository. Defaults to current directory.",
                    },
                    "skip_deploy": {
                        "type": "boolean",
                        "description": "Whether to skip the deployment step.",
                        "default": False,
                    },
                },
            },
        ),
        Tool(
            name="security_only",
            description="Run only the Security Sentinel (Semgrep + Bandit + dependency audit).",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Absolute path to the git repository.",
                    },
                },
            },
        ),
        Tool(
            name="test_only",
            description="Run only the Test Pilot (auto-detect framework, run tests, self-debug loop).",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Absolute path to the git repository.",
                    },
                },
            },
        ),
        Tool(
            name="git_only",
            description="Run only the Git Guardian (create commit with LLM-generated message + open PR).",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Absolute path to the git repository.",
                    },
                    "no_pr": {
                        "type": "boolean",
                        "description": "Skip PR creation.",
                        "default": False,
                    },
                },
            },
        ),
        Tool(
            name="deploy_only",
            description="Run only the Launch Controller (generate CI/CD, deploy, setup monitoring).",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Absolute path to the git repository.",
                    },
                    "target": {
                        "type": "string",
                        "description": "Deploy target: 'vercel' or 'docker'.",
                    },
                },
            },
        ),
        Tool(
            name="get_status",
            description="Show current Afterburner configuration.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
    ]


# ──────────────────────────── Tool Handlers ────────────────────────────


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool invocations from the MCP client (Cursor/Antigravity)."""

    repo_path = arguments.get("repo_path", os.environ.get("AFTERBURNER_REPO_PATH", os.getcwd()))
    repo_path = os.path.abspath(repo_path)

    try:
        if name == "run_afterburner":
            result = await _run_full_pipeline(
                repo_path,
                skip_deploy=arguments.get("skip_deploy", False),
            )

        elif name == "security_only":
            result = await _run_security_only(repo_path)

        elif name == "test_only":
            result = await _run_test_only(repo_path)

        elif name == "git_only":
            result = await _run_git_only(
                repo_path,
                no_pr=arguments.get("no_pr", False),
            )

        elif name == "deploy_only":
            result = await _run_deploy_only(
                repo_path,
                target=arguments.get("target"),
            )

        elif name == "get_status":
            result = _get_status()

        else:
            result = f"Unknown tool: {name}"

        return [TextContent(type="text", text=str(result))]

    except Exception as e:
        logger.error("Tool '{}' failed: {}", name, str(e))
        return [TextContent(type="text", text=f"Error: {str(e)}")]


# ──────────────────────────── Tool Implementations ────────────────────────────


async def _run_full_pipeline(repo_path: str, skip_deploy: bool = False) -> str:
    """Run the full Afterburner pipeline and return Markdown summary."""
    from src.graph.workflow import run_afterburner

    # Run synchronously in executor to avoid blocking
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        lambda: run_afterburner(
            repo_path=repo_path,
            trigger_source="mcp",
            skip_deploy=skip_deploy,
        ),
    )

    return result.get("final_summary", "Pipeline completed but no summary generated.")


async def _run_security_only(repo_path: str) -> str:
    """Run security scan only."""
    from src.utils.logging import setup_logging
    from src.agents.change_detector import change_detector_node
    from src.agents.security_sentinel import security_sentinel_node

    setup_logging()

    def _run():
        state = {
            "repo_path": repo_path,
            "changed_files": [],
            "trigger_source": "mcp",
            "reflection_count": 0,
        }
        state.update(change_detector_node(state))
        return security_sentinel_node(state)

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _run)

    passed = result.get("security_passed", True)
    count = result.get("security_issues_count", 0)
    icon = "✅" if passed else "❌"

    return f"{icon} Security scan complete: {count} issue(s) found. {'PASSED' if passed else 'BLOCKED'}"


async def _run_test_only(repo_path: str) -> str:
    """Run tests only."""
    from src.utils.logging import setup_logging
    from src.agents.change_detector import change_detector_node
    from src.agents.test_pilot import test_pilot_node

    setup_logging()

    def _run():
        state = {
            "repo_path": repo_path,
            "changed_files": [],
            "trigger_source": "mcp",
            "test_debug_iterations": 0,
        }
        state.update(change_detector_node(state))
        return test_pilot_node(state)

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _run)

    passed = result.get("tests_passed", False)
    icon = "✅" if passed else "❌"

    return f"{icon} Tests {'passed' if passed else 'failed'}."


async def _run_git_only(repo_path: str, no_pr: bool = False) -> str:
    """Run git commit only."""
    from src.utils.logging import setup_logging
    from src.agents.change_detector import change_detector_node
    from src.agents.git_guardian import git_guardian_node

    setup_logging()

    if no_pr:
        os.environ["AFTERBURNER_AUTO_PR"] = "false"

    def _run():
        state = {
            "repo_path": repo_path,
            "changed_files": [],
            "trigger_source": "mcp",
            "security_passed": True,
            "tests_passed": True,
        }
        state.update(change_detector_node(state))
        return git_guardian_node(state)

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _run)

    sha = result.get("commit_sha", "unknown")
    pr = result.get("pr_url")

    msg = f"📦 Committed: {sha[:8] if sha else 'failed'}"
    if pr:
        msg += f"\n🔗 PR: {pr}"
    return msg


async def _run_deploy_only(repo_path: str, target: str = None) -> str:
    """Run deploy only."""
    from src.utils.logging import setup_logging
    from src.agents.launch_controller import launch_controller_node

    setup_logging()

    if target:
        os.environ["AFTERBURNER_DEPLOY_TARGET"] = target

    def _run():
        state = {
            "repo_path": repo_path,
            "skip_deploy": False,
        }
        return launch_controller_node(state)

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _run)

    status = result.get("deployment_status", "unknown")
    url = result.get("deployment_url")
    icon = "✅" if status == "success" else ("⏭️" if status == "skipped" else "❌")

    msg = f"{icon} Deploy: {status}"
    if url:
        msg += f"\n🔗 {url}"
    return msg


def _get_status() -> str:
    """Return current configuration as formatted string."""
    from src.config import settings

    return (
        "🔥 Afterburner Configuration\n"
        f"- LLM: {settings.LLM_PROVIDER} ({settings.LLM_MODEL})\n"
        f"- GitHub: {settings.GITHUB_REPO or 'Not configured'}\n"
        f"- Auto PR: {settings.AUTO_PR}\n"
        f"- Security: Semgrep={settings.ENABLE_SEMGREP}, Bandit={settings.ENABLE_BANDIT}\n"
        f"- Deploy: {settings.DEPLOY_TARGET or 'None'}\n"
        f"- Max retries: test={settings.MAX_TEST_DEBUG_ITERATIONS}, reflection={settings.MAX_REFLECTION_RETRIES}\n"
    )


# ──────────────────────────── Server Entry Point ────────────────────────────


async def main():
    """Run the MCP stdio server."""
    logger.info("Starting Afterburner MCP server...")
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
