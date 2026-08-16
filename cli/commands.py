from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from cressida.core.events import EventBus, EventType
from cressida.core.paths import (
    _check_project_dir_is_safe, knowledge_dir, mission_dir, missions_root, project_dir,
)
from cressida.core.registry import AgentRegistry
from cressida.core.types import AgentRole, MissionState, MissionStatus, Priority, Task, TaskStatus
from cressida.evaluation.feedback_collector import FeedbackCollector
from cressida.evaluation.reward_store import RewardStore
from cressida.memory.system import MemorySystem
from cressida.orchestration.coordinator import Coordinator
from cressida.state.shared_state import SharedState


def _wire_vault_sync(event_bus: EventBus) -> None:
    """Subscribe the Obsidian/markdown bridge to task and mission completion so
    every run's outputs land in the vault (or the local markdown fallback)
    without a manual sync step."""
    try:
        from cressida.obsidian.bridge import get_bridge

        bridge = get_bridge()
        if bridge is not None:
            bridge.subscribe_to_events(event_bus, missions_root(), knowledge_dir())
    except Exception as e:
        print(f"[commands] vault sync wiring skipped: {e}")


def _wire_narrator(event_bus: EventBus) -> None:
    """Subscribe a live console narrator so a mission's progress is visible in
    its terminal as it happens, not just as a final result line."""
    try:
        from cressida.autonomy.narrator import wire_console_narrator

        wire_console_narrator(event_bus)
    except Exception as e:
        print(f"[commands] console narrator wiring skipped: {e}")


def _wire_live_log(event_bus: EventBus) -> None:
    """Subscribe the JSONL live-event sink (core/live_log.py) so a headless
    run — no console window, no TTY to narrate into — still has a
    disk-durable, appendable record that `cressida watch` (or anything else)
    can tail without polling mission_status."""
    try:
        from cressida.core.live_log import wire_live_log

        wire_live_log(event_bus)
    except Exception as e:
        print(f"[commands] live log wiring skipped: {e}")


