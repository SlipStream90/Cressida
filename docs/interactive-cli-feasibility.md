# Feasibility: an interactive CRESSIDA CLI

## Current state

`cli/__init__.py` builds a single argparse parser with subcommands (`run`,
`status`, `dashboard`, `daemon`, `feedback`, `rewards`, `resolve-escalation`).
Every invocation is one-shot: parse args, `asyncio.run(async_main())`, exit.
There is no persistent process a user talks to interactively — the closest
thing is `cressida daemon`, which loops forever watching `missions/inbox/` and
`missions/scheduled/` for new briefs, plus a `StatusServer` HTTP endpoint
(`daemon/mcp_server.py` also starts these on first tool call).

Two things already give CRESSIDA "session" behavior without a REPL:
- The **MCP server** (`mcp_server.py`) exposes `run_mission`,
  `mission_status`, `mission_progress`, `list_missions`, `read_mission_file`,
  `resolve_escalation`, `cressida_status`, plus Obsidian and learning-playbook
  tools — this is already the interactive surface, just driven by a chat
  client (Claude Code / opencode) instead of a terminal REPL.
- `run_mission` (in `mcp_server.py`) spawns the actual mission as its own OS
  process (`_spawn_mission_window`) with `CREATE_NEW_CONSOLE` on Windows, or
  detached elsewhere, and returns immediately with a mission ID. The mission
  itself is never something a foreground shell blocks on.

## What "interactive CLI" would mean here

Two distinct things get called "interactive CLI" and they have very
different scope:

1. **A REPL for mission *management*** — a persistent `cressida shell`
   process where the same nouns as the argparse subcommands (`status`,
   `list_missions`, `resolve-escalation`, `rewards list`) are typed without
   re-invoking the interpreter each time, with tab completion and history.
2. **An interactive mission *authoring* flow** — prompting the user
   conversationally to build up a brief (clarifying questions, provider
   choice, target dir) before calling `run_mission`, instead of taking a
   brief as a single CLI argument or file.

These are additive, not exclusive, and (1) is a prerequisite UI for (2).

## Feasibility

**Straightforward — no architectural blockers.** The command logic already
lives in plain async functions in `cli/commands.py`
(`run_mission`, `show_status`, `run_daemon`, `submit_feedback`,
`list_rewards`, `export_rewards`, `resolve_escalation`) that take an
`argparse.Namespace`. A REPL just needs to:

- Keep one process alive and re-parse each typed line into the same
  `argparse.Namespace` shape (`shlex.split(line)` +
  `parser.parse_args(tokens)` reuses `build_parser()` unchanged).
- Loop `while True: line = input("cressida> ")`.
- Await the existing command coroutines on a persistent event loop instead of
  a fresh `asyncio.run()` per call.

No new dependency is required for a basic version: stdlib `input()` (or
`cmd.Cmd`) plus the existing `argparse` parser covers it. `rich` is already a
dependency and gets prompt styling / live status tables for free. `click` is
declared in `pyproject.toml` but currently unused — if richer completion or
multi-line prompts (`click_repl`, `prompt_toolkit`) turn out to matter, that
codebase already carries the dependency to build on, but it is not needed for
a first version.

## What doesn't change

- `run_mission` should keep spawning missions as detached
  processes/console-windows, not run them in the REPL's own event loop —
  mission execution is minutes-to-hours, agent-by-agent, and the REPL needs
  to stay responsive for `status`/`resolve-escalation` calls on *other*
  missions while one is running. This mirrors what `mcp_server.py` already
  does.
- `cressida daemon` stays the unattended/background entry point; the REPL is
  a foreground, human-attended alternative, not a replacement.

## Effort estimate

- **REPL shell over existing commands** (item 1 above): small — a new
  `cli/shell.py` with a loop, reusing `build_parser()` and the command
  functions as-is. Half a day including a `demo()`/smoke test per the
  project's "non-trivial logic needs one runnable check" convention.
- **Conversational brief authoring** (item 2): medium — needs new prompting
  logic (what to ask, in what order, when to stop and call `run_mission`)
  that doesn't exist anywhere in the codebase yet; this is new product
  surface, not a wrapper over existing code.
- **Live mission-progress rendering inside the REPL** (watching a spawned
  mission's `mission_progress` output stream in place, rather than the
  detached console window): medium — `cressida dashboard` already renders
  this as a web UI (`cressida/dashboard`); a terminal equivalent would reuse
  its polling logic against `core/progress.py` rather than the HTTP layer.

## Recommendation

Feasible and low-risk to start with item 1 (a thin REPL over the existing
argparse commands) — it reuses everything, adds no required dependency, and
gives an immediate quality-of-life win (no re-typing `cressida` per command,
tab completion, session-local mission-ID memory so `status` / `resolve-
escalation` don't need the ID repeated). Item 2 (conversational brief
authoring) is a separate, larger decision — worth scoping only once it's
clear the REPL itself is wanted.
