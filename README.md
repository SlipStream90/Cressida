# CRESSIDA

**Autonomous Multi-Agent Software Engineering Intelligence Framework**

CRESSIDA takes a plain-English brief and runs a full software engineering pipeline — research, spec, architecture, implementation, tests, review — using a team of specialised LLM agents coordinated by a dependency graph. It works with any major LLM provider and can run unattended via a scheduler daemon.

---

## Onboarding (clone → install → use)

Cloned the repo and want to drive CRESSIDA from Claude Code (or any MCP client)? Three steps.

```bash
# 1. Clone
git clone git@github.com:SlipStream90/Cressida.git cressida
cd cressida

# 2. (recommended) isolate in a virtual environment
python -m venv .venv
# Windows:        .venv\Scripts\activate
# macOS / Linux:  source .venv/bin/activate

# 3. Bootstrap: installs CRESSIDA + wires up the MCP server
python onboard.py --provider anthropic
```

`onboard.py` verifies your Python (3.11+), runs `pip install -e .` so `python -m cressida.mcp_server` works from any directory, and prints the exact MCP-server config **pinned to your interpreter**. Pass `--register` to add it to Claude Code automatically (needs the `claude` CLI); otherwise copy the printed command:

```bash
claude mcp add-json cressida '{"command":"/path/to/python","args":["-m","cressida.mcp_server"]}' --scope user
```

