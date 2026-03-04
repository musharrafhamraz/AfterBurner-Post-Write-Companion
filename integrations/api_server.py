"""Afterburner API Server — FastAPI + WebSocket backend for the VSCode extension."""

import asyncio
import json
import os
import sys
import traceback
from typing import Optional, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
import uvicorn
from loguru import logger


app = FastAPI(title="Afterburner API", version="0.1.0")
main_loop: Optional[asyncio.AbstractEventLoop] = None

@app.on_event("startup")
async def startup_event():
    global main_loop
    main_loop = asyncio.get_running_loop()

# ──────────────────────────── WebSocket Manager ────────────────────────────


class ConnectionManager:
    """Manages active WebSocket connections and broadcasts state updates."""

    def __init__(self):
        self.connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.connections.add(websocket)
        logger.info("WebSocket client connected ({} total)", len(self.connections))

    def disconnect(self, websocket: WebSocket):
        self.connections.discard(websocket)
        logger.info("WebSocket client disconnected ({} total)", len(self.connections))

    async def broadcast(self, message: dict):
        """Send a JSON message to all connected clients."""
        dead = set()
        for ws in self.connections:
            try:
                await ws.send_json(message)
            except Exception:
                dead.add(ws)
        self.connections -= dead


manager = ConnectionManager()

# ──────────────────────────── State Tracking ────────────────────────────

# Current pipeline state — updated after each node completes
current_state: dict = {
    "status": "idle",
    "current_stage": "none",
    "stages": {
        "detect_changes": {"status": "pending", "detail": ""},
        "security_review": {"status": "pending", "detail": ""},
        "test_run": {"status": "pending", "detail": ""},
        "git_commit": {"status": "pending", "detail": ""},
        "deploy": {"status": "pending", "detail": ""},
        "summarize": {"status": "pending", "detail": ""},
    },
    "errors": [],
    "final_summary": None,
    "result": None,
}

last_run_result: Optional[dict] = None


def reset_state():
    """Reset pipeline state for a new run."""
    global current_state
    current_state = {
        "status": "idle",
        "current_stage": "none",
        "stages": {
            "detect_changes": {"status": "pending", "detail": ""},
            "security_review": {"status": "pending", "detail": ""},
            "test_run": {"status": "pending", "detail": ""},
            "git_commit": {"status": "pending", "detail": ""},
            "deploy": {"status": "pending", "detail": ""},
            "summarize": {"status": "pending", "detail": ""},
        },
        "errors": [],
        "final_summary": None,
        "result": None,
    }


# ──────────────────────────── Node Callback ────────────────────────────


def on_node_complete(node_name: str, node_output: dict, full_state: dict):
    """
    Callback invoked after each LangGraph node completes.
    Updates current_state and broadcasts to all WebSocket clients.
    """
    global current_state

    # Map internal node names to stage keys
    stage_map = {
        "detect_changes": "detect_changes",
        "security_review": "security_review",
        "test_run": "test_run",
        "git_commit": "git_commit",
        "deploy": "deploy",
        "summarize": "summarize",
        "hard_fail": "summarize",
    }

    stage_key = stage_map.get(node_name)

    if stage_key and stage_key in current_state["stages"]:
        # Build detail string based on the node
        detail = _build_detail(node_name, node_output, full_state)
        current_state["stages"][stage_key] = {
            "status": "complete",
            "detail": detail,
        }

    current_state["current_stage"] = node_name

    # Update error list
    if node_output.get("errors"):
        current_state["errors"].extend(node_output["errors"])

    # Check for hard fail
    if node_output.get("hard_fail"):
        current_state["status"] = "failed"

    # Check for final summary
    if node_output.get("final_summary"):
        current_state["final_summary"] = node_output["final_summary"]

    # Mark the next stage as running
    stage_order = ["detect_changes", "security_review", "test_run", "git_commit", "deploy", "summarize"]
    if stage_key in stage_order:
        idx = stage_order.index(stage_key)
        if idx + 1 < len(stage_order):
            next_stage = stage_order[idx + 1]
            if current_state["stages"][next_stage]["status"] == "pending":
                current_state["stages"][next_stage]["status"] = "running"

    # Broadcast update
    if main_loop:
        asyncio.run_coroutine_threadsafe(
            manager.broadcast({
                "type": "state_update",
                "data": current_state,
            }),
            main_loop
        )


