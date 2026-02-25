# 🚀 Afterburner — Post-Write Companion

**Afterburner** is a lightweight 4-agent system (LangGraph + CrewAI) that activates *after* your code is written — handling security review, testing, git hygiene, deployment, and monitoring.

> You vibe-code in **Cursor / Aider / Antigravity** → type `/afterburner` → Afterburner ships production-ready code.

## Quick Start

```bash
# 1. Install
pip install -e .

# 2. Configure
cp .env.example .env
# Edit .env with your API keys

# 3. Run
afterburner run --repo-path /path/to/your/project
```

## Integration

### Cursor / Antigravity (MCP Server)
```json
// .cursor/mcp.json
{
  "mcpServers": {
    "afterburner": {
      "command": "python",
      "args": ["-m", "integrations.mcp_server"],
      "env": { "AFTERBURNER_REPO_PATH": "." }
    }
  }
}
```

### Aider (CLI)
```yaml
# .aider.conf.yml
custom-commands:
  afterburner: "python -m integrations.cli run"
```

## Architecture

```
Trigger → Change Detector → Security Sentinel → Test Pilot → Git Guardian → Launch Controller → Summary
                                ↑ reflection loop ↑
```

**4 Agents:**
| Agent | Role |
|-------|------|
| Security Sentinel | Semgrep + Bandit + npm/cargo audit + LLM triage |
| Test Pilot | pytest / vitest / Playwright + self-debug loop (×4) |
| Git Guardian | Conventional Commits + branch + PR |
| Launch Controller | CI/CD generation + Vercel/Docker deploy + monitoring |

## License

MIT
