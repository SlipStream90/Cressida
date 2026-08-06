#!/usr/bin/env python3
"""CRESSIDA onboarding — clone, install, and wire up the MCP server in one step.

For collaborators who just cloned the repo. Run it with the Python you want
CRESSIDA to use (ideally inside a virtual environment):

    python onboard.py                 # install + print MCP registration
    python onboard.py --provider anthropic   # also install a provider SDK
    python onboard.py --register      # also register with Claude Code / opencode / Codex + install the skill

What it does:
  1. Verifies your Python is >= 3.11.
  2. Installs CRESSIDA in editable mode (`pip install -e .`) so
     `python -m cressida.mcp_server` works from anywhere — no matter what
     folder you cloned into.
  3. Prints (or registers) the exact MCP server config, pinned to *this*
     Python interpreter so the server always starts. With --register, wires
     it into whichever of Claude Code (`claude` CLI) / opencode (`opencode`
     CLI) / Codex (`codex` CLI) are found on PATH, and installs the
     `cressida` skill (skills/cressida/SKILL.md) into Claude Code and Codex
     so missions get auto-invoked for project-sized requests without the
     user having to name CRESSIDA explicitly.

It is safe to re-run.
"""
from __future__ import annotations

import argparse
import json
import shutil
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


def _register_claude(cfg: dict) -> bool:
    """Best-effort: register with Claude Code via the `claude` CLI if present."""
    from shutil import which

    if which("claude") is None:
        return False
    payload = json.dumps(cfg)
    code = _run(["claude", "mcp", "add-json", "cressida", payload, "--scope", "user"])
    return code == 0


def _register_opencode(cfg: dict) -> bool:
    """Best-effort: wire into opencode's global config if the `opencode` CLI is present.

    opencode has no CLI setter for MCP servers (confirmed against its docs) — the
    global config at ~/.config/opencode/opencode.json is a plain JSON file, merged
    with project-level config at load time. So we read-modify-write it directly.
    """
    from shutil import which

    if which("opencode") is None:
        return False

    path = Path.home() / ".config" / "opencode" / "opencode.json"
    data: dict = {}
    if path.exists():
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError) as e:
            print(f"  (couldn't read {path}: {e} — leaving opencode config untouched)")
            return False

    data.setdefault("mcp", {})["cressida"] = {
        "type": "local",
        "command": [cfg["command"], *cfg["args"]],
        "enabled": True,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")
    print(f"  Wrote MCP config to {path}")
    return True


def _register_codex(cfg: dict) -> bool:
    """Best-effort: wire into the Codex CLI's ~/.codex/config.toml if present.

    No TOML writer in stdlib (tomllib is read-only), so this appends a
    marker-delimited block rather than parsing/rewriting the file — same
    style Codex's own MCP installers (e.g. headroom) already use in this
    file, and skipped entirely if that block is already there.
    # ponytail: naive text-append, not a real TOML merge. Fine as long as
    # nothing else writes a [mcp_servers.cressida] block; upgrade to a TOML
    # library if config.toml ever needs programmatic edits elsewhere.
    """
    from shutil import which

    if which("codex") is None:
        return False

    path = Path.home() / ".codex" / "config.toml"
    if path.exists() and "[mcp_servers.cressida]" in path.read_text(encoding="utf-8"):
        return True  # already registered

    block = (
        "\n# --- Cressida MCP server ---\n"
        "[mcp_servers.cressida]\n"
        f'command = "{cfg["command"]}"\n'
        f'args = {json.dumps(cfg["args"])}\n'
        f'env = {{ "PYTHONPATH" = "{REPO.parent.as_posix()}" }}\n'
        "# --- end Cressida MCP server ---\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(block)
    print(f"  Appended MCP config to {path}")
    return True


def _install_skills() -> list[str]:
    """Copy the bundled Cressida skill (auto-invoke trigger) to every
    skill-aware client found on this machine (Claude Code, Codex). opencode
    has no skill mechanism -- it gets a nudge in its AGENTS.md instead (see
    the one-time onboarding note in docs/, not automated here since AGENTS.md
    is user-owned free text, not a directory CRESSIDA can safely overwrite).
    """
    src = REPO / "skills" / "cressida" / "SKILL.md"
    if not src.exists():
        return []

    installed = []
    for base, client in ((Path.home() / ".claude", "claude"), (Path.home() / ".codex", "codex")):
        if not base.exists():
            continue
        dest_dir = base / "skills" / "cressida"
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, dest_dir / "SKILL.md")
        installed.append(client)
    return installed


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
    claude_registered = args.register and _register_claude(cfg)
    opencode_registered = args.register and _register_opencode(cfg)
    codex_registered = args.register and _register_codex(cfg)
    skills_installed = args.register and _install_skills()

    print("\n" + "=" * 68)
    if claude_registered:
        print("MCP server 'cressida' registered with Claude Code (user scope).")
        print("Restart Claude Code, then try:  cressida_status")
    else:
        print("Add this MCP server to Claude Code. Easiest way (needs the `claude` CLI):\n")
        print(f"  claude mcp add-json cressida '{json.dumps(cfg)}' --scope user\n")
        print("Or paste this into ~/.claude.json (or your client's mcpServers block):\n")
        print(json.dumps({"mcpServers": {"cressida": cfg}}, indent=2))

    print()
    if opencode_registered:
        print("MCP server 'cressida' registered with opencode (~/.config/opencode/opencode.json).")
        print("Restart opencode, then try:  opencode mcp list")
    elif args.register:
        print("opencode CLI not found on PATH — skipped opencode registration.")

    print()
    if codex_registered:
        print("MCP server 'cressida' registered with Codex (~/.codex/config.toml).")
        print("Restart Codex to pick it up.")
    elif args.register:
        print("Codex CLI not found on PATH — skipped Codex registration.")

    print()
    if skills_installed:
        print(f"Cressida skill installed for auto-invocation: {', '.join(skills_installed)}.")
        print("(opencode has no skill mechanism — see AGENTS.md for its equivalent nudge.)")
    print("=" * 68)

    print("\nNo API key required if you already have the Claude Code or opencode")
    print("CLI installed & logged in — CRESSIDA runs missions through it. Otherwise")
    print("set a provider key, e.g.  export ANTHROPIC_API_KEY=sk-...  (or use Ollama).")
    print("Then in Claude Code:  run_mission(brief=\"Build a todo REST API\")")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
