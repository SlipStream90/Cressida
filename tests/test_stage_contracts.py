from __future__ import annotations

from cressida.cli.commands import _build_mission_state
from cressida.core.paths import resolve_mission_artifact_path
from cressida.core import AgentRole
from cressida.orchestration.context_builder import ContextBuilder


def test_stage_handoffs_include_required_upstream_artifacts(tmp_path):
    state = _build_mission_state(
        "mission_stage_contracts", "build a web application", target_dir=str(tmp_path)
    )

    reads = {task_id: set(task.metadata.get("reads", [])) for task_id, task in state.tasks.items()}
    assert "missions/mission_stage_contracts/intelligence/research_report.md" in reads["architecture"]
    assert "missions/mission_stage_contracts/backlog.json" in reads["review"]

    # TANNER turns Q's build sheet into a task list, so it reads the sheet and
    # the PRD — not the Roadmap, ARCHITECTURE.md and methodology brief it used
    # to get. Everything it needs from those is carried into BUILD_SPEC.md, and
    # the wider context had it spending 15 minutes planning five tasks for a
    # three-file service.
    assert reads["planning"] == {
        "missions/mission_stage_contracts/architecture/BUILD_SPEC.md",
        "missions/mission_stage_contracts/intelligence/PRD.md",
    }

    architecture_writes = state.tasks["architecture"].metadata["writes"]
    assert architecture_writes == [
        "missions/mission_stage_contracts/ARCHITECTURE.md",
        # The build sheet Q writes for BRANCH — see below for why BRANCH reads
        # this instead of the architecture document itself.
        "missions/mission_stage_contracts/architecture/BUILD_SPEC.md",
    ]

    # BRANCH gets the build sheet, the task list and the PRD — not every
    # document the mission produced. It previously received ARCHITECTURE.md and
    # the methodology brief too, then went looking through the mission tree for
    # the rest; on one live mission that consumed the entire implementation run
    # and it never wrote a file.
    assert reads["implementation"] == {
        "missions/mission_stage_contracts/architecture/BUILD_SPEC.md",
        "missions/mission_stage_contracts/backlog.json",
        "missions/mission_stage_contracts/intelligence/PRD.md",
    }


def test_review_audits_the_build_sheet_branch_implemented_from(tmp_path):
    """REVIEW used to read ARCHITECTURE.md but not BUILD_SPEC.md, while BRANCH
    reads only BUILD_SPEC.md — so "architecture compliance" was scored against
    a document the implementer never opened. Both must be present."""
    state = _build_mission_state(
        "mission_review_reads", "build a web application", target_dir=str(tmp_path)
    )
    review_reads = set(state.tasks["review"].metadata["reads"])
    implementation_reads = set(state.tasks["implementation"].metadata["reads"])

    spec = "missions/mission_review_reads/architecture/BUILD_SPEC.md"
    assert spec in implementation_reads
    assert spec in review_reads, "REVIEW cannot judge compliance against a spec it never reads"
    assert "missions/mission_review_reads/ARCHITECTURE.md" in review_reads


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


def test_context_builder_reads_relocated_upstream_artifact(tmp_path, monkeypatch):
    missions = tmp_path / "relocated-missions"
    monkeypatch.setenv("CRESSIDA_MISSIONS_DIR", str(missions))
    artifact = missions / "mission_context_test" / "intelligence" / "research_report.md"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("# upstream research", encoding="utf-8")

    prompt = ContextBuilder().build_prompt(
        task_id="product_definition",
        agent_role=AgentRole.INTELLIGENCE,
        mission_id="mission_context_test",
        brief="build a thing",
        reads=["missions/mission_context_test/intelligence/research_report.md"],
        task_description="Define the product.",
        writes=["missions/mission_context_test/intelligence/PRD.md"],
        target_dir=tmp_path / "target-project",
    )
    assert "# upstream research" in prompt
    assert "research_report.md" in prompt
    assert "PRD.md" in prompt
