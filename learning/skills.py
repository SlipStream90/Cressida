from __future__ import annotations

"""Autonomous skill creation — Hermes-style procedural memory.

When a mission completes a task type *successfully for the first time*, the
synthesizer captures it as a reusable **skill**: a short procedure note stored
under `knowledge/skills/<slug>.md` and tracked in `skills/index.json`. Next time
a similar task appears, the skill is available as prior procedural knowledge
(surfaced via the owning agent's playbook), so the framework does not re-derive
solved procedures from scratch.

Skills also *self-improve*: re-encountering a skill's task type bumps its
`uses` count and refreshes provenance, and a later failure flips it to
`needs_review` so the next reflection pass can revise it.
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:60] or "skill"


class SkillSynthesizer:
    def __init__(self, base_path: str | Path = "knowledge/skills") -> None:
        self._base = Path(base_path)
        self._base.mkdir(parents=True, exist_ok=True)
        self._index_path = self._base / "index.json"

    def _load_index(self) -> dict[str, Any]:
        if self._index_path.exists():
            try:
                return json.loads(self._index_path.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _save_index(self, index: dict[str, Any]) -> None:
        self._index_path.write_text(json.dumps(index, indent=2, default=str), encoding="utf-8")

    def synthesize_from_mission(self, state: Any) -> list[str]:
        """Scan a mission's completed tasks and mint/refresh skills. Never raises.

        Returns the slugs of skills created or updated.
        """
        touched: list[str] = []
        try:
            index = self._load_index()
            tasks = getattr(state, "tasks", {}) or {}
            mission_id = getattr(state, "mission_id", "")
            for task in tasks.values():
                status = getattr(task, "status", None)
                status_val = status.value if hasattr(status, "value") else str(status)
                agent = getattr(task, "agent", None)
                if agent is None:
                    continue
                role = agent.value if hasattr(agent, "value") else str(agent)
                task_type = (task.metadata or {}).get("task_type") or task.name
                slug = _slug(f"{role}-{task_type}")

                if status_val == "COMPLETED":
                    touched.append(self._record_success(index, slug, role, task, task_type, mission_id))
                elif status_val == "FAILED" and slug in index:
                    index[slug]["status"] = "needs_review"
                    index[slug]["last_failure"] = mission_id
            self._save_index(index)
        except Exception as exc:
            print(f"[skills] synthesis error: {exc}")
        return [t for t in touched if t]

    def _record_success(
        self,
        index: dict[str, Any],
        slug: str,
        role: str,
        task: Any,
        task_type: str,
        mission_id: str,
    ) -> str:
        now = datetime.now().isoformat()
        if slug in index:
            entry = index[slug]
            entry["uses"] = entry.get("uses", 1) + 1
            entry["last_used"] = now
            entry["status"] = "active"
            if mission_id and mission_id not in entry.get("missions", []):
                entry.setdefault("missions", []).append(mission_id)
            self._write_skill_note(slug, entry)
            return slug

        entry = {
            "slug": slug,
            "name": task_type,
            "owner": role,
            "trigger": task_type,
            "uses": 1,
            "status": "active",
            "created": now,
            "last_used": now,
            "missions": [mission_id] if mission_id else [],
            "steps": [
                f"Confirm the task is a '{task_type}' handled by {role}.",
                "Load the relevant prior artifacts named in task.metadata['reads'].",
                f"Apply {role}'s standard procedure for this task type.",
                "Validate the output against the mission's objectives before finishing.",
            ],
        }
        index[slug] = entry
        self._write_skill_note(slug, entry)
        return slug

    def _write_skill_note(self, slug: str, entry: dict[str, Any]) -> None:
        lines = [
            f"# Skill: {entry['name']}",
            "",
            f"- **Owner:** {entry['owner']}",
            f"- **Trigger:** task type `{entry['trigger']}`",
            f"- **Status:** {entry['status']} · used {entry.get('uses', 1)}×",
            f"- **First learned:** {entry.get('created', '')}",
            "",
            "## Procedure",
            "",
        ]
        for i, step in enumerate(entry.get("steps", []), 1):
            lines.append(f"{i}. {step}")
        lines.append("")
        lines.append(
            "_Auto-synthesised by CRESSIDA's learning loop (agent R). "
            "Self-improves as the task type recurs; flips to needs_review on failure._"
        )
        (self._base / f"{slug}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def list_skills(self) -> list[dict[str, Any]]:
        return list(self._load_index().values())
