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
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from mcp.server.fastmcp import FastMCP

# ── Resolve Cressida root from this file's location ──────────────────────────
# mcp_server.py lives at <root>/cressida/mcp_server.py
_CRESSIDA_PACKAGE = Path(__file__).parent          # .../Cressida/cressida/
_CRESSIDA_ROOT    = _CRESSIDA_PACKAGE.parent       # .../Cressida/  (the *import* root)

# Make sure the package is importable before importing from it.
if str(_CRESSIDA_ROOT) not in sys.path:
    sys.path.insert(0, str(_CRESSIDA_ROOT))

# Missions live under the package dir — which is the repository root and holds the
# tracked agents/, knowledge/, and missions/ trees. The previous anchor used
# _CRESSIDA_ROOT, one level higher, putting missions outside the repo and in a
# different tree from the one agents wrote to. See cressida/core/paths.py.
from cressida.core.paths import missions_root as _missions_root  # noqa: E402

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

# ── Status monitoring (starts once on first use) ─────────────────────────────
_monitor_started = False


def _ensure_monitor_started() -> None:
    """Start StatusServer + StallMonitor as background tasks (once)."""
    global _monitor_started
    if _monitor_started:
        return
    _monitor_started = True
    try:
        from cressida.core.events import EventBus
        from cressida.autonomy.monitor import StatusServer, StallMonitor

        bus = EventBus()
        status_file = _missions_dir() / "status.json"

        server = StatusServer(bus, status_file=str(status_file))
        monitor = StallMonitor(bus)

        loop = asyncio.get_event_loop()
        loop.create_task(server.run())
        loop.create_task(monitor.run())
        print(f"[CRESSIDA] Status monitor started (status_file={status_file})")
    except Exception as exc:
        print(f"[CRESSIDA] Warning: Could not start status monitor: {exc}")

    try:
        from cressida.dashboard import start_dashboard_background

        start_dashboard_background()
    except Exception as exc:
        print(f"[CRESSIDA] Warning: Could not start dashboard: {exc}")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _missions_dir() -> Path:
    d = _missions_root()
    d.mkdir(parents=True, exist_ok=True)
    return d


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

# Track running missions — either a subprocess.Popen (own console window) or,
# when a window can't be spawned, the in-process asyncio.Task fallback.
_running_missions: dict[str, asyncio.Task | subprocess.Popen] = {}


def _spawn_mission_window(
    mission_id: str, brief_path: str, provider: str, ollama_model: str, project_dir: str,
) -> subprocess.Popen | None:
    """Launch the mission as its own OS process in a new, visible console window.

    Missions used to run as an asyncio.Task inside this MCP server process —
    invisible, and sharing this process's stdout. A dedicated window lets you
    watch each mission's own agent-by-agent output live, and matches how the
    rest of Cressida already treats a mission's state as disk-shared rather
    than in-process (see core/progress.py) — a separate OS process is just
    that same boundary made literal.

    Returns the Popen handle, or None if no window could be opened (e.g.
    non-Windows/headless), in which case the caller falls back to running the
    mission in-process as before.
    """
    cmd = [
        sys.executable, "-m", "cressida.cli", "run", brief_path,
        "--mission-id", mission_id,
        "--provider", provider,
        "--ollama-model", ollama_model,
    ]
    if project_dir:
        cmd += ["--project-dir", project_dir]

    popen_kwargs: dict = {"cwd": str(_CRESSIDA_ROOT)}
    if sys.platform == "win32":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_CONSOLE
    else:
        # No universal "new terminal window" primitive off Windows; running
        # detached at least keeps it out of this process's own stdout.
        popen_kwargs["start_new_session"] = True

    try:
        return subprocess.Popen(cmd, **popen_kwargs)
    except Exception as exc:
        print(f"[CRESSIDA] Could not spawn mission window for {mission_id}: {exc}")
        return None


