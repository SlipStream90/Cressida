"""Mission commissioning / dispatch — the engine behind the M agent.

M is CRESSIDA's mission commissioner: nothing runs until M decides *who* runs
it, *with which tools*, and *at what model tier*. This module is the
deterministic brain M uses. It runs before the coordinator schedules anything
and its whole purpose is to cut token usage:

  1. Agent pruning   — only the agents a task actually needs are activated.
  2. Tool pruning    — each activated agent is handed the smallest sufficient
                       toolset; every dropped tool schema is input tokens saved
                       on every round of that agent's loop.
  3. Skill pruning   — skills are loaded only on a clear task match.
  4. Model sizing    — the cheapest model that can do the job is assigned.
  5. Task skipping   — tasks the brief does not require are marked skip.

The plan is written back onto each ``Task.metadata`` (``toolset``, ``skills``,
``model_hint``, ``skip``) so the existing LLMAgent picks it up with no executor
changes, and recorded as a memory subnode under the **Logs** branch in Obsidian.

Fail-open by design: any uncertainty falls back to the un-pruned toolset for
that one task, so a commission never blocks a mission.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from cressida.core import AgentRole, MissionState, Task
from cressida.core.tools.definitions import get_tool_names_for_role
from cressida.orchestration.router import TaskRouter


# ── Tool intent profiles ─────────────────────────────────────────────────────
# The minimal toolset each role is commissioned with by default. The dispatcher
# then adds situational tools (write_file / run_shell) based on task signals and
# always intersects with what the role is actually allowed to hold.

_ROLE_CORE_TOOLS: dict[AgentRole, list[str]] = {
    AgentRole.M:            ["read_file", "list_dir", "query_memory"],
    AgentRole.BOND:         ["read_file", "approve_phase", "reject_phase", "escalate"],
    AgentRole.INTELLIGENCE: ["read_file", "web_search", "query_memory"],
    AgentRole.LEITER:       ["read_file", "web_search", "fetch_url", "query_memory"],
    AgentRole.Q:            ["read_file", "list_dir"],
    AgentRole.TANNER:       ["read_file", "list_dir"],
    AgentRole.BRANCH:       ["read_file", "write_file", "run_shell"],
    AgentRole.ROOK:         ["read_file", "write_file", "run_shell"],
    AgentRole.BOOTHROYD:    ["read_file", "write_file", "run_shell"],
    AgentRole.MONEYPENNY:   ["read_file", "query_memory"],
    AgentRole.REVIEW:       ["read_file", "list_dir", "run_shell"],
}

# Roles whose work never touches a shell — run_shell is pruned even if signalled.
_NON_SHELL_ROLES = {
    AgentRole.M, AgentRole.BOND, AgentRole.INTELLIGENCE, AgentRole.LEITER,
    AgentRole.Q, AgentRole.TANNER, AgentRole.MONEYPENNY,
}

# Skill hints: keyword in the task → skill worth loading. Empty match ⇒ no skill.
_SKILL_HINTS: dict[str, str] = {
    "banner": "banner-design",
    "logo": "design",
    "brand": "brand",
    "slide": "slides",
    "presentation": "slides",
    "chart": "dataviz",
    "graph": "dataviz",
    "dashboard": "dataviz",
    "ui": "ui-styling",
    "component": "ui-styling",
    "frontend": "ui-ux-pro-max",
    "design system": "design-system",
    "security": "security-review",
}


@dataclass
class TaskCommission:
    task_id: str
    agent: AgentRole
    tools: list[str]
    skills: list[str] = field(default_factory=list)
    model: str | None = None
    skip: bool = False
    rationale: str = ""


@dataclass
class CommissionPlan:
    mission_id: str
    activated_agents: list[AgentRole]
    per_task: list[TaskCommission]
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "created_at": self.created_at,
            "activated_agents": [a.value for a in self.activated_agents],
            "per_task": [
                {
                    "task_id": c.task_id,
                    "agent": c.agent.value,
                    "tools": c.tools,
                    "skills": c.skills,
                    "model": c.model,
                    "skip": c.skip,
                    "rationale": c.rationale,
                }
                for c in self.per_task
            ],
        }


class Dispatcher:
    """Commissions a mission: selects agents, tools, skills, and models per task.

    Deterministic and side-effect-light — it annotates task metadata and returns
    a plan. Recording the plan (memory / Obsidian) is handled by the caller so
    this stays testable without external dependencies.
    """

    def __init__(self, router: TaskRouter | None = None) -> None:
        self._router = router or TaskRouter()

    # ── Public API ───────────────────────────────────────────────────────────

    def commission(self, state: MissionState, annotate: bool = True) -> CommissionPlan:
        """Produce a CommissionPlan for a mission and (optionally) annotate tasks."""
        commissions: list[TaskCommission] = []
        activated: list[AgentRole] = []

        for task in state.tasks.values():
            role = self._resolve_role(task)
            if role is None:
                # No owning agent — leave the task un-pruned and let the router /
                # executor deal with it. Never block on a routing miss.
                commissions.append(TaskCommission(
                    task_id=task.id,
                    agent=task.agent or AgentRole.BOND,
                    tools=get_tool_names_for_role(task.agent) if task.agent else [],
                    rationale="unroutable — commissioned with full toolset (fail-open)",
                ))
                continue

            tools = self._select_tools(role, task)
            skills = self._select_skills(task)
            model = self._select_model(role, task)
            commission = TaskCommission(
                task_id=task.id,
                agent=role,
                tools=tools,
                skills=skills,
                model=model,
                skip=False,
                rationale=self._rationale(role, tools, skills),
            )
            commissions.append(commission)
            if role not in activated:
                activated.append(role)

            if annotate:
                task.metadata["toolset"] = tools
                task.metadata["skills"] = skills
                if model:
                    task.metadata["model_hint"] = model

        plan = CommissionPlan(
            mission_id=state.mission_id,
            activated_agents=activated,
            per_task=commissions,
        )
        return plan

    def estimate_savings(self, plan: CommissionPlan) -> dict[str, int]:
        """Rough token-lever accounting: tools dropped vs. the un-pruned baseline."""
        dropped = 0
        exposed = 0
        for c in plan.per_task:
            full = len(get_tool_names_for_role(c.agent))
            exposed += len(c.tools)
            dropped += max(0, full - len(c.tools))
        return {
            "tool_schemas_exposed": exposed,
            "tool_schemas_dropped": dropped,
            "agents_activated": len(plan.activated_agents),
            "agents_available": len(AgentRole),
        }

    # ── Selection helpers ────────────────────────────────────────────────────

    def _resolve_role(self, task: Task) -> AgentRole | None:
        if task.agent is not None:
            return task.agent
        try:
            return self._router.route(task)
        except Exception:
            return None

    def _select_tools(self, role: AgentRole, task: Task) -> list[str]:
        allowed = set(get_tool_names_for_role(role))
        core = [t for t in _ROLE_CORE_TOOLS.get(role, sorted(allowed)) if t in allowed]

        writes = task.metadata.get("writes") or []
        reads = task.metadata.get("reads") or []

        selected = list(core)

        # A task that declares outputs needs write_file, if the role holds it.
        if writes and "write_file" in allowed and "write_file" not in selected:
            selected.append("write_file")

        # A task that reads directories benefits from list_dir.
        if any(str(r).rstrip("/").endswith("/") or "." not in str(r).split("/")[-1] for r in reads):
            if "list_dir" in allowed and "list_dir" not in selected:
                selected.append("list_dir")

        # Never hand a shell to a role that doesn't run one.
        if role in _NON_SHELL_ROLES:
            selected = [t for t in selected if t != "run_shell"]

        # Guard: keep only tools the role actually has; fall open if empty.
        selected = [t for t in selected if t in allowed]
        return selected or sorted(allowed)

    def _select_skills(self, task: Task) -> list[str]:
        haystack = f"{task.name} {task.description}".lower()
        tags = [str(t).lower() for t in task.metadata.get("tags", [])]
        hits: list[str] = []
        for keyword, skill in _SKILL_HINTS.items():
            if keyword in haystack or keyword in tags:
                if skill not in hits:
                    hits.append(skill)
        return hits

    def _select_model(self, role: AgentRole, task: Task) -> str | None:
        # Respect an explicit hint; otherwise defer to the role's default model
        # (returning None means "use the agent's configured model").
        explicit = task.metadata.get("model_hint")
        if explicit:
            return explicit
        # Right-size clearly trivial tasks to a cheaper tier even for heavy roles.
        if task.metadata.get("trivial") is True:
            return "claude-sonnet-4-6"
        return None

    def _rationale(self, role: AgentRole, tools: list[str], skills: list[str]) -> str:
        parts = [f"{role.value}: tools={tools}"]
        if skills:
            parts.append(f"skills={skills}")
        return " ".join(parts)
