from __future__ import annotations

"""Convert canonical Anthropic-format tool schemas to provider-specific formats.

definitions.py holds one canonical representation per tool (Anthropic format).
This module converts those on demand — no duplication of tool definitions.

Anthropic canonical format:
    {
        "name": "read_file",
        "description": "...",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string", ...}},
            "required": ["path"]
        }
    }

OpenAI format:
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "...",
            "parameters": {     ← same shape as input_schema
                "type": "object",
                "properties": {...},
                "required": [...]
            }
        }
    }

Gemini format (google-generativeai SDK):
    {
        "name": "read_file",
        "description": "...",
        "parameters": {         ← type strings are UPPERCASE
            "type": "OBJECT",
            "properties": {
                "path": {"type": "STRING", "description": "..."}
            },
            "required": ["path"]
        }
    }
    Wrapped in: genai.protos.Tool(function_declarations=[...])
"""

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    pass  # avoid hard import of genai at module level


# ── JSON Schema type → Gemini type string ────────────────────────────────────

_JSON_TO_GEMINI: dict[str, str] = {
    "string":  "STRING",
    "integer": "INTEGER",
    "number":  "NUMBER",
    "boolean": "BOOLEAN",
    "array":   "ARRAY",
    "object":  "OBJECT",
    "null":    "STRING",  # Gemini has no null type; coerce to string
}


def _schema_to_gemini(schema: dict[str, Any]) -> dict[str, Any]:
    """Recursively convert a JSON Schema dict to Gemini parameter format."""
    result: dict[str, Any] = {}

    raw_type = schema.get("type", "string")
    result["type"] = _JSON_TO_GEMINI.get(str(raw_type).lower(), "STRING")

    if "description" in schema:
        result["description"] = schema["description"]

    if "properties" in schema:
        result["properties"] = {
            k: _schema_to_gemini(v) for k, v in schema["properties"].items()
        }

    if "required" in schema:
        result["required"] = schema["required"]

    if "items" in schema:
        result["items"] = _schema_to_gemini(schema["items"])

    if "enum" in schema:
        result["enum"] = schema["enum"]

    return result


# ── Converters ────────────────────────────────────────────────────────────────

def to_openai(tool: dict[str, Any]) -> dict[str, Any]:
    """Convert one Anthropic-format tool schema to OpenAI function-call format."""
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool.get("description", ""),
            "parameters": tool.get("input_schema", {"type": "object", "properties": {}}),
        },
    }


def to_openai_list(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [to_openai(t) for t in tools]


def to_gemini_declarations(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert a list of Anthropic-format tool schemas to Gemini FunctionDeclaration dicts."""
    declarations = []
    for tool in tools:
        decl: dict[str, Any] = {
            "name": tool["name"],
            "description": tool.get("description", ""),
        }
        raw_schema = tool.get("input_schema", {})
        if raw_schema:
            decl["parameters"] = _schema_to_gemini(raw_schema)
        declarations.append(decl)
    return declarations


def to_gemini_tool(tools: list[dict[str, Any]]) -> Any:
    """Return a google.genai types.Tool built from Anthropic-format schemas.

    Returns None if google-genai is not installed (callers can skip tool use gracefully).
    """
    try:
        from google.genai import types as gtypes  # type: ignore[import]

        declarations = to_gemini_declarations(tools)
        fn_decls = [
            gtypes.FunctionDeclaration(
                name=d["name"],
                description=d.get("description", ""),
            )
            for d in declarations
        ]
        return gtypes.Tool(function_declarations=fn_decls)
    except Exception:
        return None
