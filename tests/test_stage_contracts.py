from __future__ import annotations

from cressida.cli.commands import _build_mission_state
from cressida.core.paths import resolve_mission_artifact_path


def test_stage_handoffs_include_required_upstream_artifacts(tmp_path):
    state = _build_mission_state(
        "mission_stage_contracts", "build a web application", target_dir=str(tmp_path)
    )

    reads = {task_id: set(task.metadata.get("reads", [])) for task_id, task in state.tasks.items()}
    assert "missions/mission_stage_contracts/intelligence/research_report.md" in reads["architecture"]
    assert "missions/mission_stage_contracts/intelligence/methodology_brief.md" in reads["planning"]
    assert "missions/mission_stage_contracts/intelligence/Roadmap.md" in reads["planning"]
    assert "missions/mission_stage_contracts/backlog.json" in reads["review"]

    architecture_writes = state.tasks["architecture"].metadata["writes"]
    assert architecture_writes == ["missions/mission_stage_contracts/ARCHITECTURE.md"]


def test_trivial_stage_does_not_require_skipped_methodology_artifact(tmp_path):
    state = _build_mission_state(
        "mission_stage_contracts_trivial", "build a small utility", target_dir=str(tmp_path), trivial=True
    )
    assert "methodology_research" not in state.tasks
    assert all(
        "methodology_brief.md" not in path
        for task in state.tasks.values()
        for path in task.metadata.get("reads", [])
    )


def test_mission_artifacts_follow_relocated_missions_root(tmp_path, monkeypatch):
    missions = tmp_path / "relocated-missions"
    monkeypatch.setenv("CRESSIDA_MISSIONS_DIR", str(missions))
    resolved = resolve_mission_artifact_path(
        "missions/mission_path_test/intelligence/research_report.md",
        "mission_path_test",
    )
    assert resolved == missions / "mission_path_test" / "intelligence" / "research_report.md"
