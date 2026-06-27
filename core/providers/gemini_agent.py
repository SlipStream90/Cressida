from __future__ import annotations

"""Google Gemini provider agent.

Uses the current google-genai SDK (import google.genai).
The older google-generativeai package is deprecated — this agent does NOT use it.

Install:  pip install google-genai
API key:  GEMINI_API_KEY or GOOGLE_API_KEY environment variable

Model selection (configurable via _GEMINI_MODELS):
  Strategic agents (BOND, INTELLIGENCE, Q): gemini-2.0-flash   (best balance)
  Implementation agents:                    gemini-2.0-flash   (fast + capable)

Override any model via the model_map constructor param.

Tool calling:
  FunctionDeclarations are built from Anthropic-format schemas via tool_adapters.
  The agentic loop drives responses and tool calls using the stateful Chat API.
  Tool results are fed back as FunctionResponsePart objects.
"""

import os
from pathlib import Path
from typing import Any

try:
    import google.genai as genai  # type: ignore[import]
    from google.genai import types as gtypes  # type: ignore[import]
    _GENAI_AVAILABLE = True
except ImportError:
    _GENAI_AVAILABLE = False

from cressida.core import AgentRole, MissionState, Task
from cressida.core.tools.definitions import get_tools_for_role
from cressida.core.tools.implementations import execute_tool
from cressida.core.providers.base import ProviderAgentBase, _MAX_TOOL_ROUNDS
from cressida.core.providers.tool_adapters import to_gemini_declarations


# ── Model table ───────────────────────────────────────────────────────────────

_STRATEGIC = {AgentRole.BOND, AgentRole.INTELLIGENCE, AgentRole.Q}

_GEMINI_MODELS: dict[AgentRole, str] = {
    r: ("gemini-2.0-flash" if r in _STRATEGIC else "gemini-2.0-flash")
    for r in AgentRole
}

# JSON Schema type → google.genai types.Type enum value (string)
_TYPE_MAP: dict[str, str] = {
    "string":  "STRING",
    "integer": "INTEGER",
    "number":  "NUMBER",
    "boolean": "BOOLEAN",
    "array":   "ARRAY",
    "object":  "OBJECT",
    "null":    "STRING",
}


class GeminiAgent(ProviderAgentBase):
    """Agent backed by Google Gemini via the google-genai SDK.

    Function calling is implemented using FunctionDeclarations.
    The agentic loop sends tool responses via Chat.send_message()
    as a list of FunctionResponsePart objects.
    """

    def __init__(
        self,
        role: AgentRole,
        model_map: dict[AgentRole, str] | None = None,
        agents_dir: str | Path = "agents",
        cressida_root: str | Path = ".",
        max_tokens: int = 8192,
    ) -> None:
        if not _GENAI_AVAILABLE:
            raise ImportError(
                "Gemini agent requires the google-genai package. "
                "Run: pip install google-genai"
            )
        super().__init__(role=role, agents_dir=agents_dir, cressida_root=cressida_root, max_tokens=max_tokens)

        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or ""
        self._client = genai.Client(api_key=api_key) if api_key else genai.Client()
        self._model = (model_map or _GEMINI_MODELS).get(role, "gemini-2.0-flash")

    # ── Tool schema builders ──────────────────────────────────────────────────

    def _build_tool(self, anthropic_tools: list[dict[str, Any]]) -> gtypes.Tool | None:
        """Convert Anthropic-format schemas into a single Gemini Tool object."""
        if not anthropic_tools:
            return None
        declarations = to_gemini_declarations(anthropic_tools)
        fn_decls: list[gtypes.FunctionDeclaration] = []
        for d in declarations:
            params = d.get("parameters")
            fn_decls.append(
                gtypes.FunctionDeclaration(
                    name=d["name"],
                    description=d.get("description", ""),
                    parameters=self._to_schema(params) if params else None,
                )
            )
        return gtypes.Tool(function_declarations=fn_decls)

    def _to_schema(self, d: dict[str, Any]) -> gtypes.Schema:
        """Recursively convert our Gemini-style type dict to gtypes.Schema."""
        raw_type = d.get("type", "STRING")
        type_str = raw_type if str(raw_type).isupper() else _TYPE_MAP.get(str(raw_type).lower(), "STRING")

        props: dict[str, gtypes.Schema] = {}
        for k, v in d.get("properties", {}).items():
            props[k] = self._to_schema(v)

        items = self._to_schema(d["items"]) if "items" in d else None

        return gtypes.Schema(
            type=type_str,
            description=d.get("description", ""),
            properties=props if props else None,
            required=d.get("required", []),
            items=items,
            enum=d.get("enum", []),
        )

    # ── Agentic loop ──────────────────────────────────────────────────────────

    async def execute(self, state: MissionState, task: Task) -> Any:
        system_prompt = self._load_spec()
        user_prompt = self._build_user_prompt(state, task)

        anthropic_tools = get_tools_for_role(self.role)
        gemini_tool = self._build_tool(anthropic_tools)

        config = gtypes.GenerateContentConfig(
            systemInstruction=system_prompt,
            maxOutputTokens=self._max_tokens,
            tools=[gemini_tool] if gemini_tool else [],
        )

        chat = self._client.chats.create(model=self._model, config=config)
        response = chat.send_message(user_prompt)

        for _ in range(_MAX_TOOL_ROUNDS):
            fn_calls = self._extract_fn_calls(response)

            if not fn_calls:
                text = self._extract_text(response)
                self._write_output(state.mission_id, task, text)
                return text

            tool_parts: list[gtypes.Part] = []
            for fn_call in fn_calls:
                fn_name = fn_call.name
                fn_args = dict(fn_call.args) if fn_call.args else {}
                # PhaseRejectedError / PhaseEscalatedError propagate intentionally
                result = execute_tool(fn_name, fn_args, mission_id=state.mission_id)
                tool_parts.append(
                    gtypes.Part(
                        function_response=gtypes.FunctionResponse(
                            name=fn_name,
                            response={"result": result},
                        )
                    )
                )

            response = chat.send_message(tool_parts)

        text = self._extract_text(response)
        self._write_output(state.mission_id, task, text)
        return text

    # ── Parsing helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _extract_fn_calls(response: Any) -> list[Any]:
        calls: list[Any] = []
        try:
            for part in response.candidates[0].content.parts:
                if hasattr(part, "function_call") and part.function_call and part.function_call.name:
                    calls.append(part.function_call)
        except Exception:
            pass
        return calls

    @staticmethod
    def _extract_text(response: Any) -> str:
        parts: list[str] = []
        try:
            for part in response.candidates[0].content.parts:
                if hasattr(part, "text") and part.text:
                    parts.append(part.text)
        except Exception:
            try:
                parts.append(response.text or "")
            except Exception:
                pass
        return "\n".join(parts)
