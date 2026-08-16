"""Guards for the untrusted inputs that reach path joins and status parsing.

mission_id arrives from the model (MCP tools) and over HTTP (the dashboard's
/api/missions/<id>); vault paths and mission-relative filenames arrive from
MCP tool arguments. All of them were joined onto a base directory unchecked,
so "../../.." resolved outside the tree.
"""

from __future__ import annotations

import json

import pytest

import cressida.mcp_server as mcp_server
from cressida.core.paths import InvalidMissionIdError, mission_dir
from cressida.core.progress import get_mission_progress
from cressida.core.tools.implementations import execute_tool
from cressida.obsidian.bridge import ObsidianBridge


@pytest.mark.parametrize("bad", ["../..", "a/b", "a\\b", "..", "", "   ", "~", "C:evil"])
def test_mission_dir_rejects_ids_that_escape_the_missions_tree(bad):
    with pytest.raises(InvalidMissionIdError):
        mission_dir(bad)


def test_mission_dir_accepts_a_normal_id(tmp_path, monkeypatch):
    monkeypatch.setenv("CRESSIDA_MISSIONS_DIR", str(tmp_path))
    assert mission_dir("mission_20260101_000000_000001").parent == tmp_path


def test_progress_reports_not_found_instead_of_raising(tmp_path, monkeypatch):
    # The dashboard serves this over HTTP — a rejected id must be JSON, not a 500.
    monkeypatch.setenv("CRESSIDA_MISSIONS_DIR", str(tmp_path))
    assert get_mission_progress("../../..") == {"mission_id": "../../..", "found": False}


