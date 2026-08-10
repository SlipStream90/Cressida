"""Regression tests for orchestration/escalation.py::resolve_mission_escalation.

Covers the two bugs it fixes: resolve_escalation used to only write a sibling
resolution.json, never touching (1) the escalations/*.json PENDING record
_check_bond_gate actually reads, or (2) the COMPLETED BOND task in
execution_state.json that must go back to PENDING for a resume to re-run it."""

from __future__ import annotations

import json

from cressida.orchestration.escalation import resolve_mission_escalation


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_resolve_flips_pending_escalation_status(tmp_path, monkeypatch):
    monkeypatch.setenv("CRESSIDA_MISSIONS_DIR", str(tmp_path))
    mission_id = "mission_esc_test"
    esc_path = tmp_path / mission_id / "escalations" / "arch_choice.json"
    _write_json(esc_path, {"status": "PENDING", "issue": "which db?"})

    result = resolve_mission_escalation(mission_id, "use postgres", resolved_by="test")

    assert result["escalations_resolved"] == ["arch_choice.json"]
    updated = json.loads(esc_path.read_text(encoding="utf-8"))
    assert updated["status"] == "RESOLVED"
    assert updated["resolution"] == "use postgres"


def test_resolve_resets_completed_bond_task_to_pending(tmp_path, monkeypatch):
    monkeypatch.setenv("CRESSIDA_MISSIONS_DIR", str(tmp_path))
    mission_id = "mission_bond_block_test"
    exec_path = tmp_path / mission_id / "execution_state.json"
    _write_json(exec_path, {
        "mission_id": mission_id,
        "status": "ESCALATED",
        "bond_gate_blocked": "BOND's latest decision is REJECTED",
        "tasks": {
            "research": {"status": "COMPLETED", "agent": "INTELLIGENCE", "name": "research", "error": None},
            "bond_approve_plan": {"status": "COMPLETED", "agent": "BOND", "name": "bond_approve_plan", "error": None},
            "planning": {"status": "PENDING", "agent": "M", "name": "planning", "error": None},
        },
    })

    result = resolve_mission_escalation(mission_id, "approved, proceed", resolved_by="test")

    assert result["bond_task_reset"] is True
    updated = json.loads(exec_path.read_text(encoding="utf-8"))
    assert updated["tasks"]["bond_approve_plan"]["status"] == "PENDING"
    assert updated["tasks"]["research"]["status"] == "COMPLETED"  # untouched
    assert "bond_gate_blocked" not in updated


def test_resolve_is_noop_safe_with_no_state_at_all(tmp_path, monkeypatch):
    monkeypatch.setenv("CRESSIDA_MISSIONS_DIR", str(tmp_path))
    result = resolve_mission_escalation("mission_never_existed", "whatever", resolved_by="test")
    assert result == {"escalations_resolved": [], "bond_task_reset": False}