@mcp.tool()
async def run_mission(
    brief: str,
    provider: str = "auto",
    ollama_model: str = "llama3.2",
    priority: str = "medium",
    project_dir: str = "",
) -> str:
    """Start a new Cressida mission from a plain-English brief.

    Cressida runs: research -> methodology research -> product definition ->
    architecture -> BOND gate -> planning -> implementation -> review. Returns
    immediately with a mission ID.

    Usage flow:
      1. Call run_mission with your brief -> get mission_id
      2. Call mission_status to check progress
      3. Call read_mission_file to inspect outputs

    Args:
        brief:        What you want built. Can be a plain-English description
                      or a path to a markdown file containing a PRD.
        provider:     auto | opencode | claude_cli | codex | anthropic | openai | gemini | groq | ollama
        ollama_model: Only used when provider=ollama. Default: llama3.2
        priority:     low | medium | high.
        project_dir:  Absolute path to the project the mission should act on —
                      where implementation code is written. Pass this whenever the
                      mission targets an existing codebase; naming the path in the
                      brief alone is NOT enough, because the agent subprocess is
                      only granted access to directories passed here. Defaults to
                      CRESSIDA_PROJECT_DIR, then the server's working directory.

    Returns:
        Mission ID and status message.
    """
    from datetime import datetime as _dt

    _ensure_monitor_started()

    mission_id = f"mission_{_dt.now().strftime('%Y%m%d_%H%M%S')}"

    # Resolve a path-form brief to its actual content *here*, before it is ever
    # persisted. cli/commands.py:run_mission also resolves a path -- but it
    # resolves the path to the copy this function writes below, not the
    # original argument. If that original argument was itself a path (this
    # tool's docstring explicitly invites that: "or a path to a markdown
    # file"), the copy just contains the path string, and cli/commands.py's
    # resolve step reads back... the path string, one level short of the real
    # content. That silently starved Dispatcher._select_skills (which
    # keyword-matches against state.brief for skill selection) of every real
    # word in the brief -- it only ever saw path fragments like "users" and
    # "desktop", never "frontend" or "dashboard". Skill selection isn't the
    # only downstream reader of state.brief, so this is fixed at the source,
    # not patched in the one place it happened to be noticed.
    resolved_brief = brief
    try:
        candidate = Path(brief.strip())
        if candidate.is_file():
            resolved_brief = candidate.read_text(encoding="utf-8")
    except OSError:
        pass  # Not a valid path on this OS (e.g. too long) -- treat as literal text.

    # Keep the brief inside the mission it belongs to. It used to be written to
    # the directory above the repo root, where concurrent missions overwrote each
    # other's brief and the stray files were left behind on failure.
    out_dir = _mission_path(mission_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    brief_path = out_dir / "brief.md"
    brief_path.write_text(resolved_brief, encoding="utf-8")

    # Spawn the mission in its own visible console window so it can be watched
    # live, agent by agent, instead of running silently inside this MCP server
    # process. Falls back to the old in-process asyncio task if a window can't
    # be opened (e.g. this MCP server itself is running headless).
    proc = _spawn_mission_window(mission_id, str(brief_path), provider, ollama_model, project_dir)
    if proc is not None:
        _running_missions[mission_id] = proc
        window_note = "Running in its own console window — watch it live there.\n"
    else:
        task = asyncio.create_task(
            _background_mission(
                mission_id, str(brief_path), provider, ollama_model, priority, project_dir
            )
        )
        _running_missions[mission_id] = task
        window_note = "Running in-process (no console window could be opened).\n"

    return (
        window_note +
        f"Mission started: {mission_id}\n"
        f"Output: {out_dir}\n\n"
        f"The mission is running in the background. "
        f"Call mission_status(mission_id=\"{mission_id}\") to check progress. "
        f"Files will appear in the output directory as each phase completes."
    )


async def _background_mission(
    mission_id: str, brief_path: str, provider: str, ollama_model: str, priority: str,
    project_dir: str = "",
) -> None:
    """Run a mission in the background."""
    try:
        await _run_mission_bg(
            mission_id, brief_path, provider, ollama_model, priority, project_dir
        )
    except Exception as exc:
        print(f"[CRESSIDA] Mission {mission_id} failed: {exc}")
        _persist_failure(mission_id, str(exc))
    finally:
        _running_missions.pop(mission_id, None)
        # The brief now lives inside the mission directory as part of its record,
        # so it is deliberately not deleted — it is the mission's provenance.


def _persist_failure(mission_id: str, error: str) -> None:
    """Write a failure execution_state.json so mission_status can report it."""
    path = _mission_path(mission_id) / "execution_state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "mission_id": mission_id,
        "status": "failed",
        "tasks": {},
        "error": error,
        "updated_at": datetime.utcnow().isoformat() + "Z",
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"[CRESSIDA] Persisted failure state for {mission_id}: {path}")


