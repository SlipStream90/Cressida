"""Regression tests for the pinned `trivial` mission-sizing verdict.

`is_trivial_mission` asks M (an LLM) and returns False on *any* failure — no
agent registered, timeout, unparseable reply. It was previously called on every
run, including every resume, so a mission first classified trivial=True could
come back False on resume merely because M timed out that time.

That silently changes the DAG *shape*: `trivial` decides whether
``methodology_research`` exists at all. `_rehydrate_from_execution_state` then
overlays saved statuses onto a differently-shaped DAG — the exact corruption
its own docstring warns about ("the DAG shape must be deterministic for a given
(mission_id, brief, trivial) triple").

Pinning the verdict on first run makes the third element of that triple
durable.
"""

from __future__ import annotations

import json

from cressida.cli.commands import (
    _build_mission_state,
    _load_persisted_trivial,
    _persist_initial_state,
)
from cressida.core.events import EventBus
from cressida.core.paths import mission_dir
from cressida.core.registry import AgentRegistry
from cressida.memory.system import MemorySystem
from cressida.orchestration.coordinator import Coordinator


def test_fresh_mission_has_no_pinned_verdict(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CRESSIDA_MISSIONS_DIR", str(tmp_path))
    assert _load_persisted_trivial("mission_never_run") is None


def test_trivial_changes_dag_shape(tmp_path, monkeypatch) -> None:
    """The premise of the bug: the verdict is not cosmetic, it adds or removes
    a task. If this ever stops being true the pinning below is unnecessary."""
    monkeypatch.setenv("CRESSIDA_MISSIONS_DIR", str(tmp_path))

    lean = _build_mission_state("m_lean", "brief", target_dir=str(tmp_path), trivial=True)
    full = _build_mission_state("m_full", "brief", target_dir=str(tmp_path), trivial=False)

    assert "methodology_research" not in lean.tasks
    assert "methodology_research" in full.tasks


def test_verdict_round_trips_through_initial_state(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CRESSIDA_MISSIONS_DIR", str(tmp_path))

    for verdict in (True, False):
        mission_id = f"mission_pin_{verdict}"
        state = _build_mission_state(
            mission_id, "build a thing", target_dir=str(tmp_path), trivial=verdict
        )
        assert state.metadata["trivial"] is verdict

        _persist_initial_state(state)
        assert _load_persisted_trivial(mission_id) is verdict


def test_coordinator_persist_preserves_verdict(tmp_path, monkeypatch) -> None:
    """The first _persist_state after startup rewrites execution_state.json. If
    it dropped the key, the pin would survive only until the mission started —
    i.e. it would be gone by the time any resume needed it."""
    monkeypatch.setenv("CRESSIDA_MISSIONS_DIR", str(tmp_path))
    mission_id = "mission_pin_survives_persist"

    state = _build_mission_state(
        mission_id, "build a thing", target_dir=str(tmp_path), trivial=True
    )
    _persist_initial_state(state)

    coordinator = Coordinator(AgentRegistry(), EventBus(), MemorySystem())
    coordinator._persist_state(state)

    payload = json.loads((mission_dir(mission_id) / "execution_state.json").read_text(encoding="utf-8"))
    assert payload["trivial"] is True
    assert _load_persisted_trivial(mission_id) is True


def test_corrupt_state_file_falls_back_to_reclassifying(tmp_path, monkeypatch) -> None:
    """A damaged file must not crash the resume — returning None just means
    'ask M again', which is the old behaviour and safe."""
    monkeypatch.setenv("CRESSIDA_MISSIONS_DIR", str(tmp_path))
    mission_id = "mission_corrupt"
    path = mission_dir(mission_id) / "execution_state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")

    assert _load_persisted_trivial(mission_id) is None


def test_missing_key_falls_back_to_reclassifying(tmp_path, monkeypatch) -> None:
    """Missions started before this change have no `trivial` key. They must
    degrade to the old behaviour rather than being read as False."""
    monkeypatch.setenv("CRESSIDA_MISSIONS_DIR", str(tmp_path))
    mission_id = "mission_legacy"
    path = mission_dir(mission_id) / "execution_state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"mission_id": mission_id, "tasks": {}}), encoding="utf-8")

    assert _load_persisted_trivial(mission_id) is None