def test_mcp_mission_file_refuses_to_escape(tmp_path, monkeypatch):
    monkeypatch.setenv("CRESSIDA_MISSIONS_DIR", str(tmp_path))
    mdir = tmp_path / "m1"
    (mdir / "intelligence").mkdir(parents=True)
    (mdir / "intelligence" / "PRD.md").write_text("real", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("not yours", encoding="utf-8")

    assert mcp_server._mission_file("m1", "intelligence/PRD.md").read_text(encoding="utf-8") == "real"
    with pytest.raises(ValueError):
        mcp_server._mission_file("m1", "../secret.txt")
    with pytest.raises(ValueError):
        mcp_server._mission_path("../..")


def test_vault_path_refuses_to_escape(tmp_path):
    bridge = ObsidianBridge(vault_path=str(tmp_path))
    assert bridge.vault_path("Notes/idea.md").parent == (tmp_path / "Notes")
    for bad in ("../escape.md", "sub/../../out.md"):
        with pytest.raises(ValueError):
            bridge.vault_path(bad)


def test_list_missions_reports_real_status_not_unknown(tmp_path, monkeypatch):
    # Statuses serialize UPPERCASE; the summary used to compare against
    # lowercase literals, so every mission came back "unknown".
    monkeypatch.setenv("CRESSIDA_MISSIONS_DIR", str(tmp_path))
    (tmp_path / "m_done").mkdir()
    (tmp_path / "m_done" / "execution_state.json").write_text(json.dumps({
        "mission_id": "m_done",
        "status": "COMPLETED",
        "tasks": {"research": {"status": "COMPLETED"}, "review": {"status": "COMPLETED"}},
    }), encoding="utf-8")
    (tmp_path / "m_bad").mkdir()
    (tmp_path / "m_bad" / "execution_state.json").write_text(json.dumps({
        "mission_id": "m_bad",
        "status": "FAILED",
        "tasks": {"research": {"status": "COMPLETED"}, "review": {"status": "FAILED"}},
    }), encoding="utf-8")

    by_id = {m["id"]: m["status"] for m in json.loads(mcp_server.list_missions())}
    assert by_id["m_done"] == "completed"
    assert by_id["m_bad"] == "failed"


def test_bad_tool_arguments_come_back_as_a_result_not_an_exception():
    # One malformed tool call from the model used to raise out of the agentic
    # loop and fail the whole task.
    out = execute_tool("read_file", {"nonexistent_kwarg": 1}, mission_id="m1")
    assert out.startswith("ERROR calling tool 'read_file'")
    assert execute_tool("no_such_tool", {}, mission_id="m1").startswith("Unknown tool")


def test_new_mission_id_is_readable_sortable_and_unique(tmp_path, monkeypatch):
    monkeypatch.setenv("CRESSIDA_MISSIONS_DIR", str(tmp_path))
    from cressida.core.paths import new_mission_id

    brief = "Build the QueueLLM frontend Phase 1-2 implementation."
    first = new_mission_id(brief)
    second = new_mission_id(brief)

    assert first == "20260816-queuellm-frontend-phase-01".replace(
        "20260816", first.split("-")[0]
    )
    assert second.endswith("-02"), second      # same brief, same day, next slot
    assert first != second                     # reserved by mkdir, not by clock
    assert (tmp_path / first).is_dir()
    assert sorted([second, first]) == [first, second]  # ids sort chronologically

    # A stopword-only brief still yields a usable id rather than an empty slug.
    assert new_mission_id("build the app").split("-")[1] != ""
    assert new_mission_id("").split("-")[1] == "mission"


def test_new_mission_id_truncates_on_word_boundaries(tmp_path, monkeypatch):
    monkeypatch.setenv("CRESSIDA_MISSIONS_DIR", str(tmp_path))
    from cressida.core.paths import _slugify_brief

    slug = _slugify_brief("Build the QueueLLM frontend Phase 1-2 implementation now")
    assert "-" in slug and len(slug) <= 28
    assert not slug.endswith("-")
    assert all(w in ("queuellm", "frontend", "phase", "implementation", "now")
               for w in slug.split("-")), slug


def test_invoker_binds_an_auto_mission_to_the_calling_cli(monkeypatch):
    """Running Cressida from a CLI should run the mission on that CLI."""
    from cressida.core.providers.auto import provider_for_invoker

    monkeypatch.delenv("CRESSIDA_INVOKER", raising=False)
    assert provider_for_invoker("auto", "opencode") == "opencode"
    assert provider_for_invoker("auto", "claude") == "claude_cli"
    assert provider_for_invoker("auto", "Kilo-Code") == "kilocode"
    assert provider_for_invoker("auto", "codex") == "codex"

    # An explicit provider always wins over the invoker.
    assert provider_for_invoker("gemini", "opencode") == "gemini"

    # Unknown or absent invoker leaves detection in charge.
    assert provider_for_invoker("auto", "some-editor") == "auto"
    assert provider_for_invoker("auto", "") == "auto"

    # Env var is the fallback for anything launched from a shell.
    monkeypatch.setenv("CRESSIDA_INVOKER", "opencode")
    assert provider_for_invoker("auto", "") == "opencode"
    assert provider_for_invoker("auto", "codex") == "codex"  # argument beats env


def test_write_guard_ignores_the_summary_it_writes_itself(tmp_path, monkeypatch):
    """The BRANCH file-write check must not count the agent's own summary.

    ProviderAgentBase._write_output persists the closing chat message to the
    task's declared outputs *before* the executor asks "did this agent write
    anything?". Counting that file made the guard validate its own side
    effect, so it could never fail — and the failure it exists to catch went
    through it: on a live mission BRANCH shipped no source code, the mission
    was marked COMPLETED, and REVIEW scored the delivery 2.0/10.
    """
    from datetime import datetime, timedelta

    from cressida.core.types import AgentRole, Task
    from cressida.core.providers.base import declared_write_targets
    from cressida.orchestration.executor import _wrote_files_since

    monkeypatch.setenv("CRESSIDA_MISSIONS_DIR", str(tmp_path / "missions"))
    mission_id = "m_guard"
    project = tmp_path / "project"
    project.mkdir()

    task = Task(
        id="implementation", name="Implementation", description="",
        agent=AgentRole.BRANCH,
        metadata={"writes": [f"missions/{mission_id}/implementation/"]},
    )
    started = datetime.now()
    task.started_at = started

    targets = declared_write_targets(mission_id, task)
    assert targets, "task declares outputs"
    for t in targets:                      # what _write_output would persist
        t.parent.mkdir(parents=True, exist_ok=True)
        t.write_text("Let me check the environment.", encoding="utf-8")

    # Only the agent's own summary exists -> the agent produced nothing.
    assert _wrote_files_since(mission_id, started, project, ignore=targets) is False
    # Without the exclusion the guard passes on its own side effect.
    assert _wrote_files_since(mission_id, started, project) is True

    # Real code in the target project -> the guard passes.
    (project / "main.py").write_text("app = 1\n", encoding="utf-8")
    assert _wrote_files_since(mission_id, started, project, ignore=targets) is True


def test_write_guard_still_fails_a_stale_task(tmp_path, monkeypatch):
    from datetime import datetime, timedelta

    monkeypatch.setenv("CRESSIDA_MISSIONS_DIR", str(tmp_path / "missions"))
    from cressida.orchestration.executor import _wrote_files_since

    (tmp_path / "missions" / "m_old").mkdir(parents=True)
    (tmp_path / "missions" / "m_old" / "old.md").write_text("x", encoding="utf-8")
    future = datetime.now() + timedelta(hours=1)
    assert _wrote_files_since("m_old", future) is False
