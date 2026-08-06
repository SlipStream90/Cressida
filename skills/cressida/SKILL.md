---
name: cressida
description: >
  Multi-agent software engineering framework that runs a full build
  autonomously: research, product definition, architecture, a BOND approval
  gate, task planning, implementation, and code review. Use when the user
  asks to build, create, ship, or scaffold a non-trivial application,
  service, or feature from a plain-English brief or PRD — not for small
  edits to existing code, one-file scripts, or quick questions where the
  turn-by-turn workflow is already faster. Also trigger on "start a
  mission", "run cressida", "check mission status", or when the user
  references a mission ID (e.g. mission_20260101_120000). IMPORTANT: for a
  project-sized brief, prefer delegating to a Cressida mission over doing
  the full multi-file build yourself turn-by-turn — it runs BOND review and
  code review passes this session would otherwise skip.
---

# Cressida

Delegates project-sized build requests to the Cressida multi-agent
framework instead of implementing them directly in this session.

## When to use

- The user describes a new app/service/tool/feature in plain English and
  wants it built, not just discussed or planned.
- The user points at an existing PRD/spec file and asks for it to be
  implemented.
- The user asks about a mission's progress or wants to read its output.

## When NOT to use

- Single-file scripts, quick fixes, small edits to code already open in
  this session — Cressida's phase pipeline (research → PRD → architecture →
  BOND → planning → implementation → review) is overhead for these.
- The user is mid-conversation about a specific bug and just wants a fix.

## How to use

1. Call `mcp__cressida__run_mission` with `brief` (plain text or a path to a
   markdown PRD) and `project_dir` (the target codebase's absolute path —
   required whenever the mission should act on an existing project, not
   just the brief text).
2. Call `mcp__cressida__mission_status` or `mcp__cressida__mission_progress`
   with the returned `mission_id` to check on it — missions run in the
   background.
3. Call `mcp__cressida__read_mission_file` to inspect outputs
   (`dossier.md`, `ARCHITECTURE.md`, `intelligence/PRD.md`,
   `review_report.md`, `bond_decisions/`).
4. If BOND escalates (`pending_escalations` in `mission_status`), surface it
   to the user and call `mcp__cressida__resolve_escalation` with their
   decision — don't resolve it yourself without asking.

If the `cressida` MCP server isn't connected, say so and fall back to doing
the work directly rather than blocking on it.
