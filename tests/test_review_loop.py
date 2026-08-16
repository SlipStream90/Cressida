from __future__ import annotations

import asyncio

from cressida.cli.commands import _run_review_loop
from cressida.core import AgentRole, MissionState, MissionStatus, Task, TaskStatus
from cressida.core.events import EventBus
from cressida.core.registry import AgentRegistry
from cressida.memory.system import MemorySystem


def _completed_review_state(mission_id: str) -> MissionState:
    state = MissionState(mission_id=mission_id, brief="build a thing", status=MissionStatus.COMPLETED)
    state.add_task(Task(
        id="review",
        name="Code review",
        description="Review the target project",
        agent=AgentRole.REVIEW,
        status=TaskStatus.COMPLETED,
    ))
    return state


def test_review_loop_blocks_unparseable_verdict(tmp_path, monkeypatch):
    monkeypatch.setenv("CRESSIDA_MISSIONS_DIR", str(tmp_path / "missions"))
    mission_id = "mission_review_unknown"
    report = tmp_path / "missions" / mission_id / "review_report.md"
    report.parent.mkdir(parents=True)
    report.write_text("Review finished, see notes.", encoding="utf-8")

    result = asyncio.run(_run_review_loop(
        _completed_review_state(mission_id), mission_id, AgentRegistry(),
        MemorySystem(), EventBus(), str(tmp_path),
    ))

    assert result.status == MissionStatus.FAILED
    assert "parseable review verdict" in result.metadata["review_loop_blocked"]


def test_review_loop_blocks_after_round_cap(tmp_path, monkeypatch):
    monkeypatch.setenv("CRESSIDA_MISSIONS_DIR", str(tmp_path / "missions"))
    monkeypatch.setenv("CRESSIDA_MAX_REVIEW_ROUNDS", "0")
    mission_id = "mission_review_exhausted"
    report = tmp_path / "missions" / mission_id / "review_report.md"
    report.parent.mkdir(parents=True)
    report.write_text(
        "RECOMMENDATION: NEEDS_FIXES\n\n## Outstanding Items\n- Fix the failing test\n",
        encoding="utf-8",
    )

    result = asyncio.run(_run_review_loop(
        _completed_review_state(mission_id), mission_id, AgentRegistry(),
        MemorySystem(), EventBus(), str(tmp_path),
    ))

    assert result.status == MissionStatus.FAILED
    assert result.metadata["review_loop_exhausted"] is True
