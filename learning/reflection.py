from __future__ import annotations

"""Post-mission reflection — the loop that turns experience into learning.

After a mission finishes, the ReflectionEngine looks at what actually happened —
task outcomes, execution times, review scores, and human/automated feedback in the
reward store — and distils durable, reusable lessons into each agent's playbook.

Unlike the failure-only PostMortemAnalyzer, reflection learns from *successes* too:
a high-scoring approach becomes a reinforced heuristic; a low score or negative
feedback becomes a caution. It works with zero LLM calls (deterministic distillation
from signals), and can optionally accept an LLM `distiller` for richer synthesis.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .playbook import PlaybookStore


# A distiller takes (role, raw_context) and returns a list of short lesson strings.
Distiller = Callable[[str, str], list[str]]


@dataclass
class Insight:
    role: str
    text: str
    kind: str = "heuristic"       # heuristic | caution | pattern
    source: str = ""
    tags: list[str] = field(default_factory=list)


_GOOD_SCORE = 0.75
_POOR_SCORE = 0.5


class ReflectionEngine:
    def __init__(
        self,
        playbooks: PlaybookStore | None = None,
        evaluations_path: str | Path = "evaluations",
        distiller: Distiller | None = None,
    ) -> None:
        self._playbooks = playbooks or PlaybookStore()
        self._eval_path = Path(evaluations_path)
        self._distiller = distiller

    # ── public API ───────────────────────────────────────────────────────────

    def reflect_on_mission(
        self,
        state: Any,
        strategic_memory: Any = None,
        obsidian: Any = None,
    ) -> list[Insight]:
        """Distil lessons from a completed mission and write them to playbooks.

        Best-effort and side-effect tolerant: never raises. Returns the insights
        recorded, for logging/inspection.
        """
        insights: list[Insight] = []
        try:
            rewards = self._load_rewards(getattr(state, "mission_id", ""))
            insights.extend(self._from_rewards(state, rewards))
            insights.extend(self._from_task_outcomes(state))
            if self._distiller is not None:
                insights.extend(self._from_distiller(state, rewards))
        except Exception as exc:  # reflection must never break mission finalisation
            print(f"[reflection] distillation error: {exc}")

        # commit insights → playbooks (dedup/reinforce happens inside the store)
        for ins in insights:
            try:
                self._playbooks.add_entry(
                    role=ins.role,
                    text=ins.text,
                    source=ins.source,
                    kind=ins.kind,
                    tags=ins.tags,
                )
            except Exception:
                pass

        self._mirror(state, insights, strategic_memory, obsidian)
        return insights

    # ── deterministic distillation ───────────────────────────────────────────

    def _from_rewards(self, state: Any, rewards: list[dict[str, Any]]) -> list[Insight]:
        out: list[Insight] = []
        mission_id = getattr(state, "mission_id", "")
        for r in rewards:
            agent = str(r.get("agent") or "").upper()
            if not agent:
                continue
            reward = r.get("reward")
            comment = (r.get("metadata") or {}).get("comment", "") or ""
            action = r.get("action", "task")
            src = f"mission:{mission_id}"

            # A concrete human/automated comment is the richest lesson signal.
            if comment.strip():
                if isinstance(reward, (int, float)) and reward < _POOR_SCORE:
                    out.append(Insight(agent, f"Watch out: {comment.strip()}",
                                        kind="caution", source=src, tags=["feedback"]))
                else:
                    out.append(Insight(agent, comment.strip(),
                                        kind="heuristic", source=src, tags=["feedback"]))
                continue

            # Otherwise turn the numeric signal into a light reinforcement note.
            if isinstance(reward, (int, float)):
                if reward >= _GOOD_SCORE:
                    out.append(Insight(
                        agent,
                        f"'{action}' approach scored {reward:.2f} — a reliable pattern to reuse.",
                        kind="pattern", source=src, tags=["reward"]))
                elif reward < _POOR_SCORE:
                    out.append(Insight(
                        agent,
                        f"'{action}' scored only {reward:.2f} — revisit the approach next time.",
                        kind="caution", source=src, tags=["reward"]))
        return out

    def _from_task_outcomes(self, state: Any) -> list[Insight]:
        out: list[Insight] = []
        mission_id = getattr(state, "mission_id", "")
        tasks = getattr(state, "tasks", {}) or {}
        for task in tasks.values():
            agent = getattr(task, "agent", None)
            if agent is None:
                continue
            role = agent.value if hasattr(agent, "value") else str(agent)
            status = getattr(task, "status", None)
            status_val = status.value if hasattr(status, "value") else str(status)
            src = f"mission:{mission_id}/task:{getattr(task, 'id', '')}"

            if status_val == "FAILED" and getattr(task, "error", None):
                out.append(Insight(
                    role.upper(),
                    f"Task '{task.name}' failed: {str(task.error)[:160]}. "
                    "Check inputs/preconditions before repeating this task type.",
                    kind="caution", source=src, tags=["failure"]))
        return out

    def _from_distiller(self, state: Any, rewards: list[dict[str, Any]]) -> list[Insight]:
        """Optional richer synthesis via an injected LLM distiller (one call/role)."""
        out: list[Insight] = []
        roles = {str(r.get("agent") or "").upper() for r in rewards if r.get("agent")}
        for role in sorted(roles):
            context = json.dumps(
                [r for r in rewards if str(r.get("agent") or "").upper() == role],
                default=str,
            )[:6000]
            try:
                for lesson in (self._distiller(role, context) or []):
                    out.append(Insight(role, lesson.strip(), kind="heuristic",
                                       source=f"mission:{getattr(state, 'mission_id', '')}",
                                       tags=["distilled"]))
            except Exception as exc:
                print(f"[reflection] distiller failed for {role}: {exc}")
        return out

    # ── io helpers ───────────────────────────────────────────────────────────

    def _load_rewards(self, mission_id: str) -> list[dict[str, Any]]:
        if not mission_id:
            return []
        path = self._eval_path / mission_id / "reward_records.jsonl"
        if not path.exists():
            return []
        records: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except Exception:
                    pass
        return records

    def _mirror(
        self,
        state: Any,
        insights: list[Insight],
        strategic_memory: Any,
        obsidian: Any,
    ) -> None:
        if not insights:
            return
        mission_id = getattr(state, "mission_id", "")

        # Strategic memory: record the successful lessons as reusable patterns.
        if strategic_memory is not None:
            for ins in insights:
                try:
                    strategic_memory.record_pattern(
                        pattern=f"[{ins.role}] {ins.text[:120]}",
                        context=f"mission={mission_id} kind={ins.kind}",
                        success=(ins.kind != "caution"),
                    )
                except Exception:
                    pass

        # Obsidian: file a Knowledge subnode summarising what was learned.
        try:
            bridge = obsidian
            if bridge is None:
                from cressida.obsidian.bridge import get_bridge
                bridge = get_bridge()
            if bridge is not None:
                bridge.store_subnode(
                    branch="knowledge",
                    title=f"Reflection — {mission_id}",
                    content=self._render_note(mission_id, insights),
                    tags=["reflection", "learning"],
                    metadata={"mission_id": mission_id, "agent": "R"},
                )
        except Exception:
            pass

    @staticmethod
    def _render_note(mission_id: str, insights: list[Insight]) -> str:
        lines = [
            f"# Reflection — {mission_id}",
            "",
            f"_{len(insights)} lesson(s) distilled into agent playbooks on "
            f"{datetime.now().strftime('%Y-%m-%d %H:%M')}._",
            "",
        ]
        by_role: dict[str, list[Insight]] = {}
        for ins in insights:
            by_role.setdefault(ins.role, []).append(ins)
        for role in sorted(by_role):
            lines.append(f"## {role}")
            for ins in by_role[role]:
                lines.append(f"- **[{ins.kind}]** {ins.text}")
            lines.append("")
        return "\n".join(lines)
