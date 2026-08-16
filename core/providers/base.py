from __future__ import annotations

"""Shared base class for all provider-specific LLM agents.

Provider agents (OpenAI, Gemini, Groq, Ollama) inherit from ProviderAgentBase
instead of implementing Agent directly. This keeps spec loading, output writing,
and context assembly in one place without touching the existing core/llm_agent.py
(Anthropic agent).

All provider agents implement:
  execute(state, task) -> Any    (provider-specific agentic loop)
  get_capabilities() -> list[str]  (shared, from TASK_TYPE_ROUTE)
"""

import json
from abc import abstractmethod
from pathlib import Path
from typing import Any

from cressida.core.events import EventBus, EventType, publish_safe
from cressida.core.interfaces import Agent
from cressida.core import AgentRole, MissionState, Task
from cressida.core.paths import mission_dir, project_dir, resolve_mission_artifact_path, resolve_under_home
from cressida.orchestration.context_builder import ContextBuilder


_MAX_TOOL_ROUNDS = 40


class ProviderAgentBase(Agent):
    """Abstract base that handles spec loading, context building, and output writing.

    Concrete provider agents only need to implement `execute()`.
    """

    def __init__(
        self,
        role: AgentRole,
        agents_dir: str | Path = "agents",
        cressida_root: str | Path = ".",
        max_tokens: int = 8192,
    ) -> None:
        self.role = role
        # Relative spec dirs are anchored to cressida_home(), not the CWD.
        self._agents_dir = resolve_under_home(agents_dir)
        self._context_builder = ContextBuilder(cressida_root)
        self._max_tokens = max_tokens
        self._spec: str | None = None

    # ── Shared helpers ────────────────────────────────────────────────────────

    def _load_spec(self) -> str:
        if self._spec is None:
            spec_path = self._agents_dir / f"{self.role.value.lower()}.md"
            if spec_path.exists():
                self._spec = spec_path.read_text(encoding="utf-8")
            else:
                self._spec = (
                    f"You are the {self.role.value} agent in the CRESSIDA "
                    "multi-agent software engineering framework. "
                    "Execute the task assigned to you according to your role's responsibilities."
                )
        return self._spec

    def _build_user_prompt(self, state: MissionState, task: Task) -> str:
        return self._context_builder.build_prompt(
            task_id=task.id,
            agent_role=task.agent or self.role,
            mission_id=state.mission_id,
            brief=state.brief,
            reads=task.metadata.get("reads", []),
            task_description=task.description,
            writes=task.metadata.get("writes", []),
            objectives=state.objectives if state.objectives else None,
            target_dir=project_dir(state),
            skills=task.metadata.get("skills"),
        )

    def _write_output(self, mission_id: str, task: Task, content: str) -> None:
        writes: list[str] = task.metadata.get("writes", [])
        if not writes:
            out_dir = mission_dir(mission_id) / "outputs"
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / f"{task.id}.md").write_text(content, encoding="utf-8")
            return

        # CLI-backed providers (claude_cli, opencode, codex, kilocode) have
        # real Write/Edit tools and are instructed to author these files
        # themselves during the task -- `content` here is just their closing
        # chat message. Unconditionally overwriting `writes` targets with
        # that message was clobbering real documents the agent had already
        # written moments earlier (see missions/mission_20260810_224212:
        # intelligence/PRD.md ended up as a 6-line "verified the artifacts"
        # note while the real 60-line PRD sat one level up, at the mission
        # root -- exactly the path a downstream task's `reads` never looks).
        # `_reconcile_file_write` only falls back to writing `content` when
        # there's no evidence a tool already produced the real file; for
        # providers that only return text (no file-write tools at all), that
        # fallback is what has always persisted their output, unchanged.
        cutoff = (task.started_at.timestamp() - 2.0) if task.started_at else None

        for write_path in writes:
            resolved = write_path.replace("<mission_id>", mission_id)
            # Anchored to cressida_home(), not the CWD. Resolving against the CWD
            # meant a mission launched from outside the package wrote its
            # artifacts into a second mission tree that no downstream `reads`
            # could find. Absolute paths still pass through, which is how a
            # mission writes into an external target project.
            p = resolve_mission_artifact_path(resolved, mission_id)
            target = p if p.suffix else (p / f"{task.id}.md")
            self._reconcile_file_write(mission_id, target, content, cutoff)

    def _reconcile_file_write(
        self, mission_id: str, target: Path, content: str, cutoff: float | None,
    ) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)

        if cutoff is None:
            target.write_text(content, encoding="utf-8")
            return

        if target.exists() and target.stat().st_mtime >= cutoff:
            # The agent's own tools already wrote real content here during
            # this task run -- don't clobber it with the closing chat text.
            return

        # Same basename, different (wrong) location, written during this
        # task run: relocate it rather than losing it under a stub.
        for candidate in mission_dir(mission_id).rglob(target.name):
            if candidate == target:
                continue
            try:
                if candidate.stat().st_mtime >= cutoff:
                    target.write_text(candidate.read_text(encoding="utf-8"), encoding="utf-8")
                    return
            except OSError:
                continue

        # Nothing found -- the agent narrated instead of using a tool (or
        # this provider has no file-write tools at all). Persist the text.
        target.write_text(content, encoding="utf-8")

    async def get_capabilities(self) -> list[str]:
        from cressida.orchestration.router import TASK_TYPE_ROUTE
        return [k for k, v in TASK_TYPE_ROUTE.items() if v == self.role]

    # ── Intra-task observability (optional, purely additive) ───────────────────

    async def _emit_tool_started(
        self, event_bus: EventBus | None, mission_id: str, task_id: str, tool_name: str, tool_input: Any = None,
    ) -> None:
        """Publish TOOL_USE_STARTED. Never raises — see publish_safe's docstring.

        ``tool_input`` is truncated/stringified defensively since it can be
        arbitrary provider-specific structure (a CLI's parsed JSON tool-call
        args, an SDK's typed object, ...) and this must never fail to publish
        just because some input didn't serialize cleanly.
        """
        await publish_safe(
            event_bus, EventType.TOOL_USE_STARTED,
            {
                "mission_id": mission_id, "task_id": task_id, "agent": self.role.value,
                "tool_name": tool_name, "tool_input": _safe_preview(tool_input),
            },
            source=self.role,
        )

    async def _emit_tool_completed(
        self, event_bus: EventBus | None, mission_id: str, task_id: str, tool_name: str,
        result: Any = None, is_error: bool = False,
    ) -> None:
        """Publish TOOL_USE_COMPLETED. Never raises — see publish_safe's docstring."""
        await publish_safe(
            event_bus, EventType.TOOL_USE_COMPLETED,
            {
                "mission_id": mission_id, "task_id": task_id, "agent": self.role.value,
                "tool_name": tool_name, "result_preview": _safe_preview(result), "is_error": is_error,
            },
            source=self.role,
        )

    # ── Abstract ──────────────────────────────────────────────────────────────

    @abstractmethod
    async def execute(self, state: MissionState, task: Task, event_bus: EventBus | None = None) -> Any:
        ...


def _safe_preview(value: Any, limit: int = 300) -> str:
    """Best-effort short string preview of a tool input/output for the live
    log — this is for a human glancing at `cressida watch`, not a faithful
    serialization, so any value that can't be stringified cleanly just
    becomes "<unprintable>" rather than raising."""
    try:
        text = value if isinstance(value, str) else json.dumps(value, default=str)
    except Exception:
        try:
            text = repr(value)
        except Exception:
            return "<unprintable>"
    return text[:limit]
