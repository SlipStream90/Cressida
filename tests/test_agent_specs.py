"""Guards on the agent specs themselves.

Specs are injected verbatim into every agent prompt (see
orchestration/context_builder.py::_read_agent_spec) and nothing parses them,
so a spec can rot silently — it stays "valid" no matter what it says. Both
guards here cover mistakes that actually shipped:

  * ARGUS and GREENWAY were merged away (knowledge/decisions.md) but four
    specs kept routing escalations to them for months. BRANCH was telling
    itself to escalate security findings to an agent that does not exist.
  * A spec file with no matching AgentRole is never loaded by anything, so
    it looks like a live part of the system while being inert.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from cressida.core import AgentRole

_AGENTS_DIR = Path(__file__).parent.parent / "agents"
_LIVE_ROLES = {r.value for r in AgentRole}

# Roles that existed in earlier rosters and were merged into the current ones.
# A spec naming any of these is routing work into a void.
_RETIRED_ROLES = ("ARGUS", "GREENWAY", "SENTINEL")

_SPEC_FILES = sorted(p for p in _AGENTS_DIR.glob("*.md") if p.stem.upper() in _LIVE_ROLES)


def test_every_live_role_has_a_spec():
    """Roles are registered from the enum (core/agent_factory.py), so a role
    without a spec file silently runs on the constitution alone."""
    missing = {r for r in _LIVE_ROLES if not (_AGENTS_DIR / f"{r.lower()}.md").exists()}
    assert not missing, f"AgentRole members with no spec file: {sorted(missing)}"


@pytest.mark.parametrize("spec", _SPEC_FILES, ids=lambda p: p.name)
def test_spec_does_not_route_to_a_retired_agent(spec: Path):
    text = spec.read_text(encoding="utf-8")
    found = [r for r in _RETIRED_ROLES if re.search(rf"\b{r}\b", text)]
    assert not found, (
        f"{spec.name} references retired agent(s) {found}. These were merged away; "
        "escalations sent to them go nowhere. Route to REVIEW or BOND instead."
    )