def _build_mission_state(
    mission_id: str,
    brief: str,
    default_priority: Priority = Priority.CRITICAL,
    target_dir: str | Path | None = None,
    trivial: bool = False,
) -> MissionState:
    """Build a standard MissionState DAG.

        research ─┬─> methodology_research ─┬─> architecture -> bond gate ->
                  └─> product_definition ───┘   planning -> implementation -> review

    ``trivial`` (see orchestration/commissioner.py) is M's mission-sizing
    verdict: a small script/CLI/utility skips the field-survey
    methodology_research phase entirely (architecture then only waits on
    product_definition), and the remaining strategic tasks get
    ``metadata["trivial"] = True`` so Dispatcher.commission() — already wired
    into every mission via Coordinator._commission_mission — downgrades them
    from the opus tier to the faster worker-tier model. This is the fix for a
    one-file CLI tool otherwise running the exact same multi-document,
    opus-tier architecture review as a production backend.

    LEITER's methodology_research and INTELLIGENCE's product_definition run in the
    same parallel batch: one establishes *how* the field builds this today, the
    other *what* we are building. Q's architecture waits on both.

    ``target_dir`` is the project the mission acts on — where implementation code
    is written. Mission *analysis* artifacts (research, PRD, architecture) always
    stay under the mission directory; only implementation goes to the target. When
    omitted it falls back to CRESSIDA_PROJECT_DIR, then the working directory, so
    "run Cressida inside the project I'm working on" needs no configuration.

    Exposed here so other modules can reuse the same mission shape without
    duplicating the task setup logic.
    """
    state = MissionState(mission_id=mission_id, brief=brief, status=MissionStatus.PENDING)

    target = Path(target_dir).expanduser().resolve() if target_dir else project_dir()
    _check_project_dir_is_safe(target)
    state.metadata["project_dir"] = str(target)
    state.add_task(Task(
        id="research",
        name="Research phase",
        description=f"Research technologies for: {brief[:200]}",
        agent=AgentRole.INTELLIGENCE,
        priority=default_priority,
        metadata={
            "reads": [], "writes": [f"missions/{mission_id}/intelligence/research_report.md"],
            "trivial": trivial,
        },
    ))
    if not trivial:
        state.add_task(Task(
            id="methodology_research",
            name="Methodology research",
            description=(
                "Search the open internet for the CURRENT state of the art for building this mission. "
                "Read primary sources (official docs, changelogs, release notes, advisories) with fetch_url — "
                "search snippets alone are not enough to cite a claim. Establish current versions and release "
                "dates for every dependency, identify deprecated or superseded approaches and what replaced "
                "them, extract the idiomatic patterns and project structure to follow, and record known "
                "pitfalls. Cite every claim with a URL and date; label anything unverified as [UNVERIFIED]."
            ),
            agent=AgentRole.LEITER,
            priority=default_priority,
            depends_on=["research"],
            metadata={
                "reads": [f"missions/{mission_id}/intelligence/research_report.md"],
                "writes": [
                    f"missions/{mission_id}/intelligence/methodology_brief.md",
                    f"missions/{mission_id}/intelligence/sources.md",
                ],
            },
        ))
    state.add_task(Task(
        id="product_definition",
        name="Product definition",
        description="Define product requirements, user personas, and MVP scope",
        agent=AgentRole.INTELLIGENCE,
        priority=default_priority,
        depends_on=["research"],
        metadata={
            "reads": [f"missions/{mission_id}/intelligence/research_report.md"],
            "writes": [
                f"missions/{mission_id}/intelligence/PRD.md",
                f"missions/{mission_id}/intelligence/Roadmap.md",
            ],
        },
    ))
    architecture_reads = [
        f"missions/{mission_id}/intelligence/research_report.md",
        f"missions/{mission_id}/intelligence/PRD.md",
        f"missions/{mission_id}/intelligence/Roadmap.md",
    ]
    architecture_depends_on = ["product_definition"]
    architecture_description = (
        "Design system architecture, API contracts, and data models. "
        "The mission subprocess always has WebSearch/WebFetch/context7, Bash, and read-only "
        "GitHub/Supabase tools available with no extra approval (see "
        "core/providers/claude_cli_agent.py:_ALLOWED_TOOLS). If — and only if — the architecture "
        "genuinely requires a tool outside that floor (e.g. creating a PR, applying a migration, "
        "some other MCP tool discovered as relevant to this mission), do NOT assume it's "
        "available. Instead write "
        f"missions/{mission_id}/architecture/mcp_tool_requests.json as a JSON array, one entry "
        "per requested tool: {\"tool\": \"<exact mcp__server__tool name>\", \"tier\": "
        "\"info|reversible|external\", \"justification\": \"why this mission needs it and what "
        "it would be used for\"}. Classify honestly: \"external\" means it sends something, "
        "spends money, publishes, or mutates a system this machine doesn't own — expect those to "
        "be rejected. If nothing beyond the default floor is needed, write an empty array or "
        "omit the file entirely."
    )
    if not trivial:
        architecture_reads.append(f"missions/{mission_id}/intelligence/methodology_brief.md")
        architecture_depends_on.append("methodology_research")
        architecture_description += (
            " Follow the methodology brief: use the versions, patterns, and project structure it "
            "verified, and avoid the approaches it flags as deprecated."
        )
    state.add_task(Task(
        id="architecture",
        name="Architecture design",
        description=architecture_description,
        agent=AgentRole.Q,
        priority=default_priority,
        depends_on=architecture_depends_on,
        metadata={
            "reads": architecture_reads,
            "trivial": trivial,
            "writes": [
                f"missions/{mission_id}/ARCHITECTURE.md",
            ],
        },
    ))
    bond_reads = [
        f"missions/{mission_id}/intelligence/research_report.md",
        f"missions/{mission_id}/intelligence/PRD.md",
        f"missions/{mission_id}/ARCHITECTURE.md",
        f"missions/{mission_id}/architecture/mcp_tool_requests.json",
    ]
    bond_tool_instructions = (
        " Also review architecture/mcp_tool_requests.json if present. For each requested tool, "
        "decide independently — do not defer to Q's self-assigned tier, re-derive it. Approve "
        "only tools whose use is genuinely local/reversible or pure information retrieval; reject "
        "anything with an effect outside this machine (sending something, spending money, "
        "publishing, merging/pushing to a remote, mutating a hosted database) regardless of how "
        "the request justifies it — that class of action needs a human decision, not a BOND "
        "approval. Record your verdict in the decision JSON under \"approved_mcp_tools\": [list "
        "of exact tool names you approve, empty if none]. Note: this approval is not the only "
        "safeguard — approved names are still checked against a hardcoded dangerous-keyword "
        "filter before they reach the mission subprocess, so treat this as a real review, not a "
        "formality that will be caught downstream anyway."
    )
    bond_description = (
        "Review the research, PRD, and architecture artifacts."
        + bond_tool_instructions
        + " Write the authoritative decision to "
        + f"missions/{mission_id}/bond_decisions/approve_plan.json as JSON with keys "
        + '"decision" (APPROVED, REJECTED, or ESCALATED), "reason", and '
        + '"approved_mcp_tools". If your provider exposes approve_phase, reject_phase, '
        + "or escalate, you may also call it, but the JSON file is mandatory."
    )
    if not trivial:
        bond_reads.insert(1, f"missions/{mission_id}/intelligence/methodology_brief.md")
        bond_description = (
            "Review the research, methodology brief, PRD, and architecture artifacts. "
            "Check that the architecture actually follows the verified methodology and does not "
            "rely on approaches the brief flags as deprecated or unverified."
            + bond_tool_instructions
            + " Write the authoritative decision to "
            + f"missions/{mission_id}/bond_decisions/approve_plan.json as JSON with keys "
            + '"decision" (APPROVED, REJECTED, or ESCALATED), "reason", and '
            + '"approved_mcp_tools". If your provider exposes approve_phase, reject_phase, '
            + "or escalate, you may also call it, but the JSON file is mandatory."
        )
    state.add_task(Task(
        id="bond_approve_plan",
        name="BOND: approve plan",
        description=bond_description,
        agent=AgentRole.BOND,
        priority=default_priority,
        depends_on=["architecture"],
        metadata={
            "reads": bond_reads,
            "writes": [f"missions/{mission_id}/bond_decisions/"],
            "trivial": trivial,
        },
    ))
    state.add_task(Task(
        id="planning",
        name="Task planning",
        description="Decompose tasks, create dependency graph, and populate execution backlog",
        agent=AgentRole.TANNER,
        priority=default_priority,
        depends_on=["bond_approve_plan"],
        metadata={
            "reads": [
                f"missions/{mission_id}/intelligence/PRD.md",
                f"missions/{mission_id}/intelligence/Roadmap.md",
                f"missions/{mission_id}/ARCHITECTURE.md",
            ],
            "writes": [f"missions/{mission_id}/backlog.json"],
        },
    ))
    if not trivial:
        state.tasks["planning"].metadata["reads"].append(
            f"missions/{mission_id}/intelligence/methodology_brief.md"
        )
    implementation_reads = [
        f"missions/{mission_id}/intelligence/PRD.md",
        f"missions/{mission_id}/ARCHITECTURE.md",
        f"missions/{mission_id}/backlog.json",
    ]
    implementation_description = (
        "Implement the code based on the PRD, architecture, and backlog. "
        "Write all source files, tests, and configuration files as specified. "
        "Use the write_file tool to create each file. "
        f"Write all source files under the target project directory: {target}"
    )
    if not trivial:
        implementation_reads.insert(1, f"missions/{mission_id}/intelligence/methodology_brief.md")
        implementation_description = (
            "Implement the code based on the PRD, architecture, and backlog. "
            "Write all source files, tests, and configuration files as specified. "
            "Use the versions, patterns, and idioms established in the methodology brief — "
            "do not fall back on older patterns it marks as superseded. "
            "Use the write_file tool to create each file. "
            f"Write all source files under the target project directory: {target}"
        )
    state.add_task(Task(
        id="implementation",
        name="Implementation",
        description=implementation_description,
        agent=AgentRole.BRANCH,
        priority=default_priority,
        depends_on=["planning"],
        metadata={
            "reads": implementation_reads,
            # The mission-local implementation notes stay here so REVIEW's reads
            # keep working; actual source files go to the target project via
            # write_file, which passes absolute paths through untouched.
            "writes": [f"missions/{mission_id}/implementation/"],
            "project_dir": str(target),
        },
    ))
    state.add_task(Task(
        id="review",
        name="Code review",
        description=_review_task_description(),
        agent=AgentRole.REVIEW,
        priority=default_priority,
        depends_on=["implementation"],
        metadata={
            "reads": [
                f"missions/{mission_id}/implementation/",
                f"missions/{mission_id}/intelligence/PRD.md",
                f"missions/{mission_id}/intelligence/Roadmap.md",
                f"missions/{mission_id}/ARCHITECTURE.md",
                f"missions/{mission_id}/backlog.json",
            ],
            "writes": [f"missions/{mission_id}/review_report.md"],
        },
    ))
    if not trivial:
        state.tasks["review"].metadata["reads"].insert(
            1, f"missions/{mission_id}/intelligence/methodology_brief.md"
        )
    return state


