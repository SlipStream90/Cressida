from __future__ import annotations

"""OpenAI Codex CLI provider agent.

Drives agents through the local `codex` command-line tool in non-interactive
exec mode, same shape as ClaudeCLIAgent / OpenCodeAgent.

How it works
------------
    codex exec -C <target> -s workspace-write -o <tmpfile> -

The prompt is piped over stdin (`-` forces stdin read even though a prompt
argument is also accepted — kept consistent with the other two CLI
providers, which both avoid the command-line-length limit this way).
`-o/--output-last-message` writes just the agent's final text to a file,
which sidesteps parsing Codex's `--json` event stream (JSONL of turns/tool
calls) the way OpenCodeAgent has to for its own JSON output — there's
nothing here we need from the intermediate events.

`-s workspace-write` is Codex's coarse-grained equivalent of Claude CLI's
`--permission-mode acceptEdits`: edits and shell commands are allowed but
boxed to the working directory (plus --add-dir grants), no destructive
full-disk access, no per-tool allowlist (Codex has no tool-allowlist
mechanism, unlike Claude Code's --allowedTools).
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from cressida.core import AgentRole, MissionState, Task
from cressida.core.paths import cressida_home, project_dir
from cressida.core.events import EventBus
from cressida.core.providers.base import ProviderAgentBase
from cressida.core.providers.claude_cli_agent import _terminate_process_tree


_DEFAULT_TIMEOUT = float(os.environ.get("CRESSIDA_CODEX_TIMEOUT", "3600"))


def _fallback_codex_locations() -> list[Path]:
    """Well-known install locations to probe when `codex` isn't on PATH."""
    home = Path.home()
    names = ("codex.exe", "codex.cmd", "codex.ps1", "codex")
    dirs = [
        home / ".local" / "bin",
        home / "bin",
        home / "AppData" / "Roaming" / "npm",
        Path("/usr/local/bin"),
        Path("/opt/homebrew/bin"),
    ]
    return [d / n for d in dirs for n in names]


def codex_cli_path() -> str | None:
    """Return the path to the `codex` binary, or None if it can't be found.

    Resolution order:
      1. CRESSIDA_CODEX_CLI explicit override (path or command name).
      2. `codex` on the current PATH (shutil.which).
      3. Well-known per-user/global install locations (PATH-independent).
    """
    override = os.environ.get("CRESSIDA_CODEX_CLI", "").strip()
    if override:
        if Path(override).exists():
            return override
        return shutil.which(override)

    found = shutil.which("codex")
    if found:
        return found

    for candidate in _fallback_codex_locations():
        if candidate.exists():
            return str(candidate)

    return None


class CodexAgent(ProviderAgentBase):
    """Agent that produces output by shelling out to the `codex` CLI."""

    _PROVIDER_NAME = "codex"

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

        self._cli = cli_path or codex_cli_path()
        if not self._cli:
            raise RuntimeError(
                "Codex provider selected but the `codex` binary was not found. "
                "Install the Codex CLI and ensure it is on PATH, or set "
                "CRESSIDA_CODEX_CLI to its full path."
            )

        self._model = model or os.environ.get("CRESSIDA_CODEX_MODEL") or ""
        # Normalise the "use the provider default" sentinels (0 or None) to
        # the module's _DEFAULT_TIMEOUT so subprocess.run never receives a 0
        # (which would time out immediately) or a bare None here.
        self._timeout = _DEFAULT_TIMEOUT if (timeout is None or timeout == 0) else timeout

    async def execute(self, state: MissionState, task: Task, event_bus: EventBus | None = None) -> Any:
        system_prompt = self._load_spec()
        user_prompt = self._build_user_prompt(state, task)
        full_prompt = f"[Agent Spec: {self.role.value}]\n\n{system_prompt}\n\n---\n\n[Task]\n\n{user_prompt}"

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
        home = str(cressida_home())

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            out_path = f.name

        cmd = [
            self._cli, "exec",
            "-C", work_dir,
            "-s", "workspace-write",
            "--skip-git-repo-check",
            # Research-capable Codex calls need network access for their model
            # transport and current-source lookups; keep writes in the normal
            # workspace-write sandbox instead of bypassing the sandbox.
            "-c", "sandbox_workspace_write.network_access=true",
            "-o", out_path,
        ]
        if work_dir != home:
            cmd.extend(["--add-dir", home])
        # Codex persists its auth/session state under CODEX_HOME (normally
        # ~/.codex). The mission subprocess has its own workspace sandbox, so
        # granting only the project and Cressida home makes state_*.sqlite
        # appear read-only and Codex exits before answering. Grant the active
        # Codex home explicitly so nested Cressida missions can use the same
        # authenticated Codex installation as the parent process.
        codex_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).expanduser().resolve()
        if str(codex_home) not in {work_dir, home}:
            cmd.extend(["--add-dir", str(codex_home)])
        if self._model:
            cmd.extend(["-m", self._model])
        cmd.append("-")  # force stdin read for the prompt

        # subprocess.run(timeout=...) only kills the direct child on Windows,
        # orphaning `codex`'s own descendant processes to keep writing into
        # the mission's project dir after we've declared the task dead (same
        # issue fixed for KiloCodeAgent). Use Popen + the shared process-tree
        # killer so a timeout actually stops the whole tree.
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
            if proc.returncode != 0:
                raise RuntimeError(
                    f"Codex CLI exited {proc.returncode} for role {self.role.value}.\n"
                    f"stderr: {(stderr or '').strip()[:2000]}\n"
                    f"stdout: {(stdout or '').strip()[:2000]}"
                )
            out_file = Path(out_path)
            return out_file.read_text(encoding="utf-8").strip() if out_file.exists() else stdout.strip()
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
                f"Codex CLI timed out after {self._timeout}s for role {self.role.value}."
            ) from exc
        finally:
            try:
                os.unlink(out_path)
            except OSError:
                pass
