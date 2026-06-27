from __future__ import annotations

"""Provider auto-detection and agent class resolution.

Priority order (first match wins):
  1. CRESSIDA_PROVIDER env var (explicit override — always respected)
  2. ANTHROPIC_API_KEY + anthropic package installed
  3. OPENAI_API_KEY   + openai   package installed
  4. GEMINI_API_KEY or GOOGLE_API_KEY + google-generativeai installed
  5. GROQ_API_KEY     + openai   package installed (Groq uses OpenAI-compat)
  6. Ollama server reachable at localhost:11434 (no API key needed)

The CRESSIDA_PROVIDER env var (or --provider CLI flag) accepts:
  anthropic | openai | gemini | groq | ollama
"""

import os
import urllib.request
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cressida.core.interfaces import Agent
    from cressida.core import AgentRole
    from pathlib import Path


PROVIDER_ANTHROPIC = "anthropic"
PROVIDER_OPENAI    = "openai"
PROVIDER_GEMINI    = "gemini"
PROVIDER_GROQ      = "groq"
PROVIDER_OLLAMA    = "ollama"

_ALL_PROVIDERS = (
    PROVIDER_ANTHROPIC,
    PROVIDER_OPENAI,
    PROVIDER_GEMINI,
    PROVIDER_GROQ,
    PROVIDER_OLLAMA,
)


def detect_provider() -> str:
    """Return the name of the first available provider.

    Checks packages and environment variables in priority order.
    Raises RuntimeError if no provider is available.
    """
    # Explicit override always wins
    explicit = os.environ.get("CRESSIDA_PROVIDER", "").strip().lower()
    if explicit:
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

    # Ollama (local, no API key, no Python SDK needed)
    if _ollama_reachable():
        return PROVIDER_OLLAMA

    raise RuntimeError(
        "No LLM provider is available. Set one of:\n"
        "  ANTHROPIC_API_KEY  (+ pip install anthropic)\n"
        "  OPENAI_API_KEY     (+ pip install openai)\n"
        "  GEMINI_API_KEY     (+ pip install google-generativeai)\n"
        "  GROQ_API_KEY       (+ pip install openai)\n"
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
) -> Agent:
    """Instantiate the correct agent class for the given provider and role."""
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
