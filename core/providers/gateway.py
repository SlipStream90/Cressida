from __future__ import annotations

"""Gateway routing: pick the best available *provider* for each agent role,
instead of one fixed provider for the whole mission.

`provider="auto"` (core/providers/auto.py::detect_provider) already picks a
single provider by priority order and every role in the mission runs on it.
`provider="gateway"` is additive to that, not a replacement: it calls
`detect_available_providers()` once to see everything actually usable right
now (API keys present, CLI installed, Ollama reachable — same probes
`detect_provider()` already uses), then scores each available provider against
the *role's* tier and picks the best fit per role. A cheap classification task
(BOND's approve/reject, M's commissioning) doesn't need the same provider as
BRANCH's backend implementation, which ships as the mission's actual
deliverable — this lets, e.g., a fast/cheap/local provider handle planning
roles while a stronger one is reserved for execution roles, if both are
available, without the user hand-picking a provider per role themselves.

What this does NOT do: pick a specific *model* string. Every provider agent
class already resolves its own per-role model internally (see
core/model_tiers.py for the anthropic-family mapping, and each of
gemini_agent.py/openai_agent.py's own internal role->model maps) — gateway
routing only decides which of those already-correct, already-maintained
mappings gets used for a given role, so there's no second, independently
maintained set of model-name literals to drift out of date.

The scoring table below is a hand-set heuristic, not a benchmarked result —
adjust `_PROVIDER_TIER_SCORE` as real usage data suggests better weights.
"""

from cressida.core import AgentRole
from cressida.core.model_tiers import ROLE_MODEL

# ── Role tiers, derived from model_tiers.py's own tiering rather than a
# second hand-maintained list — model_tiers.py already encodes "planner
# (fast/cheap, output gated downstream)" vs "executor (ships as the mission's
# deliverable)" via which Claude tier each role runs on. Reusing it here means
# this file can't silently drift from model_tiers.py's categorization.
def _role_tier(role: AgentRole) -> str:
    model = ROLE_MODEL.get(role, "")
    if "haiku" in model:
        return "trivial"   # one-shot classification, off the critical path
    if "opus" in model:
        return "executor"  # ships as the mission's actual deliverable
    return "planner"       # produces a plan/decision checked downstream


# Per-provider heuristic scores, one column per role tier. Higher is better.
# Rationale: hosted-frontier providers (anthropic/openai/gemini and the CLI
# tools that ride on top of them) score well on "executor" (capability
# matters most, since a defect ships); groq's inference speed and ollama's
# zero-cost/local nature make them attractive for "trivial"/"planner" tiers
# where throughput matters more than squeezing out extra reasoning depth, but
# they score lower on "executor" since their strongest hosted models still
# generally trail frontier-tier coding capability.
_PROVIDER_TIER_SCORE: dict[str, dict[str, int]] = {
    "anthropic":  {"executor": 10, "planner": 9, "trivial": 7},
    "claude_cli": {"executor": 10, "planner": 9, "trivial": 7},
    "openai":     {"executor": 8,  "planner": 8, "trivial": 6},
    "codex":      {"executor": 8,  "planner": 8, "trivial": 6},
    "opencode":   {"executor": 7,  "planner": 7, "trivial": 6},
    "kilocode":   {"executor": 7,  "planner": 7, "trivial": 6},
    "gemini":     {"executor": 7,  "planner": 8, "trivial": 8},
    "groq":       {"executor": 4,  "planner": 6, "trivial": 10},
    "ollama":     {"executor": 3,  "planner": 5, "trivial": 6},
}

# Fallback score for a provider this table doesn't know about yet (e.g. a
# new provider landed and this table wasn't updated) — treated as viable but
# unremarkable, rather than excluded outright.
_UNKNOWN_PROVIDER_SCORE = 5


def select_provider_for_role(role: AgentRole, available_providers: list[str]) -> str:
    """Pick the best of `available_providers` for `role`'s tier.

    Raises ValueError if `available_providers` is empty — there is no sane
    provider to fall back to, and returning a made-up default would silently
    route a mission to something nobody confirmed is usable. Callers (see
    core/agent_factory.py) are expected to have already validated the list is
    non-empty via detect_available_providers() before routing per-role.
    """
    if not available_providers:
        raise ValueError("select_provider_for_role: no available providers to choose from")

    tier = _role_tier(role)
    return max(
        available_providers,
        key=lambda p: _PROVIDER_TIER_SCORE.get(p, {}).get(tier, _UNKNOWN_PROVIDER_SCORE),
    )
