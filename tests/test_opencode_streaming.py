"""Tests for OpenCodeAgent._parse_output's tool-event extraction.

The hard requirement (per the observability "must not affect functionality"
constraint): _parse_output's returned text must be identical to what it
returned before tool-event collection was added — only the second tuple
element (tool_events) is new."""

from __future__ import annotations

from cressida.core.providers.opencode_agent import OpenCodeAgent


def test_parse_output_returns_text_and_empty_events_for_plain_message():
    stdout = '{"type":"message","content":[{"type":"text","text":"hello"}]}'
    text, events = OpenCodeAgent._parse_output(stdout)
    assert text == "hello"
    assert events == []


def test_parse_output_collects_tool_use_and_matching_result():
    lines = [
        '{"type":"tool_use","id":"t1","name":"bash","input":{"cmd":"ls"}}',
        '{"type":"tool_result","id":"t1","output":"file1\\nfile2"}',
        '{"type":"message","content":[{"type":"text","text":"Done listing files"}]}',
    ]
    text, events = OpenCodeAgent._parse_output("\n".join(lines))
    assert text == "Done listing files"
    assert len(events) == 1
    assert events[0]["tool"] == "bash"
    assert events[0]["input"] == {"cmd": "ls"}
    assert events[0]["output"] == "file1\nfile2"
    assert events[0]["is_error"] is False


def test_parse_output_marks_errored_tool_result():
    lines = [
        '{"type":"tool_use","id":"t1","name":"bash","input":{"cmd":"badcmd"}}',
        '{"type":"tool_result","id":"t1","output":"command not found","is_error":true}',
    ]
    text, events = OpenCodeAgent._parse_output("\n".join(lines))
    assert events[0]["is_error"] is True


def test_parse_output_accepts_kilo_nested_tool_shape():
    lines = [
        '{"type":"tool_use","part":{"type":"tool","tool":"bash",'
        '"state":{"status":"completed","input":{"cmd":"pwd"},"output":"C:\\\\repo"}}}',
        '{"type":"text","part":{"type":"text","text":"finished"}}',
    ]
    text, events = OpenCodeAgent._parse_output("\n".join(lines))
    assert text == "finished"
    assert events[0]["tool"] == "bash"
    assert events[0]["input"] == {"cmd": "pwd"}
    assert events[0]["output"] == "C:\\repo"


def test_parse_output_handles_tool_result_without_matching_call():
    stdout = '{"type":"tool_result","id":"unknown","output":"orphaned"}'
    text, events = OpenCodeAgent._parse_output(stdout)
    assert len(events) == 1
    assert events[0]["output"] == "orphaned"


def test_parse_output_empty_stdout_returns_empty_text_and_events():
    text, events = OpenCodeAgent._parse_output("")
    assert text == ""
    assert events == []


def test_parse_output_plain_text_fallback_unaffected_by_event_collection():
    # Non-JSON lines feed last_content line-by-line (pre-existing behavior,
    # unrelated to tool-event collection) — the last line wins.
    stdout = "# Some markdown result\nwith no JSON at all"
    text, events = OpenCodeAgent._parse_output(stdout)
    assert text == "with no JSON at all"
    assert events == []
