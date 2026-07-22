from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    import anthropic
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False

from cressida.core.interfaces import Agent
from cressida.core import AgentRole, MissionState, Task
from cressida.core.tools.definitions import get_tools_for_role, select_tools_for_task
from cressida.core.tools.implementations import execute_tool, PhaseRejectedError, PhaseEscalatedError
from cressida.orchestration.context_builder import ContextBuilder


# BOND and strategic agents use Opus for deeper reasoning.
# Implementation agents use Sonnet for throughput.
_ROLE_MODEL: dict[AgentRole, str] = {
    AgentRole.BOND:         "claude-opus-4-8",
    AgentRole.INTELLIGENCE: "claude-opus-4-8",
    AgentRole.Q:            "claude-opus-4-8",
    AgentRole.TANNER:       "claude-sonnet-4-6",
    AgentRole.BRANCH:       "claude-sonnet-4-6",
    AgentRole.ROOK:         "claude-sonnet-4-6",
    AgentRole.BOOTHROYD:    "claude-sonnet-4-6",
    AgentRole.MONEYPENNY:   "claude-sonnet-4-6",
    AgentRole.REVIEW:       "claude-sonnet-4-6",
}

_DEFAULT_MODEL = "claude-sonnet-4-6"
_MAX_TOOL_ROUNDS = 40  # safety cap on the agentic loop


class LLMAgentError(Exception):
    pass


class LLMAgent(Agent):
    """Concrete implementation of Agent that executes work via Claude LLM.

    Preserves all existing interfaces untouched:
    - Implements Agent ABC from core/interfaces.py
    - Reads agent spec from agents/<role>.md (unchanged markdown files)
    - Receives prompts built by the existing ContextBuilder
    - Publishes nothing directly — the TaskExecutor handles events

    The agentic loop:
    1. System prompt  = agent markdown spec
    2. User message   = ContextBuilder-assembled context
    3. Tool calls     = role-specific tools executed in Python
    4. Loop until stop_reason == end_turn or tool rounds exhausted
    5. Write output   = task.metadata['writes'] paths (or default outputs/)
    """

    def __init__(
        self,
        role: AgentRole,
        agents_dir: str | Path = "agents",
        cressida_root: str | Path = ".",
        max_tokens: int = 8192,
    ) -> None:
        if not _ANTHROPIC_AVAILABLE:
            raise LLMAgentError(
                "anthropic package is not installed. Run: pip install anthropic"
            )
        self.role = role
        self._agents_dir = Path(agents_dir)
        self._cressida_root = Path(cressida_root)
        self._context_builder = ContextBuilder(cressida_root)
        self._client = anthropic.Anthropic()
        self._model = _ROLE_MODEL.get(role, _DEFAULT_MODEL)
        self._max_tokens = max_tokens
        self._spec: str | None = None

    # ── Spec loading ─────────────────────────────────────────────────────────

    def _load_spec(self) -> str:
        if self._spec is None:
            spec_path = self._agents_dir / f"{self.role.value.lower()}.md"
            if spec_path.exists():
                self._spec = spec_path.read_text(encoding="utf-8")
            else:
                self._spec = (
                    f"You are the {self.role.value} agent in the CRESSIDA "
                    "multi-agent software engineering framework. Execute the task "
                    "assigned to you according to your role's responsibilities."
                )
        return self._spec

    # ── Core execution ───────────────────────────────────────────────────────

    async def execute(self, state: MissionState, task: Task) -> Any:
        """Run the agentic tool loop and return the final text output."""
        system_prompt = self._load_spec()
        user_prompt = self._context_builder.build_prompt(
            task_id=task.id,
            agent_role=task.agent or self.role,
            mission_id=state.mission_id,
            brief=state.brief,
            reads=task.metadata.get("reads", []),
            task_description=task.description,
            objectives=state.objectives if state.objectives else None,
        )

        # M (the dispatcher) may have pruned the toolset for this task to cut
        # token usage; select_tools_for_task honours that annotation and falls
        # open to the role's full toolset when none is declared.
        tools = select_tools_for_task(self.role, task.metadata)
        # A task can also be right-sized to a cheaper model via M's model_hint.
        model = task.metadata.get("model_hint") or self._model
        messages: list[dict[str, Any]] = [{"role": "user", "content": user_prompt}]
        rounds = 0

        while rounds < _MAX_TOOL_ROUNDS:
            kwargs: dict[str, Any] = {
                "model": model,
                "max_tokens": self._max_tokens,
                "system": system_prompt,
                "messages": messages,
            }
            if tools:
                kwargs["tools"] = tools

            response = self._client.messages.create(**kwargs)
            rounds += 1

            assistant_content = response.content
            messages.append({"role": "assistant", "content": assistant_content})

            if response.stop_reason == "end_turn":
                text = self._extract_text(assistant_content)
                self._write_output(state.mission_id, task, text)
                return text

            if response.stop_reason == "tool_use":
                tool_results: list[dict[str, Any]] = []
                for block in assistant_content:
                    if block.type != "tool_use":
                        continue
                    # PhaseRejectedError / PhaseEscalatedError propagate up intentionally
                    output = execute_tool(block.name, block.input, mission_id=state.mission_id)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": output if isinstance(output, str) else json.dumps(output),
                    })
                messages.append({"role": "user", "content": tool_results})
            else:
                # Unexpected stop reason — return whatever text we have
                return self._extract_text(assistant_content)

        # Tool round cap exceeded — return accumulated text
        last_text = self._extract_text(messages[-1].get("content", []))
        self._write_output(state.mission_id, task, last_text)
        return last_text

    async def get_capabilities(self) -> list[str]:
        from cressida.orchestration.router import TASK_TYPE_ROUTE
        return [k for k, v in TASK_TYPE_ROUTE.items() if v == self.role]

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _extract_text(content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for block in content:
                if hasattr(block, "text"):
                    parts.append(block.text)
                elif isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text", ""))
            return "\n".join(parts)
        return str(content)

    def _write_output(self, mission_id: str, task: Task, content: str) -> None:
        """Write agent output to the paths declared in task.metadata['writes'].

        Falls back to missions/<id>/outputs/<task_id>.md when no writes are declared.
        Preserves the existing convention: if a write path has no extension, it is
        treated as a directory and the file is named <task_id>.md inside it.
        """
        writes: list[str] = task.metadata.get("writes", [])
        if not writes:
            out_dir = Path("missions") / mission_id / "outputs"
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / f"{task.id}.md").write_text(content, encoding="utf-8")
            return

        for write_path in writes:
            resolved = write_path.replace("<mission_id>", mission_id)
            p = Path(resolved)
            if not p.is_absolute():
                p = Path.cwd() / p
            if p.suffix:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(content, encoding="utf-8")
            else:
                p.mkdir(parents=True, exist_ok=True)
                (p / f"{task.id}.md").write_text(content, encoding="utf-8")
