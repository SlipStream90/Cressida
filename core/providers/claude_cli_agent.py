from __future__ import annotations

"""Claude CLI provider agent.

Drives agents through the local `claude` command-line tool (Claude Code) in
non-interactive print mode, instead of calling the Anthropic HTTP API directly.

Why this exists
---------------
The API providers (anthropic / openai / gemini / groq) all require an API key in
the environment. This provider needs none: it shells out to the `claude` binary,
which authenticates with whatever the user is already logged into (Claude
subscription / OAuth / keychain). That makes Cressida runnable on a machine that
has the Claude CLI installed but no ANTHROPIC_API_KEY set.

How it works
------------
For each task we build the same system spec + context prompt every provider gets,
then invoke:

    claude -p --output-format json \
           --model <model> \
           --append-system-prompt-file <spec-file> \
           --add-dir <cressida-home> [--add-dir <target-project>] \
           --permission-mode acceptEdits

run with the target project as its working directory, feeding the (potentially
large) user prompt on stdin so we never hit OS command-line length limits.

The --add-dir / --permission-mode flags are not optional niceties. The CLI is
sandboxed to its working directory and, under -p, there is no human present to
approve an access prompt — so without them a read outside cwd is denied outright
and file writes are refused even inside the mission's own folder. That failure
mode is quiet: the agent returns its work as text, nothing reaches disk, and
every later phase re-derives context that was never written down. The CLI runs its own single-shot completion and
returns a JSON envelope whose `result` field is the final assistant text, which
we hand to ProviderAgentBase._write_output exactly like the other providers.

Notes / limitations
-------------------
- This is a text-completion backend: it does not expose Cressida's internal
  phase-gate tools (get_tools_for_role / execute_tool). The context builder
  already inlines every `reads` file into the prompt, so agents have what they
  need; BOND-style hard reject/escalate control flow is not available through
  the CLI path. For the standard research → spec → build → review pipeline this
  is sufficient.
- We deliberately do NOT pass --bare, because --bare forces ANTHROPIC_API_KEY
  auth and would defeat the whole point of using the CLI's own login.
"""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from cressida.core import AgentRole, MissionState, Task
from cressida.core.model_tiers import ROLE_MODEL, DEFAULT_MODEL
from cressida.core.paths import _check_project_dir_is_safe, cressida_home, project_dir
from cressida.core.providers.base import ProviderAgentBase

# How long (seconds) to wait on a single CLI completion before giving up.
_DEFAULT_TIMEOUT = float(os.environ.get("CRESSIDA_CLAUDE_CLI_TIMEOUT", "3600"))


def _fallback_cli_locations() -> list[Path]:
    """Well-known install locations to probe when `claude` isn't on PATH.

    The MCP server (and other launchers) can run with a stripped-down PATH that
    omits per-user bin dirs like ~/.local/bin, so `shutil.which` alone misses a
    perfectly good install. We probe the usual spots directly.
    """
    home = Path.home()
    names = ("claude.exe", "claude.cmd", "claude.bat", "claude")
    dirs = [
        home / ".local" / "bin",
        home / "bin",
        home / "AppData" / "Roaming" / "npm",          # npm global on Windows
        home / "AppData" / "Local" / "Programs" / "claude",
        Path("/usr/local/bin"),
        Path("/opt/homebrew/bin"),
    ]
    return [d / n for d in dirs for n in names]


def claude_cli_path() -> str | None:
    """Return the path to the `claude` binary, or None if it can't be found.

    Resolution order:
      1. CRESSIDA_CLAUDE_CLI explicit override (path or command name).
      2. `claude` on the current PATH (shutil.which).
      3. Well-known per-user/global install locations (PATH-independent).

    Step 3 exists because the MCP server can launch with a PATH that omits
    ~/.local/bin, which is where the Claude Code CLI installs by default.
    """
    override = os.environ.get("CRESSIDA_CLAUDE_CLI", "").strip()
    if override:
        if Path(override).exists():
            return override
        resolved = shutil.which(override)
        return resolved  # None if the override name isn't resolvable

    found = shutil.which("claude")
    if found:
        return found

    for candidate in _fallback_cli_locations():
        if candidate.exists():
            return str(candidate)

    return None


