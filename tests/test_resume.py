"""Regression test for cli/commands.py::_rehydrate_from_execution_state — the
mission-resume overlay described in CRESSIDA_ROBUSTNESS_AND_RETRIEVAL_PLAN.md
§3.1. Builds a fresh DAG, marks a subset COMPLETED on disk (as
Coordinator._persist_state does mid-mission), then confirms rehydration
leaves exactly those tasks COMPLETED and everything else PENDING so the
scheduler only re-runs what didn't finish."""

from __future__ import annotations

import json

from cressida.cli.commands import _build_mission_state, _rehydrate_from_execution_state
from cressida.core import TaskStatus


def test_rehydrate_marks_only_previously_completed_tasks(tmp_path, monkeypatch):
    monkeypatch.setenv("CRESSIDA_MISSIONS_DIR", str(tmp_path))
    mission_id = "mission_test_resume"

    state = _build_mission_state(mission_id, "build a thing", target_dir=str(tmp_path))
    all_task_ids = set(state.tasks)
    assert {"research", "methodology_research", "product_definition"} <= all_task_ids

    completed_ids = {"research", "methodology_research"}
    tasks_data = {
        tid: {"status": "COMPLETED" if tid in completed_ids else "PENDING", "agent": None, "name": tid, "error": None}
        for tid in all_task_ids
    }
    exec_state_path = tmp_path / mission_id / "execution_state.json"
    exec_state_path.parent.mkdir(parents=True, exist_ok=True)
    exec_state_path.write_text(
        json.dumps({"mission_id": mission_id, "status": "IN_PROGRESS", "tasks": tasks_data}), encoding="utf-8"
    )

    # Rebuild a second, independent fresh DAG (as a real resume invocation
    # does) and rehydrate it — proves the overlay works against a brand new
    # object graph, not just the one execution_state.json happened to be
    # derived from in this test.
    fresh_state = _build_mission_state(mission_id, "build a thing", target_dir=str(tmp_path))
    resumed = _rehydrate_from_execution_state(fresh_state, mission_id)

    assert resumed is True
    for tid in completed_ids:
        assert fresh_state.tasks[tid].status == TaskStatus.COMPLETED
    for tid in all_task_ids - completed_ids:
        assert fresh_state.tasks[tid].status == TaskStatus.PENDING


def test_rehydrate_leaves_failed_tasks_pending_for_retry(tmp_path, monkeypatch):
    monkeypatch.setenv("CRESSIDA_MISSIONS_DIR", str(tmp_path))
    mission_id = "mission_test_resume_failed"

    state = _build_mission_state(mission_id, "build a thing", target_dir=str(tmp_path))
    tasks_data = {tid: {"status": "FAILED", "agent": None, "name": tid, "error": "boom"} for tid in state.tasks}
    exec_state_path = tmp_path / mission_id / "execution_state.json"
    exec_state_path.parent.mkdir(parents=True, exist_ok=True)
    exec_state_path.write_text(json.dumps({"mission_id": mission_id, "tasks": tasks_data}), encoding="utf-8")

    fresh_state = _build_mission_state(mission_id, "build a thing", target_dir=str(tmp_path))
    _rehydrate_from_execution_state(fresh_state, mission_id)

    for task in fresh_state.tasks.values():
        assert task.status == TaskStatus.PENDING


def test_rehydrate_no_op_when_no_execution_state(tmp_path, monkeypatch):
    monkeypatch.setenv("CRESSIDA_MISSIONS_DIR", str(tmp_path))
    state = _build_mission_state("mission_never_run", "build a thing", target_dir=str(tmp_path))
    assert _rehydrate_from_execution_state(state, "mission_never_run") is False
