# Cressida Robustness & Retrieval Execution Plan

**Status:** Draft for review
**Author:** Claude (session 2026-08-10), drafted while mission_20260810_073356 ran
**Scope:** (1) make mission execution failsafe, (2) give research agents durable web search, (3) implement the two-tier RAG + summarizer design from 2026-08-08

---

## 1. Why this plan exists

Three consecutive missions (`mission_20260809_230043`, `mission_20260809_232000`, `mission_20260810_002656`) crashed identically at LEITER's `methodology_research` task with exit code `4294967295` and empty stderr — undiagnosable with the logging that existed at the time. A fourth attempt (`mission_20260810_011351`) never even reached `execution_state.json` creation. `mission_20260810_073356` finally got past that phase, but then hit a **second, unrelated** failure: BOND's `bond_approve_plan` gate parsed a genuinely-approved decision as unapproved and killed the mission with a false `ESCALATED`, because of a regex bug in `coordinator.py::_parse_bond_decision_file`.

Neither failure had a recovery path. Both required a human (me, this session) reading source code, diagnosing by hand, and hand-rolling a resume script that doesn't officially exist. That is the core problem this plan addresses: **Cressida has no first-class notion of "resume" or "retry," so every unexpected failure mode is a full mission write-off** — expensive in tokens (research/methodology/architecture/BOND all re-run) and in wall-clock time.

