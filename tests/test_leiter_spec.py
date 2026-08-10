"""LEITER's spec used to instruct it to fetch via 'headless Firefox' — a tool
that was never actually granted (LEITER's real floor is WebSearch/WebFetch/
Bash; see core/tools/definitions.py's LEITER entry and
core/providers/claude_cli_agent.py's _ALLOWED_TOOLS). Following that
instruction meant LEITER would try to shell out to a real Firefox process via
Bash, which is the leading suspect for LEITER's disproportionate mission
failures / the unrooted 4294967295 exit code. Guard against it coming back."""

from pathlib import Path

_LEITER_SPEC = Path(__file__).parent.parent / "agents" / "leiter.md"


def test_leiter_spec_does_not_prescribe_a_browser_binary():
    text = _LEITER_SPEC.read_text(encoding="utf-8").lower()
    assert "headless firefox" not in text
    assert "firefox --headless" in text  # only allowed as a named "don't do this"