def _review_task_description() -> str:
    """Shared REVIEW task prompt for both a mission's first review and every
    review-loop fix round (see ``_run_review_loop``) — the contract has to be
    identical everywhere so ``_parse_review_verdict`` can read any of them.

    The plain-English "provide a review report" instruction that used to be
    here left REVIEW free to write whatever prose it wanted (observed: "Score:
    7.5/10, Recommendation: Conditional" with a "Required before approval"
    list in one report, different wording in another) — fine for a human to
    read, useless for code to gate on reliably. This adds a structured
    verdict line on top, the same way BOND's gate needed an explicit
    ``Decision: <verdict>`` contract (see ``_parse_bond_decision_file``)
    rather than relying on free text.
    """
    return (
        "Review the implemented code for quality, correctness, and adherence to the "
        "architecture. Run tests if available. Provide a review report at review_report.md.\n\n"
        "End the report with a machine-parseable verdict line, formatted EXACTLY like one of "
        "these (on its own line, no surrounding markdown emphasis):\n\n"
        "RECOMMENDATION: APPROVED\n"
        "RECOMMENDATION: NEEDS_FIXES\n\n"
        "If NEEDS_FIXES, follow it with a `## Outstanding Items` section listing every concrete, "
        "actionable fix required (compile errors, missing files, failing tests, security issues, "
        "etc.) as a plain list — one item per line, specific enough that another engineer could "
        "act on it without re-reading the whole review. Reserve NEEDS_FIXES for things that should "
        "actually block approval; purely optional/nice-to-have suggestions don't count and "
        "shouldn't force APPROVED into NEEDS_FIXES."
    )


