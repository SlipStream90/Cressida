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

import asyncio
import json
import logging
import os
import queue
import shutil
import signal
import sys
import subprocess
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from cressida.core import AgentRole, MissionState, Task
from cressida.core.model_tiers import ROLE_MODEL, DEFAULT_MODEL
from cressida.core.paths import _check_project_dir_is_safe, cressida_home, mission_dir, project_dir
from cressida.core.events import EventBus
from cressida.core.providers.base import ProviderAgentBase

# How long (seconds) to wait on a single CLI completion before giving up.
_DEFAULT_TIMEOUT = float(os.environ.get("CRESSIDA_CLAUDE_CLI_TIMEOUT", "3600"))

# The rest of the package has no established `logging` convention (grepping
# core/ and orchestration/ turns up zero `logging.getLogger`/`basicConfig`
# calls anywhere — diagnostics today are plain `print(f"[tag] ...")`). This is
# the first module to use the stdlib `logging` module, so it attaches its own
# StreamHandler rather than relying on root-logger config that may never
# happen: without this, `logger.info(...)` below would be silently swallowed
# (Python's logging "lastResort" handler only surfaces WARNING and above), and
# a CLI-subprocess failure would go back to being invisible — the exact
# problem this change exists to fix.
_logger = logging.getLogger("cressida.claude_cli")
if not _logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s: %(message)s"))
    _logger.addHandler(_handler)
    _logger.setLevel(logging.INFO)

# Tools granted to every mission subprocess with no per-call approval (see
# --allowedTools below). The line we hold: information retrieval and locally-
# reversible actions are fair game; anything with a consequence outside this
# machine — sending mail, spending money, publishing, merging/pushing to a
# remote, mutating a hosted database — is deliberately left OFF this list, so
# it's denied outright under non-interactive `-p` rather than silently granted.
# A mission needing one of those has to be a human decision, not a standing
# grant baked into every run. Add to this list only by the same test: "if this
# fires with nobody watching, does anything happen outside this machine?" If
# yes, it doesn't belong here.
_ALLOWED_TOOLS: tuple[str, ...] = (
    # Research / information — no side effects at all.
    "WebSearch", "WebFetch",
    "mcp__context7__resolve-library-id", "mcp__context7__query-docs",
    # Local execution — installs/tests/git all run against the granted
    # --add-dir trees. Not sandboxed to them (Bash isn't scoped by --add-dir),
    # but is the only way a mission actually builds; see the coordinator's
    # pre-mission git snapshot for the local reversibility this depends on.
    "Bash",
    # GitHub: read/search only. No create_*, push_files, merge_pull_request,
    # update_*, or fork/create_repository — those mutate a real remote repo,
    # which is an external system, not something this machine owns.
    "mcp__github__get_file_contents",
    "mcp__github__get_issue",
    "mcp__github__get_pull_request",
    "mcp__github__get_pull_request_comments",
    "mcp__github__get_pull_request_files",
    "mcp__github__get_pull_request_reviews",
    "mcp__github__get_pull_request_status",
    "mcp__github__list_commits",
    "mcp__github__list_issues",
    "mcp__github__list_pull_requests",
    "mcp__github__search_code",
    "mcp__github__search_issues",
    "mcp__github__search_repositories",
    "mcp__github__search_users",
    # Supabase: read/introspection only. No apply_migration, execute_sql,
    # deploy_edge_function, or branch mutation — those change a live hosted
    # project, which is an external system even when scoped to a branch.
    "mcp__supabase__list_edge_functions",
    "mcp__supabase__list_extensions",
    "mcp__supabase__list_migrations",
    "mcp__supabase__list_tables",
    "mcp__supabase__list_branches",
    "mcp__supabase__get_advisors",
    "mcp__supabase__get_logs",
    "mcp__supabase__get_edge_function",
    "mcp__supabase__get_project_url",
    "mcp__supabase__get_publishable_keys",
    "mcp__supabase__generate_typescript_types",
    "mcp__supabase__search_docs",
    # Deliberately excluded entirely (not narrowed, not partially allowed):
    # Apollo.io (CRM/email/purchasing — every tool has a real-world target),
    # Higgsfield (publishes content, spends credits, deploys publicly),
    # Gmail/Calendar/Drive (real personal accounts once authenticated),
    # Playwright (drives the user's actual logged-in browser session),
    # Stitch (unrelated to this stack; revisit if a mission actually needs it).
)

