from __future__ import annotations

from pathlib import Path
from typing import Any

from cressida.core.types import AgentRole, AgentMessage


class ContextBuilder:
    def __init__(self, cressida_root: str | Path = "cressida") -> None:
        self._root = Path(cressida_root)

    def build_prompt(
        self,
        task_id: str,
        agent_role: AgentRole,
        mission_id: str,
        brief: str,
        reads: list[str],
        task_description: str,
        objectives: list[str] | None = None,
    ) -> str:
        sections: list[str] = []
        sections.append(f"# MISSION: {mission_id}")
        sections.append(f"## Brief\n{brief}")
        if objectives:
            sections.append("## Objectives\n" + "\n".join(f"- {o}" for o in objectives))
        sections.append(f"## Task: {task_id}\n{task_description}")
        sections.append(f"## Agent: {agent_role.value}")

        # The constitution governs *how* every agent works, so it is injected
        # ahead of the role spec and outranks it. Best-effort: a missing file
        # never breaks a prompt.
        constitution = self._read_constitution()
        if constitution:
            sections.append(
                "## Constitution — binding on all agents\n"
                "These rules govern how you work and take precedence over your agent "
                "spec and playbook. A resolved human escalation outranks them.\n\n"
                + constitution
            )

        spec = self._read_agent_spec(agent_role)
        if spec:
            sections.append(f"## Agent Specification\n{spec}")

        # Learned playbook: this agent's own accumulated experience from past
        # missions, injected so behaviour improves over time (Hermes-style loop).
        # Best-effort and bounded — a missing learning layer never breaks a prompt.
        playbook = self._read_playbook(agent_role)
        if playbook:
            sections.append(
                f"## Learned Playbook — {agent_role.value}\n"
                "Lessons you have accumulated from past missions. Apply the relevant "
                "ones; treat [AVOID] items as known pitfalls.\n\n" + playbook
            )

        for path in reads:
            content = self._resolve_read(path, mission_id)
            if content:
                sections.append(f"## Context: {path}\n{content}")
            else:
                sections.append(f"## Context: {path}\n*Not found*")

        sections.append("## Output Requirements\nProduce the outputs specified in your agent spec. Write all artifacts to the mission directory.")

        return "\n\n---\n\n".join(sections)

    def _read_constitution(self) -> str | None:
        path = self._root / "agents" / "CONSTITUTION.md"
        try:
            if path.exists():
                return path.read_text(encoding="utf-8")
        except Exception:
            return None
        return None

    def _read_agent_spec(self, role: AgentRole) -> str | None:
        path = self._root / "agents" / f"{role.value.lower()}.md"
        if path.exists():
            return path.read_text(encoding="utf-8")
        return None

    def _read_playbook(self, role: AgentRole) -> str | None:
        try:
            from cressida.learning.playbook import PlaybookStore

            store = PlaybookStore(self._root / "knowledge" / "playbooks")
            rendered = store.render_for_prompt(role.value)
            return rendered or None
        except Exception:
            return None

    def _resolve_read(self, read_path: str, mission_id: str) -> str | None:
        resolved = read_path.replace("<mission_id>", mission_id)
        candidates = [
            self._root / resolved,
            self._root / "missions" / mission_id / resolved,
            self._root / "knowledge" / resolved,
            Path(resolved),
        ]
        for c in candidates:
            if c.exists():
                if c.is_dir():
                    return self._read_dir(c)
                return c.read_text(encoding="utf-8")
        return None

    def _read_dir(self, path: Path) -> str:
        lines: list[str] = []
        for f in sorted(path.iterdir()):
            if f.is_file() and f.suffix in (".md", ".py", ".json", ".yaml", ".txt"):
                lines.append(f"--- {f.name} ---")
                lines.append(f.read_text(encoding="utf-8"))
        return "\n".join(lines)
