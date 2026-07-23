from __future__ import annotations

"""The Curator — Hermes-style "periodic nudge" that keeps learning healthy.

Left alone, playbooks would grow without bound and stale lessons would crowd out
useful ones. The Curator runs periodically (e.g. from the daemon, or on demand via
agent R) to:

  - consolidate each role's playbook (merge duplicates, prune below the cap),
  - decay scores so lessons that stop being reinforced fade,
  - surface a short "nudge" summary of the strongest current learnings.

It is deterministic, cheap, and side-effect tolerant.
"""

from pathlib import Path
from typing import Any

from .playbook import PlaybookStore
from .skills import SkillSynthesizer


class Curator:
    def __init__(
        self,
        playbooks: PlaybookStore | None = None,
        skills: SkillSynthesizer | None = None,
    ) -> None:
        self._playbooks = playbooks or PlaybookStore()
        self._skills = skills or SkillSynthesizer()

    def consolidate_all(self, decay: bool = True) -> dict[str, int]:
        """Consolidate + optionally decay every role's playbook.

        Returns {role: entries_pruned}.
        """
        report: dict[str, int] = {}
        for role in self._playbooks.all_roles():
            try:
                if decay:
                    self._playbooks.decay(role)
                report[role] = self._playbooks.consolidate(role)
            except Exception as exc:
                print(f"[curator] consolidate failed for {role}: {exc}")
        return report

    def nudge(self, top_n: int = 3) -> str:
        """A short digest of the strongest learnings across all roles."""
        lines = ["# Learning nudge", ""]
        roles = self._playbooks.all_roles()
        if not roles:
            return "No learnings recorded yet."
        for role in roles:
            top = self._playbooks.render_for_prompt(role, limit=top_n)
            if top:
                lines.append(f"## {role.upper()}")
                lines.append(top)
                lines.append("")
        skills = self._skills.list_skills()
        if skills:
            lines.append("## Skills")
            for s in skills[:top_n * 3]:
                lines.append(f"- {s.get('name')} ({s.get('owner')}) · used {s.get('uses', 1)}×")
        return "\n".join(lines)

    def stats(self) -> dict[str, Any]:
        return {
            "playbooks": self._playbooks.summary(),
            "skills": len(self._skills.list_skills()),
        }
