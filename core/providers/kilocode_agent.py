from __future__ import annotations

"""Kilo Code CLI provider agent.

Drives agents through the local `kilo` command-line tool (Kilo Code) in
non-interactive run mode, same shape as ClaudeCLIAgent / OpenCodeAgent /
CodexAgent.

Research summary (see the module-level report handed back with this change
for full citations)
--------------------------------------------------------------------------
Kilo Code (github.com/Kilo-Org/kilocode, published as `@kilocode/cli` on
npm) ships a real standalone CLI — it is not VS-Code/JetBrains-only. It is
an explicit fork of OpenCode ("Kilo CLI is a fork of OpenCode, enhanced to
work within the Kilo agentic engineering platform" — kilo.ai/docs), and
that lineage is confirmed by the installed binary itself: `kilo --help`
prints an `opencode` banner and its JSONL event schema
(`step_start`/`text`/`tool`/`step_finish`) is OpenCode's, not a new format.
Installing `@kilocode/cli` puts two equivalent binaries on PATH, `kilo` and
`kilocode` (verified locally: both resolve via `where kilo` / `where
kilocode` to the same package's bin/kilo entrypoint) — this module prefers
`kilo` since that's the name used throughout Kilo's own docs and cheatsheet.

`kilo --version` / `kilo run --help` (installed locally, v7.4.20) confirm
the exact flags used below:
    kilo run [message..] --format json --auto --dir <cwd> [--model <m>]
- `run [message..]` is the one-shot, scriptable, non-interactive command
  (the bare `kilo [project]` command launches the interactive TUI instead).
  When no `message` positional is given, `kilo run` reads the prompt from
  stdin (verified: `echo "say BANANA" | kilo run --format json --auto`
  returned "BANANA" as the model's answer) — used here instead of a command
  argument for the same reason CodexAgent/OpenCodeAgent do it: avoids
  Windows command-line length limits for a large agent-spec+context prompt.
- `--auto` auto-approves all permission prompts, Kilo's non-interactive
  pipeline flag (docs: "Kilo's autonomous mode allows it to run in
  automated environments like CI/CD pipelines without requiring user
  interaction"). Without it, a non-interactive run auto-*rejects* approval
  requests and exits 1 — --auto is required for this to ever get anything
  done unattended, mirroring Codex's `-s workspace-write` / Claude CLI's
  `--permission-mode acceptEdits`. `--dangerously-skip-permissions` also
  exists but is explicitly documented as bypassing *denied* permissions
  too, not just unset ones, so it's not used here.
- `--format json` switches from the default human-formatted TTY output to
  one-JSON-object-per-line streaming events (verified locally). This is
  what's parsed for both the final answer and (best-effort) tool-call
  observability below — see `_parse_output`.
- `--model provider/model` selects a model (`kilo models` lists what's
  configured); `--dir` sets the working directory the run executes in.
- There is no separate "system prompt" flag; like OpenCodeAgent, the agent
  spec is prepended to the task prompt rather than passed as its own flag.
- Auth: `kilo auth login`/`kilo auth list` manage the CLI's own stored
  credentials (`~/.local/share/kilo/auth.json`) — no ANTHROPIC_API_KEY or
  similar env var is required from Cressida's side, exactly like the other
  CLI providers. (Locally this ran successfully with zero stored
  credentials, via Kilo's own default free-tier routing — irrelevant to
  this integration, which only needs the CLI to exist and run.)

Notes / limitations
--------------------
- Like OpenCodeAgent, this is a text-completion backend: it does not expose
  Cressida's internal phase-gate tools. The context builder already inlines
  every `reads` file into the prompt.
- Tool-call observability is parsed from the completed JSONL output after
  `subprocess.run` returns, not from a live-streaming subprocess read. Kilo
  does stream JSONL, but a real live read (Popen + incremental
  stdout.readline()) adds failure surface (partial-line buffering, stall
  detection, an extra thread) for a coding-agent task that already blocks
  until done. Emitting the parsed tool-call events immediately after the
  process exits — in the same order Kilo produced them — gives `cressida
  watch` the same event content and ordering without changing how (or
  whether) the task's actual result is obtained; the primary execution path
  here is the same blocking subprocess.run() every other CLI provider uses.
  Per the hard constraint that observability must never affect
  functionality: `_emit_tool_started`/`_emit_tool_completed` are called
  from a best-effort loop wrapped in try/except (on top of `publish_safe`
  already never raising) strictly *after* the CLI's final text has been
  parsed out of `proc.stdout`, so nothing about them can change what
  `execute()` returns or whether it raises.
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
from cressida.core.providers.base import ProviderAgentBase, cli_lock
from cressida.core.providers.opencode_agent import parse_jsonl_stream
# Reuse the proven, platform-correct process-tree kill (kills the whole
# cmd.exe -> node.exe chain, not just the direct child) so a timed-out
# `kilo run` cannot leave an orphaned agent still editing the project.
from cressida.core.providers.claude_cli_agent import _terminate_process_tree


# How long (seconds) to wait on a single CLI completion before giving up.
_DEFAULT_TIMEOUT = float(os.environ.get("CRESSIDA_KILOCODE_TIMEOUT", "3600"))


def _fallback_kilocode_locations() -> list[Path]:
    """Well-known install locations to probe when neither `kilo` nor
    `kilocode` is on PATH."""
    home = Path.home()
    names = (
        "kilo.exe", "kilo.cmd", "kilo.ps1", "kilo",
        "kilocode.exe", "kilocode.cmd", "kilocode.ps1", "kilocode",
    )
    dirs = [
        home / ".local" / "bin",
        home / "bin",
        home / "AppData" / "Roaming" / "npm",   # npm global on Windows
        Path("/usr/local/bin"),
        Path("/opt/homebrew/bin"),
    ]
    return [d / n for d in dirs for n in names]


def kilocode_cli_path() -> str | None:
    """Return the path to the Kilo Code CLI binary, or None if not found.

    Resolution order:
      1. CRESSIDA_KILOCODE_CLI explicit override (path or command name).
      2. `kilo` on the current PATH (the name used in Kilo's own docs).
      3. `kilocode` on the current PATH (the package's alternate bin name —
         `npm install -g @kilocode/cli` installs both).
      4. Well-known per-user/global install locations (PATH-independent).
    """
    override = os.environ.get("CRESSIDA_KILOCODE_CLI", "").strip()
    if override:
        if Path(override).exists():
            return override
        return shutil.which(override)

    found = shutil.which("kilo")
    if found:
        return found

    found = shutil.which("kilocode")
    if found:
        return found

    for candidate in _fallback_kilocode_locations():
        if candidate.exists():
            return str(candidate)

    return None


class KiloCodeAgent(ProviderAgentBase):
    """Agent that produces output by shelling out to the Kilo Code CLI."""

    _PROVIDER_NAME = "kilocode"

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

        self._cli = cli_path or kilocode_cli_path()
        if not self._cli:
            raise RuntimeError(
                "Kilo Code provider selected but neither the `kilo` nor `kilocode` "
                "binary was found. Install the Kilo Code CLI "
                "(npm install -g @kilocode/cli) and ensure it is on PATH, or set "
                "CRESSIDA_KILOCODE_CLI to its full path."
            )

        # Explicit model > env override > let Kilo pick its own default.
        self._model = model or os.environ.get("CRESSIDA_KILOCODE_MODEL") or ""
        # Normalise the "use the provider default" sentinels (0 or None) to
        # the module's _DEFAULT_TIMEOUT so subprocess.run never receives a 0
        # (which would time out immediately) or a bare None here.
        self._timeout = _DEFAULT_TIMEOUT if (timeout is None or timeout == 0) else timeout

    async def execute(self, state: MissionState, task: Task, event_bus: EventBus | None = None) -> Any:
        system_prompt = self._load_spec()
        user_prompt = self._build_user_prompt(state, task)

        # Kilo has no separate system-prompt flag, so (like OpenCodeAgent)
        # the agent spec is prepended to the task prompt.
        full_prompt = f"[Agent Spec: {self.role.value}]\n\n{system_prompt}\n\n---\n\n[Task]\n\n{user_prompt}\n\n{self._artifact_boundary_prompt(state, task)}"

        text, tool_events = await self._invoke(full_prompt, project_dir(state))

        # Best-effort observability, strictly after the result is already
        # in hand — see module docstring's "Notes / limitations" for why
        # this can never affect execute()'s return value or control flow.
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

    @staticmethod
    def _artifact_boundary_prompt(state: MissionState, task: Task) -> str:
        writes = task.metadata.get("writes") or []
        if not writes:
            return ""
        files = "\n".join(f"- {path}" for path in writes)
        return (
            "## Cressida Artifact Boundary — mandatory\n"
            "Your native Kilo filesystem tools are sandboxed to the target project. "
            "Do not use native read/glob/write tools on the Cressida mission directory. "
            "Use the connected Cressida MCP tools `read_mission_file` and "
            "`write_mission_file` for mission artifacts, with this mission_id and a "
            "mission-relative filename. Publish every declared artifact before ending:\n"
            f"mission_id: `{state.mission_id}`\n{files}\n"
            "If those MCP tools are unavailable, do not probe the mission path; return "
            "the complete artifact contents in your final response so Cressida can persist them."
            + (" For BOND, do not call approve_phase/reject_phase/escalate unless those "
               "tools are visibly available; always write the required decision JSON."
               if task.agent == AgentRole.BOND else "")
        )

    # ── CLI invocation ──────────────────────────────────────────────────────

    async def _invoke(self, prompt: str, target: Path | None = None) -> tuple[str, list[dict[str, Any]]]:
        import asyncio

        # Serialized per CLI — see cli_lock() in providers/base.py for why
        # two concurrent invocations of this CLI fail on its own SQLite store.
        async with cli_lock("kilo"):
            return await asyncio.get_event_loop().run_in_executor(
                None, self._invoke_blocking, prompt, target
            )

    def _invoke_blocking(self, prompt: str, target: Path | None = None) -> tuple[str, list[dict[str, Any]]]:
        work_dir = str((target or project_dir()).resolve())
        cmd = [
            self._cli,
            "run",
            "--format", "json",
            "--auto",
            "--dir", work_dir,
        ]
        if self._model:
            cmd.extend(["--model", self._model])

        # Prompt goes over stdin (no message positional) — avoids Windows
        # command-line length limits, same as CodexAgent/OpenCodeAgent.
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
            # `kilo` installs on Windows as `kilo.cmd` (cmd.exe -> node.exe).
            # `subprocess.run` only kills the direct child (cmd.exe) on timeout,
            # orphaning the real agent process — still holding --auto and writing
            # into the mission's project dir after we've declared the task dead.
            # Kill the whole tree and reap it so its stdout pipe closes and the
            # handles are released before we raise.
            try:
                _terminate_process_tree(proc)
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
                f"Kilo Code CLI timed out after {self._timeout}s for role {self.role.value}."
            ) from exc

        if proc.returncode != 0:
            raise RuntimeError(
                f"Kilo Code CLI exited {proc.returncode} for role {self.role.value}.\n"
                f"stderr: {(stderr or '').strip()[:2000]}\n"
                f"stdout: {(stdout or '').strip()[:2000]}"
            )

        return self._parse_output(stdout)

    @staticmethod
    def _parse_output(stdout: str) -> tuple[str, list[dict[str, Any]]]:
        # Kilo's CLI is a fork of OpenCode and emits OpenCode's JSONL schema
        # verbatim, so both providers share one parser (see its docstring).
        return parse_jsonl_stream(stdout, "Kilo Code CLI")