Separately, on 2026-08-08 a two-tier retrieval architecture (live web search + persistent RAG, FAISS-backed, staleness-routed) was designed for Cressida but never implemented (see memory obs #18). This plan folds that design in, since it's the other half of "make research agents' information-gathering robust."

---

## 2. Confirmed current state (don't re-litigate these)

- `web_search` and `fetch_url` are **already implemented** and already granted to LEITER and INTELLIGENCE (`core/tools/definitions.py::_WEB_SEARCH`, `_ROLE_TOOLS["LEITER"]`). Implementation is in `core/tools/implementations.py::_web_search` / `_fetch_url`: Brave Search API when `BRAVE_API_KEY` is set, falling back to DuckDuckGo HTML scraping otherwise, with an exception-safe path that never crashes the caller. `BRAVE_API_KEY` is confirmed set in this environment.
- There is **no RAG / vector store / embedding layer anywhere in the codebase.** The 2026-08-08 design is architecture-only; nothing was built.
- There is **no resume mechanism.** `cli/commands.py::_build_mission_state` always constructs a fresh all-`PENDING` task DAG. `TaskExecutor` does skip tasks already marked `COMPLETED` in a given in-memory run (`coordinator.py:430`), but nothing rehydrates that state from `execution_state.json` on a fresh process start. `resolve_escalation` only clears the `escalations/*.json` mechanism — it does nothing for the (more common, as of this session) `bond_gate_blocked` metadata path.
- The `4294967295` (`0xFFFFFFFF`, i.e. `-1` as an unsigned 32-bit exit code) crash is still **not root-caused**. Logging instrumentation was added this session (`claude_cli_agent.py::_write_failure_log`, mission/task ID threading) but no repro has been captured since. Windows-specific subprocess termination (job-object kill, console-window close, antivirus interference) are the leading suspects, not Cressida's own code.
- BOND's decision-parsing bug (regex too strict against `"Decision recorded: **APPROVED**"` phrasing) **has been patched** in this session (`coordinator.py::_parse_bond_decision_file`). This plan treats that as done and focuses on preventing the *category* of bug, not just this instance.

---

## 3. Failsafe / robustness workstream

### 3.1 First-class mission resume (highest priority)

The single highest-leverage fix. Every failure mode below is cheaper to recover from once this exists.

- Add `execution_state.json` rehydration to `_build_mission_state` (or a new `_resume_mission_state`): if `missions/<id>/execution_state.json` already exists when `run_mission` is called with that `mission_id`, load it, rebuild the same DAG (deterministic — same brief, same trivial flag), and overlay `COMPLETED`/`FAILED` statuses from disk onto the freshly-built tasks before scheduling.
- Expose this as a real path in both the CLI (`cressida run --mission-id <id>` should resume, not silently restart) and the MCP server (`run_mission` should detect an existing mission directory for a given ID and resume instead of erroring or duplicating work; alternatively add an explicit `resume_mission(mission_id)` MCP tool).
- This is exactly what the ad-hoc script this session did by hand (rebuild DAG via `_build_mission_state`, replay `COMPLETED` from `execution_state.json`, call `coordinator.run_mission`). Promote it from a one-off script into `orchestration/resume.py` with a test.

### 3.2 BOND gate: remove the ambiguity class, not just this bug

The regex fix stops one phrasing from breaking, but BOND can still phrase its verdict in some other way the regex doesn't anticipate, and `_check_bond_gate` **fails closed by picking whichever decision file has the latest mtime** — which is a race between BOND's own JSON write and markdown write, not a meaningful signal.

- Change `_check_bond_gate` to always prefer the `.json` decision artifact over `.md` when both exist for the same gate, instead of "most recent by mtime." JSON is structured and unambiguous; markdown is a fallback for providers that can't call `approve_phase`/`reject_phase` as real tools. Falling back to markdown-regex parsing should only happen when no JSON file exists at all.
- Add a small regression test fixture: a handful of real BOND `.md` outputs already seen in this repo (`missions/mission_20260729_194951/bond_decisions/bond_approve_plan.md` has the `"**Decision: rejected.**"` phrasing cited in the existing docstring; this session's `mission_20260810_073356/bond_decisions/bond_approve_plan.md` has the `"Decision recorded: **APPROVED**"` phrasing) as parser test cases, so future phrasing drift is caught before it reaches a live mission.
- Log a warning (not just silent block) whenever the gate falls back to markdown parsing at all — that fallback path is inherently fragile and should be visible in the mission's own log, not just discoverable by reading source code after the fact.

### 3.3 Diagnose the `4294967295` crash properly

Logging exists now but hasn't caught a repro. Rather than wait for the next silent failure:

- Wrap the `claude` CLI subprocess invocation with an explicit timeout and a distinguishing check for `-1`/`4294967295` return codes specifically — on Windows, `subprocess` reports this value when the child process is terminated by a signal/job-object kill rather than exiting normally. Capture `WMI`/Job Object termination reason if feasible, or at minimum log CPU/memory of the parent process at the moment of failure (rules out OOM-triggered termination by a resource governor or antivirus).
- Add automatic **retry-with-backoff** (2 attempts, exponential) specifically for this exit code class, since it appears to be transient/environmental rather than a logic error in the prompt or task. This alone would likely have prevented 3 of the 4 stalled missions from this session without needing a diagnosis at all.
- Verify whether headless Firefox or any other external binary LEITER might reach for is actually required and present (a prior session hypothesis, unconfirmed either way — LEITER's actual tool floor is `web_search`/`fetch_url`/`read_file`/`query_memory`, none of which need a browser, so this hypothesis should be explicitly ruled out or removed from consideration by grepping `agents/leiter.md` and confirming no browser dependency is invoked).

### 3.4 Stall detection follow-through

`autonomy/monitor.py::StallMonitor` exists and is wired into the MCP server's background tasks (`mcp_server.py::_ensure_monitor_started`). Confirm it actually:
- Fires on a mission whose `execution_state.json` hasn't updated in N minutes (this session's `mission_20260810_011351` sat at "initializing" indefinitely with no observable alert).
- Surfaces that stall somewhere a human/agent checking `mission_status` would see it — today, "initializing forever" and "healthy and running" look identical from the MCP status tools.

### 3.5 Test coverage

None of the above should ship without: a unit test for `_parse_bond_decision_file` covering both phrasings on record, a unit test for the resume path (build DAG, mark 5/8 complete, confirm scheduler only re-runs the remaining 3), and an integration-style test (can be a fast, mocked-provider mission) that exercises the full research→...→review DAG at least once in CI so a regression like the BOND parser bug is caught before a real mission burns tokens on it.

---

## 4. Retrieval workstream: two-tier RAG + web search + summarizer

Implements the 2026-08-08 design (memory obs #18), which was architected but never built. Restating it here so this plan is self-contained, plus the summarizer layer requested this round.

### 4.1 Tier 1 — Live web (volatile / current information)

Already partially built: `web_search` → results, `fetch_url` → raw page text (12k char cap, stdlib-only HTML stripping). Missing pieces:

- **Extract**: `fetch_url`'s current HTML-stripping is generic; add a lightweight readability-style extraction (strip nav/ads/boilerplate) so the summarizer isn't wasting tokens on chrome. This can reuse patterns from the `claude-obsidian:defuddle` skill already available in this environment rather than reinventing extraction.
- **Summarize**: a new `_summarize_page(text, query)` step between fetch and context injection — map-reduce style for anything over a threshold (e.g. ~4k tokens): chunk, summarize each chunk against the query, then a final combine pass. This is the "summarizer" piece: it exists nowhere in Cressida today; `fetch_url` currently returns raw (truncated) text directly into the agent's context.
- **Rerank**: cheap keyword/embedding-similarity rerank of multi-result `web_search` output against the query before any fetch happens, so LEITER/INTELLIGENCE don't burn a fetch+summarize cycle on a low-relevance result.

### 4.2 Tier 2 — Persistent RAG (stable knowledge)

- **Storage**: FAISS, per the original decision (Cressida is single-user, local-first; Qdrant's concurrent-write/filtered-search strengths aren't needed yet — revisit only if that changes).
- **Ingestion, two paths sharing one index**:
  1. Periodic external doc crawl (library docs Cressida repeatedly needs — the same libraries LEITER verifies per mission, e.g. Anime.js/Motion/Kokonut UI/Bklit UI this session — so re-verification doesn't require a fresh web search every mission).
  2. Incremental internal ingestion hooked into the **existing** learning layer (`learning/reflection.py`, `learning/playbook.py`) — architecture notes, ADRs, and past solutions become searchable automatically as a side effect of missions completing, with no separate crawler needed. This creates the feedback loop the original design called out: solutions Cressida discovers become context for future missions.
- **Retrieval**: embed query → FAISS similarity search → rerank → (optionally) summarize if the retrieved chunk set is large.

### 4.3 Routing between tiers

- Staleness/confidence heuristic: check the persistent RAG store first; if the best match is recent enough (embedding similarity above threshold, doc age under a per-topic staleness limit — library version docs go stale faster than architectural patterns) and confident enough, use it. Otherwise fall through to live web search, and **write the result back into the RAG store** so the next mission that needs it gets a cache hit.
- Explicitly deferred (per original design, still correct): a learned router. Query volume doesn't yet justify it; the heuristic is simpler and sufficient while Cressida is young.

### 4.4 Where this plugs into the agent floor

- LEITER and INTELLIGENCE already have `web_search`/`fetch_url`/`query_memory` — the two-tier router should live *behind* those same tool names (agents shouldn't need new tool grants; the router decides RAG-vs-web internally) so no `_ROLE_TOOLS` changes are required for the roles that already research.
- Consider extending `query_memory` (already role-gated) to be the single entry point agents call, with the router + summarizer + RAG/web split happening inside its implementation — keeps the per-role tool surface small (per M's "never expose a tool a task doesn't demonstrably need" principle) while adding real capability underneath.

### 4.5 Implementation order

1. Summarizer (`_summarize_page`) — smallest, immediately reduces context bloat from the web search tier that's already live.
2. FAISS store + embedding ingestion from the learning layer (internal path) — reuses infrastructure that already runs after every mission, so the marginal cost is low.
3. Retrieval + staleness routing.
4. External doc crawl (periodic) — lowest priority; the internal-ingestion feedback loop and on-demand web tier cover most needs without it.

---

## 5. Suggested sequencing

1. §3.1 (resume) and §3.2 (BOND gate hardening) first — both are small, both directly prevent repeat of what happened this session, and §3.1 makes every subsequent failure (including ones this plan doesn't anticipate) cheaper to recover from.
2. §3.3 (crash retry/diagnosis) and §3.4 (stall visibility) next — closes the loop on the *other* failure mode seen this session.
3. §3.5 (tests) alongside 1–2, not after — the BOND bug specifically was the kind of thing a two-line regression test would have caught before it ever reached a live mission.
4. §4 (retrieval) last — it's valuable but additive; nothing in §3 depends on it, and it's a larger scope of new code (FAISS integration, embedding pipeline) than the failsafe fixes.
