from __future__ import annotations

"""OpenCode CLI provider agent.

Drives agents through the local `opencode` command-line tool in non-interactive
run mode, similar to how ClaudeCLIAgent uses the `claude` CLI.

Why this exists
---------------
OpenCode is an open source AI coding agent that supports 75+ LLM providers.
Using it as a provider means Cressida can leverage OpenCode's model routing,
authentication, and provider management without requiring separate API keys
for each provider.

How it works
------------
For each task we build the same system spec + context prompt every provider gets,
then invoke:

    opencode run --format json --model <model> --dir <cwd> "<prompt>"

The CLI runs a single-shot completion and returns output which we parse and
hand to ProviderAgentBase._write_output exactly like the other providers.

Notes / limitations
-------------------
- This is a text-completion backend: it does not expose Cressida's internal
  phase-gate tools. For the standard research -> spec -> build -> review
  pipeline this is sufficient.
- The prompt is passed as a command argument (not stdin) for simplicity.
  For very large prompts, consider using --file to attach a prompt file.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from cressida.core import AgentRole, MissionState, Task
from cressida.core.paths import project_dir
from cressida.core.providers.base import ProviderAgentBase


# Strategic roles get the strongest model; workers get the faster one.
# These are OpenCode's default models when no model is specified.
_STRATEGIC = {AgentRole.BOND, AgentRole.INTELLIGENCE, AgentRole.LEITER, AgentRole.Q}
_STRATEGIC_MODEL = ""  # Let OpenCode pick its default
_WORKER_MODEL = ""     # Let OpenCode pick its default

# How long (seconds) to wait on a single CLI completion before giving up.
_DEFAULT_TIMEOUT = float(os.environ.get("CRESSIDA_OPENCODE_TIMEOUT", "3600"))


def _fallback_opencode_locations() -> list[Path]:
    """Well-known install locations to probe when `opencode` isn't on PATH."""
    home = Path.home()
    names = ("opencode.exe", "opencode.cmd", "opencode.bat", "opencode")
    dirs = [
        home / ".local" / "bin",
        home / "bin",
        home / "AppData" / "Roaming" / "npm",
        home / "AppData" / "Local" / "Programs" / "opencode",
        Path("/usr/local/bin"),
        Path("/opt/homebrew/bin"),
    ]
    return [d / n for d in dirs for n in names]


def opencode_cli_path() -> str | None:
    """Return the path to the `opencode` binary, or None if it can't be found.

    Resolution order:
      1. CRESSIDA_OPENCODE_CLI explicit override (path or command name).
      2. `opencode` on the current PATH (shutil.which).
      3. Well-known per-user/global install locations (PATH-independent).
    """
    override = os.environ.get("CRESSIDA_OPENCODE_CLI", "").strip()
    if override:
        if Path(override).exists():
            return override
        resolved = shutil.which(override)
        return resolved

    found = shutil.which("opencode")
    if found:
        return found

    for candidate in _fallback_opencode_locations():
        if candidate.exists():
            return str(candidate)

    return None


class OpenCodeAgent(ProviderAgentBase):
    """Agent that produces output by shelling out to the `opencode` CLI."""

    _PROVIDER_NAME = "opencode"

    def __init__(
        self,
        role: AgentRole,
        model: str | None = None,
        cli_path: str | None = None,
        agents_dir: str | Path = "agents",
        cressida_root: str | Path = ".",
        max_tokens: int = 8192,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        super().__init__(role=role, agents_dir=agents_dir, cressida_root=cressida_root, max_tokens=max_tokens)

        self._cli = cli_path or opencode_cli_path()
        if not self._cli:
            raise RuntimeError(
                "OpenCode provider selected but the `opencode` binary was not found. "
                "Install OpenCode (https://opencode.ai) and ensure it is on PATH, or set "
                "CRESSIDA_OPENCODE_CLI to its full path."
            )

        # Explicit model > env override > per-role default (empty = use OpenCode default).
        self._model = (
            model
            or os.environ.get("CRESSIDA_OPENCODE_MODEL")
            or (_STRATEGIC_MODEL if role in _STRATEGIC else _WORKER_MODEL)
            or ""
        )
        # Working directory is chosen per task (the mission's target project)
        # rather than pinned to the install dir — see _invoke_blocking.
        self._timeout = timeout

    async def execute(self, state: MissionState, task: Task) -> Any:
        system_prompt = self._load_spec()
        user_prompt = self._build_user_prompt(state, task)

        # Combine system prompt and user prompt for opencode
        # OpenCode doesn't have a separate system prompt flag like claude CLI,
        # so we prepend the agent spec to the user prompt.
        full_prompt = f"[Agent Spec: {self.role.value}]\n\n{system_prompt}\n\n---\n\n[Task]\n\n{user_prompt}"

        # Run against the mission's target project, not the Cressida install.
        text = await self._invoke(full_prompt, project_dir(state))

        self._write_output(state.mission_id, task, text)
        return text

    # ── CLI invocation ──────────────────────────────────────────────────────

    async def _invoke(self, prompt: str, target: Path | None = None) -> str:
        import asyncio

        return await asyncio.get_event_loop().run_in_executor(
            None, self._invoke_blocking, prompt, target
        )

    def _invoke_blocking(self, prompt: str, target: Path | None = None) -> str:
        work_dir = str((target or project_dir()).resolve())
        cmd = [
            self._cli,
            "run",
            "--format", "json",
            "--dir", work_dir,
        ]

        # Only add --model if a specific model is configured
        if self._model:
            cmd.extend(["--model", self._model])

        # Pass prompt via stdin to avoid Windows command line length limits.
        # OpenCode's run command reads from stdin when no message argument is given.
        try:
            proc = subprocess.run(
                cmd,
                input=prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self._timeout,
                cwd=work_dir,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"OpenCode CLI timed out after {self._timeout}s for role {self.role.value}."
            ) from exc

        if proc.returncode != 0:
            raise RuntimeError(
                f"OpenCode CLI exited {proc.returncode} for role {self.role.value}.\n"
                f"stderr: {(proc.stderr or '').strip()[:2000]}"
            )

        return self._parse_output(proc.stdout)

    @staticmethod
    def _parse_output(stdout: str) -> str:
        """Extract the assistant text from `--format json` stdout.

        OpenCode outputs JSONL (one JSON object per line). We look for
        the last message-type event with content, filtering out tool calls
        and other non-text events.
        """
        raw = (stdout or "").strip()
        if not raw:
            return ""

        lines = raw.splitlines()
        last_content = ""

        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                # Not JSON — might be plain text output (skip raw JSONL lines)
                if not line.startswith("{"):
                    last_content = line
                continue

            if not isinstance(data, dict):
                continue

            # Skip tool_use events (these are agent actions, not text output)
            if data.get("type") == "tool_use":
                continue
            if data.get("type") == "tool_result":
                continue

            # Look for message events with content
            if data.get("type") == "message" and data.get("content"):
                content = data["content"]
                # Filter out tool_use blocks from content
                if isinstance(content, list):
                    text_parts = [
                        part.get("text", "")
                        for part in content
                        if isinstance(part, dict) and part.get("type") == "text"
                    ]
                    content = "\n".join(text_parts)
                if content:
                    last_content = content

            # Also handle simpler result format
            elif data.get("result"):
                last_content = data["result"]
            elif data.get("text"):
                last_content = data["text"]

        if last_content:
            return last_content.strip()

        # Fallback: try to extract any text-looking content from the raw output
        # Look for markdown-formatted content (common in agent outputs)
        if "```" in raw or "# " in raw:
            return raw

        return ""
