"""Regression test for ProviderAgentBase._write_output clobbering real agent
output with the closing chat-text summary.

CLI-backed providers (claude_cli, opencode, codex, kilocode) have real
Write/Edit tools and write their actual deliverable themselves during the
task. `_write_output` used to unconditionally overwrite every path in
task.metadata["writes"] with `content` (just the agent's final chat
message) afterwards -- so a real 60-line PRD.md the agent wrote correctly
got replaced by a 6-line "I verified the artifacts" note, and every
downstream task's `reads` (which point at exactly that path) got the note
instead of the document. Observed for real in
missions/mission_20260810_224212/intelligence/PRD.md vs the real PRD.md
that landed one level up at the mission root.

This test exercises _write_output directly against a concrete subclass
(no CLI, no network) using CRESSIDA_HOME so mission_dir() and
resolve_under_home() agree on the same tree, matching real deployment."""

from __future__ import annotations

import os
import time

import pytest

from cressida.core import AgentRole, Task
from cressida.core.paths import mission_dir
from cressida.core.providers.base import ProviderAgentBase


class _DummyAgent(ProviderAgentBase):
    async def execute(self, state, task, event_bus=None):
        raise NotImplementedError


@pytest.fixture
def agent():
    return _DummyAgent(role=AgentRole.INTELLIGENCE)


def _task_with_writes(writes, started_at):
    return Task(
        id="product_definition", name="product_definition", description="",
        agent=AgentRole.INTELLIGENCE, started_at=started_at,
        metadata={"writes": writes},
    )


def test_does_not_clobber_file_the_agent_already_wrote(tmp_path, monkeypatch, agent):
    monkeypatch.setenv("CRESSIDA_HOME", str(tmp_path))
    mission_id = "mission_reconcile_test"
    from datetime import datetime
    started_at = datetime.now()

    real_path = mission_dir(mission_id) / "intelligence" / "PRD.md"
    real_path.parent.mkdir(parents=True, exist_ok=True)
    real_path.write_text("# Real PRD\n\nFull requirements document.", encoding="utf-8")

    task = _task_with_writes([f"missions/{mission_id}/intelligence/PRD.md"], started_at)
    agent._write_output(mission_id, task, "I verified the artifacts and they look good.")

    assert real_path.read_text(encoding="utf-8") == "# Real PRD\n\nFull requirements document."


def test_relocates_same_named_file_written_to_the_wrong_path(tmp_path, monkeypatch, agent):
    monkeypatch.setenv("CRESSIDA_HOME", str(tmp_path))
    mission_id = "mission_reconcile_relocate_test"
    from datetime import datetime
    started_at = datetime.now()

    # Agent wrote the real content to the mission root instead of intelligence/.
    wrong_path = mission_dir(mission_id) / "PRD.md"
    wrong_path.parent.mkdir(parents=True, exist_ok=True)
    wrong_path.write_text("# Real PRD (wrong location)\n\nFull requirements document.", encoding="utf-8")

    expected_path = mission_dir(mission_id) / "intelligence" / "PRD.md"
    task = _task_with_writes([f"missions/{mission_id}/intelligence/PRD.md"], started_at)
    agent._write_output(mission_id, task, "I verified the artifacts and they look good.")

    assert expected_path.exists()
    assert expected_path.read_text(encoding="utf-8") == wrong_path.read_text(encoding="utf-8")


def test_falls_back_to_chat_text_when_nothing_was_written(tmp_path, monkeypatch, agent):
    monkeypatch.setenv("CRESSIDA_HOME", str(tmp_path))
    mission_id = "mission_reconcile_fallback_test"
    from datetime import datetime
    started_at = datetime.now()

    expected_path = mission_dir(mission_id) / "intelligence" / "PRD.md"
    task = _task_with_writes([f"missions/{mission_id}/intelligence/PRD.md"], started_at)
    agent._write_output(mission_id, task, "narrated content, no tool calls made")

    assert expected_path.read_text(encoding="utf-8") == "narrated content, no tool calls made"


def test_ignores_stale_same_named_file_from_before_this_task(tmp_path, monkeypatch, agent):
    """A same-basename file from a PREVIOUS task run must not be picked up as
    if the current task produced it — only files touched during this run count."""
    monkeypatch.setenv("CRESSIDA_HOME", str(tmp_path))
    mission_id = "mission_reconcile_stale_test"
    from datetime import datetime

    stale_path = mission_dir(mission_id) / "PRD.md"
    stale_path.parent.mkdir(parents=True, exist_ok=True)
    stale_path.write_text("stale content from an earlier task", encoding="utf-8")
    old_time = time.time() - 3600
    os.utime(stale_path, (old_time, old_time))

    started_at = datetime.now()  # this task starts well after the stale write
    expected_path = mission_dir(mission_id) / "intelligence" / "PRD.md"
    task = _task_with_writes([f"missions/{mission_id}/intelligence/PRD.md"], started_at)
    agent._write_output(mission_id, task, "fresh chat text for this run")

    assert expected_path.read_text(encoding="utf-8") == "fresh chat text for this run"
