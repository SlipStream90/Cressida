# CRESSIDA Architecture

## Overview
CRESSIDA is an autonomous multi-agent software engineering intelligence framework. It operates as a coordinated system of 8 specialized agents orchestrated by BOND, executing missions through a structured pipeline of intelligence, planning, implementation, and review.

## System Architecture

```
┌─────────────────────────────────────────────────────┐
│                   CRESSIDA COMMAND                   │
│           Mission Authority & Lifecycle Mgmt         │
└────────────────────┬────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────┐
│                      BOND                            │
│           Director of Operations & Orchestrator       │
│           Strategy, Approval Gates, Conflict Res.     │
└────┬──────┬──────┬──────┬──────┬──────┬──────┬─────┘
     │      │      │      │      │      │      │
  ┌──▼┐  ┌──▼──┐ ┌▼───┐ ┌▼───┐ ┌▼───┐ ┌▼───┐ ┌▼───┐
  │INT│  │ Q  │ │ T  │ │ B  │ │ R  │ │BH  │ │MP  │
  │   │  │    │ │    │ │    │ │    │ │    │ │    │
  └───┘  └─────┘ └────┘ └────┘ └────┘ └────┘ └────┘
  ┌───┐
  │RV │
  │   │
  └───┘
```

## Agent Roster (8)

| Agent | Role | Reports To |
|---|---|---|
| BOND | Director of Operations | CRESSIDA COMMAND |
| INTELLIGENCE | Research & Product Strategy | BOND |
| Q | Architecture | BOND |
| TANNER | Planning & Dependency Graph | BOND |
| BRANCH | Backend Engineering | BOND |
| ROOK | Frontend Engineering | BOND |
| BOOTHROYD | Infrastructure | BOND |
| MONEYPENNY | Knowledge Operations & Runtime Tracking | BOND |
| REVIEW | Quality & Security Assurance | BOND |

## Core Subsystems

### 1. Event System (`core/events.py`)
Async event bus with publish/subscribe pattern. All system communication flows through events. 16 event types covering full mission lifecycle.

### 2. State Management (`state/`)
Pydantic-validated shared state: MissionStateModel, ExecutionState (with NodeStatus, TaskInfo, batch tracking), AgentState (idle/busy, task history), SharedState.

### 3. Memory System (`memory/`)
Three-tier memory + retrieval:
- Strategic (cross-mission, JSON-persisted) in `memory/strategic.py`
- Mission (in-memory per mission) in `memory/mission.py`
- Agent (per-task scratch) in `memory/agent.py`
- Retrieval (keyword + semantic modes) in `memory/retrieval.py`
- Facade with write()/query() interfaces in `memory/system.py`

### 4. Orchestration (`orchestration/`)
- Context Builder (`context_builder.py`): Resolves reads[], assembles agent prompts
- Dependency Graph (`dependency_graph.py`): DAG with cycle detection, topological sort, parallel batches
- Scheduler (`scheduler.py`): Critical path computation, parallelization ratio
- Coordinator (`coordinator.py`): Mission lifecycle management
- Executor (`executor.py`): Backlog execution with dependency resolution, retry logic, failure recovery
- Router (`router.py`): Keyword-to-agent routing

### 5. Evaluation (`evaluation/`)
- Scorer (`scoring.py`): Weighted multi-dim scoring
- Metrics Collector (`metrics.py`): Category aggregation
- Reward Store (`reward_store.py`): JSONL persistence, FeedbackReceived handler
- Evaluation Records (`evaluation_records.py`): Per-mission evaluation storage
- Feedback Collector (`feedback_collector.py`): CLI feedback intake, event emission

## Data Flow

```
Mission Brief → SharedState → BOND → TANNER (Graph) → Executor (Backlog) → Agents → REVIEW → BOND (Close)
```

## Execution Pipeline

**Phase 1 — Intelligence & Planning (sequential)**
```
INTELLIGENCE (Research + PRD) → Q (Architecture) → TANNER (Task Graph) → BOND (Approval)
```

**Phase 2 — Implementation (parallel where dependencies allow)**
```
BRANCH ║ ROOK ║ BOOTHROYD
```

**Phase 3 — Review**
```
REVIEW → BOND
```

**Phase 4 — Completion**
```
BOND → CRESSIDA COMMAND (final report)
```

## Backlog Task Schema
Every task in backlog.json includes:
```json
{
  "task_id": "T-001",
  "agent": "BRANCH",
  "phase": "A",
  "reads": ["agents/branch.md", "missions/<mission_id>/ARCHITECTURE.md"],
  "writes": ["missions/<mission_id>/implementation/phase_a/"],
  "dependencies": ["T-000"],
  "complexity": "L",
  "output_artifact": "foundation services",
  "description": ""
}
```

## Technology Stack
- Python 3.11+
- Pydantic for state validation
- asyncio for concurrent execution
- JSON/JSONL for persistence
- Markdown for agent intelligence layer

## Mission-Level Patterns (MSN-2026-001 OpSpyglass)

### Pattern: API-only AI Systems
When GPU/fine-tuning infrastructure is unavailable or out of scope,
prompt engineering + weighted feedback scoring is a valid and
deployable substitute for LoRA-based personalization.
Style adaptation via system prompt variants is sufficient for
MVP preference learning. Upgrade path to fine-tuning exists
by swapping reward_service.py and style_presets.yaml for
a trained model without changing interfaces.

### Pattern: FAISS for Per-User Preference Retrieval at MVP Scale
Managed vector DBs are not required until multi-tenancy at scale.
Per-user FAISS indexes on local disk are sufficient for MVP.
Interface abstraction in vector_service.py allows migration
to managed vector DB without touching workflow code.

### Pattern: LangGraph + Redis Cloud Checkpointing
LangGraph's async node execution with Redis-backed checkpointing
enables resumable workflows across API timeouts, which is critical
for ElevenLabs synthesis latency in multi-variant generation.
