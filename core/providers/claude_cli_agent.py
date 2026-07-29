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

        text = await self._invoke(system_prompt, user_prompt, target, model, extra_tools)

        self._write_output(state.mission_id, task, text)
        return text

    # ── CLI invocation ──────────────────────────────────────────────────────

    async def _invoke(
        self, system_prompt: str, user_prompt: str, target: Path | None = None,
        model: str | None = None, extra_tools: list[str] | None = None,
    ) -> str:
        import asyncio

        # Run the blocking subprocess in a thread so we don't stall the event
        # loop and stay portable across asyncio subprocess quirks on Windows.
        return await asyncio.get_event_loop().run_in_executor(
            None, self._invoke_blocking, system_prompt, user_prompt, target, model, extra_tools
        )

    def _invoke_blocking(
        self, system_prompt: str, user_prompt: str, target: Path | None = None,
        model: str | None = None, extra_tools: list[str] | None = None,
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
            # extra_tools are this mission's BOND-approved additions on top of
            # the static floor (see execute() above) — already passed through
            # the keyword backstop before reaching here.
            all_tools = list(_ALLOWED_TOOLS) + [t for t in (extra_tools or []) if t not in _ALLOWED_TOOLS]
            cmd.extend(["--allowedTools", *all_tools])

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