def _build_detail(node_name: str, output: dict, state: dict) -> str:
    """Build a human-readable detail string for a completed node."""
    if node_name == "detect_changes":
        files = output.get("changed_files", [])
        return f"{len(files)} file(s) changed"

    elif node_name == "security_review":
        passed = output.get("security_passed", True)
        count = output.get("security_issues_count", 0)
        icon = "✅" if passed else "❌"
        return f"{icon} {count} issue(s) — {'PASSED' if passed else 'BLOCKED'}"

    elif node_name == "test_run":
        passed = output.get("tests_passed", False)
        results = output.get("test_results", [])
        total_pass = sum(r.get("passed", 0) for r in results)
        total_fail = sum(r.get("failed", 0) for r in results)
        icon = "✅" if passed else "❌"
        return f"{icon} {total_pass} passed, {total_fail} failed"

    elif node_name == "git_commit":
        sha = output.get("commit_sha", "")
        pr = output.get("pr_url", "")
        detail = f"Commit: {sha[:8]}" if sha else "No commit"
        if pr:
            detail += f" | PR: {pr}"
        return detail

    elif node_name == "deploy":
        status = output.get("deployment_status", "skipped")
        url = output.get("deployment_url", "")
        detail = f"Status: {status}"
        if url:
            detail += f" | URL: {url}"
        return detail

    elif node_name == "summarize":
        return "Report generated"

    elif node_name == "hard_fail":
        return "💥 Pipeline hard-failed"

    return ""


