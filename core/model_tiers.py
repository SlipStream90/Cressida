from __future__ import annotations

"""Single source of truth for which Claude model each agent role runs on.

Both providers — core/llm_agent.py (native Anthropic API) and
core/providers/claude_cli_agent.py (the `claude` CLI subprocess, the one
actually used when no ANTHROPIC_API_KEY is set) — used to hardcode their own
independent copies of this mapping. That's a real drift risk: this file
already caught one case where the CLI provider's copy was stale while the
native one had moved on. Import ROLE_MODEL / DEFAULT_MODEL from here instead
of hardcoding either.

Tiering rationale (2026-07-29): planners/deciders — roles that produce a plan,
a decision, or a classification, not the mission's shipped deliverable — run
on the faster sonnet/haiku tiers, because their output is checked by a
downstream gate (BOND, or the next agent that reads their file) rather than
shipping as-is, so low latency matters more than squeezing out extra reasoning
depth. Executors — roles whose output ships as the mission's actual
deliverable (implementation code, test suites, infra config) — run on opus,
since a defect there is expensive to catch after the fact.
"""

from cressida.core import AgentRole

ROLE_MODEL: dict[AgentRole, str] = {
    # Planners / deciders — fast tiers; output is gated or classification-only.
    AgentRole.M:            "claude-haiku-4-5-20251001",  # one-shot commission/complexity classification
    AgentRole.R:            "claude-haiku-4-5-20251001",  # post-hoc distillation, off the mission's critical path
    AgentRole.INTELLIGENCE: "claude-sonnet-5",             # research + PRD — checked downstream by Q/BOND
    AgentRole.LEITER:       "claude-sonnet-5",             # methodology research — checked downstream by BOND
    AgentRole.Q:            "claude-sonnet-5",             # architecture — gated by BOND before anything builds on it
    AgentRole.BOND:         "claude-sonnet-5",             # approve/reject decision, not shipped code
    AgentRole.TANNER:       "claude-sonnet-5",             # task graph — checked implicitly by whether execution proceeds

    # Executors — output ships as the mission's actual deliverable.
    AgentRole.BRANCH:       "claude-opus-5",   # backend implementation
    AgentRole.ROOK:         "claude-opus-5",   # frontend implementation
    AgentRole.BOOTHROYD:    "claude-opus-5",   # infra/deployment config
    AgentRole.MONEYPENNY:   "claude-opus-5",   # knowledge/memory indexing that other agents rely on at runtime
    AgentRole.REVIEW:       "claude-opus-5",   # produces test suites + review verdicts that gate shipping
}

DEFAULT_MODEL = "claude-sonnet-5"
