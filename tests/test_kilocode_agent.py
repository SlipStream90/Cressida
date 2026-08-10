"""Tests for KiloCodeAgent: provider registration/discovery and
_parse_output's text + tool-event extraction from Kilo's `--format json`
JSONL output shape (step_start / text / tool_use / step_finish / error)."""

from __future__ import annotations

import pytest

from cressida.core.providers.kilocode_agent import KiloCodeAgent


def test_parse_output_extracts_last_text_event():
    lines = [
        '{"type":"step_start","part":{"type":"step-start"}}',
        '{"type":"text","part":{"type":"text","text":"partial"}}',
        '{"type":"text","part":{"type":"text","text":"final answer"}}',
        '{"type":"step_finish","part":{"type":"step-finish","reason":"stop"}}',
    ]
    text, events = KiloCodeAgent._parse_output("\n".join(lines))
    assert text == "final answer"
    assert events == []


def test_parse_output_collects_tool_use_events():
    lines = [
        '{"type":"tool_use","part":{"type":"tool","tool":"bash",'
        '"state":{"status":"completed","input":{"cmd":"ls"},"output":"a\\nb"}}}',
        '{"type":"text","part":{"type":"text","text":"listed files"}}',
    ]
    text, events = KiloCodeAgent._parse_output("\n".join(lines))
    assert text == "listed files"
    assert len(events) == 1
    assert events[0] == {
        "tool": "bash",
        "input": {"cmd": "ls"},
        "output": "a\nb",
        "is_error": False,
    }


def test_parse_output_marks_errored_tool_call():
    lines = [
        '{"type":"tool_use","part":{"type":"tool","tool":"bash",'
        '"state":{"status":"error","input":{"cmd":"badcmd"},"output":"not found"}}}',
    ]
    _, events = KiloCodeAgent._parse_output("\n".join(lines))
    assert events[0]["is_error"] is True


def test_parse_output_raises_on_error_event_with_no_text():
    lines = [
        '{"type":"error","error":{"data":{"message":"boom"}}}',
    ]
    with pytest.raises(RuntimeError, match="boom"):
        KiloCodeAgent._parse_output("\n".join(lines))


def test_parse_output_error_event_ignored_if_text_present():
    lines = [
        '{"type":"text","part":{"type":"text","text":"recovered"}}',
        '{"type":"error","error":{"data":{"message":"minor warning"}}}',
    ]
    text, _ = KiloCodeAgent._parse_output("\n".join(lines))
    assert text == "recovered"


def test_parse_output_empty_stdout():
    text, events = KiloCodeAgent._parse_output("")
    assert text == ""
    assert events == []


def test_parse_output_valid_json_no_text_event_returns_empty_text():
    lines = [
        '{"type":"tool_use","part":{"type":"tool","tool":"bash",'
        '"state":{"status":"completed","input":{},"output":"ok"}}}',
    ]
    text, events = KiloCodeAgent._parse_output("\n".join(lines))
    assert text == ""
    assert len(events) == 1


def test_parse_output_non_json_falls_back_to_raw():
    stdout = "plain text output, not JSONL"
    text, events = KiloCodeAgent._parse_output(stdout)
    assert text == stdout
    assert events == []


def test_kilocode_cli_path_respects_env_override(monkeypatch, tmp_path):
    fake_cli = tmp_path / "kilo"
    fake_cli.write_text("")
    monkeypatch.setenv("CRESSIDA_KILOCODE_CLI", str(fake_cli))
    from cressida.core.providers.kilocode_agent import kilocode_cli_path

    assert kilocode_cli_path() == str(fake_cli)


def test_provider_kilocode_registered_in_auto():
    from cressida.core.providers.auto import PROVIDER_KILOCODE

    assert PROVIDER_KILOCODE == "kilocode"