# Per-mission additions to the floor above go through Q (proposes, in
# ARCHITECTURE's mcp_tool_requests.json) then BOND (approves/rejects in its
# gate decision — see cli/commands.py's bond_tool_instructions and
# orchestration/coordinator.py's _check_bond_gate). Neither pass is trusted
# alone: BOND's approval is itself just an LLM judgment call, exactly the kind
# of thing indirect prompt injection targets (a fetched page or tool
# description engineered to talk the reviewer into approving something it
# shouldn't). This keyword filter is the backstop underneath both passes —
# names matching these substrings are stripped from the approved list
# regardless of what Q proposed or BOND approved, no exceptions. It is
# intentionally coarse (denylists are inherently incomplete against tools it
# has never seen); it exists to catch the obvious cases the review pipeline
# might still wave through, not to replace that pipeline.
_DANGEROUS_TOOL_KEYWORDS: tuple[str, ...] = (
    "send", "publish", "purchase", "buy", "billing", "transaction",
    "merge_pull_request", "push_files", "create_or_update_file",
    "create_repository", "fork_repository", "create_issue", "create_pull_request",
    "update_issue", "update_pull_request", "delete", "remove",
    "execute_sql", "apply_migration", "deploy", "reset_branch", "rebase_branch",
    "merge_branch", "email", "campaign", "authenticate", "webhook",
)


def filter_dynamic_tools(candidates: list[str]) -> tuple[list[str], list[tuple[str, str]]]:
    """Split a BOND-approved tool list into (safe, rejected) against the hard
    keyword backstop. ``rejected`` is a list of (tool_name, matched_keyword)
    pairs so the caller can log exactly what was stripped and why — this
    should never fire silently."""
    safe: list[str] = []
    rejected: list[tuple[str, str]] = []
    for name in candidates:
        lowered = name.lower()
        hit = next((kw for kw in _DANGEROUS_TOOL_KEYWORDS if kw in lowered), None)
        if hit:
            rejected.append((name, hit))
        elif name not in _ALLOWED_TOOLS:  # no point re-adding what's already granted
            safe.append(name)
    return safe, rejected


def _descendant_pids(root_pid: int) -> list[int]:
    """Return PIDs in the process tree rooted at ``root_pid`` on Windows."""
    try:
        import ctypes
        from ctypes import wintypes
        class _ProcessEntry32W(ctypes.Structure):
            _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                        ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_void_p),
                        ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                        ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG),
                        ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260)]
        k32=ctypes.windll.kernel32
        k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        k32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ProcessEntry32W)]
        k32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ProcessEntry32W)]
        snap=k32.CreateToolhelp32Snapshot(0x2, 0)
        if snap == ctypes.c_void_p(-1).value:
            raise OSError
        rows=[]
        try:
            e=_ProcessEntry32W(); e.dwSize=ctypes.sizeof(e)
            if k32.Process32FirstW(snap, ctypes.byref(e)):
                while True:
                    rows.append((int(e.th32ParentProcessID), int(e.th32ProcessID)))
                    if not k32.Process32NextW(snap, ctypes.byref(e)):
                        break
        finally:
            k32.CloseHandle(snap)
    except Exception:
        try:
            out=subprocess.run(["wmic","process","get","processid,parentprocessid"], capture_output=True, text=True, timeout=10).stdout
            rows=[]
            for line in out.splitlines()[1:]:
                parts=line.split()
                if len(parts)>=2 and parts[-1].isdigit() and parts[-2].isdigit():
                    rows.append((int(parts[-2]), int(parts[-1])))
        except Exception:
            return []
    children: dict[int, list[int]] = {}
    for ppid, pid in rows:
        children.setdefault(ppid, []).append(pid)
    found=[]; stack=[root_pid]
    while stack:
        cur=stack.pop(); found.append(cur); stack.extend(children.get(cur, []))
    return found


def _open_process_handle(pid: int, access: int):
    """Open a handle to ``pid`` with the given access rights, or None. Windows
    only — uses the kernel32 API directly so we can both terminate and wait on
    the exact (possibly reparented) process."""
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        return kernel32.OpenProcess(access, False, pid)
    except Exception:
        return None


def _pid_alive(pid: int) -> bool:
    """Deterministic check of whether a PID is still running (Windows). Opens a
    handle and asks for its exit code: a still-running process returns
    STILL_ACTIVE (259), an exited one returns its exit code (or fails to open).
    This avoids the async/race of polling `wmic`."""
    import ctypes
    kernel32 = ctypes.windll.kernel32
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = _open_process_handle(pid, PROCESS_QUERY_LIMITED_INFORMATION)
    if not handle:
        return False
    try:
        exit_code = ctypes.c_ulong()
        if kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return exit_code.value == 259  # STILL_ACTIVE
        return False
    finally:
        kernel32.CloseHandle(handle)


