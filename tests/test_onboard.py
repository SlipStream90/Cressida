from __future__ import annotations

import importlib.util
from pathlib import Path


_SPEC = importlib.util.spec_from_file_location("cressida_onboard", Path(__file__).parents[1] / "onboard.py")
assert _SPEC and _SPEC.loader
_ONBOARD = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_ONBOARD)
_read_jsonc = _ONBOARD._read_jsonc


def test_read_jsonc_accepts_comments_trailing_commas_and_string_slashes(tmp_path):
    path = tmp_path / "kilo.jsonc"
    path.write_text(
        '{\n'
        '  // keep this user comment valid input\n'
        '  "url": "https://example.test/a//b",\n'
        '  "nested": [1, 2,], /* trailing comma */\n'
        '}\n',
        encoding="utf-8",
    )

    assert _read_jsonc(path) == {
        "url": "https://example.test/a//b",
        "nested": [1, 2],
    }