def _persist_initial_state(state: MissionState) -> None:
    """Make a fresh mission visible before its first agent batch returns."""
    path = mission_dir(state.mission_id) / "execution_state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    tasks = {
        task_id: {
            "status": task.status.value if hasattr(task.status, "value") else str(task.status),
            "agent": task.agent.value if task.agent else None,
            "name": task.name,
            "error": None,
        }
        for task_id, task in state.tasks.items()
    }
    path.write_text(json.dumps({
        "mission_id": state.mission_id,
        "status": MissionStatus.PENDING.value,
        "tasks": tasks,
        "updated_at": datetime.now().isoformat(),
    }, indent=2), encoding="utf-8")


def _rehydrate_from_execution_state(state: MissionState, mission_id: str) -> bool:
    """If ``missions/<id>/execution_state.json`` already exists, overlay its
    per-task COMPLETED/FAILED statuses onto the freshly-built (all-PENDING)
    DAG so ``Coordinator._execute_batch`` — which already skips any task
    whose status isn't PENDING — re-runs only what never finished.

    This is what makes resuming a crashed/escalated mission a real, built-in
    path instead of the hand-rolled "rebuild DAG, replay COMPLETED, call
    coordinator.run_mission" script that previously had to be done by hand
    reading source (see CRESSIDA_ROBUSTNESS_AND_RETRIEVAL_PLAN.md §3.1). The
    DAG shape must be deterministic for a given (mission_id, brief, trivial)
    triple — which it is, since ``_build_mission_state`` is a pure function of
    those three inputs — or the overlay would apply old statuses to the wrong
    tasks.

    Returns True if anything was rehydrated (existing execution state found),
    False for a genuinely fresh mission.
    """
    path = mission_dir(mission_id) / "execution_state.json"
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"[commands] resume: could not read {path}, starting fresh: {e}")
        return False

    tasks_data = payload.get("tasks") or {}
    if not tasks_data:
        return False

    resumed = 0
    for task_id, saved in tasks_data.items():
        task = state.tasks.get(task_id)
        if task is None:
            continue  # DAG shape changed (e.g. brief edited) — ignore stale entries
        saved_status = str(saved.get("status", "")).upper()
        if saved_status == TaskStatus.COMPLETED.value:
            task.status = TaskStatus.COMPLETED
            task.error = None
            resumed += 1
        elif saved_status == TaskStatus.FAILED.value:
            # Leave FAILED tasks PENDING so they're retried on resume rather
            # than permanently skipped — a FAILED task is the whole reason a
            # human is resuming this mission in the first place.
            continue

    if resumed:
        print(f"[commands] resuming {mission_id}: {resumed} task(s) already COMPLETED, skipping re-run")
    return resumed > 0


