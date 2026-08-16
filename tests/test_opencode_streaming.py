"""Tests for the shared OpenCode/Kilo JSONL parser.

Every payload in this stream hangs off `part` — the fixtures below are the
shapes a live `opencode run --format json` actually emits (captured from
opencode locally; Kilo's CLI is a fork and emits the same schema, which is
why both providers share one parser).

The regression these guard: an earlier parser read `name`/`input`/`content`
off the top level, found nothing, and fell through to returning the *raw
JSONL stream* as the agent's answer — which then got written verbatim into
the task's declared output files as if it were a real document.
"""

from __future__ import annotations

import pytest

from cressida.core.providers.kilocode_agent import KiloCodeAgent
from cressida.core.providers.opencode_agent import OpenCodeAgent, parse_jsonl_stream


def test_parse_output_returns_last_text_event():
    lines = [
        '{"type":"step_start","part":{"id":"p1"}}',
        '{"type":"text","part":{"text":"first pass"}}',
        '{"type":"text","part":{"text":"hello"}}',
        '{"type":"step_finish","part":{"reason":"stop"}}',
    ]
    text, events = OpenCodeAgent._parse_output("\n".join(lines))
    assert text == "hello"
    assert events == []


def test_parse_output_collects_tool_use_with_input_and_output():
    lines = [
        '{"type":"tool_use","part":{"tool":"bash","callID":"c1","state":'
        '{"status":"completed","input":{"command":"ls"},"output":"file1\\nfile2"}}}',
        '{"type":"text","part":{"text":"Done listing files"}}',
    ]
    text, events = OpenCodeAgent._parse_output("\n".join(lines))
    assert text == "Done listing files"
    assert len(events) == 1
    assert events[0]["tool"] == "bash"
    assert events[0]["input"] == {"command": "ls"}
    assert events[0]["output"] == "file1\nfile2"
    assert events[0]["is_error"] is False


def test_parse_output_marks_errored_tool_state():
    stdout = (
        '{"type":"tool_use","part":{"tool":"bash","state":'
        '{"status":"error","input":{"command":"badcmd"},"output":"command not found"}}}'
    )
    _, events = OpenCodeAgent._parse_output(stdout)
    assert events[0]["is_error"] is True


def test_tool_only_run_returns_empty_text_not_the_raw_stream():
    # No text event at all. Returning "" is the point: the caller writes this
    # into the task's declared output files, and a JSONL blob there reads as
    # a real document to every downstream agent.
    stdout = (
        '{"type":"step_start","part":{"id":"p1"}}\n'
        '{"type":"tool_use","part":{"tool":"read","state":{"status":"completed"}}}'
    )
    text, events = OpenCodeAgent._parse_output(stdout)
    assert text == ""
    assert len(events) == 1


def test_error_event_without_text_raises():
    stdout = '{"type":"error","error":{"data":{"message":"model unavailable"}}}'
    with pytest.raises(RuntimeError, match="model unavailable"):
        OpenCodeAgent._parse_output(stdout)


def test_error_event_names_the_calling_cli():
    stdout = '{"type":"error","error":{"data":{"message":"boom"}}}'
    with pytest.raises(RuntimeError, match="Kilo Code CLI"):
        KiloCodeAgent._parse_output(stdout)
    with pytest.raises(RuntimeError, match="OpenCode CLI"):
        OpenCodeAgent._parse_output(stdout)


def test_parse_output_empty_stdout_returns_empty_text_and_events():
    text, events = OpenCodeAgent._parse_output("")
    assert text == ""
    assert events == []


def test_plain_text_output_is_returned_whole():
    # Not JSON at all (e.g. --format ignored) — return everything rather than
    # silently keeping only the last line.
    stdout = "# Some markdown result\nwith no JSON at all"
    text, events = OpenCodeAgent._parse_output(stdout)
    assert text == stdout
    assert events == []


def test_both_providers_share_one_parser():
    stdout = '{"type":"text","part":{"text":"same"}}'
    assert OpenCodeAgent._parse_output(stdout) == KiloCodeAgent._parse_output(stdout)
    assert parse_jsonl_stream(stdout, "X") == ("same", [])