class ClaudeCLIAgent(ProviderAgentBase):
    """Agent that produces output by shelling out to the `claude` CLI."""

    _PROVIDER_NAME = "claude-cli"

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

        self._cli = cli_path or claude_cli_path()
        if not self._cli:
            raise RuntimeError(
                "Claude CLI provider selected but the `claude` binary was not found. "
                "Install the Claude CLI and ensure it is on PATH, or set "
                "CRESSIDA_CLAUDE_CLI to its full path."
            )

        # Explicit model > env override > per-role default (core/model_tiers.py).
        self._model = (
            model
            or os.environ.get("CRESSIDA_CLAUDE_MODEL")
            or ROLE_MODEL.get(role, DEFAULT_MODEL)
        )
        # The working directory is now chosen per task (the mission's target
        # project), not pinned to the install dir — see _invoke_blocking.
        self._timeout = timeout

    async def execute(self, state: MissionState, task: Task) -> Any:
        system_prompt = self._load_spec()
        user_prompt = self._build_user_prompt(state, task)

        # The CLI is sandboxed to its working directory, so it must be told about
        # both trees the mission legitimately spans: the target project and the
        # Cressida install (mission artifacts, specs, knowledge).
        target = project_dir(state)
        # M's commissioning plan (orchestration/commissioner.py) can right-size a
        # trivial mission onto the worker-tier model even for a strategic role —
        # a per-task override beats this agent's fixed per-role default.
        model = task.metadata.get("model_hint") or self._model
        text = await self._invoke(system_prompt, user_prompt, target, model)

        self._write_output(state.mission_id, task, text)
        return text

    # ── CLI invocation ──────────────────────────────────────────────────────

    async def _invoke(
        self, system_prompt: str, user_prompt: str, target: Path | None = None, model: str | None = None,
    ) -> str:
        import asyncio

        # Run the blocking subprocess in a thread so we don't stall the event
        # loop and stay portable across asyncio subprocess quirks on Windows.
        return await asyncio.get_event_loop().run_in_executor(
            None, self._invoke_blocking, system_prompt, user_prompt, target, model
        )

    def _invoke_blocking(
        self, system_prompt: str, user_prompt: str, target: Path | None = None, model: str | None = None,
    ) -> str:
        # The agent spec can be large; pass it as a file to avoid arg limits.
        spec_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        )
        try:
            spec_file.write(system_prompt)
            spec_file.close()

            target = (target or project_dir()).resolve()
            # Re-checked here, not just at mission-creation time: this is the
            # actual point where `target` becomes an --add-dir grant to a
            # bypassPermissions subprocess, so it's the boundary that matters.
            _check_project_dir_is_safe(target)
            home = cressida_home()

            cmd = [
                self._cli,
                "-p",
                "--output-format", "json",
                "--model", model or self._model,
                "--append-system-prompt-file", spec_file.name,
                # Grant the two trees a mission spans. Without --add-dir the CLI
                # refuses to read anything outside its cwd, and under -p there is
                # nobody to approve the prompt, so the read is denied outright.
                "--add-dir", str(home),
                # Under -p, ANY tool use (edits, Bash, WebSearch, MCP tools like
                # context7) requires approval that cannot be given non-interactively.
                # acceptEdits pre-grants file edits (Edit/Write/NotebookEdit) only —
                # everything else still needs an explicit allow. We deliberately do
                # NOT use bypassPermissions: that skips every check with no boundary
                # left at all. Instead we allow exactly what a mission needs to run
                # end to end (web research + package installs/tests/git via Bash)
                # and leave everything else (destructive commands, unlisted MCP
                # tools, etc.) subject to normal denial under -p.
                "--permission-mode", "acceptEdits",
            ]
            if target != home:
                cmd.extend(["--add-dir", str(target)])
            # --allowedTools is variadic (consumes args until the next `--flag`),
            # so it must come last — anything appended after it risks being
            # swallowed into the tool list instead of parsed as its own flag.
            cmd.extend([
                "--allowedTools",
                "WebSearch", "WebFetch",
                "mcp__context7__resolve-library-id", "mcp__context7__query-docs",
                "Bash",
            ])

            try:
                proc = subprocess.run(
                    cmd,
                    input=user_prompt,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=self._timeout,
                    # Run in the target project, not the Cressida install, so
                    # relative work the agent does lands where the mission acts.
                    cwd=str(target),
                )
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError(
                    f"Claude CLI timed out after {self._timeout}s for role {self.role.value}."
                ) from exc

            if proc.returncode != 0:
                raise RuntimeError(
                    f"Claude CLI exited {proc.returncode} for role {self.role.value}.\n"
                    f"stderr: {(proc.stderr or '').strip()[:2000]}"
                )

            return self._parse_output(proc.stdout)
        finally:
            try:
                os.unlink(spec_file.name)
            except OSError:
                pass

    @staticmethod
    def _parse_output(stdout: str) -> str:
        """Extract the final assistant text from `--output-format json` stdout."""
        raw = (stdout or "").strip()
        if not raw:
            return ""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # Not JSON (e.g. plain text fallback) — return as-is.
            return raw

        if isinstance(data, dict):
            if data.get("is_error"):
                raise RuntimeError(
                    f"Claude CLI reported an error: {data.get('result') or data}"
                )
            result = data.get("result")
            if isinstance(result, str):
                return result
            # Some versions nest the text differently; fall back to the blob.
            return json.dumps(data)
        return raw