def _parse_review_verdict(report_path: Path) -> tuple[str, str]:
    """Parse a review_report.md written under the ``_review_task_description``
    contract into ``(verdict, outstanding_items_text)``.

    ``verdict`` is one of ``"APPROVED"``, ``"NEEDS_FIXES"``, or ``"UNKNOWN"``.
    UNKNOWN (missing file, or no parseable verdict line at all) deliberately
    does NOT trigger a fix round — looping on a report the parser can't read
    would burn the fix budget on a formatting problem instead of a real one;
    that case is left for a human to look at, same as BOND failing closed on
    an unparseable decision file.
    """
    if not report_path.exists():
        return "UNKNOWN", ""
    text = report_path.read_text(encoding="utf-8")

    m = re.search(
        r"^\s*RECOMMENDATION\s*:\s*(APPROVED|NEEDS[_ -]?FIXES)\b",
        text, re.IGNORECASE | re.MULTILINE,
    )
    if m:
        verdict = "NEEDS_FIXES" if "NEED" in m.group(1).upper() else "APPROVED"
    else:
        # Fallback for reports written before this contract existed, or by a
        # REVIEW run that ignored it — free-text "Recommendation: <word>"
        # phrasing observed in the wild (e.g. "**Recommendation: Conditional**").
        m2 = re.search(r"recommendation\s*:?\**\s*([A-Za-z][A-Za-z \-]{0,30})", text, re.IGNORECASE)
        if not m2:
            return "UNKNOWN", ""
        word = m2.group(1).strip().lower()
        if "approve" in word and "not" not in word:
            verdict = "APPROVED"
        elif any(k in word for k in ("condition", "reject", "block", "fail")):
            verdict = "NEEDS_FIXES"
        else:
            return "UNKNOWN", ""

    outstanding = ""
    if verdict == "NEEDS_FIXES":
        m3 = re.search(r"##\s*Outstanding Items\s*\n(.*?)(?:\n##\s|\Z)", text, re.IGNORECASE | re.DOTALL)
        if m3:
            outstanding = m3.group(1).strip()
        else:
            # Same fallback tier as above: older/off-contract reports used
            # headings like "Required before approval" / "Missing Items".
            chunks = []
            for heading in (r"required before approval", r"missing items"):
                m4 = re.search(rf"{heading}[^\n]*\n(.*?)(?:\n##\s|\n---|\Z)", text, re.IGNORECASE | re.DOTALL)
                if m4:
                    chunks.append(m4.group(1).strip())
            outstanding = "\n\n".join(chunks).strip()
    return verdict, outstanding


def _render_fix_brief(outstanding: str, source_mission_id: str, round_num: int) -> str:
    return (
        f"# Fix round {round_num} — resolve outstanding code review items\n\n"
        f"A code review of this project (missions/{source_mission_id}/review_report.md) found the "
        "following items that must be fixed before the implementation can be approved. Fix all of "
        "them in the existing codebase; do not rewrite working code the review didn't flag.\n\n"
        f"## Outstanding items\n\n"
        + (outstanding or (
            "(the review flagged NEEDS_FIXES but did not enumerate items in the expected format — "
            f"re-read the full report at missions/{source_mission_id}/review_report.md and fix "
            "whatever is blocking approval.)"
        ))
    )


