from __future__ import annotations

from io import BytesIO, StringIO
import importlib.util
from pathlib import Path


_SPEC = importlib.util.spec_from_file_location("cressida_mcp_server", Path(__file__).parents[1] / "mcp_server.py")
assert _SPEC and _SPEC.loader
_MCP = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MCP)


def test_coerce_brief_text_accepts_file_like_and_bytes_inputs():
    assert _MCP._coerce_brief_text(StringIO("# PRD")) == "# PRD"
    assert _MCP._coerce_brief_text(BytesIO(b"# PRD")) == "# PRD"
    assert _MCP._coerce_brief_text("inline brief") == "inline brief"