def _hard_kill_pid(pid: int) -> None:
    """Force-terminate a PID via the Windows API. More reliable than `taskkill`
    here because it does not race with the OS reparenting a grandchild off the
    original tree the moment its direct parent (cmd.exe) exits — we hold a
    handle to the exact PID and call TerminateProcess on it. TerminateProcess is
    asynchronous: the process is only actually gone once it has run down, which
    is why callers must wait on the handle (see _terminate_process_tree)."""
    PROCESS_TERMINATE = 0x0001
    handle = _open_process_handle(pid, PROCESS_TERMINATE)
    if handle:
        try:
            import ctypes
            k32 = ctypes.windll.kernel32
            k32.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
            k32.TerminateProcess.restype = ctypes.c_int
            k32.TerminateProcess(handle, 1)
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    else:
        # Fall back to taskkill if we couldn't open a handle (e.g. already gone).
        try:
            subprocess.run(
                ["taskkill", "/F", "/PID", str(pid)],
                capture_output=True, text=True, timeout=5,
            )
        except Exception:
            pass


def _wait_pid_gone(pid: int, timeout: float) -> bool:
    """Block until PID ``pid`` has actually exited (TerminateProcess completed),
    or ``timeout`` seconds elapse. Uses WaitForSingleObject on the process
    handle so we don't return while the OS is still tearing the process down —
    that teardown is exactly what closes the orphan's still-open stdout pipe and
    unblocks the reader threads waiting on it."""
    import ctypes
    kernel32 = ctypes.windll.kernel32
    kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel32.WaitForSingleObject.restype = ctypes.c_uint32
    SYNCHRONIZE = 0x00100000
    handle = _open_process_handle(pid, SYNCHRONIZE)
    if not handle:
        return True  # can't open -> treat as gone
    try:
        rc = kernel32.WaitForSingleObject(handle, int(timeout * 1000))
        return rc == 0  # WAIT_OBJECT_0 -> signalled (exited)
    finally:
        kernel32.CloseHandle(handle)


