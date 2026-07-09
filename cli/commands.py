from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from cressida.core.events import EventBus, EventType
from cressida.core.registry import AgentRegistry
from cressida.core.types import AgentRole, MissionState, MissionStatus, Priority, Task, TaskStatus
from cressida.evaluation.feedback_collector import FeedbackCollector
from cressida.evaluation.reward_store import RewardStore
from cressida.memory.system import MemorySystem
from cressida.orchestration.coordinator import Coordinator
from cressida.state.shared_state import SharedState


def _build_mission_state(
    mission_id: str,
    brief: str,
    default_priority: Priority = Priority.CRITICAL,
) -> MissionState:
    """Build a standard MissionState DAG: research -> product -> architecture -> planning -> implementation -> review.

    Exposed here so other modules can reuse the same mission shape without
    duplicating the task setup logic.
    """
    state = MissionState(mission_id=mission_id, brief=brief, status=MissionStatus.PENDING)
    state.add_task(Task(
        id="research",
        name="Research phase",
        description=f"Research technologies for: {brief[:200]}",
        agent=AgentRole.INTELLIGENCE,
        priority=default_priority,
        metadata={"reads": [], "writes": [f"missions/{mission_id}/intelligence/research_report.md"]},
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
    state.add_task(Task(
        id="architecture",
        name="Architecture design",
        description="Design system architecture, API contracts, and data models",
        agent=AgentRole.Q,
        priority=default_priority,
        depends_on=["product_definition"],
        metadata={
            "reads": [
                f"missions/{mission_id}/intelligence/PRD.md",
                f"missions/{mission_id}/intelligence/Roadmap.md",
            ],
            "writes": [f"missions/{mission_id}/ARCHITECTURE.md"],
        },
    ))
    state.add_task(Task(
        id="bond_approve_plan",
        name="BOND: approve plan",
        description=(
            "Review the research, PRD, and architecture artifacts. "
            "Use approve_phase to approve the plan or reject_phase to block it. "
            "Use escalate if confidence is below 0.7."
        ),
        agent=AgentRole.BOND,
        priority=default_priority,
        depends_on=["architecture"],
        metadata={
            "reads": [
                f"missions/{mission_id}/intelligence/research_report.md",
                f"missions/{mission_id}/intelligence/PRD.md",
                f"missions/{mission_id}/ARCHITECTURE.md",
            ],
            "writes": [f"missions/{mission_id}/bond_decisions/"],
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
                f"missions/{mission_id}/ARCHITECTURE.md",
            ],
            "writes": [f"missions/{mission_id}/backlog.json"],
        },
    ))
    state.add_task(Task(
        id="implementation",
        name="Implementation",
        description=(
            "Implement the code based on the PRD, architecture, and backlog. "
            "Write all source files, tests, and configuration files as specified. "
            "Use the write_file tool to create each file."
        ),
        agent=AgentRole.BRANCH,
        priority=default_priority,
        depends_on=["planning"],
        metadata={
            "reads": [
                f"missions/{mission_id}/intelligence/PRD.md",
                f"missions/{mission_id}/ARCHITECTURE.md",
                f"missions/{mission_id}/backlog.json",
            ],
            "writes": [f"missions/{mission_id}/implementation/"],
        },
    ))
    state.add_task(Task(
        id="review",
        name="Code review",
        description=(
            "Review the implemented code for quality, correctness, and adherence "
            "to the architecture. Run tests if available. Provide a review report."
        ),
        agent=AgentRole.REVIEW,
        priority=default_priority,
        depends_on=["implementation"],
        metadata={
            "reads": [
                f"missions/{mission_id}/implementation/",
                f"missions/{mission_id}/intelligence/PRD.md",
                f"missions/{mission_id}/ARCHITECTURE.md",
            ],
            "writes": [f"missions/{mission_id}/review_report.md"],
        },
    ))
    return state


async def run_mission(args: argparse.Namespace) -> int:
    brief_path = Path(args.brief)
    if brief_path.exists():
        brief = brief_path.read_text(encoding="utf-8")
    else:
        brief = args.brief

    mission_id = getattr(args, "mission_id", None) or f"mission_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    event_bus = EventBus()
    registry = AgentRegistry()
    memory = MemorySystem()
    registry.register_default(
        provider=getattr(args, "provider", "auto"),
        ollama_model=getattr(args, "ollama_model", "llama3.2"),
        ollama_host=getattr(args, "ollama_host", "http://localhost:11434"),
        timeout=getattr(args, "timeout", 0),
    )

    state = _build_mission_state(mission_id, brief)

    coordinator = Coordinator(registry, event_bus, memory)
    shared = SharedState()
    shared.mission = type(shared.mission)(mission_id=mission_id, brief=brief)

    print(f"Starting mission: {mission_id}")
    result = await coordinator.run_mission(state, shared)

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
    """Resolve a BOND escalation and unblock a mission.

    Writes missions/<mission_id>/escalations/resolution.json which
    BOND checks before proceeding.
    """
    import json as _json
    mission_id = args.mission_id
    action = args.action
    resolution = {
        "resolved": True,
        "action": action,
        "resolved_at": datetime.now().isoformat(),
        "resolved_by": "CRESSIDA COMMAND",
    }
    path = Path("missions") / mission_id / "escalations" / "resolution.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json.dumps(resolution, indent=2), encoding="utf-8")
    print(f"Escalation resolved for mission {mission_id}.")
    print(f"  Action: {action}")
    print(f"  Resolution written to: {path}")
    return 0
