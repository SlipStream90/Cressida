"""Cressida MCP Server.

Exposes Cressida's multi-agent pipeline as MCP tools so Claude Code (or any
MCP-compatible client) can trigger missions, check status, read outputs, and
resolve BOND escalations from anywhere on the device.

Run directly for testing:
    python -m cressida.mcp_server

Register globally in ~/.claude/settings.json:
    {
      "mcpServers": {
        "cressida": {
          "command": "python",
          "args": ["-m", "cressida.mcp_server"],
          "cwd": "C:/Users/adity/Desktop/Cressida"
        }
      }
    }
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from mcp.server.fastmcp import FastMCP

# ── Resolve Cressida root from this file's location ──────────────────────────
# mcp_server.py lives at <root>/cressida/mcp_server.py
_CRESSIDA_PACKAGE = Path(__file__).parent          # .../cressida/
_CRESSIDA_ROOT    = _CRESSIDA_PACKAGE.parent       # .../Cressida/
# Missions are written to <root>/missions/ (relative to project root)
_MISSIONS_DIR     = _CRESSIDA_ROOT / "missions"    # .../Cressida/missions/

# Make sure the package is importable
if str(_CRESSIDA_ROOT) not in sys.path:
    sys.path.insert(0, str(_CRESSIDA_ROOT))

mcp = FastMCP(
    "Cressida",
    instructions=(
        "Multi-agent software engineering framework. "
        "Use run_mission to start a new project from a plain-English brief. "
        "Use mission_status to check progress. "
        "Use read_mission_file to inspect outputs. "
        "Use resolve_escalation when BOND requests a human decision."
    ),
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _missions_dir() -> Path:
    _MISSIONS_DIR.mkdir(parents=True, exist_ok=True)
    return _MISSIONS_DIR


def _mission_path(mission_id: str) -> Path:
    return _missions_dir() / mission_id


def _load_execution_state(mission_id: str) -> dict:
    p = _mission_path(mission_id) / "execution_state.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def _list_escalations(mission_id: str) -> list[str]:
    esc_dir = _mission_path(mission_id) / "escalations"
    if not esc_dir.exists():
        return []
    return [f.name for f in esc_dir.iterdir() if f.suffix == ".json" and f.stem != "resolution"]


# ── Tools ─────────────────────────────────────────────────────────────────────

# Track running missions
_running_missions: dict[str, asyncio.Task] = {}


@mcp.tool()
async def run_mission(
    brief: str,
    provider: str = "auto",
    ollama_model: str = "llama3.2",
    priority: str = "medium",
) -> str:
    """Start a new Cressida mission from a plain-English brief.

    Cressida spins up 9 agents and runs: research -> spec -> architecture ->
    BOND gate -> implementation -> review. Returns immediately with a mission ID.

    Usage flow:
      1. Call run_mission with your brief -> get mission_id
      2. Call mission_status to check progress
      3. Call read_mission_file to inspect outputs

    Args:
        brief:        What you want built. Can be a plain-English description
                      or a path to a markdown file containing a PRD.
        provider:     auto | opencode | claude_cli | anthropic | openai | gemini | groq | ollama
        ollama_model: Only used when provider=ollama. Default: llama3.2
        priority:     low | medium | high.

    Returns:
        Mission ID and status message.
    """
    from datetime import datetime as _dt

    mission_id = f"mission_{_dt.now().strftime('%Y%m%d_%H%M%S')}"

    brief_path = _CRESSIDA_ROOT / "_mcp_brief.md"
    brief_path.write_text(brief, encoding="utf-8")

    # Run in background — returns immediately so the MCP client doesn't time out
    task = asyncio.create_task(
        _background_mission(mission_id, str(brief_path), provider, ollama_model, priority)
    )
    _running_missions[mission_id] = task

    out_dir = _mission_path(mission_id)
    return (
        f"Mission started: {mission_id}\n"
        f"Output: {out_dir}\n\n"
        f"The mission is running in the background. "
        f"Call mission_status(mission_id=\"{mission_id}\") to check progress. "
        f"Files will appear in the output directory as each phase completes."
    )


async def _background_mission(
    mission_id: str, brief_path: str, provider: str, ollama_model: str, priority: str
) -> None:
    """Run a mission in the background."""
    try:
        await _run_mission_bg(mission_id, brief_path, provider, ollama_model, priority)
    except Exception as exc:
        print(f"[CRESSIDA] Mission {mission_id} failed: {exc}")
    finally:
        _running_missions.pop(mission_id, None)
        try:
            bp = Path(brief_path)
            if bp.exists():
                bp.unlink()
        except Exception:
            pass


async def _run_mission_bg(
    mission_id: str, brief_path: str, provider: str, ollama_model: str, priority: str
) -> None:
    from cressida.cli.commands import run_mission as _run_mission
    import argparse

    args = argparse.Namespace(
        brief=brief_path,
        mission_id=mission_id,
        provider=provider,
        ollama_model=ollama_model,
        ollama_host="http://localhost:11434",
        priority=priority,
    )

    _missions_dir()
    prev_cwd = os.getcwd()
    os.chdir(_CRESSIDA_ROOT)
    try:
        exit_code = await _run_mission(args)
        status = "completed" if exit_code == 0 else "failed"
        print(f"[CRESSIDA] Mission {mission_id} {status}.")
    finally:
        os.chdir(prev_cwd)


@mcp.tool()
def mission_status(mission_id: str) -> str:
    """Get the current status of a running or completed Cressida mission.

    Args:
        mission_id: The mission ID returned by run_mission (e.g. MSN-2026-001)

    Returns:
        JSON with task states, counts, and any pending escalations.
    """
    state = _load_execution_state(mission_id)
    escalations = _list_escalations(mission_id)

    if not state:
        # Fall back to the global status.json if available
        status_file = _MISSIONS_DIR / "status.json"
        if status_file.exists():
            global_status = json.loads(status_file.read_text(encoding="utf-8"))
            return json.dumps(global_status, indent=2)
        return f"No state found for mission {mission_id!r}. Is the mission ID correct?"

    tasks = state.get("tasks", {})
    counts: dict[str, int] = {}
    for t in tasks.values():
        s = t.get("status", "unknown")
        counts[s] = counts.get(s, 0) + 1

    result = {
        "mission_id": mission_id,
        "task_counts": counts,
        "total_tasks": len(tasks),
        "tasks": {tid: {"status": t.get("status"), "agent": t.get("agent")} for tid, t in tasks.items()},
        "pending_escalations": escalations,
    }
    return json.dumps(result, indent=2)


@mcp.tool()
def list_missions() -> str:
    """List all Cressida missions with their completion status.

    Returns:
        JSON list of missions sorted by most recent first.
    """
    mdir = _missions_dir()
    missions = []
    for d in sorted(mdir.iterdir(), reverse=True):
        if not d.is_dir() or d.name in ("inbox", "scheduled", "processed"):
            continue
        state = _load_execution_state(d.name)
        tasks = state.get("tasks", {})
        statuses = [t.get("status") for t in tasks.values()]
        overall = (
            "completed" if all(s == "completed" for s in statuses) and statuses
            else "failed" if any(s == "failed" for s in statuses)
            else "running" if any(s in ("in_progress", "pending") for s in statuses)
            else "unknown"
        )
        missions.append({
            "id": d.name,
            "status": overall,
            "task_count": len(tasks),
            "escalations": _list_escalations(d.name),
        })
    return json.dumps(missions, indent=2)


@mcp.tool()
def read_mission_file(mission_id: str, filename: str) -> str:
    """Read an output file from a completed mission.

    Common files to read:
      - dossier.md              — mission brief and summary
      - ARCHITECTURE.md         — system architecture designed by agents
      - intelligence/PRD.md     — product requirements document
      - intelligence/research_report.md
      - review_report.md        — final code review
      - bond_review.md          — BOND's gate decision
      - execution_state.json    — raw task execution state

    Args:
        mission_id: Mission ID (e.g. MSN-2026-001)
        filename:   Relative path within the mission folder

    Returns:
        File contents as text.
    """
    target = _mission_path(mission_id) / filename
    if not target.exists():
        # List what's actually there to help the caller
        mpath = _mission_path(mission_id)
        if not mpath.exists():
            return f"Mission {mission_id!r} not found."
        files = [str(f.relative_to(mpath)) for f in mpath.rglob("*") if f.is_file()]
        return f"File {filename!r} not found in mission {mission_id}.\n\nAvailable files:\n" + "\n".join(sorted(files))
    return target.read_text(encoding="utf-8", errors="replace")


@mcp.tool()
def list_mission_files(mission_id: str) -> str:
    """List all output files produced by a mission.

    Args:
        mission_id: Mission ID (e.g. MSN-2026-001)

    Returns:
        Sorted list of relative file paths.
    """
    mpath = _mission_path(mission_id)
    if not mpath.exists():
        return f"Mission {mission_id!r} not found."
    files = sorted(str(f.relative_to(mpath)) for f in mpath.rglob("*") if f.is_file())
    return "\n".join(files)


@mcp.tool()
def resolve_escalation(mission_id: str, decision: str) -> str:
    """Resolve a BOND escalation so the mission can continue.

    When BOND is unsure about an architectural decision, it escalates and halts
    the mission. Call this tool with your decision to resume.

    Args:
        mission_id: Mission ID with a pending escalation
        decision:   Your plain-English decision or approval text

    Returns:
        Confirmation that the resolution was written.
    """
    esc_dir = _mission_path(mission_id) / "escalations"
    if not esc_dir.exists():
        return f"No escalations directory found for mission {mission_id!r}."

    pending = [f for f in esc_dir.iterdir() if f.suffix == ".json" and f.stem != "resolution"]
    if not pending:
        return f"No pending escalations for mission {mission_id!r}."

    resolution = {
        "resolved_at": datetime.utcnow().isoformat() + "Z",
        "decision": decision,
        "resolved_escalations": [f.name for f in pending],
    }
    resolution_path = esc_dir / "resolution.json"
    resolution_path.write_text(json.dumps(resolution, indent=2), encoding="utf-8")

    return (
        f"Resolution written for mission {mission_id}.\n"
        f"Resolved {len(pending)} escalation(s): {[f.name for f in pending]}\n"
        f"Restart the mission with: cressida run (it will pick up from the last checkpoint)"
    )


@mcp.tool()
def cressida_status() -> str:
    """Get the current Cressida system status.

    Returns:
        JSON with mission counts and system info.
    """
    mdir = _missions_dir()
    missions = []
    for d in sorted(mdir.iterdir(), reverse=True):
        if not d.is_dir() or d.name in ("inbox", "scheduled", "processed"):
            continue
        state = _load_execution_state(d.name)
        tasks = state.get("tasks", {})
        statuses = [t.get("status") for t in tasks.values()]
        overall = (
            "completed" if all(s == "completed" for s in statuses) and statuses
            else "failed" if any(s == "failed" for s in statuses)
            else "running" if any(s in ("in_progress", "pending") for s in statuses)
            else "unknown"
        )
        missions.append({"id": d.name, "status": overall})

    return json.dumps({
        "status": "operational",
        "version": "0.1.0",
        "total_missions": len(missions),
        "recent_missions": missions[:10],
    }, indent=2)


# ── Obsidian tools ────────────────────────────────────────────────────────────

def _get_bridge():
    """Return ObsidianBridge or raise a clear error."""
    from cressida.obsidian.bridge import get_bridge
    bridge = get_bridge()
    if bridge is None:
        raise RuntimeError(
            "Obsidian vault not configured. "
            "Set CRESSIDA_OBSIDIAN_VAULT env var to your vault path."
        )
    return bridge


@mcp.tool()
def obsidian_search(query: str, max_results: int = 8) -> str:
    """Search your Obsidian vault for notes matching a query.

    Cressida agents use this automatically via query_memory. Call it directly
    to find relevant notes before starting a mission or to reference prior work.

    Args:
        query:       Natural language or keyword query
        max_results: Max number of matching notes to return (default 8)

    Returns:
        Matching notes with path, title, and excerpt.
    """
    bridge = _get_bridge()
    results = bridge.search(query, max_results=max_results)
    if not results:
        return f"No vault notes found matching {query!r}."
    lines = [f"**{r['title']}** (`{r['path']}`)\n> {r['excerpt']}" for r in results]
    return "\n\n".join(lines)


@mcp.tool()
def obsidian_read(note_path: str) -> str:
    """Read a specific note from your Obsidian vault.

    Args:
        note_path: Vault-relative path (e.g. "Cressida/Knowledge/lessons.md")

    Returns:
        Full note content.
    """
    bridge = _get_bridge()
    content = bridge.read_note(note_path)
    if not content:
        # List nearby files to help
        folder = str(Path(note_path).parent)
        available = bridge.list_notes(folder)
        hint = "\n".join(available[:20]) if available else "(folder not found)"
        return f"Note {note_path!r} not found.\n\nNotes in {folder!r}:\n{hint}"
    return content


@mcp.tool()
def obsidian_write(note_path: str, content: str, tags: str = "") -> str:
    """Write or update a note in your Obsidian vault.

    Writes directly to the vault — the note will appear in Obsidian immediately.
    Existing content is overwritten.

    Args:
        note_path: Vault-relative path (e.g. "Projects/idea.md")
        content:   Markdown content for the note
        tags:      Comma-separated tags to add to frontmatter (optional)

    Returns:
        Confirmation with the full file path written.
    """
    bridge = _get_bridge()
    target = bridge.vault / note_path
    target.parent.mkdir(parents=True, exist_ok=True)

    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    if tag_list:
        try:
            import yaml
            fm_str = yaml.dump(
                {"created": datetime.utcnow().strftime("%Y-%m-%d"), "tags": tag_list},
                default_flow_style=False,
            ).strip()
            content = f"---\n{fm_str}\n---\n\n{content}"
        except ImportError:
            pass

    target.write_text(content, encoding="utf-8")
    return f"Written: {target}"


@mcp.tool()
def obsidian_list(subfolder: str = "") -> str:
    """List all notes in the Obsidian vault (or a subfolder).

    Args:
        subfolder: Vault-relative subfolder path. Leave empty for all notes.

    Returns:
        Newline-separated list of vault-relative note paths.
    """
    bridge = _get_bridge()
    notes = bridge.list_notes(subfolder)
    if not notes:
        return f"No notes found in {subfolder!r}." if subfolder else "Vault appears empty."
    return "\n".join(notes)


@mcp.tool()
def obsidian_sync_mission(mission_id: str) -> str:
    """Manually sync a mission's output files into the Obsidian vault.

    Useful if you want to pull in a mission that ran before Obsidian was configured,
    or to force a re-sync after files changed.

    Args:
        mission_id: Mission ID (e.g. MSN-2026-001)

    Returns:
        Confirmation of what was synced.
    """
    bridge = _get_bridge()
    missions_base = _CRESSIDA_PACKAGE / "missions"
    knowledge_base = _CRESSIDA_PACKAGE / "knowledge"
    bridge.sync_mission_outputs(mission_id, missions_base)
    bridge.sync_knowledge(knowledge_base)
    vault_dir = bridge.missions_dir() / mission_id
    synced = [f.name for f in vault_dir.glob("*.md")] if vault_dir.exists() else []
    return f"Synced {len(synced)} notes to vault for mission {mission_id}:\n" + "\n".join(synced)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run()
