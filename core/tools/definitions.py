from __future__ import annotations

from typing import Any

from cressida.core import AgentRole


# ── Tool schemas (Claude API format) ────────────────────────────────────────

_READ_FILE: dict[str, Any] = {
    "name": "read_file",
    "description": "Read the full text of a file. Try relative-to-mission paths first, then absolute.",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path to read"},
        },
        "required": ["path"],
    },
}

_WRITE_FILE: dict[str, Any] = {
    "name": "write_file",
    "description": "Write content to a file, creating parent directories as needed.",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Destination file path"},
            "content": {"type": "string", "description": "Content to write"},
        },
        "required": ["path", "content"],
    },
}

_LIST_DIR: dict[str, Any] = {
    "name": "list_dir",
    "description": "List files and directories at a path.",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Directory path to list"},
        },
        "required": ["path"],
    },
}

_WEB_SEARCH: dict[str, Any] = {
    "name": "web_search",
    "description": (
        "Search the web for current information. Uses Brave Search (BRAVE_API_KEY env var) "
        "or DuckDuckGo as fallback."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "num_results": {
                "type": "integer",
                "description": "Number of results to return (max 10, default 5)",
                "default": 5,
            },
        },
        "required": ["query"],
    },
}

_RUN_SHELL: dict[str, Any] = {
    "name": "run_shell",
    "description": "Execute a shell command and return stdout + stderr. Use for running tests, linters, builds.",
    "input_schema": {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Shell command to run"},
            "cwd": {
                "type": "string",
                "description": "Working directory (optional, defaults to current directory)",
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (default 60)",
                "default": 60,
            },
        },
        "required": ["command"],
    },
}

_QUERY_MEMORY: dict[str, Any] = {
    "name": "query_memory",
    "description": (
        "Query CRESSIDA strategic memory for relevant past decisions, patterns, and architecture knowledge."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "keywords": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Keywords to search for in memory",
            },
            "task_type": {
                "type": "string",
                "description": "Optional task type filter (e.g. 'architecture', 'backend')",
                "default": "",
            },
            "top_k": {
                "type": "integer",
                "description": "Number of memory chunks to return (default 5)",
                "default": 5,
            },
        },
        "required": ["keywords"],
    },
}

_APPROVE_PHASE: dict[str, Any] = {
    "name": "approve_phase",
    "description": (
        "BOND ONLY. Approve the current mission phase. "
        "Call this when you judge the phase artifacts meet the mission success criteria."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "phase": {
                "type": "string",
                "description": "Phase being approved (e.g. 'planning', 'architecture', 'implementation', 'review')",
            },
            "confidence": {
                "type": "number",
                "description": "Confidence score 0.0–1.0",
            },
            "rationale": {
                "type": "string",
                "description": "Why this phase meets acceptance criteria",
            },
            "conditions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Any conditions or caveats on the approval (may be empty)",
            },
        },
        "required": ["phase", "confidence", "rationale"],
    },
}

_REJECT_PHASE: dict[str, Any] = {
    "name": "reject_phase",
    "description": (
        "BOND ONLY. Reject the current phase and block downstream execution. "
        "Call this when phase artifacts fail the mission success criteria."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "phase": {"type": "string", "description": "Phase being rejected"},
            "reason": {"type": "string", "description": "Specific reason for rejection"},
            "required_corrections": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Ordered list of corrections required before re-submission",
            },
        },
        "required": ["phase", "reason"],
    },
}

_ESCALATE: dict[str, Any] = {
    "name": "escalate",
    "description": (
        "BOND ONLY. Escalate to CRESSIDA COMMAND when autonomous confidence is below threshold. "
        "Creates an escalation file and blocks execution until a human resolves it."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "issue": {"type": "string", "description": "What requires human judgment"},
            "context": {"type": "string", "description": "Relevant context and options"},
            "recommended_action": {
                "type": "string",
                "description": "BOND's recommended resolution if the human agrees",
                "default": "",
            },
        },
        "required": ["issue", "context"],
    },
}


# ── Role → tools mapping ─────────────────────────────────────────────────────

_BASE: list[dict[str, Any]] = [_READ_FILE, _WRITE_FILE, _LIST_DIR]

_ROLE_TOOLS: dict[str, list[dict[str, Any]]] = {
    # M reads the brief/backlog and past plans, then commissions the mission.
    # It does not implement or run shells — read + memory is all it needs.
    "M":            [_READ_FILE, _LIST_DIR, _QUERY_MEMORY],
    "BOND":         _BASE + [_APPROVE_PHASE, _REJECT_PHASE, _ESCALATE],
    "INTELLIGENCE": _BASE + [_WEB_SEARCH, _QUERY_MEMORY],
    "Q":            _BASE,
    "TANNER":       _BASE,
    "BRANCH":       _BASE + [_RUN_SHELL],
    "ROOK":         _BASE + [_RUN_SHELL],
    "BOOTHROYD":    _BASE + [_RUN_SHELL],
    "MONEYPENNY":   _BASE + [_QUERY_MEMORY],
    "REVIEW":       _BASE + [_RUN_SHELL],
}

# Lookup by tool name — used by the dispatcher to expose a pruned toolset.
_TOOL_BY_NAME: dict[str, dict[str, Any]] = {
    t["name"]: t
    for t in (
        _READ_FILE, _WRITE_FILE, _LIST_DIR, _WEB_SEARCH, _RUN_SHELL,
        _QUERY_MEMORY, _APPROVE_PHASE, _REJECT_PHASE, _ESCALATE,
    )
}


def get_tools_for_role(role: AgentRole) -> list[dict[str, Any]]:
    return list(_ROLE_TOOLS.get(role.value, _BASE))


def get_tool_names_for_role(role: AgentRole) -> list[str]:
    """Names of every tool a role *could* use (the un-pruned superset)."""
    return [t["name"] for t in _ROLE_TOOLS.get(role.value, _BASE)]


def select_tools_for_task(role: AgentRole, task_metadata: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Return the tool schemas to actually expose for a task.

    Token-reduction lever: when M (the dispatcher) has annotated the task with a
    pruned ``toolset`` list in ``task.metadata``, only those tools are sent to the
    model — every unused tool schema we drop is input tokens saved on *every*
    round of the agentic loop.

    Falls open: if no ``toolset`` is declared, or a declared name is unknown, the
    role's full toolset is returned so behaviour is never worse than before.
    """
    full = get_tools_for_role(role)
    if not task_metadata:
        return full
    wanted = task_metadata.get("toolset")
    if not wanted:
        return full
    allowed = {t["name"] for t in full}
    pruned = [
        _TOOL_BY_NAME[name]
        for name in wanted
        if name in allowed and name in _TOOL_BY_NAME
    ]
    # Never starve an agent — if pruning left nothing usable, fall back to full.
    return pruned or full
