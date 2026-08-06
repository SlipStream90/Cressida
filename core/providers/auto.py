from __future__ import annotations

"""Provider auto-detection and agent class resolution.

Priority order (first match wins):
  1. CRESSIDA_PROVIDER env var (explicit override — always respected)
  2. ANTHROPIC_API_KEY + anthropic package installed
  3. OPENAI_API_KEY   + openai   package installed
  4. GEMINI_API_KEY or GOOGLE_API_KEY + google-generativeai installed
  5. GROQ_API_KEY     + openai   package installed (Groq uses OpenAI-compat)
  6. `claude` CLI installed on PATH (no API key — uses the CLI's own login)
  7. `opencode` CLI installed on PATH (no API key — uses OpenCode's auth)
  8. Ollama server reachable at localhost:11434 (no API key needed)

The CRESSIDA_PROVIDER env var (or --provider CLI flag) accepts:
  anthropic | openai | gemini | groq | ollama | claude_cli | opencode | codex
  (claude_cli also accepts the aliases: claude-cli, cli, claude)
  (opencode also accepts the alias: oc)
"""

import os
import urllib.request
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cressida.core.interfaces import Agent
    from cressida.core import AgentRole
    from pathlib import Path


PROVIDER_ANTHROPIC  = "anthropic"
PROVIDER_OPENAI     = "openai"
PROVIDER_GEMINI     = "gemini"
PROVIDER_GROQ       = "groq"
PROVIDER_OLLAMA     = "ollama"
PROVIDER_CLAUDE_CLI = "claude_cli"
PROVIDER_OPENCODE   = "opencode"
PROVIDER_CODEX      = "codex"

_ALL_PROVIDERS = (
    PROVIDER_ANTHROPIC,
    PROVIDER_OPENAI,
    PROVIDER_GEMINI,
    PROVIDER_GROQ,
    PROVIDER_OLLAMA,
    PROVIDER_CLAUDE_CLI,
    PROVIDER_OPENCODE,
    PROVIDER_CODEX,
)

# Accepted aliases for the Claude CLI provider (normalised in detect_provider).
_CLAUDE_CLI_ALIASES = {"claude_cli", "claude-cli", "claudecli", "cli", "claude"}

# Accepted aliases for the OpenCode provider.
_OPENCODE_ALIASES = {"opencode", "oc"}

# Accepted aliases for the Codex provider.
_CODEX_ALIASES = {"codex", "openai_codex", "codex_cli"}


