from __future__ import annotations

"""Mission-level triviality classification.

agents/M.md describes M's whole job as pruning unnecessary agents/phases/model
tiers before any expensive agent runs — "never activate an agent... that the
task does not demonstrably need." Two pieces of that already exist and are
wired into every mission (Dispatcher.commission(), called from
Coordinator._commission_mission): per-task tool/skill pruning, and a
model-tier downgrade that fires *only* when a task's metadata already has
``trivial: True`` on it. Nothing, however, ever set that flag, and nothing
ever skipped a whole phase — so every mission ran the identical 8-phase,
opus-tier pipeline regardless of how small the brief was.

This module is the missing piece: one short, cheap (sonnet-tier) classification
call, made before the mission DAG is built, so ``cli/commands.py::run_mission``
can skip the field-survey methodology-research phase and set ``trivial: True``
on the strategic tasks for genuinely small briefs — activating the model-tier
downgrade that was already implemented but never triggered.

Failure/ambiguity always resolves to "not trivial" (the full pipeline): a
wrong "trivial" guess costs correctness on a real mission, a wrong "standard"
guess only costs a few extra minutes, so the fallback direction matters.
"""

import json
import re

from cressida.core import AgentRole, MissionState, Task
from cressida.core.registry import AgentRegistry

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)
_SMALL_HINTS = ("small", "tiny", "script", "cli", "command-line", "utility")
_COMPLEX_HINTS = (
    "database", "api service", "authentication", "deployment", "deploy",
    "multi-component", "microservice", "external service", "hosted",
)


def _obviously_trivial(brief: str) -> bool:
    """Avoid an expensive model round-trip for unambiguously tiny local work.

    The commissioner runs before the mission DAG exists, so a slow CLI model
    would otherwise make the mission appear stuck with no execution state.
    Ambiguous or complex briefs still go through the model classifier.
    """
    text = brief.casefold()
    return (
        len(text) <= 1200
        and any(hint in text for hint in _SMALL_HINTS)
        and not any(hint in text for hint in _COMPLEX_HINTS)
    )


_PROMPT = (
    "Classify this mission brief for pipeline sizing. Respond with ONLY a JSON "
    'object, no prose, no markdown fences: {{"trivial": true, "reason": "..."}} '
    'or {{"trivial": false, "reason": "..."}}.\n\n'
    "trivial=true: a single small script/CLI/utility with no external services, "
    "no auth, no persistence beyond a local file, and no multi-component design. "
    "It does not need a field survey of the current state of the art, nor an "
    "opus-tier architecture review with ADRs and formal schemas.\n\n"
    "trivial=false: anything involving a database, an API service, "
    "authentication, a deployment target, or multiple integrated components.\n\n"
    "Brief:\n{brief}"
)


async def is_trivial_mission(mission_id: str, brief: str, registry: AgentRegistry) -> bool:
    """Ask M to classify mission complexity. Returns False (full pipeline) if M
    isn't registered, times out, or returns anything that doesn't parse."""
    if _obviously_trivial(brief):
        print(f"[commissioner] mission {mission_id} classified trivial=True: obvious small local utility")
        return True

    m_agent = registry.get(AgentRole.M)
    if m_agent is None:
        return False

    task = Task(
        id="commission_classify",
        name="Classify mission complexity",
        description=_PROMPT.format(brief=brief[:2000]),
        agent=AgentRole.M,
    )
    state = MissionState(mission_id=f"_commission_{mission_id}", brief=brief)
    try:
        result = await m_agent.execute(state, task)
        match = _JSON_RE.search(str(result))
        if not match:
            return False
        data = json.loads(match.group())
        trivial = bool(data.get("trivial", False))
        reason = data.get("reason", "")
        print(f"[commissioner] mission {mission_id} classified trivial={trivial}: {reason}")
        return trivial
    except Exception as exc:
        print(f"[commissioner] classification skipped for {mission_id}: {exc}")
        return False
