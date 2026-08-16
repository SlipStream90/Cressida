<div align="center">

# CRESSIDA

### Autonomous Multi-Agent Software Engineering Framework

**Transform a plain-English software brief into a production-ready software system.**

From research and architecture to implementation, review, and continuous learning — coordinated by an autonomous team of specialized AI software engineers.

<p align="center">
  <strong>Research</strong> •
  <strong>Architecture</strong> •
  <strong>Planning</strong> •
  <strong>Implementation</strong> •
  <strong>Review</strong> •
  <strong>Learning</strong>
</p>

<p align="center">

![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)
![License](https://img.shields.io/badge/License-MIT-success)
![MCP](https://img.shields.io/badge/MCP-Compatible-purple)
![Platform](https://img.shields.io/badge/macOS-Linux-Windows-orange)
![Providers](https://img.shields.io/badge/Providers-9-green)

</p>

Supports

**Claude Code • Codex • OpenCode • Kilo Code • Anthropic • OpenAI • Gemini • Groq • Ollama**

---

**If you find CRESSIDA useful, please consider giving it a star.**

</div>

---

# Installation

CRESSIDA supports macOS, Linux, Windows, WSL, Docker, and Homebrew — and automatically integrates with **Claude Code**, **opencode**, and **Codex** through MCP, registering itself as an auto-invoked skill in every client that supports one.

## Requirements

| Requirement | Version |
|-------------|----------|
| Python | 3.11+ |
| Git | Latest |
| Claude Code / Codex / OpenCode *(any one, optional)* | Latest |
| Ollama *(optional)* | Latest |

## Quick Install

**macOS / Linux / WSL / Git Bash**

```bash
curl -fsSL https://raw.githubusercontent.com/SlipStream90/Cressida/MI6/install.sh | bash
```

**Windows (PowerShell)**

```powershell
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
irm https://raw.githubusercontent.com/SlipStream90/Cressida/MI6/install.ps1 | iex
```

Either installer clones CRESSIDA, creates an isolated virtual environment, installs dependencies, registers the MCP server with every client found on your machine (Claude Code, opencode, Codex), installs the auto-invoke skill into Claude Code and Codex, adds CLI commands, and verifies the installation. Restart whichever client(s) you use afterward.

**Homebrew**

```bash
brew tap SlipStream90/cressida && brew install cressida
```

## Manual Installation

```bash
git clone -b MI6 https://github.com/SlipStream90/Cressida.git
cd Cressida
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
python onboard.py --provider anthropic --register
```

> **MI6 is the installation branch.** The one-line installers above already pull from it; clone it explicitly for a manual or development install.

`--register` configures MCP and installs the auto-invoke skill for every client found on your machine, verifies providers, and prints manual registration commands for anything it couldn't reach automatically.

## Docker

```bash
docker compose up
```

Recommended for CI, self-hosting, and reproducible environments.

---

# Overview

Modern coding agents are extremely capable — but they're still fundamentally **single software engineers**. No org structure, no specialization, no dependency management, no architectural review, no accumulated experience.

CRESSIDA assembles a **software engineering organization**: twelve specialized AI roles that collaborate through a full development lifecycle from one plain-English brief.

```
Research → Methodology Analysis → Product Definition → Architecture
  → Human Approval → Planning → Parallel Implementation → Review → Continuous Learning
```

No manual orchestration required.

---

# Demo

```text
# brief.md
Build a production-ready URL shortener.
Requirements: PostgreSQL, Docker, Authentication, REST API, React frontend, Unit tests, CI pipeline
```

```bash
cressida run brief.md
```

```
✓ Market research        ✓ Architecture           ✓ Backend implementation
✓ Technology evaluation  ✓ Dependency graph        ✓ Frontend implementation
✓ Product definition     ✓ Parallel scheduling     ✓ Infrastructure
                                                    ✓ Review  ✓ Learning
Mission Complete
```

---

# Architecture

```mermaid
flowchart TD
    A[Software Brief] --> M[Mission Commissioner]
    M --> R1[Research]
    M --> R2[Methodology]
    M --> PRD[Product Definition]
    R1 --> Q[Architecture]
    R2 --> Q
    PRD --> Q
    Q --> BOND{Approve?}
    BOND -->|Approved| PLAN[Planning]
    BOND -->|Rejected| STOP[Stop]
    PLAN --> BACKEND[Backend]
    PLAN --> FRONTEND[Frontend]
    PLAN --> INFRA[Infrastructure]
    BACKEND --> REVIEW[Review]
    FRONTEND --> REVIEW
    INFRA --> REVIEW
    REVIEW --> LEARNING[Learning]
    LEARNING --> DONE[Mission Complete]
```

---

# Why CRESSIDA?

Traditional coding assistants: `User → Prompt → LLM → Code → Prompt → LLM → More Code` — one context, one model, one engineer.

CRESSIDA: `User → Mission Commissioner → Research Team → Architecture Team → Planning Team → Implementation Teams → Review Team → Learning Layer → Mission Complete` — every specialist gets a dedicated role, tools, memory, context, and objectives.

---

# Core Principles

- **Autonomous Software Engineering** — specialized engineers collaborate like a real engineering team, not a single repeatedly-prompted model.
- **Parallel Execution** — independent work runs simultaneously (Research/Methodology/Product Definition together; Backend/Frontend/Infrastructure together). Only genuine dependencies block progress.
- **Mission Commissioning** — every task is analyzed before execution to pick its agent, tools, skills, and model tier, keeping prompts small and focused (see [Mission Commissioning](#mission-commissioning) below).
- **Provider Agnostic** — the same mission runs unchanged on Claude Code, Codex, OpenCode, Kilo Code, Anthropic, OpenAI, Gemini, Groq, or Ollama.
- **Human Approval Gates** — BOND reviews the architecture before implementation starts; a mission can continue, reject itself, or escalate to a human before a line of code is written (see [Human Approval Gates](#human-approval-gates)).
- **Failsafe Execution** — transient failures retry automatically with backoff, BOND's decision parsing prefers structured JSON over free-text markdown, and a crashed or escalated mission resumes instead of restarting from scratch — already-completed tasks are never re-run (see [Reliability & Live Monitoring](#reliability--live-monitoring)).
- **Retrieval-Augmented Memory** — research agents check a local, persistent knowledge store before hitting the live web, and every web result and every mission's distilled lessons feed back into it, so later missions get faster, cache-hit answers to questions earlier ones already answered (see [Continuous Learning](#continuous-learning)).

---

# Meet the Team

| Agent | Responsibility |
|-------|----------------|
| **M** | Mission commissioner — routing, orchestration, task dispatch |
| **INTELLIGENCE** | Product research, PRDs, market analysis |
| **LEITER** | Methodology research and technology validation |
| **Q** | Software architecture, APIs, system design |
| **BOND** | Autonomous approval gate and architectural review |
| **TANNER** | Planning, dependency graphs, execution scheduling |
| **BRANCH** | Backend implementation |
| **ROOK** | Frontend implementation *(routed dynamically from the backlog)* |
| **BOOTHROYD** | Infrastructure, Docker, deployment *(routed dynamically)* |
| **REVIEW** | Testing, review, quality assurance |
| **R** | Reflection, learning, long-term playbooks |
| **MONEYPENNY** | Mission knowledge management and runtime tracking *(routed dynamically)* |

Every mission always runs M, INTELLIGENCE, LEITER, Q, BOND, TANNER, BRANCH, REVIEW, and R. ROOK/BOOTHROYD/MONEYPENNY only spawn when TANNER's backlog contains matching work (frontend/infra/knowledge tasks respectively).

---

# Agent Pipeline

```mermaid
graph TD
    M --> INTELLIGENCE
    M --> LEITER
    INTELLIGENCE --> Q
    LEITER --> Q
    Q --> BOND
    BOND --> TANNER
    TANNER --> BRANCH
    TANNER --> ROOK
    TANNER --> BOOTHROYD
    BRANCH --> REVIEW
    ROOK --> REVIEW
    BOOTHROYD --> REVIEW
    REVIEW --> R
```

---

# Mission Commissioning

Before any agent executes, every task is analyzed individually to determine which engineer owns it, which tools and reusable skills it needs, and which model tier its reasoning requires — instead of exposing every tool/skill/model to every agent. Smaller prompts, cheaper execution, better focus.

```mermaid
flowchart LR
    TASK --> Router
    Router --> Agent[Agent Selection]
    Router --> Tool[Tool Selection]
    Router --> Skill[Skill Selection]
    Router --> Model[Model Selection]
    Agent --> Execute[Execution]
    Tool --> Execute
    Skill --> Execute
    Model --> Execute
```

---

# Continuous Learning

After every completed mission, CRESSIDA reflects on task outcomes, review scores, execution time, and failures — then distills the result into playbooks and reusable skills, not raw conversation history. Repeated lessons strengthen; unused ones decay. Every future mission starts smarter than the last.

```mermaid
flowchart LR
    MISSION --> Reflection
    Reflection --> Distillation
    Distillation --> Playbook
    Playbook --> Prompt[Prompt Injection]
    Prompt --> NEXT[Next Mission]
```

## Retrieval (RAG)

LEITER and INTELLIGENCE's `query_memory` calls now run through a two-tier retrieval router before any live search happens:

1. **Persistent store first** — a local FAISS-backed index (checked via `query_memory`) is searched for a relevant, sufficiently fresh match. Staleness thresholds are topic-aware: fast-moving library/version docs go stale sooner than architectural patterns.
2. **Live web fallback** — on a miss (empty store, low-confidence match, or stale doc), `web_search`/`fetch_url` run as before, results are passed through a boilerplate-stripping extractor and a query-focused summarizer, and the summary is written back into the store — so the next mission that asks a similar question gets a cache hit instead of repeating the same web search.
3. **Learning feedback loop** — every mission's distilled lessons (the reflection/playbook pipeline above) are also ingested into the same store, so architectural decisions and past solutions become searchable context for future missions automatically, with no separate crawler step.

No new tool grants were needed for this — it lives entirely behind the existing `query_memory` tool surface.

---

# Human Approval Gates

Critical architectural decisions deserve review before implementation begins:

```mermaid
flowchart TD
    Architecture --> BOND{BOND Review}
    BOND -->|Approve| Planning
    BOND -->|Reject| Stop[Mission Stops]
    BOND -->|Escalate| Human[Human Decision]
```

Escalated missions wait for a decision:

```bash
cressida resolve-escalation mission_id "Approved"
```

---

# Reliability & Live Monitoring

## Live progress, no polling

Every mission — headless (e.g. driven from opencode or Claude Code via MCP) or interactive — writes `missions/<id>/live_events.jsonl` as it runs: one line per event, the moment it happens. That includes mission-level lifecycle (task started/completed/failed, phase changes, gate decisions) *and* intra-task tool activity — every file read, edit, and bash command an agent runs shows up live, the same way Claude Code's own interactive CLI shows its tool use as it happens, instead of only the before/after of a whole task. `cressida watch` tails that file instead of repeatedly calling `mission_status`:

```bash
cressida watch                      # auto-attaches to the most recently active mission
cressida watch 20260810-url-shortener-01 --tail 30 --poll-interval 0.5
```

It shows the mission's current phase, a scrolling tail of recent events (including which tool is running right now, e.g. `-> BRANCH calling bash({"command": "npm test"})`), and a "Ns since last event" heartbeat — so a long-running task reads as "still working on X" instead of looking indistinguishable from a hang. This works across every provider — the native Anthropic agent and the OpenAI/Gemini/Groq/Ollama providers stream it directly from their own tool-use loop, and the CLI-subprocess providers (Claude Code, OpenCode, Codex, Kilo Code) surface it from their own JSON/JSONL event streams where the underlying CLI exposes one. It's purely observational: the extra events are published on a best-effort side channel that can never change a task's result, output, or control flow, under any provider. When Cressida spawns a mission via its MCP server, three ways to watch it coexist, and you can use any combination: `cressida watch <mission_id>` is the primary, always-available live view; `mission_status(mission_id)` still works for plain polling; and passing `show_window=true` to `run_mission` also opens a visible console window with the mission subprocess's raw output (Windows only). By default no window opens — the mission runs hidden and `cressida watch` is the main way to see it live.

## Automatic retry and resume

- **Transient-failure retry** — task execution retries automatically (2 retries, exponential backoff) for the transient process-termination exit-code class seen under Windows job-object/console kills, instead of writing off the whole mission on an environmental blip.
- **BOND gate hardening** — the approval gate always prefers BOND's structured JSON decision over free-text markdown when both exist (rather than racing on file-modification time), and logs a warning whenever it has to fall back to markdown parsing at all.
- **Resume** — re-running `cressida run` with the same `--mission-id` rehydrates `execution_state.json`: tasks already COMPLETED are skipped, FAILED tasks are retried, and nothing already done gets re-run. A crashed or escalated mission doesn't mean starting over. The original brief is preserved across a resume, so re-run agents never end up working from a shorter "continue where you left off" string.
- **One process per mission** — resuming a mission that is still actively running is refused rather than started alongside it. Two runs of one mission share a single `execution_state.json` and one set of output files, and nothing arbitrates between them; a terminal or stalled mission still resumes normally.
- **Honest task state** — a mission records `IN_PROGRESS` and emits `task_started` the moment work begins, not at the first task boundary. On providers that only report tool activity once their CLI exits, this is the difference between "research is running" and a dashboard full of `PENDING` that looks identical to a dead process.

```bash
cressida run brief.md --mission-id 20260810-url-shortener-01   # resumes if that mission already has progress on disk
```

---

# Feature Comparison

| Capability | Traditional Coding Agents | CRESSIDA |
|------------|--------------------------|-----------|
| Multi-Agent Architecture | No | Yes |
| Dependency Graph Execution | No | Yes |
| Parallel Scheduling | No | Yes |
| Dynamic Tool/Model Selection | No | Yes |
| Human Approval Gates | No | Yes |
| Provider Agnostic | Partial | Yes |
| Self Learning | No | Yes |
| MCP Server + Auto-Invoke Skill | Partial | Yes |
| Autonomous Daemon + Scheduling | No | Yes |

---

# Provider Configuration

CRESSIDA automatically detects whichever provider you already use — no configuration changes needed when switching.

**Priority:** `CRESSIDA_PROVIDER` env var → Anthropic/OpenAI/Gemini/Groq API keys → Claude Code CLI → OpenCode CLI → Codex CLI → Kilo Code CLI → Ollama

| Provider | Setup |
|---|---|
| Anthropic | `export ANTHROPIC_API_KEY=sk-...` |
| OpenAI | `export OPENAI_API_KEY=sk-...` |
| Gemini | `export GEMINI_API_KEY=...` |
| Groq | `export GROQ_API_KEY=...` |
| Ollama | `ollama serve`, then `--provider ollama --ollama-model qwen2.5` |
| Claude Code | No API key — auto-discovered if logged in. `--provider claude_cli` |
| OpenCode | No API key — auto-discovered if logged in. `--provider opencode` |
| Codex | No API key — auto-discovered if logged in. `--provider codex` |
| Kilo Code | No API key — auto-discovered if logged in. `--provider kilocode` |

The four CLI providers each run their own real agentic tool-use loop per task (not a single-shot completion) — Cressida shells out to `claude -p` / `opencode run` / `codex exec` / `kilo run` non-interactively and reads back the final result.

### Gateway routing (`--provider gateway`)

Instead of picking one provider for the whole mission, `--provider gateway` probes every provider you have available (API keys set, CLIs on PATH) and chooses a different one **per agent role**, based on how demanding that role's tier is — strategic/planning roles get routed to the strongest available provider, fast one-shot classification roles get routed to the quickest one, and everything else falls in between. It never invents a provider outside what's actually available on your machine, and if nothing is available it fails with the same error `--provider auto` would.

```bash
cressida run brief.md --provider gateway
```

See `core/providers/gateway.py` for the exact per-role scoring table (a tunable heuristic, not a benchmark).

---

# Verify Installation

```bash
cressida --help          # run | watch | daemon | dashboard | resolve-escalation | status | learning | ...
```

Inside Claude Code, opencode, or Codex, call `cressida_status` — expect:

```
✓ MCP Server Connected
✓ Provider Detected
✓ Mission Directory Ready
✓ Learning System Ready
```

---

# Your First Mission

```text
# brief.md
Build a production-ready Todo REST API.
Requirements: PostgreSQL, JWT Authentication, Docker, OpenAPI, Unit Tests, CI/CD
```

```bash
cressida run brief.md
```

Run against an existing repository instead of a fresh one with `--project-dir ~/Projects/MyApp` (works on monoliths, microservices, and legacy codebases too — only implementation files are written into the target project; everything else stays under `missions/`).

## Mission Outputs

```
missions/
└── 20260810-url-shortener-01/
    ├── brief.md
    ├── intelligence/{research_report,PRD,Roadmap,methodology_brief}.md
    ├── ARCHITECTURE.md
    ├── bond_decisions/
    ├── backlog.json
    ├── implementation/
    ├── review_report.md
    ├── execution_state.json
    └── live_events.jsonl        # live, append-only event log — see `cressida watch`
```

Mission IDs are `YYYYMMDD-<slug>-NN`, where the slug comes from the brief and `NN` counts that day's missions — so a directory listing reads as a dated log of what was built rather than a wall of timestamps. Uniqueness comes from reserving the directory itself, so two missions launched in the same instant can never share one.

Every engineering decision is reproducible from what's on disk.

---

# Usage

| Mode | Purpose |
|-------|----------|
| CLI | One-off missions (`cressida run brief.md`) |
| Watch | Live-tail a running mission's event log (`cressida watch`) — no console window or MCP polling needed |
| MCP Server | Integrated directly into Claude Code / opencode / Codex |
| Daemon | Fully autonomous background execution |
| Dashboard | Real-time mission monitoring |

```bash
cressida run brief.md --provider openai
cressida run brief.md --project-dir ~/Projects/MyApp
cressida run brief.md --provider ollama --ollama-model qwen2.5
```

---

# MCP Integration

CRESSIDA registers as an MCP server with Claude Code, opencode, and Codex — once installed, every mission can be started without leaving your editor, in whichever of the three you use.

Useful MCP tools: `run_mission()`, `mission_status()`, `mission_progress()`, `learning_playbook()`, `learning_nudge()`, `cressida_status()`

## Auto-invocation (skills)

Claude Code and Codex both support **skills** — description-triggered instructions the agent consults automatically, without you naming CRESSIDA explicitly. `onboard.py --register` installs a `cressida` skill (`skills/cressida/SKILL.md`) into both, so a project-sized build request in an ordinary conversation gets delegated to a mission instead of built turn-by-turn in that session. It falls back to a direct build if the MCP server isn't connected, so a missing/misconfigured server never blocks the conversation.

opencode has no skill mechanism yet, so it gets the equivalent instruction appended to its `AGENTS.md` context file instead.

---

# Daemon Mode

```bash
cressida daemon
cressida daemon --provider anthropic
cressida daemon --poll-interval 5 --status-port 7437
```

Launches the Mission Watcher, Scheduler, Stall Monitor, Status Server, and Learning Engine together.

```mermaid
flowchart TD
    Inbox --> Queue[Mission Queue]
    Queue --> Commissioning
    Commissioning --> Execution
    Execution --> Review
    Review --> Learning
    Learning --> Idle
```

## Inbox & Scheduled Missions

Drop a YAML file into `missions/inbox/` and the daemon picks it up within seconds — no CLI interaction required:

```yaml
brief: Build a Todo API
priority: high
provider: anthropic
project_dir: ~/Projects/Todo
```

For recurring work (security audits, dependency upgrades, doc generation), drop one into `missions/scheduled/` instead:

```yaml
schedule: "@weekly"   # @hourly | @daily | @weekly | @monthly | ISO timestamp | 5-field cron
brief: Run a security audit
project_dir: ~/Projects/MyApp
```

## Mission Lifecycle

```mermaid
stateDiagram-v2
    [*] --> Draft
    Draft --> Commissioned
    Commissioned --> Research
    Research --> Architecture
    Architecture --> BOND
    BOND --> Planning
    Planning --> Execution
    Execution --> Review
    Review --> Reflection
    Reflection --> Completed
```

## Monitoring

```bash
cressida dashboard                 # Mission timeline, active agents, progress, stall detection
curl localhost:7437/health         # Daemon status server
curl localhost:7437/status
```

Or poll programmatically: `mission_progress(mission_id="mission_001")` returns current phase, active tasks, recent files, completion %, and stall status.

---

# Obsidian Integration

CRESSIDA optionally mirrors every mission into an Obsidian knowledge graph — research, PRDs, architecture, reviews, decisions, and lessons, automatically synchronized and searchable across every completed mission.

```mermaid
flowchart LR
    Mission --> Artifacts
    Artifacts --> Knowledge
    Knowledge --> Playbooks
    Playbooks --> Skills
    Skills --> Future[Future Missions]
```

---

# Internal Architecture

```
                         CRESSIDA
                             │
─────────────────────────────┼─────────────────────────────
 Orchestration      Providers            Learning        Runtime
      │                 │                    │              │
 Coordinator      Anthropic/OpenAI/     Reflection      Dashboard
 Dispatcher       Gemini/Groq/Ollama    Playbooks       Daemon
 Scheduler        Claude CLI/OpenCode   Skills          MCP
 Executor         Codex CLI             Reward          Monitoring
 Context                                Memory          Progress
```

Each subsystem is independently replaceable.

```
cressida/
├── agents/            specifications, constitution, prompts
├── orchestration/      coordinator, dispatcher, scheduler, executor, dependency_graph
├── core/providers/     anthropic, openai, gemini, groq, ollama, claude_cli, opencode, codex, kilocode
├── core/retrieval/     extraction, summarization, FAISS store, staleness-routed RAG
├── core/live_log.py    per-mission JSONL event sink (backs `cressida watch`)
├── learning/           reflection, playbooks, skills, rewards, curator
├── skills/             auto-invoke skill (Claude Code / Codex)
├── memory/  knowledge/  missions/  dashboard/  autonomy/  cli/  docs/  tests/
```

---

# Security

Designed around least privilege: dynamic per-task tool exposure, human approval gates, a pre-mission git snapshot for reversibility, a hardcoded dangerous-keyword filter behind BOND's approval (send/publish/delete/merge/push and similar are stripped regardless of what was approved upstream), project-directory validation, and loopback-only local services.

---

# Roadmap

**Near term** — Kubernetes execution backend, distributed mission execution, web UI, VS Code extension, visual dependency graph, mission replay.

**Medium term** — team collaboration, multi-repository missions, remote execution, distributed schedulers, agent marketplace.

**Long term** — reinforcement learning from engineering outcomes, autonomous benchmarking, mission simulation, dynamic agent generation, multi-machine orchestration.

---

# Contributing

1. Open an issue
2. Discuss large architectural changes before starting
3. Ensure all tests pass
4. Follow formatting guidelines

## Development

```bash
git clone -b MI6 https://github.com/SlipStream90/Cressida
python onboard.py
pytest
cressida dashboard   # or: cressida daemon
```

---

# FAQ

**Does CRESSIDA require Claude?** No — Claude Code, Codex, OpenCode, Kilo Code, Anthropic, OpenAI, Gemini, Groq, and Ollama are all supported.

**Can I use local models?** Yes, via Ollama.

**Does it work on existing projects?** Yes — pass `--project-dir` and it operates directly on the existing repository.

**Does it remember previous missions?** Yes — engineering experience is distilled into reusable playbooks and skills (see [Continuous Learning](#continuous-learning)).

**Is it autonomous?** Yes — run it interactively via CLI/MCP, or continuously via the daemon's inbox and scheduler.

---

# Citation

```bibtex
@software{cressida2026,
  title={CRESSIDA: Autonomous Multi-Agent Software Engineering Framework},
  author={Aditya Singh},
  year={2026},
  url={https://github.com/SlipStream90/Cressida}
}
```

---

# License

MIT License

---

<div align="center">

## Build software like an engineering organization — not a single chatbot.

If CRESSIDA helps you, consider starring the repository.

</div>