async def _run_mission_bg(
    mission_id: str, brief_path: str, provider: str, ollama_model: str, priority: str,
    project_dir: str = "",
) -> None:
    prev_cwd = os.getcwd()
    # Paths are resolved via cressida.core.paths now, so this chdir is no longer
    # what makes artifacts land correctly — but keep the process anchored at the
    # canonical home rather than one level above the repo, which is where mission
    # output used to end up.
    os.chdir(_missions_root().parent)
    try:
        from cressida.cli.commands import run_mission as _run_mission
        import argparse

        args = argparse.Namespace(
            brief=brief_path,
            mission_id=mission_id,
            provider=provider,
            ollama_model=ollama_model,
            ollama_host="http://localhost:11434",
            priority=priority,
            project_dir=project_dir or None,
        )

        _missions_dir()
        print(f"[CRESSIDA] Starting mission {mission_id} with provider={provider}")
        exit_code = await _run_mission(args)
        status = "completed" if exit_code == 0 else "failed"
        print(f"[CRESSIDA] Mission {mission_id} {status} (exit_code={exit_code}).")

        # Ensure final state is persisted
        state_path = _mission_path(mission_id) / "execution_state.json"
        if not state_path.exists():
            _persist_failure(mission_id, f"Mission ended with exit code {exit_code}")
    except Exception as exc:
        print(f"[CRESSIDA] Mission {mission_id} error in _run_mission_bg: {exc}")
        _persist_failure(mission_id, str(exc))
        raise
    finally:
        os.chdir(prev_cwd)


