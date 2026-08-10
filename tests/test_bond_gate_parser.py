"""Regression tests for Coordinator._parse_bond_decision_file and the JSON-
over-markdown preference in _check_bond_gate.

Covers the two real phrasings BOND has been observed writing (see
missions/mission_20260729_194951 and mission_20260810_073356), plus the
mtime-race scenario that the JSON-preference fix specifically targets."""

from __future__ import annotations

import json
import os

import pytest

from cressida.orchestration.coordinator import Coordinator


# ── _parse_bond_decision_file ────────────────────────────────────────────────

def test_parse_markdown_rejected_phrasing(tmp_path):
    p = tmp_path / "bond_approve_plan.md"
    p.write_text("Some preamble.\n\n**Decision: rejected.**\n\nBecause reasons.", encoding="utf-8")
    record = Coordinator._parse_bond_decision_file(p)
    assert record["decision"] == "REJECTED"


def test_parse_markdown_approved_recorded_phrasing(tmp_path):
    p = tmp_path / "bond_approve_plan.md"
    p.write_text(
        "## BOND review\n\nDecision recorded: **APPROVED**\n\nRationale: looks fine.",
        encoding="utf-8",
    )
    record = Coordinator._parse_bond_decision_file(p)
    assert record["decision"] == "APPROVED"


def test_parse_json_decision(tmp_path):
    p = tmp_path / "approve_plan.json"
    p.write_text(json.dumps({"decision": "approved", "reason": "ok", "approved_mcp_tools": ["x"]}), encoding="utf-8")
    record = Coordinator._parse_bond_decision_file(p)
    assert record["decision"] == "APPROVED"
    assert record["approved_mcp_tools"] == ["x"]


def test_parse_empty_markdown_yields_no_decision(tmp_path):
    """An empty/garbage decision file must never parse as approved."""
    p = tmp_path / "bond_approve_plan.md"
    p.write_text("", encoding="utf-8")
    record = Coordinator._parse_bond_decision_file(p)
    assert record["decision"] != "APPROVED"


# ── _check_bond_gate: JSON-over-mtime preference ────────────────────────────

class _FakeState:
    def __init__(self, mission_id: str):
        self.mission_id = mission_id
        self.metadata: dict = {}


@pytest.fixture
def coordinator(monkeypatch, tmp_path):
    monkeypatch.setenv("CRESSIDA_MISSIONS_DIR", str(tmp_path))
    # Coordinator's __init__ touches the learning layer (playbooks dir under
    # cressida_home()); that's real disk under the actual install and fine to
    # exercise as-is here, no mocking needed for what these tests check.
    from cressida.core.events import EventBus
    from cressida.core.registry import AgentRegistry
    from cressida.memory.system import MemorySystem

    return Coordinator(AgentRegistry(), EventBus(), MemorySystem())


def test_bond_gate_prefers_json_even_when_markdown_is_newer(coordinator, tmp_path):
    """The exact race this fix targets: BOND's own markdown write lands with a
    later mtime than its JSON write, but the JSON is the structured, trustworthy
    artifact and must win regardless of mtime ordering."""
    mission_id = "mission_test_bondgate"
    decisions_dir = tmp_path / mission_id / "bond_decisions"
    decisions_dir.mkdir(parents=True)

    json_path = decisions_dir / "approve_plan.json"
    json_path.write_text(json.dumps({"decision": "approved", "reason": "ok"}), encoding="utf-8")

    md_path = decisions_dir / "bond_approve_plan.md"
    md_path.write_text("**Decision: rejected.**", encoding="utf-8")

    # Force the markdown file to look newer than the JSON file.
    json_stat = json_path.stat()
    newer = json_stat.st_mtime + 10
    os.utime(md_path, (newer, newer))

    state = _FakeState(mission_id)
    approved, detail = coordinator._check_bond_gate(state)
    assert approved is True, detail


def test_bond_gate_falls_back_to_markdown_when_no_json(coordinator, tmp_path):
    mission_id = "mission_test_bondgate_md_only"
    decisions_dir = tmp_path / mission_id / "bond_decisions"
    decisions_dir.mkdir(parents=True)
    (decisions_dir / "bond_approve_plan.md").write_text(
        "Decision recorded: **APPROVED**", encoding="utf-8"
    )

    state = _FakeState(mission_id)
    approved, detail = coordinator._check_bond_gate(state)
    assert approved is True, detail


def test_bond_gate_blocks_on_empty_decisions_dir(coordinator, tmp_path):
    mission_id = "mission_test_bondgate_empty"
    (tmp_path / mission_id / "bond_decisions").mkdir(parents=True)

    state = _FakeState(mission_id)
    approved, _detail = coordinator._check_bond_gate(state)
    assert approved is False