# ──────────────────────────── WebSocket Endpoint ────────────────────────────


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time pipeline updates."""
    await manager.connect(websocket)

    # Send current state on connect
    await websocket.send_json({"type": "state_update", "data": current_state})

    try:
        while True:
            data = await websocket.receive_json()
            command = data.get("command")

            if command == "run":
                await _handle_run(data)
            elif command == "security":
                await _handle_security(data)
            elif command == "test":
                await _handle_test(data)
            elif command == "commit":
                await _handle_commit(data)
            elif command == "deploy":
                await _handle_deploy(data)
            elif command == "status":
                await _handle_status(websocket)
            else:
                await websocket.send_json({
                    "type": "error",
                    "data": f"Unknown command: {command}",
                })
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# ──────────────────────────── Command Handlers ────────────────────────────


async def _handle_run(data: dict):
    """Handle full pipeline run."""
    repo_path = data.get("repo_path", os.getcwd())
    skip_deploy = data.get("skip_deploy", True)

    reset_state()
    current_state["status"] = "running"
    current_state["stages"]["detect_changes"]["status"] = "running"
    await manager.broadcast({"type": "state_update", "data": current_state})

    loop = asyncio.get_event_loop()

    def _run():
        global last_run_result
        try:
            from src.graph.workflow import run_afterburner
            result = run_afterburner(
                repo_path=os.path.abspath(repo_path),
                trigger_source="extension",
                skip_deploy=skip_deploy,
                on_node_complete=on_node_complete,
            )
            last_run_result = result
            current_state["status"] = "failed" if result.get("hard_fail") else "complete"
            current_state["result"] = {
                "changed_files": result.get("changed_files", []),
                "security_passed": result.get("security_passed"),
                "tests_passed": result.get("tests_passed"),
                "commit_sha": result.get("commit_sha"),
                "pr_url": result.get("pr_url"),
                "deployment_status": result.get("deployment_status"),
                "deployment_url": result.get("deployment_url"),
                "hard_fail": result.get("hard_fail", False),
            }
        except Exception as e:
            current_state["status"] = "error"
            current_state["errors"].append(str(e))
            logger.error("Pipeline error: {}", traceback.format_exc())

    await loop.run_in_executor(None, _run)
    await manager.broadcast({"type": "state_update", "data": current_state})
    await manager.broadcast({"type": "run_complete", "data": current_state})


async def _handle_security(data: dict):
    """Handle security-only run."""
    repo_path = os.path.abspath(data.get("repo_path", os.getcwd()))

    reset_state()
    current_state["status"] = "running"
    current_state["stages"]["detect_changes"]["status"] = "running"
    await manager.broadcast({"type": "state_update", "data": current_state})

    loop = asyncio.get_event_loop()

    def _run():
        from src.utils.logging import setup_logging
        from src.agents.change_detector import change_detector_node
        from src.agents.security_sentinel import security_sentinel_node

        setup_logging()
        state = {"repo_path": repo_path, "changed_files": [], "trigger_source": "extension", "reflection_count": 0}
        cd_result = change_detector_node(state)
        state.update(cd_result)
        on_node_complete("detect_changes", cd_result, state)

        result = security_sentinel_node(state)
        state.update(result)
        on_node_complete("security_review", result, state)
        current_state["status"] = "complete"

    await loop.run_in_executor(None, _run)
    await manager.broadcast({"type": "state_update", "data": current_state})
    await manager.broadcast({"type": "run_complete", "data": current_state})


async def _handle_test(data: dict):
    """Handle test-only run."""
    repo_path = os.path.abspath(data.get("repo_path", os.getcwd()))

    reset_state()
    current_state["status"] = "running"
    current_state["stages"]["detect_changes"]["status"] = "running"
    await manager.broadcast({"type": "state_update", "data": current_state})

    loop = asyncio.get_event_loop()

    def _run():
        from src.utils.logging import setup_logging
        from src.agents.change_detector import change_detector_node
        from src.agents.test_pilot import test_pilot_node

        setup_logging()
        state = {"repo_path": repo_path, "changed_files": [], "trigger_source": "extension", "test_debug_iterations": 0}
        cd_result = change_detector_node(state)
        state.update(cd_result)
        on_node_complete("detect_changes", cd_result, state)

        result = test_pilot_node(state)
        state.update(result)
        on_node_complete("test_run", result, state)
        current_state["status"] = "complete"

    await loop.run_in_executor(None, _run)
    await manager.broadcast({"type": "state_update", "data": current_state})
    await manager.broadcast({"type": "run_complete", "data": current_state})


async def _handle_commit(data: dict):
    """Handle git commit-only run."""
    repo_path = os.path.abspath(data.get("repo_path", os.getcwd()))

    reset_state()
    current_state["status"] = "running"
    current_state["stages"]["detect_changes"]["status"] = "running"
    await manager.broadcast({"type": "state_update", "data": current_state})

    loop = asyncio.get_event_loop()

    def _run():
        from src.utils.logging import setup_logging
        from src.agents.change_detector import change_detector_node
        from src.agents.git_guardian import git_guardian_node

        setup_logging()
        if data.get("no_pr"):
            os.environ["AFTERBURNER_AUTO_PR"] = "false"

        state = {"repo_path": repo_path, "changed_files": [], "trigger_source": "extension", "security_passed": True, "tests_passed": True}
        cd_result = change_detector_node(state)
        state.update(cd_result)
        on_node_complete("detect_changes", cd_result, state)

        result = git_guardian_node(state)
        state.update(result)
        on_node_complete("git_commit", result, state)
        current_state["status"] = "complete"

    await loop.run_in_executor(None, _run)
    await manager.broadcast({"type": "state_update", "data": current_state})
    await manager.broadcast({"type": "run_complete", "data": current_state})


async def _handle_deploy(data: dict):
    """Handle deploy-only run."""
    repo_path = os.path.abspath(data.get("repo_path", os.getcwd()))

    reset_state()
    current_state["status"] = "running"
    current_state["stages"]["deploy"]["status"] = "running"
    await manager.broadcast({"type": "state_update", "data": current_state})

    loop = asyncio.get_event_loop()

    def _run():
        from src.utils.logging import setup_logging
        from src.agents.launch_controller import launch_controller_node

        setup_logging()
        target = data.get("target")
        if target:
            os.environ["AFTERBURNER_DEPLOY_TARGET"] = target

        state = {"repo_path": repo_path, "skip_deploy": False}
        result = launch_controller_node(state)
        on_node_complete("deploy", result, state)
        current_state["status"] = "complete"

    await loop.run_in_executor(None, _run)
    await manager.broadcast({"type": "state_update", "data": current_state})
    await manager.broadcast({"type": "run_complete", "data": current_state})


async def _handle_status(websocket: WebSocket):
    """Send current config to requesting client."""
    from src.config import settings

    config = {
        "llm_provider": settings.LLM_PROVIDER,
        "llm_model": settings.LLM_MODEL,
        "github_repo": settings.GITHUB_REPO,
        "auto_pr": settings.AUTO_PR,
        "enable_semgrep": settings.ENABLE_SEMGREP,
        "enable_bandit": settings.ENABLE_BANDIT,
        "deploy_target": settings.DEPLOY_TARGET,
        "max_test_retries": settings.MAX_TEST_DEBUG_ITERATIONS,
        "max_reflection_retries": settings.MAX_REFLECTION_RETRIES,
    }
    await websocket.send_json({"type": "config", "data": config})


# ──────────────────────────── REST Endpoints ────────────────────────────


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


@app.get("/api/state")
async def get_state():
    return JSONResponse(content=current_state)


@app.get("/api/last-run")
async def get_last_run():
    if last_run_result:
        summary = last_run_result.get("final_summary", "No summary.")
        return JSONResponse(content={"summary": summary})
    return JSONResponse(content={"summary": None})


# ──────────────────────────── Entry Point ────────────────────────────


def main():
    """Run the API server."""
    port = int(os.environ.get("AFTERBURNER_PORT", "7777"))
    logger.info("Starting Afterburner API server on port {}", port)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
