from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from cressida.core.events import Event, EventBus, EventType
from cressida.core.paths import cressida_home, mission_dir
from cressida.core.providers.claude_cli_agent import filter_dynamic_tools
from cressida.core.registry import AgentRegistry
from cressida.core.types import AgentRole, MissionState, MissionStatus, Task, TaskStatus
from cressida.memory.system import MemorySystem
from cressida.state.shared_state import SharedState

from cressida.learning import Curator, PlaybookStore, ReflectionEngine, SkillSynthesizer

from .dependency_graph import CyclicDependencyError, DependencyGraph
from .dispatcher import Dispatcher
from .executor import TaskExecutor
from .router import TaskRouter
from .scheduler import Scheduler


class CoordinationError(Exception):
    pass


class Coordinator:
    def __init__(
        self,
        registry: AgentRegistry,
        event_bus: EventBus,
        memory: MemorySystem,
    ) -> None:
        self._registry = registry
        self._event_bus = event_bus
        self._memory = memory
        self._router = TaskRouter()
        self._dispatcher = Dispatcher(self._router)
        self._executor = TaskExecutor(registry, self._router, event_bus)
        self._graph = DependencyGraph()
        self._scheduler = Scheduler(self._graph)

        # Learning layer (agent R): reflection distils lessons into per-agent
        # playbooks after every mission; the curator keeps them consolidated.
        # Anchor to the canonical home so the write side lines up with the
        # ContextBuilder read side, which resolves knowledge/ the same way.
        pkg_dir = cressida_home()
        self._playbooks = PlaybookStore(pkg_dir / "knowledge" / "playbooks")
        self._reflection = ReflectionEngine(
            playbooks=self._playbooks,
            evaluations_path=pkg_dir / "evaluations",
        )
        self._skills = SkillSynthesizer(pkg_dir / "knowledge" / "skills")
        self._curator = Curator(playbooks=self._playbooks, skills=self._skills)

    async def run_mission(self, state: MissionState, shared: SharedState | None = None) -> MissionState:
        state.status = MissionStatus.IN_PROGRESS
        await self._event_bus.publish(
            Event(type=EventType.MISSION_STARTED, data={"mission_id": state.mission_id, "brief": state.brief}, source="coordinator")
        )

        self._snapshot_project_dir(state)

        try:
            # M commissions the mission first: prune agents/tools/skills per task
            # (annotates task.metadata) so downstream agents run lean. Recording
            # the plan is best-effort and never blocks execution.
            self._commission_mission(state)

            self._build_graph(state)
            schedule = self._scheduler.compute_schedule()
            self._memory.strategic.record_decision(
                decision_id=f"schedule_{state.mission_id}",
                title="Execution schedule",
                description=f"Schedule with {len(schedule.order)} tasks across {len(schedule.parallel_batches)} batches",
                alternatives=[],
                chosen="topological_sort",
                rationale="Optimal parallelization with dependency resolution",
                author="coordinator",
                tags=["scheduling", state.mission_id],
            )

            for batch_idx, batch in enumerate(schedule.parallel_batches):
                batch_tasks = [state.tasks[tid] for tid in batch if tid in state.tasks]
                await self._execute_batch(batch_tasks, state, batch_idx, schedule)

                if any(t.agent == AgentRole.BOND for t in batch_tasks):
                    approved, detail = self._check_bond_gate(state)
                    if not approved:
                        state.status = MissionStatus.ESCALATED
                        state.metadata["bond_gate_blocked"] = detail
                        self._persist_state(state)
                        await self._event_bus.publish(
                            Event(type=EventType.MISSION_FAILED, data={
                                "mission_id": state.mission_id,
                                "error": f"BOND gate blocked planning/implementation: {detail}",
                            }, source="coordinator")
                        )
                        return state

            self._finalize_mission(state)

        except CyclicDependencyError as e:
            state.status = MissionStatus.FAILED
            self._persist_state(state)
            await self._event_bus.publish(
                Event(type=EventType.MISSION_FAILED, data={"mission_id": state.mission_id, "error": str(e)}, source="coordinator")
            )

        except Exception as e:
            state.status = MissionStatus.FAILED
            self._persist_state(state)
            await self._event_bus.publish(
                Event(type=EventType.MISSION_FAILED, data={"mission_id": state.mission_id, "error": str(e)}, source="coordinator")
            )

        return state

    def _snapshot_project_dir(self, state: MissionState) -> None:
        """Best-effort git checkpoint of the mission's target project, taken
        before any agent touches it.

        Agents now run with --permission-mode bypassPermissions (see
        core/providers/claude_cli_agent.py) — there is no per-action approval
        step left to catch a bad edit or an errant Bash command. This commit is
        the safety net that makes a mission's damage reversible: if it goes
        wrong, ``git diff``/``git reset --hard`` against this commit gets the
        project back to where it started. Uses ``--allow-empty`` so a restore
        point exists even on a first run against an already-clean tree.

        Never raises and never blocks the mission: a missing ``git`` binary, an
        unconfigured commit identity, or any other failure is logged and
        swallowed. The identity is passed per-invocation (``-c user.name=...``)
        rather than written to config, so this never mutates the user's git
        setup.
        """
        import subprocess

        raw_target = state.metadata.get("project_dir")
        if not raw_target:
            return
        target_path = Path(raw_target)
        if not target_path.is_dir():
            return

        try:
            if not (target_path / ".git").exists():
                subprocess.run(
                    ["git", "init", "-q"],
                    cwd=str(target_path), capture_output=True, text=True, timeout=30,
                )
            subprocess.run(
                ["git", "add", "-A"],
                cwd=str(target_path), capture_output=True, text=True, timeout=120,
            )
            result = subprocess.run(
                [
                    "git", "-c", "user.name=Cressida", "-c", "user.email=cressida@local",
                    "commit", "--allow-empty",
                    "-m", f"cressida: pre-mission snapshot ({state.mission_id})",
                ],
                cwd=str(target_path), capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0:
                sha = subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    cwd=str(target_path), capture_output=True, text=True, timeout=15,
                ).stdout.strip()
                state.metadata["pre_mission_snapshot"] = sha
                print(f"[coordinator] pre-mission snapshot {sha[:8]} committed for {state.mission_id}")
            else:
                print(f"[coordinator] pre-mission snapshot commit failed: {result.stderr.strip()[:500]}")
        except Exception as e:
            print(f"[coordinator] pre-mission snapshot skipped: {e}")

    @staticmethod
    def _parse_bond_decision_file(path: Path) -> dict[str, Any]:
        """Normalize a BOND decision artifact into ``{"decision", "rationale",
        "approved_mcp_tools"}`` regardless of whether BOND wrote clean JSON
        (via a real ``approve_phase``/``reject_phase`` tool call) or free-text
        markdown (the observed fallback under the ``claude_cli`` provider,
        which does not expose those as real callable tools — see
        ``missions/mission_20260729_194951/bond_decisions/bond_approve_plan.md``
        for a concrete example: ``**Decision: rejected.**`` with no JSON at
        all). A JSON code fence embedded in the markdown is used for
        ``approved_mcp_tools`` if present; otherwise that list is empty,
        which is the safe default — "no tools requested" costs nothing.
        """
        import json as _json
        import re as _re

        text = path.read_text(encoding="utf-8")

        if path.suffix == ".json":
            record = _json.loads(text)
            return {
                "decision": str(record.get("decision", "")).upper(),
                "rationale": str(record.get("reason") or record.get("rationale") or ""),
                "approved_mcp_tools": record.get("approved_mcp_tools") or [],
            }

        # Markdown fallback: look for "Decision:"/"Verdict:"/"gate":  <verdict>
        # (BOND has been observed writing all three labels, and using the
        # unsuffixed "APPROVE"/"REJECT" as well as "APPROVED"/"REJECTED"), then
        # for an embedded ```json ... approved_mcp_tools ... ``` fence if BOND
        # included one.
        m = _re.search(
            r"(?:decision|verdict|gate)[:\s]*\**\s*(APPROVE(?:D)?|REJECT(?:ED)?|ESCALATE(?:D)?)",
            text, _re.IGNORECASE,
        )
        decision = m.group(1).upper() if m else ""
        decision = {"APPROVE": "APPROVED", "REJECT": "REJECTED", "ESCALATE": "ESCALATED"}.get(decision, decision)
        approved_mcp_tools: list[str] = []
        for fence in _re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, _re.DOTALL):
            try:
                fence_data = _json.loads(fence)
            except Exception:
                continue
            if isinstance(fence_data, dict) and "approved_mcp_tools" in fence_data:
                approved_mcp_tools = fence_data.get("approved_mcp_tools") or []
                break
        return {"decision": decision, "rationale": text[:400], "approved_mcp_tools": approved_mcp_tools}

    def _check_bond_gate(self, state: MissionState) -> tuple[bool, str]:
        """Whether BOND actually approved the plan — the real enforcement this
        gate was missing.

        Previously nothing read BOND's decision at all: ``_execute_batch``
        only checks whether the *task* completed (i.e. produced output without
        raising), not what BOND *decided*, so Planning and Implementation ran
        unconditionally even after a REJECTED or unresolved-ESCALATE verdict.
        That was tolerable when every tool call still needed human approval;
        now that mission subprocesses run with a fixed tool allowlist and no
        per-action prompt (see core/providers/claude_cli_agent.py), this is
        the last checkpoint before code gets written, so it has to actually
        gate.

        Also extracts BOND's ``approved_mcp_tools`` (per-mission additions to
        the default tool floor Q may have requested in
        ``architecture/mcp_tool_requests.json``) and stores the
        keyword-filtered result on ``state.metadata`` for ClaudeCLIAgent to
        pick up on the next subprocess launch. This filtering is deliberately
        redundant with the one ``ClaudeCLIAgent.execute`` does again right
        before building ``--allowedTools`` — see ``filter_dynamic_tools``'s
        docstring for why a single filter pass isn't trusted either.

        Fails closed: no readable decision file, an unparseable one, or any
        decision other than "APPROVED" all block the mission. This is
        deliberate — under the ``claude_cli`` provider, BOND's
        ``approve_phase``/``reject_phase``/``escalate`` tools are not real
        callable tools (see ``ClaudeCLIAgent``'s docstring and the
        ``tooling_gap`` note BOND itself has logged before, e.g.
        ``missions/mission_20260729_120842/bond_decisions/approve_plan.json``),
        so an agent that never wrote a well-formed decision file at all is
        exactly the failure mode to block on, not silently pass through.

        Returns ``(approved, detail)`` where ``detail`` explains the verdict
        or the block reason.
        """
        m_dir = mission_dir(state.mission_id)

        esc_dir = m_dir / "escalations"
        if esc_dir.is_dir():
            import json as _json
            for f in sorted(esc_dir.glob("*.json")):
                try:
                    rec = _json.loads(f.read_text(encoding="utf-8"))
                except Exception:
                    continue
                if str(rec.get("status", "")).upper() == "PENDING":
                    return False, (
                        f"Unresolved escalation at {f}: {rec.get('issue', '(no issue text)')}. "
                        f"Resolve it (see resolve_escalation) before this mission can proceed."
                    )

        decisions_dir = m_dir / "bond_decisions"
        if not decisions_dir.is_dir():
            return False, (
                f"BOND produced no decisions directory at {decisions_dir}. "
                "No approval on record — refusing to proceed to planning/implementation."
            )

        candidates = sorted(
            (p for p in decisions_dir.iterdir() if p.suffix in (".json", ".md")),
            key=lambda p: p.stat().st_mtime, reverse=True,
        )
        if not candidates:
            return False, (
                f"BOND's decisions directory ({decisions_dir}) is empty — no approval on record."
            )

        latest = candidates[0]
        try:
            record = self._parse_bond_decision_file(latest)
        except Exception as e:
            return False, f"BOND's decision file ({latest}) could not be parsed: {e}"

        decision = record["decision"]
        if decision == "APPROVED":
            safe_tools, rejected_tools = filter_dynamic_tools(list(record["approved_mcp_tools"]))
            state.metadata["approved_mcp_tools"] = safe_tools
            if rejected_tools:
                print(
                    f"[coordinator] BOND approved tool(s) blocked by keyword backstop: "
                    f"{[(n, kw) for n, kw in rejected_tools]}"
                )
            tools_note = f" Additional tools granted: {safe_tools}." if safe_tools else ""
            return True, f"BOND approved ({latest.name}): {record['rationale'][:200]}{tools_note}"
        return False, (
            f"BOND's latest decision ({latest.name}) is '{decision or '(missing)'}', not APPROVED: "
            f"{record['rationale'][:400]}"
        )

    def _commission_mission(self, state: MissionState) -> None:
        """Run M's dispatcher, annotate tasks, and record the plan (best-effort)."""
        try:
            plan = self._dispatcher.commission(state, annotate=True)
        except Exception as e:  # never let commissioning block a mission
            print(f"[coordinator] commission skipped: {e}")
            return

        savings = self._dispatcher.estimate_savings(plan)

        # 1) Strategic memory — durable, queryable record of the plan.
        try:
            self._memory.strategic.record_decision(
                decision_id=f"commission_{state.mission_id}",
                title="M commission plan",
                description=(
                    f"Activated {len(plan.activated_agents)} agents; "
                    f"dropped {savings['tool_schemas_dropped']} tool schemas "
                    f"({savings['tool_schemas_exposed']} exposed)."
                ),
                alternatives=["commission all agents with full toolsets"],
                chosen="selective_commission",
                rationale="Minimise token usage by activating only required agents/tools.",
                author="M",
                tags=["commission", "dispatch", state.mission_id],
            )
        except Exception as e:
            print(f"[coordinator] commission memory write failed: {e}")

        # 2) Obsidian — store the plan as a subnode under the Logs branch.
        try:
            from cressida.obsidian.bridge import get_bridge

            bridge = get_bridge()
            if bridge is not None:
                body = self._render_commission_note(plan, savings)
                bridge.store_subnode(
                    branch="logs",
                    title=f"Commission — {state.mission_id}",
                    content=body,
                    tags=["commission", "dispatch"],
                    metadata={"mission_id": state.mission_id, "agent": "M"},
                )
        except Exception as e:
            print(f"[coordinator] commission obsidian write failed: {e}")

    @staticmethod
    def _render_commission_note(plan: Any, savings: dict[str, int]) -> str:
        lines = [
            f"# Commission Plan — {plan.mission_id}",
            "",
            f"**Activated agents:** {', '.join(a.value for a in plan.activated_agents)}",
            f"**Tool schemas exposed:** {savings['tool_schemas_exposed']}  ",
            f"**Tool schemas dropped:** {savings['tool_schemas_dropped']}  ",
            f"**Agents activated / available:** {savings['agents_activated']} / {savings['agents_available']}",
            "",
            "## Per-task commission",
            "",
            "| Task | Agent | Tools | Skills | Model | Skip |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for c in plan.per_task:
            lines.append(
                f"| {c.task_id} | {c.agent.value} | {', '.join(c.tools) or '—'} | "
                f"{', '.join(c.skills) or '—'} | {c.model or 'default'} | {'yes' if c.skip else 'no'} |"
            )
        return "\n".join(lines)

    def _build_graph(self, state: MissionState) -> None:
        for task_id, task in state.tasks.items():
            self._graph.add_node(task_id, weight=task.priority.value if hasattr(task.priority, "value") else 50)
        for task_id, task in state.tasks.items():
            for dep_id in task.depends_on:
                self._graph.add_dependency(task_id, dep_id)

    async def _execute_batch(
        self,
        tasks: list[Task],
        state: MissionState,
        batch_idx: int,
        schedule: Any,
    ) -> None:
        pending: list[Task] = [t for t in tasks if t.status == TaskStatus.PENDING]
        if not pending:
            return

        if len(pending) == 1:
            await self._executor.execute_task(pending[0], state)
        else:
            await self._executor.execute_parallel(pending, state)

        for task in pending:
            if task.status == TaskStatus.COMPLETED:
                state.complete_task(task.id)
                await self._event_bus.publish(
                    Event(type=EventType.EVALUATION_RECORDED, data={
                        "task_id": task.id,
                        "agent": str(task.agent) if task.agent else "unknown",
                        "execution_time": task.execution_time,
                    }, source="coordinator")
                )
            elif task.status == TaskStatus.FAILED:
                state.fail_task(task.id, task.error or "unknown error")

        self._persist_state(state)

    def _finalize_mission(self, state: MissionState) -> None:
        all_completed = all(
            t.status == TaskStatus.COMPLETED for t in state.tasks.values()
        )
        any_failed = any(
            t.status == TaskStatus.FAILED for t in state.tasks.values()
        )

        if all_completed:
            state.status = MissionStatus.COMPLETED
            self._event_bus.publish(
                Event(type=EventType.MISSION_COMPLETED, data={"mission_id": state.mission_id}, source="coordinator")
            )
        elif any_failed:
            state.status = MissionStatus.FAILED
            self._event_bus.publish(
                Event(type=EventType.MISSION_FAILED, data={"mission_id": state.mission_id, "error": "One or more tasks failed"}, source="coordinator")
            )
        else:
            state.status = MissionStatus.COMPLETED
            self._event_bus.publish(
                Event(type=EventType.MISSION_COMPLETED, data={"mission_id": state.mission_id}, source="coordinator")
            )

        # Close the learning loop: distil this mission's experience into agent
        # playbooks, mint/refresh skills, and consolidate. Best-effort — never
        # allowed to affect the mission's outcome.
        self._learn_from_mission(state)

        self._persist_state(state)

    def _learn_from_mission(self, state: MissionState) -> None:
        """Run reflection + skill synthesis + consolidation after a mission."""
        try:
            insights = self._reflection.reflect_on_mission(
                state,
                strategic_memory=self._memory.strategic,
            )
            skills = self._skills.synthesize_from_mission(state)
            self._curator.consolidate_all(decay=False)
            print(
                f"[learning] mission {state.mission_id}: "
                f"{len(insights)} lesson(s), {len(skills)} skill(s) touched."
            )
        except Exception as e:  # learning must never break a mission
            print(f"[coordinator] learning skipped: {e}")

    def _persist_state(self, state: MissionState) -> None:
        """Write execution_state.json so MCP status tools can read it."""
        # Canonical mission dir — see core/paths.py. The previous
        # `Path(__file__).parent.parent.parent` climbed one level above the repo
        # root and wrote missions outside it, splitting them from agent output.
        path = mission_dir(state.mission_id) / "execution_state.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        tasks_data = {}
        for tid, task in state.tasks.items():
            tasks_data[tid] = {
                "status": task.status.value if hasattr(task.status, "value") else str(task.status),
                "agent": task.agent.value if task.agent else None,
                "name": task.name,
                "error": task.error,
            }
        payload = {
            "mission_id": state.mission_id,
            "status": state.status.value if hasattr(state.status, "value") else str(state.status),
            "tasks": tasks_data,
            "updated_at": datetime.now().isoformat(),
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
