from __future__ import annotations

"""OpenAI-compatible provider agent.

Works with any API that implements the OpenAI chat completions spec:
  - OpenAI (GPT-4o, GPT-4o-mini, o1, ...)
  - Groq  (llama-3.3-70b-versatile, mixtral-8x7b, ...)
  - Ollama (llama3.2, qwen2.5, phi4, ...) — local, no API key
  - Any other OpenAI-compatible endpoint (LM Studio, vLLM, etc.)

The three concrete subclasses — GroqAgent and OllamaAgent — simply set
different defaults so the factory can instantiate them without extra config.

Tool call handling:
  OpenAI/Groq/Ollama all return tool calls in the same structure:
    response.choices[0].message.tool_calls  →  [ChatCompletionMessageToolCall, ...]
  Results are fed back as role="tool" messages.
"""

import json
import os
from pathlib import Path
from typing import Any

try:
    from openai import OpenAI as _OpenAIClient
    _OPENAI_SDK_AVAILABLE = True
except ImportError:
    _OPENAI_SDK_AVAILABLE = False

from cressida.core import AgentRole, MissionState, Task
from cressida.core.tools.definitions import get_tools_for_role
from cressida.core.tools.implementations import execute_tool
from cressida.core.providers.base import ProviderAgentBase, _MAX_TOOL_ROUNDS
from cressida.core.providers.tool_adapters import to_openai_list


# ── Model tables ─────────────────────────────────────────────────────────────

_STRATEGIC = {AgentRole.BOND, AgentRole.INTELLIGENCE, AgentRole.Q}

_OPENAI_MODELS: dict[AgentRole, str] = {
    r: ("gpt-4o" if r in _STRATEGIC else "gpt-4o-mini")
    for r in AgentRole
}

_GROQ_MODELS: dict[AgentRole, str] = {
    r: ("llama-3.3-70b-versatile" if r in _STRATEGIC else "llama-3.1-8b-instant")
    for r in AgentRole
}

_OLLAMA_DEFAULT_MODEL = "llama3.2"


class OpenAICompatibleAgent(ProviderAgentBase):
    """Agent that drives work via any OpenAI-compatible chat completions API.

    Parameters
    ----------
    role           : AgentRole
    base_url       : API base URL. None → uses the openai SDK default (api.openai.com).
    api_key_env    : Environment variable name that holds the API key.
                     Pass None for APIs that need no key (Ollama).
    model_map      : role → model-name override dict. Falls back to gpt-4o / gpt-4o-mini.
    agents_dir     : Path to directory containing agent spec .md files.
    cressida_root  : Root used by ContextBuilder for resolving read paths.
    max_tokens     : Max tokens per LLM call.
    """

    _PROVIDER_NAME = "openai-compatible"

    def __init__(
        self,
        role: AgentRole,
        base_url: str | None = None,
        api_key_env: str | None = "OPENAI_API_KEY",
        model_map: dict[AgentRole, str] | None = None,
        agents_dir: str | Path = "agents",
        cressida_root: str | Path = ".",
        max_tokens: int = 8192,
    ) -> None:
        if not _OPENAI_SDK_AVAILABLE:
            raise ImportError(
                f"{self._PROVIDER_NAME} agent requires the openai package. "
                "Run: pip install openai"
            )
        super().__init__(role=role, agents_dir=agents_dir, cressida_root=cressida_root, max_tokens=max_tokens)

        api_key = os.environ.get(api_key_env, "no-key") if api_key_env else "no-key"
        self._client = _OpenAIClient(api_key=api_key, base_url=base_url)
        self._model_map = model_map or _OPENAI_MODELS
        self._model = self._model_map.get(role, "gpt-4o-mini")

    async def execute(self, state: MissionState, task: Task) -> Any:
        system_prompt = self._load_spec()
        user_prompt = self._build_user_prompt(state, task)

        anthropic_tools = get_tools_for_role(self.role)
        openai_tools = to_openai_list(anthropic_tools) if anthropic_tools else []

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ]

        for _ in range(_MAX_TOOL_ROUNDS):
            kwargs: dict[str, Any] = {
                "model":      self._model,
                "messages":   messages,
                "max_tokens": self._max_tokens,
            }
            if openai_tools:
                kwargs["tools"] = openai_tools

            response = self._client.chat.completions.create(**kwargs)
            choice = response.choices[0]
            msg = choice.message

            # Append assistant turn (preserves tool_calls field if present)
            messages.append(msg.model_dump(exclude_unset=False))

            finish = choice.finish_reason

            if finish == "stop" or finish == "end_turn":
                text = msg.content or ""
                self._write_output(state.mission_id, task, text)
                return text

            if finish == "tool_calls" and msg.tool_calls:
                for tc in msg.tool_calls:
                    fn_name = tc.function.name
                    try:
                        fn_args = json.loads(tc.function.arguments or "{}")
                    except json.JSONDecodeError:
                        fn_args = {}
                    # PhaseRejectedError / PhaseEscalatedError propagate intentionally
                    result = execute_tool(fn_name, fn_args, mission_id=state.mission_id)
                    messages.append({
                        "role":         "tool",
                        "tool_call_id": tc.id,
                        "content":      result,
                    })
            else:
                # length / content_filter / unexpected
                text = msg.content or ""
                self._write_output(state.mission_id, task, text)
                return text

        # Loop cap exceeded
        last = messages[-1].get("content", "")
        text = last if isinstance(last, str) else json.dumps(last)
        self._write_output(state.mission_id, task, text)
        return text


# ── Concrete sub-providers ────────────────────────────────────────────────────

class GroqAgent(OpenAICompatibleAgent):
    """Agent backed by Groq's ultra-fast inference API.

    Requires: pip install groq   OR   pip install openai
    API key:  GROQ_API_KEY environment variable
    """

    _PROVIDER_NAME = "groq"

    def __init__(
        self,
        role: AgentRole,
        agents_dir: str | Path = "agents",
        cressida_root: str | Path = ".",
        max_tokens: int = 8192,
    ) -> None:
        super().__init__(
            role=role,
            base_url="https://api.groq.com/openai/v1",
            api_key_env="GROQ_API_KEY",
            model_map=_GROQ_MODELS,
            agents_dir=agents_dir,
            cressida_root=cressida_root,
            max_tokens=max_tokens,
        )


class OllamaAgent(OpenAICompatibleAgent):
    """Agent backed by a local Ollama server (no API key, no cloud calls).

    Requires:
      - Ollama installed and running: https://ollama.com
      - A tool-capable model pulled, e.g.: ollama pull llama3.2
      - pip install openai

    Tool support varies by model. llama3.1+, qwen2.5, phi4, and
    mistral-nemo are known to support function calling.
    """

    _PROVIDER_NAME = "ollama"

    def __init__(
        self,
        role: AgentRole,
        model: str = _OLLAMA_DEFAULT_MODEL,
        host: str = "http://localhost:11434",
        agents_dir: str | Path = "agents",
        cressida_root: str | Path = ".",
        max_tokens: int = 8192,
    ) -> None:
        super().__init__(
            role=role,
            base_url=f"{host}/v1",
            api_key_env=None,
            model_map={r: model for r in AgentRole},  # all roles use same model
            agents_dir=agents_dir,
            cressida_root=cressida_root,
            max_tokens=max_tokens,
        )