@mcp.tool()
def mission_progress(mission_id: str) -> str:
    """Get a detailed progress snapshot for a mission: current phase, per-task
    status, escalations, recently-modified files, and whether it looks stalled.

    Unlike mission_status (which only has data once execution_state.json
    exists), this infers a "phase" — Research, Product Definition,
    Architecture, BOND Gate, Planning, Implementation, Testing, Review — from
    which milestone files are actually on disk, so you can see progress during
    the pre-task research/PRD stretch too. Also flags "stalled": true if no
    file in the mission directory has changed in the last 30 minutes while the
    mission is still running.

    Args:
        mission_id: The mission ID returned by run_mission (e.g. MSN-2026-001)

    Returns:
        JSON with phase, task detail, escalations, file activity, and timing.
    """
    from cressida.core.progress import get_mission_progress

    return json.dumps(get_mission_progress(mission_id), indent=2)


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
        # Check if mission directory exists at all
        mpath = _mission_path(mission_id)
        if not mpath.exists():
            return f"Mission {mission_id!r} not found. Available missions:\n" + "\n".join(
                d.name for d in _missions_dir().iterdir()
                if d.is_dir() and d.name not in ("inbox", "scheduled", "processed")
            ) or "(none)"

        # Mission exists but no execution_state.json yet — report what we have
        files = [str(f.relative_to(mpath)) for f in mpath.rglob("*") if f.is_file()]
        return json.dumps({
            "mission_id": mission_id,
            "status": "initializing",
            "message": "Mission is starting up. execution_state.json not yet created.",
            "files_found": len(files),
            "sample_files": files[:10],
        }, indent=2)

    tasks = state.get("tasks", {})
    counts: dict[str, int] = {}
    for t in tasks.values():
        s = t.get("status", "unknown")
        counts[s] = counts.get(s, 0) + 1

    result = {
        "mission_id": mission_id,
        "status": state.get("status", "unknown"),
        "task_counts": counts,
        "total_tasks": len(tasks),
        "tasks": {tid: {"status": t.get("status"), "agent": t.get("agent")} for tid, t in tasks.items()},
        "pending_escalations": escalations,
    }
    if state.get("error"):
        result["error"] = state["error"]
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
def obsidian_store_memory(
    branch: str,
    title: str,
    content: str,
    tags: str = "",
    mission_id: str = "",
    agent: str = "",
) -> str:
    """Store a memory as a subnode under a main branch in your Obsidian vault.

    This is the canonical way to persist CRESSIDA memory into the knowledge
    graph. The note is written under the branch folder and linked from that
    branch's Map-of-Content note, so Obsidian's graph view shows a
    branch → subnode tree.

    Args:
        branch:     Main branch to file under. One of:
                    knowledge | mission | logs | decisions | escalations | postmortems
                    (any other value creates/uses a branch of that name).
        title:      Human-readable title for the subnode (becomes the note name).
        content:    Markdown body of the memory.
        tags:       Comma-separated extra tags (optional).
        mission_id: Owning mission id, if any (optional).
        agent:      Authoring agent, if any (optional).

    Returns:
        Confirmation with the subnode path and the branch it was linked under.
    """
    bridge = _get_bridge()
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    meta = {}
    if mission_id:
        meta["mission_id"] = mission_id
    if agent:
        meta["agent"] = agent
    path = bridge.store_subnode(
        branch=branch,
        title=title,
        content=content,
        tags=tag_list,
        metadata=meta,
    )
    branch_folder = bridge.BRANCHES.get(branch.lower().strip(), branch.strip() or "Misc")
    return f"Stored subnode under [[{branch_folder}]]: {path}"


@mcp.tool()
def learning_playbook(role: str = "", limit: int = 12) -> str:
    """Show CRESSIDA's learned playbooks — the accumulated experience agent R
    distils from past missions and injects into agents' future prompts.

    Args:
        role:  Agent role to show (e.g. BRANCH, TANNER, REVIEW). Leave empty for
               a one-line summary of every role's playbook size.
        limit: Max lessons to show for a specific role.

    Returns:
        The role's top-ranked lessons, or a cross-role summary.
    """
    from cressida.learning.playbook import PlaybookStore

    store = PlaybookStore(_CRESSIDA_PACKAGE / "knowledge" / "playbooks")
    if not role:
        summary = store.summary()
        if not summary:
            return "No playbooks yet — run a mission to start the learning loop."
        return "\n".join(f"{r.upper()}: {n} lesson(s)" for r, n in summary.items())
    rendered = store.render_for_prompt(role, limit=limit)
    return rendered or f"No playbook recorded for {role.upper()} yet."


@mcp.tool()
def learning_nudge() -> str:
    """Return the learning 'nudge' digest — the strongest current lessons across
    all agents plus the reusable skills the framework has synthesised. This is a
    read-only snapshot of how CRESSIDA has improved itself so far.
    """
    from cressida.learning import Curator, PlaybookStore, SkillSynthesizer

    playbooks = PlaybookStore(_CRESSIDA_PACKAGE / "knowledge" / "playbooks")
    skills = SkillSynthesizer(_CRESSIDA_PACKAGE / "knowledge" / "skills")
    return Curator(playbooks=playbooks, skills=skills).nudge()


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

def main() -> None:
    """Console-script entry point (`cressida-mcp`) and `python -m` target."""
    _ensure_monitor_started()
    mcp.run()


if __name__ == "__main__":
    main()