def _build_review_fix_state(
    mission_id: str, brief: str, target_dir: str | Path, root_mission_id: str, source_mission_id: str,
) -> MissionState:
    """Two-task DAG (``implementation`` -> ``review``) for one review-loop fix
    round — deliberately skips research/product_definition/architecture/BOND,
    since this is a targeted fix pass against an already-approved
    architecture, not a new mission from scratch. PRD/ARCHITECTURE are still
    read from the root mission for context.

    Reuses the ``implementation``/``review`` task ids and the exact
    ``_build_mission_state`` metadata shape (reads/writes/project_dir) so
    every downstream piece (Dispatcher commissioning, TaskExecutor, the
    claude_cli provider's prompt assembly) treats this exactly like any other
    mission's implementation/review pair — nothing in that path keys off
    mission shape or task count.
    """
    state = MissionState(mission_id=mission_id, brief=brief, status=MissionStatus.PENDING)
    target = Path(target_dir).expanduser().resolve()
    _check_project_dir_is_safe(target)
    state.metadata["project_dir"] = str(target)
    state.metadata["review_loop_root_mission"] = root_mission_id
    state.metadata["review_loop_source_mission"] = source_mission_id

    state.add_task(Task(
        id="implementation",
        name="Fix review findings",
        description=(
            f"A previous code review (missions/{source_mission_id}/review_report.md) found issues "
            f"that must be fixed in the project at {target}. Read that review report plus the "
            "project's PRD/architecture (linked below) for context, then fix every outstanding item "
            "— this is a targeted fix pass, not a rewrite; don't touch code the review didn't flag. "
            "Use the write_file tool to edit or create files as needed.\n\n" + brief
        ),
        agent=AgentRole.BRANCH,
        priority=Priority.HIGH,
        metadata={
            "reads": [
                f"missions/{root_mission_id}/intelligence/PRD.md",
                f"missions/{root_mission_id}/ARCHITECTURE.md",
                f"missions/{source_mission_id}/review_report.md",
            ],
            "writes": [f"missions/{mission_id}/implementation/"],
            "project_dir": str(target),
        },
    ))
    state.add_task(Task(
        id="review",
        name="Code review",
        description=_review_task_description(),
        agent=AgentRole.REVIEW,
        priority=Priority.HIGH,
        depends_on=["implementation"],
        metadata={
            "reads": [
                f"missions/{mission_id}/implementation/",
                f"missions/{root_mission_id}/intelligence/PRD.md",
                f"missions/{root_mission_id}/ARCHITECTURE.md",
            ],
            "writes": [f"missions/{mission_id}/review_report.md"],
        },
    ))
    return state


