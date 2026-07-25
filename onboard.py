#!/usr/bin/env python3
"""CRESSIDA onboarding — clone, install, and wire up the MCP server in one step.

For collaborators who just cloned the repo. Run it with the Python you want
CRESSIDA to use (ideally inside a virtual environment):

    python onboard.py                 # install + print MCP registration
    python onboard.py --provider anthropic   # also install a provider SDK
    python onboard.py --register      # also register the MCP server with Claude Code

What it does:
  1. Verifies your Python is >= 3.11.
  2. Installs CRESSIDA in editable mode (`pip install -e .`) so
     `python -m cressida.mcp_server` works from anywhere — no matter what
     folder you cloned into.
  3. Prints (or registers) the exact MCP server config for Claude Code,
     pinned to *this* Python interpreter so the server always starts.

It is safe to re-run.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
PROVIDERS = ("anthropic", "openai", "gemini", "groq", "all")


def _run(cmd: list[str]) -> int:
    print(f"\n$ {' '.join(cmd)}")
    return subprocess.call(cmd)


def _check_python() -> None:
    if sys.version_info < (3, 11):
        sys.exit(f"CRESSIDA needs Python >= 3.11 (you have {sys.version.split()[0]}).")


def _install(provider: str | None) -> None:
    target = "." if not provider else f".[{provider}]"
    code = _run([sys.executable, "-m", "pip", "install", "-e", target])
    if code != 0:
        sys.exit("pip install failed — see the output above.")


def _mcp_config() -> dict:
    # Pin the launcher to THIS interpreter so the venv/global choice sticks.
    return {
        "command": sys.executable.replace("\\", "/"),
        "args": ["-m", "cressida.mcp_server"],
    }


def _register(cfg: dict) -> bool:
    """Best-effort: register with Claude Code via the `claude` CLI if present."""
    from shutil import which

    if which("claude") is None:
        return False
    payload = json.dumps(cfg)
    code = _run(["claude", "mcp", "add-json", "cressida", payload, "--scope", "user"])
    return code == 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Onboard CRESSIDA and wire up its MCP server.")
    ap.add_argument("--provider", choices=PROVIDERS, help="also install an LLM provider SDK")
    ap.add_argument("--register", action="store_true", help="register the MCP server with Claude Code (needs the `claude` CLI)")
    ap.add_argument("--skip-install", action="store_true", help="skip pip install (just print MCP config)")
    args = ap.parse_args()

    _check_python()
    print(f"CRESSIDA repo: {REPO}")

    if not args.skip_install:
        _install(args.provider)

    cfg = _mcp_config()
    registered = args.register and _register(cfg)

    print("\n" + "=" * 68)
    if registered:
        print("MCP server 'cressida' registered with Claude Code (user scope).")
        print("Restart Claude Code, then try:  cressida_status")
    else:
        print("Add this MCP server to Claude Code. Easiest way (needs the `claude` CLI):\n")
        print(f"  claude mcp add-json cressida '{json.dumps(cfg)}' --scope user\n")
        print("Or paste this into ~/.claude.json (or your client's mcpServers block):\n")
        print(json.dumps({"mcpServers": {"cressida": cfg}}, indent=2))
    print("=" * 68)

    print("\nNo API key required if you already have the Claude Code or opencode")
    print("CLI installed & logged in — CRESSIDA runs missions through it. Otherwise")
    print("set a provider key, e.g.  export ANTHROPIC_API_KEY=sk-...  (or use Ollama).")
    print("Then in Claude Code:  run_mission(brief=\"Build a todo REST API\")")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
