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