def _terminate_process_tree(proc: "subprocess.Popen[bytes]") -> None:
    """Kill ``proc`` and, on platforms where a single ``proc.kill()`` only
    terminates the direct child while its descendants keep running, the whole
    tree beneath it — and wait until it is actually gone.

    The `claude`/`opencode`/`codex`/`kilo` CLIs install on Windows as a thin
    ``*.cmd`` shim (``cmd.exe`` -> ``node.exe``/the real binary). A bare
    ``proc.kill()`` kills ``cmd.exe`` but leaves the actual agent process
    orphaned — still holding ``--permission-mode acceptEdits`` + Bash, still
    writing into the mission's project dir, after Cressida has already declared
    the task dead. So on Windows we escalate to ``taskkill /T /F`` (tree kill),
    which removes the whole chain; on POSIX we kill the process group instead of
    just the PID for the same reason (shell wrappers, ``|`` pipelines).

    ``taskkill /F`` is asynchronous — it returns before the targeted processes
    have necessarily exited — so after issuing the kill we wait (polling
    ``proc.poll()`` and, on Windows, re-issuing the tree kill against any
    survivors) until ``proc`` reports as dead or a short budget elapses. Without
    this wait the caller's reader threads can stay blocked on the orphaned
    child's still-open stdout pipe for the full duration of the child's work."""
    deadline = time.monotonic() + 10.0
    try:
        if sys.platform == "win32":
            targets = {proc.pid}
            while time.monotonic() < deadline:
                # Refresh before every tree kill so a shim child created after
                # the first snapshot is still included in the synchronous PID
                # fallback. taskkill is repeated while the root remains alive.
                targets.update(_descendant_pids(proc.pid))
                try:
                    result = subprocess.run(
                        ["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                        capture_output=True, text=True, timeout=5,
                    )
                except Exception:
                    result = None
                if result is None or result.returncode != 0:
                    for pid in targets:
                        _hard_kill_pid(pid)
                try:
                    proc.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    pass
                if all(_wait_pid_gone(pid, 0.3) for pid in targets) and proc.poll() is not None:
                    try:
                        proc.wait(timeout=0)
                    except Exception:
                        pass
                    return
                time.sleep(0.1)
            return
        else:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                pass
            while proc.poll() is None and time.monotonic() < deadline:
                time.sleep(0.2)
            return
    except Exception:
        pass
    # Last resort: whatever proc.kill() can reach.
    try:
        proc.kill()
    except Exception:
        pass


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


class _StreamParseFailure(Exception):
    """Internal signal only — never escapes _invoke_blocking.

    Raised when the `--output-format stream-json` invocation completed with
    exit code 0 (i.e. the CLI itself did not fail) but our incremental parser
    never saw a `type: "result"` line, so there is no reliable final text to
    return. This is the "streaming/incremental parsing failed for some
    reason" case called out in the hard constraint: rather than guessing at a
    result, the caller falls back to the original blocking
    `--output-format json` invocation, which is what determines success,
    failure, and output from that point on — identical to pre-streaming
    behavior. Real CLI failures (nonzero exit, timeout, spawn failure) raise
    RuntimeError/OSError directly instead of this, and are NOT retried, since
    a fallback invocation would just fail the same way (and re-running a
    successful-looking task and getting a different final answer would itself
    be a correctness problem).
    """


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
        # Normalise the "use the provider default" sentinels (0 or None) to
        # the module's _DEFAULT_TIMEOUT. Subprocess.run treats timeout=0 as
        # "time out immediately", not "no deadline", so passing a sentinel
        # through unmodified would break every task; None also means "no
        # deadline" there but, whichever arrived, the documented default
        # (env-overridable _DEFAULT_TIMEOUT) is what should apply.
        self._timeout = _DEFAULT_TIMEOUT if (timeout is None or timeout == 0) else timeout

    async def execute(self, state: MissionState, task: Task, event_bus: EventBus | None = None) -> Any:
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

        # BOND-approved per-mission tool grants (see _check_bond_gate in
        # orchestration/coordinator.py) already passed through the keyword
        # backstop once there; re-filtered here too since this is the actual
        # boundary where a name becomes an --allowedTools grant, and trusting
        # a single upstream filter is the same mistake as trusting a single
        # classification pass.
        approved = state.metadata.get("approved_mcp_tools") or []
        extra_tools, rejected = filter_dynamic_tools(list(approved))
        for name, keyword in rejected:
            print(f"[claude-cli] dynamic tool grant '{name}' blocked by keyword backstop ('{keyword}')")

        text = await self._invoke(
            system_prompt, user_prompt, target, model, extra_tools,
            mission_id=state.mission_id, task_id=task.id, event_bus=event_bus,
        )

        self._write_output(state.mission_id, task, text)
        return text

    # ── CLI invocation ──────────────────────────────────────────────────────

    async def _invoke(
        self, system_prompt: str, user_prompt: str, target: Path | None = None,
        model: str | None = None, extra_tools: list[str] | None = None,
        mission_id: str | None = None, task_id: str | None = None,
        event_bus: EventBus | None = None,
    ) -> str:
        # Run the blocking subprocess in a thread so we don't stall the event
        # loop and stay portable across asyncio subprocess quirks on Windows.
        # We grab the loop reference here (still on the event-loop thread) so
        # the executor thread can hand tool-use events back to it via
        # asyncio.run_coroutine_threadsafe — see _handle_stream_line below.
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._invoke_blocking, system_prompt, user_prompt, target, model, extra_tools,
            mission_id, task_id, event_bus, loop,
        )

    def _invoke_blocking(
        self, system_prompt: str, user_prompt: str, target: Path | None = None,
        model: str | None = None, extra_tools: list[str] | None = None,
        mission_id: str | None = None, task_id: str | None = None,
        event_bus: EventBus | None = None, loop: "asyncio.AbstractEventLoop | None" = None,
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
            # actual point where `target` becomes an --add-dir grant to the
            # subprocess, so it's the boundary that matters.
            _check_project_dir_is_safe(target)
            home = cressida_home()

            # Primary path: stream-json + --verbose, which emits one JSON object
            # per line as the agent works (assistant tool_use blocks, user
            # tool_result blocks, and a final `type: "result"` line whose shape
            # is identical to the single-blob `--output-format json` response).
            # This lets us surface TOOL_USE_STARTED/COMPLETED live instead of
            # only finding out what happened after the whole call returns.
            cmd = self._build_cmd(spec_file.name, target, home, model, extra_tools, "stream-json")

            _logger.info(
                "invoking Claude CLI (stream-json): role=%s model=%s cwd=%s timeout=%ss cmd=%s",
                self.role.value, model or self._model, target, self._timeout, cmd,
            )

            try:
                return self._invoke_streaming(
                    cmd, user_prompt, target, mission_id, task_id, event_bus, loop,
                )
            except _StreamParseFailure as exc:
                # Our incremental parser came up empty despite the CLI exiting
                # 0 — fall back to the original non-streaming invocation, which
                # is what determines success/failure/output from here on. This
                # is the safety net described in the hard constraint: streaming
                # is a purely additive side channel, never the thing that can
                # break a task.
                _logger.warning(
                    "stream-json parsing yielded no result for role=%s (%s); "
                    "falling back to non-streaming --output-format json",
                    self.role.value, exc,
                )
                cmd_json = self._build_cmd(spec_file.name, target, home, model, extra_tools, "json")
                return self._invoke_json_blocking(cmd_json, user_prompt, target, mission_id, task_id)
        finally:
            try:
                os.unlink(spec_file.name)
            except OSError:
                pass

    def _build_cmd(
        self, spec_file_name: str, target: Path, home: Path,
        model: str | None, extra_tools: list[str] | None, output_format: str,
    ) -> list[str]:
        cmd = [
            self._cli,
            "-p",
            "--output-format", output_format,
            "--model", model or self._model,
            "--append-system-prompt-file", spec_file_name,
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
        if output_format == "stream-json":
            # Required by the CLI for stream-json in print (-p) mode.
            cmd.append("--verbose")
        if target != home:
            cmd.extend(["--add-dir", str(target)])
        # --allowedTools is variadic (consumes args until the next `--flag`),
        # so it must come last — anything appended after it risks being
        # swallowed into the tool list instead of parsed as its own flag.
        # extra_tools are this mission's BOND-approved additions on top of
        # the static floor (see execute() above) — already passed through
        # the keyword backstop before reaching here.
        all_tools = list(_ALLOWED_TOOLS) + [t for t in (extra_tools or []) if t not in _ALLOWED_TOOLS]
        cmd.extend(["--allowedTools", *all_tools])
        return cmd

    # ── Non-streaming fallback (the original, pre-observability code path) ──

    def _invoke_json_blocking(
        self, cmd: list[str], user_prompt: str, target: Path,
        mission_id: str | None, task_id: str | None,
    ) -> str:
        """The original blocking `subprocess.run` + single-blob JSON parse.

        This is the exact behavior Cressida shipped before streaming
        observability existed. It is used directly whenever the CLI/model is
        invoked without a streaming attempt available, and as the fallback
        target if streaming's incremental parser fails to produce a usable
        result (see _StreamParseFailure above) — in both cases this function,
        not the streaming path, is what determines success/failure/output.
        """
        # subprocess.run(timeout=...) only kills the direct child on Windows,
        # orphaning descendant processes that keep running (and writing into
        # `target`) after we've declared the task dead — the same class of
        # bug fixed for the streaming path below via _terminate_process_tree.
        proc_popen = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            # Run in the target project, not the Cressida install, so
            # relative work the agent does lands where the mission acts.
            cwd=str(target),
        )
        try:
            stdout, stderr = proc_popen.communicate(input=user_prompt, timeout=self._timeout)
            proc = subprocess.CompletedProcess(cmd, proc_popen.returncode, stdout, stderr)
        except subprocess.TimeoutExpired as exc:
            _logger.error(
                "Claude CLI timed out: role=%s timeout=%ss cmd=%s",
                self.role.value, self._timeout, cmd,
            )
            _terminate_process_tree(proc_popen)
            try:
                proc_popen.wait(timeout=5)
            except Exception:
                pass
            finally:
                for _pipe in (proc_popen.stdout, proc_popen.stderr, proc_popen.stdin):
                    try:
                        if _pipe is not None:
                            _pipe.close()
                    except Exception:
                        pass
            raise RuntimeError(
                f"Claude CLI timed out after {self._timeout}s for role {self.role.value}."
            ) from exc
        except OSError as exc:
            # Distinct from a nonzero exit: the process never started at all
            # (binary missing, no exec permission, bad cwd, etc.), so there is
            # no `proc`/returncode/stderr to inspect — the OSError itself is
            # the only diagnostic signal, so it's logged before re-raising
            # rather than falling through to the returncode check below.
            _logger.error(
                "Claude CLI failed to spawn: role=%s cmd=%s error=%r",
                self.role.value, cmd, exc,
            )
            raise

        # `proc.returncode` is captured and logged raw, with its Python type,
        # before any formatting/interpretation — this is the value Python's
        # own subprocess module handed back for the Windows process exit
        # code, not something Cressida derives or transforms (grepping the
        # whole package finds no bitmasking, ctypes, or struct pack/unpack
        # touching returncode anywhere). If it ever again prints as
        # 4294967295 (0xFFFFFFFF) instead of a small negative number, that
        # value originates here, at the CPython/Windows boundary, not
        # downstream in coordinator.py or mcp_server.py.
        _logger.info(
            "Claude CLI returned: role=%s returncode=%r type=%s stdout_len=%d stderr_len=%d",
            self.role.value, proc.returncode, type(proc.returncode).__name__,
            len(proc.stdout or ""), len(proc.stderr or ""),
        )

        if proc.returncode != 0:
            log_path = self._write_failure_log(
                mission_id, task_id, cmd, proc.returncode, proc.stdout, proc.stderr,
            )
            _logger.error(
                "Claude CLI exited %r for role %s; full stdout/stderr written to %s",
                proc.returncode, self.role.value, log_path,
            )
            raise RuntimeError(
                f"Claude CLI exited {proc.returncode} for role {self.role.value}.\n"
                f"stderr: {(proc.stderr or '').strip()[:2000]}\n"
                f"Full log: {log_path}"
            )

        return self._parse_output(proc.stdout)

    # ── Streaming path (additive observability; falls back on any anomaly) ──

    def _invoke_streaming(
        self, cmd: list[str], user_prompt: str, target: Path,
        mission_id: str | None, task_id: str | None,
        event_bus: EventBus | None, loop: "asyncio.AbstractEventLoop | None",
    ) -> str:
        """Run the stream-json CLI invocation, emitting TOOL_USE_STARTED /
        TOOL_USE_COMPLETED as lines arrive, and return the final result text
        extracted from the terminal `type: "result"` line — using the exact
        same field extraction as the non-streaming `--output-format json`
        path (`_extract_result_text`), so the two paths agree byte-for-byte
        on equivalent underlying content.

        Failure/timeout handling mirrors `_invoke_json_blocking` exactly
        (same log messages, same RuntimeError text, same failure-log
        machinery) so a real CLI failure looks identical to a caller
        regardless of which path produced it. Only the "CLI succeeded but we
        never saw a parseable result line" case is special-cased via
        _StreamParseFailure, which the caller (_invoke_blocking) catches and
        turns into a full non-streaming retry.
        """
        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=str(target),
            )
        except OSError as exc:
            _logger.error(
                "Claude CLI failed to spawn: role=%s cmd=%s error=%r",
                self.role.value, cmd, exc,
            )
            raise

        # stdin/stdout/stderr are all handled on background threads so a large
        # prompt being written can't deadlock against stdout/stderr pipe
        # buffers filling up (the classic Popen gotcha that subprocess.run's
        # communicate() exists to avoid) — and so we can enforce a timeout
        # across a blocking readline() the way subprocess.run's own `timeout`
        # kwarg does.
        stdout_q: "queue.Queue[str | None]" = queue.Queue()
        stderr_chunks: list[str] = []

        def _feed_stdin() -> None:
            try:
                assert proc.stdin is not None
                proc.stdin.write(user_prompt)
            except Exception:
                pass
            finally:
                try:
                    assert proc.stdin is not None
                    proc.stdin.close()
                except Exception:
                    pass

        def _read_stdout() -> None:
            try:
                assert proc.stdout is not None
                for line in proc.stdout:
                    stdout_q.put(line)
            except Exception:
                pass
            finally:
                stdout_q.put(None)  # sentinel: EOF

        def _read_stderr() -> None:
            try:
                assert proc.stderr is not None
                for line in proc.stderr:
                    stderr_chunks.append(line)
            except Exception:
                pass

        threading.Thread(target=_feed_stdin, daemon=True).start()
        stdout_thread = threading.Thread(target=_read_stdout, daemon=True)
        stdout_thread.start()
        stderr_thread = threading.Thread(target=_read_stderr, daemon=True)
        stderr_thread.start()

        tool_names: dict[str, str] = {}
        result_obj: dict | None = None
        stdout_lines: list[str] = []
        start = time.monotonic()
        timed_out = False

        try:
            while True:
                # self._timeout is None only in the unusual case a caller
                # explicitly opted out of the per-provider default; the normal
                # path (create_agent's timeout=0 sentinel) is normalised to
                # _DEFAULT_TIMEOUT in __init__, so a real deadline is the
                # common case. "None = no deadline" is honored explicitly
                # here instead of subtracting a float from None, which raised
                # TypeError on every single task (see mission_20260810_185544).
                if self._timeout is None:
                    remaining = None
                else:
                    remaining = self._timeout - (time.monotonic() - start)
                    if remaining <= 0:
                        timed_out = True
                        break
                try:
                    line = stdout_q.get(timeout=1.0 if remaining is None else min(remaining, 1.0))
                except queue.Empty:
                    continue
                if line is None:
                    break
                stdout_lines.append(line)
                stripped = line.strip()
                if not stripped:
                    continue
                # Each line is parsed defensively: a malformed or unexpected line
                # must never break the read loop or affect the eventual result —
                # it's simply skipped for observability purposes. The final
                # result still comes only from a well-formed `type: "result"` line.
                try:
                    data = json.loads(stripped)
                except Exception:
                    continue
                try:
                    self._handle_stream_line(data, tool_names, event_bus, loop, mission_id, task_id)
                except Exception:
                    pass
                if isinstance(data, dict) and data.get("type") == "result":
                    result_obj = data

            if timed_out:
                # Kill the whole tree, not just the direct child — on Windows
                # the CLI is a *.cmd shim (cmd.exe -> node.exe); a bare
                # proc.kill() leaves the agent process orphaned and still
                # writing to the project dir (see _terminate_process_tree).
                _terminate_process_tree(proc)
                try:
                    proc.wait(timeout=5)
                except Exception:
                    pass
                _logger.error(
                    "Claude CLI timed out: role=%s timeout=%ss cmd=%s",
                    self.role.value, self._timeout, cmd,
                )
                raise RuntimeError(
                    f"Claude CLI timed out after {self._timeout}s for role {self.role.value}."
                )

            try:
                returncode = proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                _terminate_process_tree(proc)
                try:
                    proc.wait(timeout=5)
                except Exception:
                    pass
                _logger.error(
                    "Claude CLI timed out: role=%s timeout=%ss cmd=%s",
                    self.role.value, self._timeout, cmd,
                )
                raise RuntimeError(
                    f"Claude CLI timed out after {self._timeout}s for role {self.role.value}."
                )
            stdout_thread.join(timeout=5)
            stderr_thread.join(timeout=5)
        finally:
            # Release the underlying pipe/file handles on every exit path
            # (completion, timeout, parse failure, or an unexpected exception)
            # so we don't leak descriptors or leave reader threads blocked on
            # them. _terminate_process_tree above already reaped the child on
            # the timeout paths; these closes are the defensive backstop.
            for pipe in (proc.stdin, proc.stdout, proc.stderr):
                try:
                    if pipe is not None:
                        pipe.close()
                except Exception:
                    pass

        stdout_text = "".join(stdout_lines)
        stderr_text = "".join(stderr_chunks)

        _logger.info(
            "Claude CLI returned: role=%s returncode=%r type=%s stdout_len=%d stderr_len=%d",
            self.role.value, returncode, type(returncode).__name__,
            len(stdout_text), len(stderr_text),
        )

        if returncode != 0:
            log_path = self._write_failure_log(
                mission_id, task_id, cmd, returncode, stdout_text, stderr_text,
            )
            _logger.error(
                "Claude CLI exited %r for role %s; full stdout/stderr written to %s",
                returncode, self.role.value, log_path,
            )
            raise RuntimeError(
                f"Claude CLI exited {returncode} for role {self.role.value}.\n"
                f"stderr: {stderr_text.strip()[:2000]}\n"
                f"Full log: {log_path}"
            )

        if result_obj is None:
            raise _StreamParseFailure(
                "no `type: \"result\"` line found in stream-json output despite exit code 0"
            )

        return self._extract_result_text(result_obj)

    def _handle_stream_line(
        self, data: Any, tool_names: dict[str, str],
        event_bus: EventBus | None, loop: "asyncio.AbstractEventLoop | None",
        mission_id: str | None, task_id: str | None,
    ) -> None:
        """Look for tool_use/tool_result content blocks in one parsed
        stream-json line and fire the corresponding observability event.

        Runs on the executor thread (see _invoke), not the event loop thread,
        so events are handed off via asyncio.run_coroutine_threadsafe rather
        than awaited directly. Every step here is best-effort: an exception
        anywhere in this function must never propagate back into the read
        loop (the caller also wraps calls to this in try/except, belt and
        suspenders) since it sits entirely outside the CLI's actual
        success/failure/output determination.
        """
        if event_bus is None or loop is None or not isinstance(data, dict):
            return
        msg_type = data.get("type")
        if msg_type == "assistant":
            content = ((data.get("message") or {}).get("content")) or []
            if not isinstance(content, list):
                return
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue
                tool_id = block.get("id")
                name = block.get("name") or "unknown"
                if tool_id:
                    tool_names[tool_id] = name
                self._fire(loop, self._emit_tool_started(
                    event_bus, mission_id or "", task_id or "", name, block.get("input"),
                ))
        elif msg_type == "user":
            content = ((data.get("message") or {}).get("content")) or []
            if not isinstance(content, list):
                return
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_result":
                    continue
                tool_id = block.get("tool_use_id")
                name = tool_names.get(tool_id, "unknown") if tool_id else "unknown"
                is_error = bool(block.get("is_error"))
                self._fire(loop, self._emit_tool_completed(
                    event_bus, mission_id or "", task_id or "", name, block.get("content"), is_error,
                ))

    @staticmethod
    def _fire(loop: "asyncio.AbstractEventLoop", coro: Any) -> None:
        """Best-effort hand-off of an emit coroutine from a worker thread back
        to the event loop. Fire-and-forget: we don't wait on the resulting
        future, since blocking the read loop on event delivery would slow
        down (and could theoretically stall) the actual CLI interaction this
        is supposed to be a side observation of. `_emit_tool_started`/
        `_emit_tool_completed` never raise by construction, so the only
        failure mode here is the hand-off itself (e.g. the loop is closed),
        which is swallowed."""
        try:
            asyncio.run_coroutine_threadsafe(coro, loop)
        except Exception:
            try:
                coro.close()
            except Exception:
                pass

    # Kept as a method for the existing call sites; the implementation is the
    # module-level write_cli_failure_log below, shared with the other CLI
    # providers so no provider has to truncate a failure to 2000 chars.
    @staticmethod
    def _write_failure_log(
        mission_id: str | None, task_id: str | None, cmd: list[str],
        returncode: int, stdout: str | None, stderr: str | None,
    ) -> str:
        return write_cli_failure_log(mission_id, task_id, cmd, returncode, stdout, stderr)

    @staticmethod
    def _extract_result_text(data: dict) -> str:
        """Shared final-result extraction for a parsed CLI result object.

        Used by both `_parse_output` (the single-blob `--output-format json`
        shape) and `_invoke_streaming` (the last `type: "result"` line of
        `--output-format stream-json`) — real testing against the installed
        CLI (2.1.225) confirmed both shapes carry identical fields
        (`is_error`, `result`, ...), so routing both through this one
        function guarantees the two invocation paths agree on output for
        equivalent underlying content, per the hard "must not change the
        final result" constraint.
        """
        if data.get("is_error"):
            raise RuntimeError(
                f"Claude CLI reported an error: {data.get('result') or data}"
            )
        result = data.get("result")
        if isinstance(result, str):
            return result
        # Some versions nest the text differently; fall back to the blob.
        return json.dumps(data)

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
            return ClaudeCLIAgent._extract_result_text(data)
        return raw