Or paste the block it prints into `~/.claude.json` (or your client's `mcpServers`), then restart the client.

**No API key required.** If you already have the **Claude Code** or **opencode** CLI installed and logged in, CRESSIDA auto-detects it and runs missions through that CLI's own session — no provider key, no billing setup. Auto-detection order is: any provider key you've set → `claude` CLI → `opencode` CLI → local Ollama. So the keyless paths are:

```bash
# already logged into Claude Code or opencode? nothing to set — it just works.
cressida run brief.md --provider claude_cli    # force the Claude CLI
cressida run brief.md --provider opencode       # force opencode
cressida run brief.md --provider ollama         # local models, also keyless
```

Prefer a hosted key instead? Set one and it takes priority:

```bash
export ANTHROPIC_API_KEY=sk-...          # or OPENAI_API_KEY / GEMINI_API_KEY / GROQ_API_KEY
```

Verify inside Claude Code by calling the `cressida_status` tool, then kick off work with `run_mission(brief="Build a todo REST API with PostgreSQL")`. Everything else — CLI (`cressida run`), the daemon, and Obsidian sync — is documented below.

> **Prefer to do it by hand?** `pip install -e ".[anthropic]"` then add the MCP server yourself. The key detail: launch it with the **same Python** you installed into (use that interpreter's absolute path in `command`), because `python -m cressida.mcp_server` must resolve the installed `cressida` package.

---

## Agents

| Agent | Role |
|---|---|
| **M** | Mission commissioner and dispatcher. Runs first on every mission and decides *who* runs it — activating only the agents a task needs and handing each a pruned toolset, relevant skills, and a right-sized model. This is the token-efficiency layer. |
| **R** | Records and learning curator. Runs *after* every mission and distils what happened into per-agent playbooks and reusable skills, then consolidates them. Those lessons are injected back into agents' future prompts — this is the self-improvement layer. |
| **BOND** | Mission director and autonomous gate. Reviews architecture before planning proceeds; can reject a plan or escalate to a human. |
| **INTELLIGENCE** | Research and product definition. Produces market research, PRDs, and roadmaps. |
| **Q** | Specification writer. Converts the PRD into an engineering spec and test strategy. |
| **TANNER** | Test engineer. Writes the full test suite before implementation begins. |
| **BRANCH** | Backend implementation. APIs, services, database layer. |
| **ROOK** | Infrastructure and deployment. Dockerfiles, Kubernetes manifests, CI/CD pipelines. |
| **BOOTHROYD** | Frontend implementation. UI components, client-side logic. |
| **MONEYPENNY** | Documentation and project tracking. Keeps the mission dossier up to date. |
| **REVIEW** | Code review and coverage audit. Final quality gate before mission close. |

Tasks run in parallel wherever the dependency graph allows. BOND sits as a mandatory checkpoint between architecture and planning — if BOND rejects the plan, all downstream tasks are blocked.

---

## Commissioning & token efficiency (M)

Before any agent is invoked, **M** commissions the mission. The `Coordinator` runs M's `Dispatcher` (`orchestration/dispatcher.py`) over the task graph and, for each task, decides:

- **Which agent** owns it (via the router map — no LLM call needed for the common case).
- **Which tools** to expose — the smallest sufficient toolset. Every tool schema dropped is input tokens saved on *every* round of that agent's agentic loop. A `Q` architecture task never sees `run_shell`; a read-only research task never sees `write_file`.
- **Which skills** to load — none by default, added only on a clear keyword match (e.g. a charting task pulls in `dataviz`).
- **Which model** — the cheapest tier that satisfies the task's reasoning demand.

The commission is written back onto each `Task.metadata` (`toolset`, `skills`, `model_hint`, `skip`), so `LLMAgent` picks it up automatically — `select_tools_for_task()` sends only the pruned tools, and it **fails open** (full toolset) whenever a selection is uncertain, so a commission never blocks a mission.

Each plan is recorded to strategic memory and stored as a subnode under the **Logs** branch in Obsidian, alongside an estimate of the tool schemas and agents it avoided activating.

---

## Learning & self-improvement (R)

Inspired by Nous Research's [Hermes](https://github.com/nousresearch/hermes-agent) agent, CRESSIDA runs a **closed learning loop** so the team gets better over missions instead of starting cold every time. Where M runs *before* a mission to make it cheap, **R** runs *after* it to make the next one smarter.

At mission finalization the `Coordinator` invokes R's learning layer (`learning/`):

1. **Reflect** — the `ReflectionEngine` reads task outcomes, review scores, execution times, and feedback from the reward store. Unlike the failure-only post-mortem analyser, it learns from **successes** too.
2. **Distil** — signals become short, reusable lessons attributed to the specific agent that should learn them: **heuristics** (do this), **patterns** (reliable approaches), and **cautions** (`[AVOID]` — known pitfalls).
3. **Reinforce, don't duplicate** — a repeated lesson bumps an existing entry's score and hit-count; lessons that stop being reinforced **decay**.
4. **Synthesize skills** — a task type completed successfully for the first time becomes a reusable **skill** (a procedure note under `knowledge/skills/`). Recurrence self-improves it; a later failure flags it `needs_review`.
5. **Consolidate** — the `Curator` merges duplicates and prunes each playbook to a bounded top-N, so injected knowledge stays sharp and **token-cheap**.

The loop closes in the `ContextBuilder`: every prompt for a role now carries a **`## Learned Playbook`** section with that agent's highest-ranked lessons. An agent's own accumulated experience shapes its future behaviour — the mechanism by which CRESSIDA actually *learns*.

Playbooks live at `knowledge/playbooks/<role>.json` (with a rendered `.md` mirror) and each reflection is mirrored as a subnode under the **Knowledge** branch in Obsidian. Inspect the state any time:

```
learning_playbook(role="BRANCH")   # MCP tool — a role's top lessons
learning_nudge()                   # digest of strongest lessons + synthesised skills
```

Everything is best-effort: with no LLM key, no reward records, or no vault, reflection still records what it can from task outcomes and never affects a mission's result.

---

## Providers

CRESSIDA is not tied to any single LLM. Set whichever API key you have and it auto-detects:

| Provider | Models (strategic / impl) | What to set |
|---|---|---|
| Anthropic | claude-opus-4-8 / claude-sonnet-4-6 | `ANTHROPIC_API_KEY` |
| OpenAI | gpt-4o / gpt-4o-mini | `OPENAI_API_KEY` |
| Google Gemini | gemini-1.5-pro / gemini-1.5-flash | `GEMINI_API_KEY` |
| Groq | llama-3.3-70b-versatile / llama-3.1-8b-instant | `GROQ_API_KEY` |
| **Claude Code CLI** | whatever your `claude` login provides | **nothing — no API key**, just `claude` installed & logged in |
| **opencode CLI** | whatever your opencode auth provides | **nothing — no API key**, just `opencode` installed & logged in |
| Ollama | any local model (default: llama3.2) | Ollama running at localhost:11434 (no key) |

If no key is set, CRESSIDA falls back to the `claude` CLI, then `opencode`, then Ollama — so a machine that already runs Claude Code or opencode needs no extra credentials.

Override detection at any time:

```bash
export CRESSIDA_PROVIDER=gemini      # env var
cressida run brief.md --provider groq   # CLI flag
```

---

## Installation

The one-liner is `python onboard.py` (see [Onboarding](#onboarding-clone--install--use)). To install manually from the repo root:

```bash
pip install -e ".[anthropic]"    # framework + a provider (or .[openai] / .[gemini] / .[groq] / .[all])
```

`pyyaml`, `aiohttp`, and `mcp` come in automatically as core dependencies (needed for the daemon scheduler and the MCP server).

Optional (for web search in INTELLIGENCE):

```bash
export BRAVE_API_KEY=...         # uses Brave Search; falls back to DuckDuckGo
```

---

## Usage

### Run a mission

```bash
cressida run brief.md
```

`brief.md` is a plain-text description of what you want built. Output lands in `cressida/missions/<mission-id>/`.

```bash
# Force a specific provider
cressida run brief.md --provider openai

# Use a local Ollama model
cressida run brief.md --provider ollama --ollama-model qwen2.5
```

### Run as a daemon (autonomous mode)

```bash
cressida daemon --provider anthropic
```

The daemon watches two directories:

- `cressida/missions/inbox/` — drop a `.yaml` file to trigger a mission immediately
- `cressida/missions/scheduled/` — schedule missions with cron or datetime expressions

**Inbox trigger** (`cressida/missions/inbox/my-task.yaml`):

```yaml
brief: "Build a REST API for a todo app with PostgreSQL"
priority: high
```

**Scheduled trigger** (`cressida/missions/scheduled/weekly-audit.yaml`):

```yaml
schedule: "@weekly"          # or: "2026-07-01T09:00:00", "@daily", "@hourly"
brief: "Run a security audit on the codebase"
```

### Resolve an escalation

When BOND escalates (human decision required), it writes to `missions/<id>/escalations/`. Resume after reviewing:

```bash
cressida resolve-escalation <mission-id> "Approved — proceed with microservices approach"
```

---

## Status and monitoring

While the daemon runs, a status server is available at `http://localhost:7437`:

```bash
curl http://localhost:7437/status   # JSON — task counts, stalled task IDs
curl http://localhost:7437/health   # {"ok": true}
```

Stalled tasks (no progress for 30 min) are detected automatically. Post-mortems are written to `memory/postmortems/` and INTELLIGENCE synthesises lessons into `knowledge/lessons.md`.

---

## Project structure

```
cressida/
├── agents/          # Agent personality specs (markdown system prompts — never modified)
├── autonomy/        # Daemon: watcher, stall monitor, post-mortem analyser
├── cli/             # CLI entry points (run, daemon, resolve-escalation)
├── core/
│   ├── llm_agent.py         # Anthropic agentic loop
│   ├── providers/           # OpenAI / Gemini / Groq / Ollama agents + auto-detect
│   ├── tools/               # Tool definitions and implementations
│   └── agent_factory.py     # Instantiates all 11 agents for a given provider
├── evaluation/      # Scoring, reward store, feedback collector
├── learning/        # Self-improvement loop (R): playbooks, reflection, skills, curator
├── obsidian/        # Obsidian bridge: bidirectional vault sync, inbox watcher
├── knowledge/       # Persistent lessons, playbooks, and synthesised skills
├── memory/          # Strategic, mission, and agent memory layers
├── missions/        # Output directory — one folder per mission
│   ├── inbox/       # Drop YAML here to trigger a mission
│   └── scheduled/   # Cron/datetime scheduled missions
├── orchestration/   # Coordinator, dispatcher (M), scheduler, dependency graph, executor, context builder
├── state/           # MissionState, AgentState, SharedState
├── mcp_server.py    # MCP server — exposes missions/status/learning as tools
├── onboard.py       # One-command collaborator setup (install + MCP wiring)
├── pyproject.toml   # Packaging — makes the clone `pip install -e .`-able
└── cressida.yaml    # Configuration
```

---

## Configuration

All defaults live in `cressida/cressida.yaml`. Key sections:

```yaml
agents:
  provider: "auto"          # auto | anthropic | openai | gemini | groq | ollama

autonomy:
  monitor:
    stall_threshold_seconds: 1800   # 30 min before a task is flagged stalled
    status_port: 7437
  bond:
    confidence_threshold: 0.7       # BOND's internal gate threshold
```

---

## How BOND gating works

After architecture is complete, BOND runs `bond_approve_plan` as a DAG task. It receives the full architecture document and uses its `approve_phase`, `reject_phase`, or `escalate` tools:

- **approve** — planning and implementation proceed in parallel
- **reject** — `PhaseRejectedError` propagates through the executor; planning is marked FAILED and all dependent tasks are blocked
- **escalate** — execution halts; writes an escalation JSON for human review; resume with `cressida resolve-escalation`

This is a hard gate, not advisory. Nothing downstream runs without BOND's sign-off.

---

## Obsidian integration

CRESSIDA has a bidirectional sync with an [Obsidian](https://obsidian.md) vault. Mission artifacts, BOND decisions, and accumulated knowledge are mirrored into the vault in real time; the vault's Inbox folder can trigger new missions without touching the CLI.

### Vault layout

```
Vault/
└── Cressida/
    ├── Inbox/              ← drop a brief note here to trigger a mission
    ├── Missions/
    │   └── MSN-2026-001/
    │       ├── Brief.md
    │       ├── Research Report.md
    │       ├── PRD.md
    │       ├── Architecture.md
    │       └── Review.md
    ├── Knowledge/          ← main branch (MOC + subnodes)
    │   ├── Knowledge.md         (branch index — links every subnode below)
    │   └── <subnode>.md
    ├── Mission Memory/
    ├── Logs/
    ├── Decisions/
    ├── Escalations/
    ├── Post-Mortems/
    └── BOND Decisions/
```

### Memory as a graph (branches → subnodes)

Every memory CRESSIDA stores becomes a **subnode under a main branch**, not a loose file. Each branch has a Map-of-Content (MOC) index note (`<Branch>/<Branch>.md`) that links to its subnodes, and each subnode carries an `up: "[[<Branch>]]"` link back — so Obsidian's graph view renders clean branch → subnode trees.

The main branches are: **Knowledge**, **Mission Memory**, **Logs**, **Decisions**, **Escalations**, **Post-Mortems**.

Storage is routed automatically:

- `MemorySystem.write()` mirrors every write into the correct branch (inferred from the path/tags, or set explicitly via `metadata["branch"]`).
- The `Dispatcher` files each commission plan under **Logs**.
- Agents and users can store a subnode directly via the MCP tool:

```
obsidian_store_memory(branch="knowledge", title="LoRA vs fine-tuning",
                      content="…", tags="ml", mission_id="MSN-1", agent="INTELLIGENCE")
```

All subnode storage is best-effort: if no vault is configured, the local memory write still succeeds and nothing breaks.

### Setup

```bash
export CRESSIDA_OBSIDIAN_VAULT="C:/Users/you/Documents/MyVault"
# or set vault_path in cressida.yaml under the obsidian: key
```

`cressida.yaml`:

```yaml
obsidian:
  vault_path: "C:/Users/you/Documents/MyVault"
  cressida_folder: "Cressida"
  inbox_folder: "Inbox"
  poll_interval_seconds: 15
```

### Triggering a mission from the vault

Create a `.md` note in `Vault/Cressida/Inbox/` with `cressida: true` in the YAML frontmatter:

```markdown
---
cressida: true
brief: "Build a REST API for a todo app with PostgreSQL"
priority: high
provider: anthropic
---
```

The daemon polls the inbox every 15 seconds (configurable), picks up the note, launches a mission, and moves the note to `Inbox/_processed/`.

### What syncs automatically

| Event | What lands in the vault |
|---|---|
| Task completes | Mission artifacts (PRD, Architecture, Review, …) → `Missions/<id>/` |
| Mission completes | Full artifact set + `Index.md` with wikilinks to every artifact |
| BOND gate decision | Verdict note → `BOND Decisions/` |
| Post-mortem | Lessons and patterns → `Knowledge/` and `Post-Mortems/` subnodes |
| Any memory write | Subnode filed under its main branch, linked from the branch MOC |
| Mission commissioned | M's commission plan → `Logs/` subnode |
| Mission reflected on | R's distilled lessons → `Knowledge/` subnode |

Agents can also search the vault during research — INTELLIGENCE queries vault notes alongside Cressida's internal strategic memory.

---

## Memory layers

| Layer | Scope | Where |
|---|---|---|
| StrategicMemory | Across all missions | `memory/*.json` |
| MissionMemory | One mission | In-memory during run |
| AgentMemory | One agent, one task | Scratch space per task |

Lessons learned from post-mortems accumulate in `knowledge/lessons.md` and are fed back into future INTELLIGENCE prompts via ContextBuilder.