def detect_provider() -> str:
    """Return the name of the first available provider.

    Checks packages and environment variables in priority order.
    Raises RuntimeError if no provider is available.
    """
    # Explicit override always wins
    explicit = os.environ.get("CRESSIDA_PROVIDER", "").strip().lower()
    if explicit:
        if explicit in _CLAUDE_CLI_ALIASES:
            return PROVIDER_CLAUDE_CLI
        if explicit in _OPENCODE_ALIASES:
            return PROVIDER_OPENCODE
        if explicit in _CODEX_ALIASES:
            return PROVIDER_CODEX
        if explicit not in _ALL_PROVIDERS:
            raise ValueError(
                f"Unknown CRESSIDA_PROVIDER={explicit!r}. "
                f"Valid options: {', '.join(_ALL_PROVIDERS)}"
            )
        return explicit

    # Anthropic
    if os.environ.get("ANTHROPIC_API_KEY") and _pkg("anthropic"):
        return PROVIDER_ANTHROPIC

    # OpenAI
    if os.environ.get("OPENAI_API_KEY") and _pkg("openai"):
        return PROVIDER_OPENAI

    # Gemini
    if (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")) and _pkg("google.genai"):
        return PROVIDER_GEMINI

    # Groq (uses openai SDK with different base_url)
    if os.environ.get("GROQ_API_KEY") and _pkg("openai"):
        return PROVIDER_GROQ

    # Claude CLI (no API key — uses the CLI's own login). Preferred over OpenCode
    # and Ollama when the `claude` binary is installed and no API key was found above.
    if _claude_cli_available():
        return PROVIDER_CLAUDE_CLI

    # OpenCode (no API key — uses OpenCode's own auth). Preferred over Codex/Ollama.
    if _opencode_available():
        return PROVIDER_OPENCODE

    # Codex CLI (no API key — uses Codex's own login). Preferred over Ollama.
    if _codex_available():
        return PROVIDER_CODEX

    # Ollama (local, no API key, no Python SDK needed)
    if _ollama_reachable():
        return PROVIDER_OLLAMA

    raise RuntimeError(
        "No LLM provider is available. Set one of:\n"
        "  ANTHROPIC_API_KEY  (+ pip install anthropic)\n"
        "  OPENAI_API_KEY     (+ pip install openai)\n"
        "  GEMINI_API_KEY     (+ pip install google-generativeai)\n"
        "  GROQ_API_KEY       (+ pip install openai)\n"
        "  Or install the Claude CLI (https://claude.com/claude-code) — no API key needed.\n"
        "  Or install OpenCode (https://opencode.ai) — no API key needed.\n"
        "  Or install the Codex CLI — no API key needed.\n"
        "  Or start Ollama locally (https://ollama.com) — no API key needed.\n"
        "  Or set CRESSIDA_PROVIDER explicitly to one of: "
        + ", ".join(_ALL_PROVIDERS)
    )


def create_agent(
    role: AgentRole,
    provider: str,
    agents_dir: str | Path = "agents",
    cressida_root: str | Path = ".",
    max_tokens: int = 8192,
    ollama_model: str = "llama3.2",
    ollama_host: str = "http://localhost:11434",
    timeout: float = 0,
) -> Agent:
    """Instantiate the correct agent class for the given provider and role."""
    # Normalise aliases passed directly (env-var path already does this).
    if provider in _CLAUDE_CLI_ALIASES:
        provider = PROVIDER_CLAUDE_CLI
    if provider in _OPENCODE_ALIASES:
        provider = PROVIDER_OPENCODE
    if provider in _CODEX_ALIASES:
        provider = PROVIDER_CODEX

    if provider == PROVIDER_ANTHROPIC:
        from cressida.core.llm_agent import LLMAgent
        return LLMAgent(role=role, agents_dir=agents_dir, cressida_root=cressida_root, max_tokens=max_tokens)

    if provider == PROVIDER_OPENAI:
        from cressida.core.providers.openai_agent import OpenAICompatibleAgent
        return OpenAICompatibleAgent(role=role, agents_dir=agents_dir, cressida_root=cressida_root, max_tokens=max_tokens)

    if provider == PROVIDER_GEMINI:
        from cressida.core.providers.gemini_agent import GeminiAgent
        return GeminiAgent(role=role, agents_dir=agents_dir, cressida_root=cressida_root, max_tokens=max_tokens)

    if provider == PROVIDER_GROQ:
        from cressida.core.providers.openai_agent import GroqAgent
        return GroqAgent(role=role, agents_dir=agents_dir, cressida_root=cressida_root, max_tokens=max_tokens)

    if provider == PROVIDER_OLLAMA:
        from cressida.core.providers.openai_agent import OllamaAgent
        return OllamaAgent(
            role=role,
            model=ollama_model,
            host=ollama_host,
            agents_dir=agents_dir,
            cressida_root=cressida_root,
            max_tokens=max_tokens,
        )

    if provider == PROVIDER_CLAUDE_CLI:
        from cressida.core.providers.claude_cli_agent import ClaudeCLIAgent
        return ClaudeCLIAgent(
            role=role,
            agents_dir=agents_dir,
            cressida_root=cressida_root,
            max_tokens=max_tokens,
            timeout=timeout if timeout > 0 else None,
        )

    if provider == PROVIDER_OPENCODE:
        from cressida.core.providers.opencode_agent import OpenCodeAgent
        return OpenCodeAgent(
            role=role,
            agents_dir=agents_dir,
            cressida_root=cressida_root,
            max_tokens=max_tokens,
            timeout=timeout if timeout > 0 else None,
        )

    if provider == PROVIDER_CODEX:
        from cressida.core.providers.codex_agent import CodexAgent
        return CodexAgent(
            role=role,
            agents_dir=agents_dir,
            cressida_root=cressida_root,
            max_tokens=max_tokens,
            timeout=timeout if timeout > 0 else None,
        )

    raise ValueError(f"Unknown provider: {provider!r}")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _pkg(name: str) -> bool:
    """Return True if a Python package is importable."""
    import importlib.util
    return importlib.util.find_spec(name) is not None


def _ollama_reachable(host: str = "http://localhost:11434", timeout: float = 1.0) -> bool:
    """Return True if an Ollama server is running at host."""
    try:
        urllib.request.urlopen(f"{host}/api/tags", timeout=timeout)
        return True
    except Exception:
        return False


def _claude_cli_available() -> bool:
    """Return True if the `claude` CLI binary is installed and actually working.

    Probes with a minimal request to catch rate-limited or broken installs.
    """
    from cressida.core.providers.claude_cli_agent import claude_cli_path
    path = claude_cli_path()
    if not path:
        return False
    # Quick probe: run a trivial completion and check for errors
    try:
        import subprocess
        proc = subprocess.run(
            [path, "-p", "--output-format", "json", "--model", "sonnet"],
            input="Reply with only the word OK",
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=15,
        )
        if proc.returncode != 0:
            return False
        import json
        data = json.loads(proc.stdout.strip())
        if data.get("is_error"):
            return False
        return True
    except Exception:
        return False


def _opencode_available() -> bool:
    """Return True if the `opencode` CLI binary is installed and locatable."""
    from cressida.core.providers.opencode_agent import opencode_cli_path
    return opencode_cli_path() is not None


def _codex_available() -> bool:
    """Return True if the `codex` CLI binary is installed and locatable."""
    from cressida.core.providers.codex_agent import codex_cli_path
    return codex_cli_path() is not None