def _record_review_loop_progress(root_mission_id: str, **fields: Any) -> None:
    """Best-effort append to missions/<root>/review_loop.json so mission_status
    /mission_progress readers (including the MCP tools) have somewhere to see
    fix-round history without knowing the derived ``<root>_fixN`` mission ids
    up front. Never raises — this is observability, not control flow."""
    path = mission_dir(root_mission_id) / "review_loop.json"
    try:
        history = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"rounds": []}
    except Exception:
        history = {"rounds": []}
    entry = {"at": datetime.now().isoformat(), **fields}
    history["rounds"].append(entry)
    history["last_updated"] = entry["at"]
    try:
        path.write_text(json.dumps(history, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[commands] review_loop.json write skipped: {e}")


async def _run_review_loop(
    result: MissionState,
    root_mission_id: str,
    registry: AgentRegistry,
    memory: MemorySystem,
    event_bus: EventBus,
    target_dir: str | None,
) -> MissionState:
    """After a mission's REVIEW task runs, automatically loop fix -> re-review
    until APPROVED or a round cap, instead of leaving a NEEDS_FIXES verdict
    sitting in review_report.md for a human to notice and manually resume
    (which is what every mission previously required — see the review task's
    old free-text-only description, now ``_review_task_description``).

    Opt out per-run with ``CRESSIDA_REVIEW_LOOP=0``. Round cap via
    ``CRESSIDA_MAX_REVIEW_ROUNDS`` (default 3) — a mission still not approved
    after that many targeted fix passes needs a human look, not more
    automated rounds spending the same usage budget.

    Each round is its own deterministic sub-mission (``<root>_fix1``,
    ``_fix2``, …) built the exact same build-state -> rehydrate -> persist ->
    coordinator.run_mission way as any other mission. That determinism is
    what makes a crash mid-round (e.g. a provider session/rate limit — the
    actual failure mode observed tonight) resumable for free: re-running
    run_mission with the ROOT mission_id replays this loop from round 1,
    re-derives the identical round mission_ids, and each round's own
    execution_state.json rehydrate skips whatever it already finished.
    """
    if os.environ.get("CRESSIDA_REVIEW_LOOP", "1") == "0":
        return result
    if result.status != MissionStatus.COMPLETED:
        return result
    if not target_dir:
        return result

    max_rounds = int(os.environ.get("CRESSIDA_MAX_REVIEW_ROUNDS", "3"))
    current_state = result
    current_mission_id = root_mission_id
    round_num = 0

    while True:
        review_task = current_state.tasks.get("review")
        if review_task is None or review_task.status != TaskStatus.COMPLETED:
            return current_state

        report_path = mission_dir(current_mission_id) / "review_report.md"
        verdict, outstanding = _parse_review_verdict(report_path)

        if verdict == "UNKNOWN":
            print(f"[commands] review loop: no parseable verdict in {report_path}, stopping (not looping blind)")
            return current_state
        if verdict == "APPROVED":
            if round_num:
                print(f"[commands] review loop: {current_mission_id} approved after {round_num} fix round(s)")
                _record_review_loop_progress(root_mission_id, round=round_num, mission_id=current_mission_id, verdict="APPROVED", final=True)
            return current_state
        if not outstanding.strip():
            print("[commands] review loop: NEEDS_FIXES but no parseable outstanding items, stopping (not looping blind)")
            return current_state
        if round_num >= max_rounds:
            current_state.metadata["review_loop_exhausted"] = True
            current_state.metadata["review_loop_last_outstanding"] = outstanding
            print(
                f"[commands] review loop hit its {max_rounds}-round cap for {root_mission_id} without "
                "approval — leaving the mission COMPLETED; outstanding items are in "
                "metadata['review_loop_last_outstanding'] and review_loop.json for a human to finish."
            )
            _record_review_loop_progress(
                root_mission_id, round=round_num, mission_id=current_mission_id,
                verdict="NEEDS_FIXES", exhausted=True, outstanding_preview=outstanding[:1000],
            )
            return current_state

        round_num += 1
        fix_mission_id = f"{root_mission_id}_fix{round_num}"
        fix_brief = _render_fix_brief(outstanding, current_mission_id, round_num)
        fix_state = _build_review_fix_state(
            fix_mission_id, fix_brief, target_dir,
            root_mission_id=root_mission_id, source_mission_id=current_mission_id,
        )
        _rehydrate_from_execution_state(fix_state, fix_mission_id)
        _persist_initial_state(fix_state)
        _record_review_loop_progress(
            root_mission_id, round=round_num, mission_id=fix_mission_id,
            source_mission_id=current_mission_id, verdict="NEEDS_FIXES",
            outstanding_preview=outstanding[:1000], status="started",
        )

        print(f"[commands] review round {round_num}: {fix_mission_id} fixing outstanding items from {current_mission_id}")
        fix_coordinator = Coordinator(registry, event_bus, memory)
        fix_shared = SharedState()
        fix_shared.mission = type(fix_shared.mission)(mission_id=fix_mission_id, brief=fix_brief)
        current_state = await fix_coordinator.run_mission(fix_state, fix_shared)
        current_mission_id = fix_mission_id

        if current_state.status != MissionStatus.COMPLETED:
            return current_state


async def run_mission(args: argparse.Namespace) -> int:
    brief_path = Path(args.brief)
    if brief_path.exists():
        brief = brief_path.read_text(encoding="utf-8")
    else:
        brief = args.brief

    # Microsecond suffix avoids two missions started in the same wall-clock
    # second colliding on mission_id (and thus on missions/<id>/).
    mission_id = getattr(args, "mission_id", None) or f"mission_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"

    event_bus = EventBus()
    _wire_vault_sync(event_bus)
    _wire_narrator(event_bus)
    _wire_live_log(event_bus)
    registry = AgentRegistry()
    memory = MemorySystem()
    registry.register_default(
        provider=getattr(args, "provider", "auto"),
        ollama_model=getattr(args, "ollama_model", "llama3.2"),
        ollama_host=getattr(args, "ollama_host", "http://localhost:11434"),
        timeout=getattr(args, "timeout", 0),
    )

    from cressida.orchestration.commissioner import is_trivial_mission
    trivial = await is_trivial_mission(mission_id, brief, registry)

    state = _build_mission_state(
        mission_id, brief, target_dir=getattr(args, "project_dir", None), trivial=trivial,
    )
    _rehydrate_from_execution_state(state, mission_id)
    _persist_initial_state(state)

    coordinator = Coordinator(registry, event_bus, memory)
    shared = SharedState()
    shared.mission = type(shared.mission)(mission_id=mission_id, brief=brief)

    print(f"Starting mission: {mission_id}")
    print(f"  mission dir:    {mission_dir(mission_id)}")
    print(f"  target project: {state.metadata.get('project_dir')}")
    result = await coordinator.run_mission(state, shared)

    result = await _run_review_loop(
        result, mission_id, registry, memory, event_bus,
        target_dir=state.metadata.get("project_dir"),
    )

    print(f"Mission {mission_id}: {result.status}")
    if result.status == MissionStatus.COMPLETED:
        print("All objectives completed successfully")
        return 0
    failed = [t for t in result.tasks.values() if t.status == TaskStatus.FAILED]
    for task in failed:
        print(f"  FAILED: {task.name} - {task.error}")
    return 1


async def show_status(args: argparse.Namespace) -> int:
    print("CRESSIDA System Status")
    print("Version: 0.1.0")
    print("Status: Operational")
    return 0


async def run_daemon(args: argparse.Namespace) -> int:
    """Run CRESSIDA unattended: watch the inbox/scheduled dirs and fire missions.

    Also starts the stall monitor and the status HTTP server. Runs until
    interrupted (Ctrl-C).
    """
    from cressida.autonomy.monitor import StallMonitor, StatusServer
    from cressida.autonomy.watcher import MissionWatcher

    # Anchor mission dirs to the canonical location (see core/paths.py) so
    # daemon-fired missions show up where mission_status reads them, regardless
    # of the daemon's working directory.
    missions_dir = missions_root()
    inbox = missions_dir / "inbox"
    scheduled = missions_dir / "scheduled"
    status_file = missions_dir / "status.json"

    event_bus = EventBus()
    _wire_vault_sync(event_bus)
    _wire_narrator(event_bus)
    _wire_live_log(event_bus)
    registry = AgentRegistry()
    memory = MemorySystem()
    registry.register_default(
        provider=getattr(args, "provider", "auto"),
        ollama_model=getattr(args, "ollama_model", "llama3.2"),
        ollama_host=getattr(args, "ollama_host", "http://localhost:11434"),
        timeout=getattr(args, "timeout", 0),
    )

    poll = getattr(args, "poll_interval", 10.0)
    port = getattr(args, "status_port", 7437)

    watcher = MissionWatcher(
        registry, event_bus, memory,
        inbox_dir=inbox, scheduled_dir=scheduled, poll_interval=poll,
    )
    monitor = StallMonitor(event_bus, memory=memory.strategic)
    server = StatusServer(event_bus, port=port, status_file=status_file)

    print("CRESSIDA daemon starting")
    print(f"  inbox:      {inbox}")
    print(f"  scheduled:  {scheduled}")
    print(f"  status:     http://localhost:{port}/status")
    print("  Ctrl-C to stop.")

    tasks = [
        asyncio.create_task(watcher.run()),
        asyncio.create_task(monitor.run()),
        asyncio.create_task(server.run()),
    ]
    try:
        await asyncio.gather(*tasks)
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\nCRESSIDA daemon stopping...")
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    return 0


async def submit_feedback(args: argparse.Namespace) -> int:
    bus = EventBus()
    collector = FeedbackCollector(bus)
    record = await collector.submit_feedback(
        task_id=args.task_id,
        score=args.score,
        comment=args.comment,
        outcome="completed",
    )
    print(f"Feedback submitted for task {record.task_id}: score={record.review_score}")
    print(f"  Comment: {record.human_feedback}")
    return 0


async def list_rewards(args: argparse.Namespace) -> int:
    store = RewardStore()
    mission_id = getattr(args, "mission_id", None)
    if mission_id:
        records = store.get_all_for_mission(mission_id)
    else:
        records = store.get_all()
    if not records:
        print("No reward records found.")
        return 0
    print(f"Reward records ({len(records)}):")
    for r in records[-20:]:
        reward_str = f"{r['reward']:.2f}" if r.get("reward") is not None else "N/A"
        print(f"  [{r.get('timestamp', '?')[:19]}] {r.get('agent', '?')}: {r.get('action', '?')} = {reward_str}")
    return 0


async def export_rewards(args: argparse.Namespace) -> int:
    store = RewardStore()
    path = store.export_jsonl(args.output)
    print(f"Reward records exported to: {path}")
    return 0


async def resolve_escalation(args: argparse.Namespace) -> int:
    """Resolve a BOND escalation and unblock a mission for resume."""
    from cressida.orchestration.escalation import resolve_mission_escalation

    mission_id = args.mission_id
    action = args.action
    result = resolve_mission_escalation(mission_id, action, resolved_by="CRESSIDA COMMAND")
    print(f"Escalation resolved for mission {mission_id}.")
    print(f"  Action: {action}")
    print(f"  Escalation records cleared: {result['escalations_resolved'] or '(none pending)'}")
    print(f"  BOND task reset for re-run: {result['bond_task_reset']}")
    print(f"  Resume with: cressida run --mission-id {mission_id} ...")
    return 0
