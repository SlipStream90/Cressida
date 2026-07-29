from __future__ import annotations

"""Detailed, disk-polled mission progress.

Why disk-polling and not the EventBus
--------------------------------------
Cressida's ``EventBus`` (core/events.py) is in-process and per-instance: the
mission coordinator, the MCP server's status monitor, and any CLI process each
construct their own bus, so events published by a running mission are not
visible outside the asyncio task that started it. ``execution_state.json``
(written by ``orchestration/coordinator.py::_persist_state``) plus the mission
directory's own files are the only state actually shared across processes —
this module reads exactly that, the same source ``mission_status`` already
polls, just with milestone-based phase inference and file-activity timestamps
layered on top so a caller can tell *what's happening* and *whether it has
stalled*, not just raw task counts.
"""

import json
import time
from pathlib import Path
from typing import Any

from cressida.core.paths import mission_dir, missions_root

# Ordered milestones: (label, candidate relative paths). The furthest milestone
# whose marker exists on disk is reported as the mission's current phase. Paths
# are checked in both the flat and "intelligence/"-nested layouts seen across
# missions (older missions wrote flat, e.g. mission_20260728_130409; newer ones
# nest research/PRD docs under intelligence/).
_MILESTONES: list[tuple[str, list[str]]] = [
    ("Brief received", ["brief.md"]),
    ("Research", ["intelligence/research_report.md", "research_report.md"]),
    ("Methodology research", ["intelligence/methodology_brief.md"]),
    ("Product definition", ["intelligence/PRD.md", "PRD.md"]),
    ("Architecture", ["ARCHITECTURE.md", "architecture/ARCHITECTURE.md", "architecture"]),
    ("BOND gate", ["bond_checkpoint_verdict.md", "bond_review.md", "bond_decisions"]),
    ("Planning", ["backlog.json", "execution_graph.json", "priority_matrix.md"]),
    ("Implementation", ["implementation"]),
    ("Testing", ["test_suite", "playwright", "coverage_report.md", "regression_tests.md"]),
    ("Review", ["review_report.md", "bond_close_review.md", "bond_final_verdict.md"]),
]

_STALL_THRESHOLD_SECONDS = 1800.0  # matches autonomy.monitor's default


def _marker_exists(mission_path: Path, candidates: list[str]) -> bool:
    for rel in candidates:
        p = mission_path / rel
        if p.is_dir():
            if any(p.rglob("*")):
                return True
        elif p.exists():
            return True
    return False


def _load_execution_state(mission_path: Path) -> dict[str, Any]:
    p = mission_path / "execution_state.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _list_escalations(mission_path: Path) -> list[str]:
    esc_dir = mission_path / "escalations"
    if not esc_dir.exists():
        return []
    return sorted(f.name for f in esc_dir.iterdir() if f.suffix == ".json" and f.stem != "resolution")


def _scan_files(mission_path: Path) -> list[dict[str, Any]]:
    files = []
    for f in mission_path.rglob("*"):
        if not f.is_file():
            continue
        try:
            stat = f.stat()
        except OSError:
            continue
        files.append({
            "path": str(f.relative_to(mission_path)).replace("\\", "/"),
            "size": stat.st_size,
            "modified": stat.st_mtime,
        })
    files.sort(key=lambda f: f["modified"], reverse=True)
    return files


def get_mission_progress(mission_id: str) -> dict[str, Any]:
    """Return a detailed progress snapshot for one mission.

    Combines ``execution_state.json`` (task-level status, when the coordinator
    has written it) with a live directory scan (milestone phase, escalations,
    last-activity time) so progress is visible even before the first task
    completes — the gap plain ``mission_status`` has while a mission is still
    in its pre-task research/PRD phase.
    """
    mission_path = mission_dir(mission_id)
    if not mission_path.exists():
        return {"mission_id": mission_id, "found": False}

    state = _load_execution_state(mission_path)
    tasks_raw = state.get("tasks", {})
    task_counts: dict[str, int] = {}
    tasks: list[dict[str, Any]] = []
    for tid, t in tasks_raw.items():
        status = t.get("status", "unknown")
        task_counts[status] = task_counts.get(status, 0) + 1
        tasks.append({
            "id": tid,
            "status": status,
            "agent": t.get("agent"),
            "name": t.get("name"),
            "error": t.get("error"),
        })

    files = _scan_files(mission_path)
    escalations = _list_escalations(mission_path)

    milestones: list[dict[str, Any]] = []
    phase = "Not started"
    phase_index = 0
    for i, (label, candidates) in enumerate(_MILESTONES, start=1):
        reached = _marker_exists(mission_path, candidates)
        milestones.append({"label": label, "reached": reached})
        if reached:
            phase = label
            phase_index = i

    mission_status = state.get("status", "").lower()
    if mission_status in ("completed", "failed", "cancelled"):
        phase = mission_status.capitalize()
        phase_index = len(_MILESTONES)
    elif escalations:
        phase = f"{phase} — awaiting BOND escalation"

    now = time.time()
    started_at = None
    brief_preview = None
    brief = mission_path / "brief.md"
    if brief.exists():
        started_at = brief.stat().st_mtime
        try:
            text = brief.read_text(encoding="utf-8", errors="replace").strip()
            brief_preview = (text[:220] + "…") if len(text) > 220 else text
        except OSError:
            pass
    last_activity = files[0]["modified"] if files else started_at

    seconds_since_activity = (now - last_activity) if last_activity else None
    stalled = bool(
        seconds_since_activity is not None
        and seconds_since_activity > _STALL_THRESHOLD_SECONDS
        and mission_status not in ("completed", "failed", "cancelled")
    )

    # Best guess at who's actually working right now: the task actively
    # in-progress if the executor recorded one, else whichever pending task
    # is next in dependency order (tasks dicts preserve insertion/exec order).
    current_agent = None
    active = [t for t in tasks if t["status"] in ("in_progress", "IN_PROGRESS", "assigned", "ASSIGNED")]
    if active:
        current_agent = active[0]["agent"]
    else:
        pending = [t for t in tasks if t["status"] in ("pending", "PENDING")]
        if pending and mission_status not in ("completed", "failed", "cancelled"):
            current_agent = pending[0]["agent"]

    failed_tasks = [t for t in tasks if t["status"] in ("failed", "FAILED", "blocked", "BLOCKED") and t.get("error")]

    return {
        "mission_id": mission_id,
        "found": True,
        "status": state.get("status", "initializing" if not state else "unknown"),
        "phase": phase,
        "phase_index": phase_index,
        "phase_total": len(_MILESTONES),
        "milestones": milestones,
        "current_agent": current_agent,
        "brief_preview": brief_preview,
        "task_counts": task_counts,
        "total_tasks": len(tasks_raw),
        "tasks": tasks,
        "failed_tasks": failed_tasks,
        "escalations": escalations,
        "file_count": len(files),
        "recent_files": files[:15],
        "started_at": started_at,
        "last_activity": last_activity,
        "elapsed_seconds": (now - started_at) if started_at else None,
        "seconds_since_activity": seconds_since_activity,
        "stalled": stalled,
        "error": state.get("error"),
    }


def list_mission_ids() -> list[str]:
    mdir = missions_root()
    if not mdir.exists():
        return []
    return sorted(
        (d.name for d in mdir.iterdir()
         if d.is_dir() and d.name not in ("inbox", "scheduled", "processed")),
        reverse=True,
    )


def get_all_mission_progress() -> list[dict[str, Any]]:
    return [get_mission_progress(mid) for mid in list_mission_ids()]
