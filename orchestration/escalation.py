"""Single implementation of "resolve a BOND escalation" shared by the CLI
(cli/commands.py) and the MCP server (mcp_server.py), which previously had
two copies that both only wrote a sibling ``resolution.json`` file without
touching anything ``Coordinator._check_bond_gate`` (orchestration/coordinator.py)
or the resume path (``cli/commands.py::_rehydrate_from_execution_state``)
actually reads. That meant "resolving" an escalation never unblocked the
mission: the gate re-read the same PENDING escalation file next run, and
even if it hadn't, the BOND task itself stayed COMPLETED so resume would
never re-run it to produce a fresh decision.

This does the two things that actually matter:
  1. Flip every pending ``escalations/*.json`` record's ``status`` off
     PENDING (what the gate's escalation check reads).
  2. Reset any COMPLETED task owned by the BOND role back to PENDING in
     execution_state.json, so the next resume re-runs BOND and lets it
     produce a new decision instead of being skipped as already-done.
Both apply unconditionally (not just for the escalations/*.json path) since
a rejected-decision block (``state.metadata["bond_gate_blocked"]``, no
escalation record at all) needs the same BOND-task reset to become
resumable.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from cressida.core.paths import mission_dir


def resolve_mission_escalation(mission_id: str, decision: str, resolved_by: str) -> dict:
    """Resolve mission_id's escalation(s) and make it resumable. Returns a
    summary dict: {"escalations_resolved": [...], "bond_task_reset": bool}."""
    m_dir = mission_dir(mission_id)
    esc_dir = m_dir / "escalations"
    resolved_names: list[str] = []

    if esc_dir.is_dir():
        for f in sorted(esc_dir.glob("*.json")):
            if f.stem == "resolution":
                continue
            try:
                rec = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if str(rec.get("status", "")).upper() != "PENDING":
                continue
            rec["status"] = "RESOLVED"
            rec["resolution"] = decision
            rec["resolved_at"] = datetime.now(timezone.utc).isoformat()
            rec["resolved_by"] = resolved_by
            f.write_text(json.dumps(rec, indent=2), encoding="utf-8")
            resolved_names.append(f.name)

    # Audit trail, kept for back-compat with anything that already reads it.
    esc_dir.mkdir(parents=True, exist_ok=True)
    (esc_dir / "resolution.json").write_text(json.dumps({
        "resolved_at": datetime.now(timezone.utc).isoformat(),
        "decision": decision,
        "resolved_by": resolved_by,
        "resolved_escalations": resolved_names,
    }, indent=2), encoding="utf-8")

    bond_task_reset = _reset_bond_task(m_dir)

    return {"escalations_resolved": resolved_names, "bond_task_reset": bond_task_reset}


def _reset_bond_task(m_dir: Path) -> bool:
    """Reset any COMPLETED BOND-owned task in execution_state.json back to
    PENDING, and clear the bond_gate_blocked marker, so resume re-runs BOND."""
    path = m_dir / "execution_state.json"
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False

    tasks = payload.get("tasks") or {}
    reset = False
    for task in tasks.values():
        if task.get("agent") == "BOND" and task.get("status") == "COMPLETED":
            task["status"] = "PENDING"
            task["error"] = None
            reset = True

    if not reset:
        return False

    payload.pop("bond_gate_blocked", None)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return True
