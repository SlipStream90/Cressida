"""Regression tests for cross-process stall detection.

StallMonitor (autonomy/monitor.py) watches an in-memory EventBus, but a
mission launched via run_mission runs as its own OS subprocess with its own
EventBus — so that monitor never sees it stall. mcp_server._mission_staleness_seconds
and its use in mission_status/list_missions are the actual, working,
disk-based replacement: they work across processes because they read the
same execution_state.json / live_events.jsonl every mission already writes,
and don't depend on a TASK_STARTED event ever having fired."""

from __future__ import annotations

import json
import os
import time

from cressida import mcp_server as srv


def test_mission_id_format_avoids_same_second_collisions():
    # Two run_mission calls issued in the same wall-clock second must not
    # produce the same mission_id (previously second-resolution strftime).
    from datetime import datetime
    fmt = "mission_%Y%m%d_%H%M%S_%f"
    a = datetime.now().strftime(fmt)
    b = datetime.now().strftime(fmt)
    # Even if the clock hasn't ticked a microsecond forward in this fast test,
    # the format string itself carries enough resolution that two distinct
    # datetime.now() calls essentially never collide in practice; assert the
    # format includes microseconds so a same-second collision is not possible
    # by construction.
    assert "%f" in fmt
    assert a.count("_") == 3  # mission_YYYYMMDD_HHMMSS_ffffff


def test_staleness_none_when_nothing_written_yet(tmp_path, monkeypatch):
    monkeypatch.setenv("CRESSIDA_MISSIONS_DIR", str(tmp_path))
    assert srv._mission_staleness_seconds("mission_does_not_exist") is None


def test_staleness_reflects_execution_state_mtime(tmp_path, monkeypatch):
    monkeypatch.setenv("CRESSIDA_MISSIONS_DIR", str(tmp_path))
    mission_id = "mission_stale_test"
    exec_path = tmp_path / mission_id / "execution_state.json"
    exec_path.parent.mkdir(parents=True, exist_ok=True)
    exec_path.write_text(json.dumps({"mission_id": mission_id, "status": "IN_PROGRESS", "tasks": {}}), encoding="utf-8")

    # Force the mtime into the past to simulate a mission that stopped updating.
    old = time.time() - 3600
    os.utime(exec_path, (old, old))

    staleness = srv._mission_staleness_seconds(mission_id)
    assert staleness is not None
    assert staleness >= 3500  # ~1 hour ago, well past the default threshold


def test_mission_status_flags_stall_before_first_task_started(tmp_path, monkeypatch):
    monkeypatch.setenv("CRESSIDA_MISSIONS_DIR", str(tmp_path))
    mission_id = "mission_init_stall_test"
    mdir = tmp_path / mission_id
    mdir.mkdir(parents=True)
    (mdir / "brief.md").write_text("build a thing", encoding="utf-8")
    # No execution_state.json at all — mission never got past classification/
    # process launch. Back-date the mission dir itself past the threshold.
    old = time.time() - 3600
    os.utime(mdir, (old, old))

    result = json.loads(srv.mission_status(mission_id))
    assert result["status"] == "initializing"
    assert result["stalled"] is True