def _as_text(value: object) -> str:
    """Best-effort str for partially-drained pipe output.

    A killed process's pipes can hand back bytes (or nothing) depending on how
    far the drain got, and this runs on the path that logs a failure — it must
    not raise while trying to record why something else went wrong.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).decode("utf-8", errors="replace")
    return "" if value is None else str(value)


def write_cli_failure_log(
    mission_id: str | None, task_id: str | None, cmd: list[str],
    returncode: int, stdout: str | None, stderr: str | None,
) -> str:
    """Persist the full, untruncated stdout/stderr of a failed CLI invocation.

    Every CLI provider's error message truncates output to 2000 characters,
    and these CLIs report their failures as JSON on stdout — so a failure
    whose cause sits past that cutoff was undiagnosable. Observed on
    missions/20260816-small-url-shortener-service-03: TANNER exited 1 and the
    captured stdout stopped mid-way through the agent's shell exploration,
    with the actual error event beyond the cut.

    Written under missions/<mission_id>/logs/. Falls back to a temp file if
    mission_id is unavailable, and never raises: a failure while logging a
    failure must not mask the original error.
    """
    try:
        if mission_id:
            out_dir = mission_dir(mission_id) / "logs"
        else:
            out_dir = Path(tempfile.gettempdir()) / "cressida_logs"
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        name = f"{task_id or 'unknown_task'}_{stamp}.log"
        log_path = out_dir / name
        log_path.write_text(
            "cmd: " + json.dumps(cmd) + "\n"
            f"returncode: {returncode!r} (type={type(returncode).__name__})\n"
            "\n--- stdout ---\n" + (stdout or "") +
            "\n--- stderr ---\n" + (stderr or ""),
            encoding="utf-8",
        )
        return str(log_path)
    except Exception as exc:
        _logger.error("failed to write CLI failure log to disk: %r", exc)
        return "(failed to write log file)"
