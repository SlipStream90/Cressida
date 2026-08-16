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
from cressida.core.events import EventBus
from cressida.core.providers.base import ProviderAgentBase
from cressida.core.providers.claude_cli_agent import _terminate_process_tree


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
        # Normalise the "use the provider default" sentinels (0 or None) to
        # the module's _DEFAULT_TIMEOUT so subprocess.run never receives a 0
        # (which would time out immediately) or a bare None here.
        self._timeout = _DEFAULT_TIMEOUT if (timeout is None or timeout == 0) else timeout

    async def execute(self, state: MissionState, task: Task, event_bus: EventBus | None = None) -> Any:
        system_prompt = self._load_spec()
        user_prompt = self._build_user_prompt(state, task)

        # Combine system prompt and user prompt for opencode
        # OpenCode doesn't have a separate system prompt flag like claude CLI,
        # so we prepend the agent spec to the user prompt.
        full_prompt = f"[Agent Spec: {self.role.value}]\n\n{system_prompt}\n\n---\n\n[Task]\n\n{user_prompt}"

        # Run against the mission's target project, not the Cressida install.
        text, tool_events = await self._invoke(full_prompt, project_dir(state))

        # Best-effort observability, strictly after the result is already in
        # hand — parsed from the completed JSONL output rather than a live
        # Popen read (same tradeoff KiloCodeAgent makes; see its docstring).
        # Wrapped in try/except on top of publish_safe's own never-raise
        # guarantee so this can never change execute()'s return value.
        try:
            for ev in tool_events:
                await self._emit_tool_started(
                    event_bus, state.mission_id, task.id, ev["tool"], tool_input=ev.get("input"),
                )
                await self._emit_tool_completed(
                    event_bus, state.mission_id, task.id, ev["tool"],
                    result=ev.get("output"), is_error=ev.get("is_error", False),
                )
        except Exception:
            pass

        self._write_output(state.mission_id, task, text)
        return text

    # ── CLI invocation ──────────────────────────────────────────────────────

    async def _invoke(self, prompt: str, target: Path | None = None) -> tuple[str, list[dict[str, Any]]]:
        import asyncio

        return await asyncio.get_event_loop().run_in_executor(
            None, self._invoke_blocking, prompt, target
        )

    def _invoke_blocking(self, prompt: str, target: Path | None = None) -> tuple[str, list[dict[str, Any]]]:
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
        # subprocess.run(timeout=...) only kills the direct child on Windows,
        # orphaning descendant processes to keep running after we've declared
        # the task dead (same issue fixed for KiloCodeAgent/CodexAgent). Use
        # Popen + the shared process-tree killer so a timeout actually stops
        # the whole tree.
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=work_dir,
        )
        try:
            stdout, stderr = proc.communicate(input=prompt, timeout=self._timeout)
        except subprocess.TimeoutExpired as exc:
            _terminate_process_tree(proc)
            try:
                proc.wait(timeout=5)
            except Exception:
                pass
            finally:
                for _pipe in (proc.stdout, proc.stderr, proc.stdin):
                    try:
                        if _pipe is not None:
                            _pipe.close()
                    except Exception:
                        pass
            raise RuntimeError(
                f"OpenCode CLI timed out after {self._timeout}s for role {self.role.value}."
            ) from exc

        if proc.returncode != 0:
            raise RuntimeError(
                f"OpenCode CLI exited {proc.returncode} for role {self.role.value}.\n"
                f"stderr: {(stderr or '').strip()[:2000]}\n"
                # The CLI reports its own failures as JSON on *stdout*
                # ({"type":"error",...}) and usually leaves stderr empty, so
                # omitting stdout here left every failure diagnosis-free.
                f"stdout: {(stdout or '').strip()[:2000]}"
            )

        return self._parse_output(stdout)

    @staticmethod
    def _parse_output(stdout: str) -> tuple[str, list[dict[str, Any]]]:
        return parse_jsonl_stream(stdout, "OpenCode CLI")


def parse_jsonl_stream(stdout: str, cli_name: str) -> tuple[str, list[dict[str, Any]]]:
    """Parse OpenCode's `--format json` JSONL into (final_text, tool_events).

    Shared with KiloCodeAgent: Kilo's CLI is a fork of OpenCode and emits
    this exact schema (its `--help` even prints an `opencode` banner), so
    both providers parse the same stream. Verified against a live
    `opencode run --format json`:

        {"type":"step_start", "part":{...}}
        {"type":"text",       "part":{"text":"..."}}
        {"type":"tool_use",   "part":{"tool":"bash",
                                      "state":{"status":"completed",
                                               "input":{...},"output":"..."}}}
        {"type":"step_finish","part":{...}}
        {"type":"error",      "error":{"data":{"message":"..."}}}

    Every payload hangs off `part` — nothing useful lives at the top level
    besides `type`. Each "text" event carries a full message rather than an
    incremental delta, so the last one is the final answer.
    """
    raw = (stdout or "").strip()
    if not raw:
        return "", []

    last_text = ""
    tool_events: list[dict[str, Any]] = []
    error_message: str | None = None
    saw_any_json = False

    for line in raw.splitlines():
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        saw_any_json = True

        evt_type = data.get("type")
        part = data.get("part") or {}

        if evt_type == "text":
            text = part.get("text")
            if isinstance(text, str) and text:
                last_text = text
        elif evt_type == "tool_use":
            state = part.get("state") or {}
            tool_events.append({
                "tool": part.get("tool") or "unknown",
                "input": state.get("input"),
                "output": state.get("output"),
                "is_error": state.get("status") == "error",
            })
        elif evt_type == "error":
            err = data.get("error") or {}
            msg = (err.get("data") or {}).get("message") or err.get("message")
            if msg:
                error_message = str(msg)

    if error_message and not last_text:
        raise RuntimeError(f"{cli_name} reported an error: {error_message}")

    if last_text:
        return last_text.strip(), tool_events

    if saw_any_json:
        # Valid JSONL stream but no text event (e.g. a tool-only run) —
        # nothing more to extract. Returning "" rather than the raw stream
        # matters: the caller writes this straight into the task's declared
        # output files, and a JSONL blob there looks like a real document
        # to every downstream agent.
        return "", tool_events

    # Not JSON at all — plain text (e.g. --format ignored). Return as-is
    # rather than silently dropping the output.
    return raw, []
