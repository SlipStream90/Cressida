from __future__ import annotations

import importlib.util
from pathlib import Path


_SPEC = importlib.util.spec_from_file_location("cressida_mcp_server", Path(__file__).parents[1] / "mcp_server.py")
assert _SPEC and _SPEC.loader
_MCP = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MCP)
_mission_artifact_path = _MCP._mission_artifact_path


def test_mission_artifact_path_rejects_escape(tmp_path, monkeypatch):
    monkeypatch.setenv("CRESSIDA_MISSIONS_DIR", str(tmp_path))
    (tmp_path / "mission_test").mkdir()

    assert _mission_artifact_path("mission_test", "intelligence/report.md").name == "report.md"
    try:
        _mission_artifact_path("mission_test", "../../outside.md")
    except ValueError:
        pass
    else:
        raise AssertionError("mission artifact path escaped its mission directory")
