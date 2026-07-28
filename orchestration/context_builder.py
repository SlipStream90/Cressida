from __future__ import annotations

from pathlib import Path
from typing import Any

from cressida.core.paths import cressida_home, mission_dir, project_dir
from cressida.core.types import AgentRole, AgentMessage


def _resolve_root(cressida_root: str | Path | None) -> Path:
    """Interpret a caller-supplied root, tolerating the legacy relative defaults.

    Historically callers passed ``"."`` or ``"cressida"``, which only resolved
    correctly when the process happened to be launched from the right directory.
    Both now collapse to ``cressida_home()``.
    """
    if cressida_root is None:
        return cressida_home()
    p = Path(cressida_root)
    if p.is_absolute():
        return p
    if str(p) in (".", "", "cressida"):
        return cressida_home()
    return cressida_home() / p


class ContextBuilder:
    def __init__(self, cressida_root: str | Path | None = None) -> None:
        # Default to the canonical home rather than a relative literal, so specs,
        # playbooks, and mission artifacts resolve identically no matter what the
        # process working directory is. A relative root (including the legacy "."
        # and "cressida" defaults callers still pass) is interpreted against home.
        self._root = _resolve_root(cressida_root)

    def build_prompt(
        self,
        task_id: str,
        agent_role: AgentRole,
        mission_id: str,
        brief: str,
        reads: list[str],
        task_description: str,
        objectives: list[str] | None = None,
        target_dir: str | Path | None = None,
    ) -> str:
        sections: list[str] = []
        sections.append(f"# MISSION: {mission_id}")
        sections.append(f"## Brief\n{brief}")
        sections.append(
            "## Directories\n"
            f"- Mission directory (analysis artifacts): `{mission_dir(mission_id)}`\n"
            f"- Target project (source code goes here): `{target_dir or project_dir()}`\n"
            "\nUse absolute paths when writing source files into the target project. "
            "Relative paths are interpreted against the Cressida installation, not "
            "the target project."
        )
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
