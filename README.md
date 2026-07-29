# CRESSIDA

**Autonomous Multi-Agent Software Engineering Intelligence Framework**

CRESSIDA takes a plain-English brief and runs a full software engineering pipeline — research, methodology scan, product definition, architecture, planning, implementation, review — using a team of specialised LLM agents coordinated by a dependency graph. It works with any major LLM provider and can run unattended via a scheduler daemon.

The pipeline:

```
research ─┬─> methodology research (LEITER) ─┬─> architecture ─> BOND gate ─>
          └─> product definition ────────────┘   planning ─> implementation ─> review
```

**M** commissions the mission before anything runs (pruning agents, tools, and models to cut tokens); **R** reflects on it afterwards (distilling lessons into per-agent playbooks). **BOND** is a hard gate in the middle.

---

## Onboarding (clone → install → use)

### Fastest: one-line install

```bash
# macOS / Linux / WSL / Git-Bash
curl -fsSL https://raw.githubusercontent.com/SlipStream90/Cressida/MI6/install.sh | bash
```

```powershell
# Windows PowerShell
irm https://raw.githubusercontent.com/SlipStream90/Cressida/MI6/install.ps1 | iex
```

Either script clones the repo to `~/.cressida`, builds an **isolated virtualenv**, installs CRESSIDA, and registers the MCP server with Claude Code — then restart the client and call `cressida_status`. Add a provider with `CRESSIDA_PROVIDER=anthropic` before running, or stay keyless via the Claude Code / opencode CLI. Re-run any time to update. *(Requires the repo to be public and `git` + Python 3.11+ installed.)*

**Homebrew** (macOS/Linux):

```bash
brew tap SlipStream90/cressida && brew install cressida
```

Taps from [`SlipStream90/homebrew-cressida`](https://github.com/SlipStream90/homebrew-cressida), installing the [`v0.1.0`](https://github.com/SlipStream90/Cressida/releases/tag/v0.1.0) release into an isolated venv (`cressida` and `cressida-mcp` land on your `PATH`). Run `brew info cressida` after install for the exact MCP registration command. Formula source: [`packaging/homebrew/cressida.rb`](packaging/homebrew/cressida.rb).

### Manual: clone and bootstrap

Prefer to see each step? Three of them.

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

**Obsidian is optional.** Nothing in onboarding requires it. If `CRESSIDA_OBSIDIAN_VAULT` is unset, the vault bridge simply no-ops — missions, the M dispatcher, and the R learning loop all run normally, and memory/lessons/playbooks still persist to local JSON/Markdown under `memory/` and `knowledge/`. Set the vault later only if you want the graph mirror.

> **Prefer to do it by hand?** `pip install -e ".[anthropic]"` then add the MCP server yourself. The key detail: launch it with the **same Python** you installed into (use that interpreter's absolute path in `command`), because `python -m cressida.mcp_server` must resolve the installed `cressida` package.

---

## Agents

| Agent | Role |
|---|---|
| **M** | Mission commissioner and dispatcher. Runs first on every mission and decides *who* runs it — activating only the agents a task needs and handing each a pruned toolset, relevant skills, and a right-sized model. This is the token-efficiency layer. |
| **R** | Records and learning curator. Runs *after* every mission and distils what happened into per-agent playbooks and reusable skills, then consolidates them. Those lessons are injected back into agents' future prompts — this is the self-improvement layer. |
| **BOND** | Mission director and autonomous gate. Reviews architecture before planning proceeds; can reject a plan or escalate to a human. |
| **INTELLIGENCE** | Research and product definition. Produces market research, PRDs, and roadmaps. |
| **LEITER** | External intelligence. As soon as the mission is drafted, goes out to the open internet and reads primary sources to establish how this is actually built *today* — current versions, idiomatic patterns, deprecated approaches, known pitfalls — and writes a cited methodology brief that Q's architecture and BRANCH's implementation are held to. |
| **Q** | Architecture. Converts the PRD into a system design, API contracts, and data models. |
| **TANNER** | Planning. Builds the dependency graph, finds the parallelisable batches and critical path, and populates the backlog. |
| **BRANCH** | Backend implementation. APIs, services, database layer. |
| **ROOK** | Frontend implementation. UI components, client-side logic. |
| **BOOTHROYD** | Infrastructure and deployment. Dockerfiles, Kubernetes manifests, CI/CD pipelines. |
| **MONEYPENNY** | Knowledge operations and runtime tracking. Keeps the mission dossier up to date. |
| **REVIEW** | Code review, testing, and coverage audit. Final quality gate before mission close. |

Tasks run in parallel wherever the dependency graph allows — LEITER's methodology research runs alongside INTELLIGENCE's product definition, and Q waits on both. BOND sits as a mandatory checkpoint between architecture and planning — if BOND rejects the plan, all downstream tasks are blocked.

LEITER exists because a model's priors go stale. It is the one agent required to cite a fetched URL and date for every claim, and to mark anything it could not verify as `[UNVERIFIED]` — so the architecture is designed against the ecosystem as it is now, not as it was at training time. Web search uses `BRAVE_API_KEY` when set and falls back to DuckDuckGo; `fetch_url` reads the pages themselves.

---

## The constitution

Every agent's prompt carries [`agents/CONSTITUTION.md`](agents/CONSTITUTION.md) — 15 articles that govern *how* agents work, injected ahead of the role spec and outranking it. Precedence is: a resolved human escalation → the constitution → the agent spec → the learned playbook → the agent's own judgment.

Each article pairs a rule with **the reason it exists**, deliberately: an agent that understands why a rule is there can apply it to a situation the wording never anticipated, where one that merely memorised it will either follow it into absurdity or drop it the moment the phrasing doesn't quite fit. The articles cover scope discipline, producing declared artifacts at declared paths, evidence over recall, faithful reporting, when to escalate versus when to just go check, role boundaries, decision trails, least privilege, secrets, and finishing the whole task.

Two properties are treated as load-bearing above the rest — **honest reporting** and **reversibility** — because those are what make every other rule recoverable when it gets broken.

---

## Directories: the install vs. the target project

A mission spans two trees, and keeping them straight is what lets Cressida run against any project from any working directory:

| Tree | What lives there | How it resolves |
|---|---|---|
| **Cressida home** | Agent specs, knowledge, playbooks, and all mission artifacts (`missions/<id>/`) | The package directory. Override with `CRESSIDA_HOME`; move just missions with `CRESSIDA_MISSIONS_DIR`. |
| **Target project** | The codebase the mission acts on — where implementation source is written | `--project-dir`, else `CRESSIDA_PROJECT_DIR`, else the current directory. |

Analysis artifacts (research report, methodology brief, PRD, architecture, review) always stay in the mission directory, so a mission never litters the project it is working on. Only implementation source goes to the target.

All path resolution goes through [`core/paths.py`](core/paths.py): relative paths are anchored to Cressida home, never the process working directory, while **absolute paths pass through untouched** — which is how an agent writes into the target project.

```bash
# Act on an existing codebase from anywhere
cressida run brief.md --project-dir /path/to/my-app
```

> Naming the target in the brief prose is **not** sufficient. CLI-backed providers (`claude_cli`, `opencode`) run sandboxed and are only granted the directories Cressida passes them, so the target must be supplied as a parameter — via `--project-dir`, the MCP `project_dir` argument, or `project_dir:` in an inbox brief's frontmatter.

---

## Commissioning & token efficiency (M)

Before any agent is invoked, **M** commissions the mission. The `Coordinator` runs M's `Dispatcher` (`orchestration/dispatcher.py`) over the task graph and, for each task, decides:

- **Which agent** owns it (via the router map — no LLM call needed for the common case).
- **Which tools** to expose — the smallest sufficient toolset. Every tool schema dropped is input tokens saved on *every* round of that agent's agentic loop. A `Q` architecture task never sees `run_shell`; a read-only research task never sees `write_file`.
- **Which skills** to load — added on a clear keyword match (e.g. a charting task pulls in `dataviz`) *and* unconditionally for every code-writing task (`BRANCH`, `ROOK`, `BOOTHROYD`, `REVIEW`), which always get **`ponytail`** — anti-over-engineering guidance (YAGNI, stdlib-first, simplest-thing-that-works) — regardless of whether the brief happens to say "simplify."
- **Which model** — the cheapest tier that satisfies the task's reasoning demand.

The commission is written back onto each `Task.metadata` (`toolset`, `skills`, `model_hint`, `skip`), so `LLMAgent` picks it up automatically — `select_tools_for_task()` sends only the pruned tools, and it **fails open** (full toolset) whenever a selection is uncertain, so a commission never blocks a mission.

**Mission-level sizing** (`orchestration/commissioner.py`) runs one short, cheap classification call *before* the task graph is even built: a genuinely trivial brief (a single small script/CLI/utility) skips the field-survey `methodology_research` phase entirely and marks its remaining strategic tasks so they run on the faster planner-tier model instead of the executor tier — a one-file CLI tool no longer runs the identical multi-document, top-tier-model pipeline as a production backend. A misclassification always falls back to the full pipeline, never the reverse.

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

| Provider | Models | What to set |
|---|---|---|
| Anthropic / Claude Code CLI | see per-role tiering below | `ANTHROPIC_API_KEY`, or nothing if `claude` is installed & logged in |
| OpenAI | gpt-4o / gpt-4o-mini | `OPENAI_API_KEY` |
| Google Gemini | gemini-1.5-pro / gemini-1.5-flash | `GEMINI_API_KEY` |
| Groq | llama-3.3-70b-versatile / llama-3.1-8b-instant | `GROQ_API_KEY` |
| **opencode CLI** | whatever your opencode auth provides | **nothing — no API key**, just `opencode` installed & logged in |
| Ollama | any local model (default: llama3.2) | Ollama running at localhost:11434 (no key) |

If no key is set, CRESSIDA falls back to the `claude` CLI, then `opencode`, then Ollama — so a machine that already runs Claude Code or opencode needs no extra credentials.

**Per-role model tier (Anthropic-backed providers, `core/model_tiers.py` — single source of truth for both the native and CLI providers):**

| Tier | Roles | Model | Why |
|---|---|---|---|
| Fast | `M`, `R` | `claude-haiku-4-5-20251001` | one-shot classification / post-hoc distillation, off the critical path |
| Planner | `INTELLIGENCE`, `LEITER`, `Q`, `BOND`, `TANNER` | `claude-sonnet-5` | output is gated (BOND) or read by the next agent, not shipped as-is |
| Executor | `BRANCH`, `ROOK`, `BOOTHROYD`, `MONEYPENNY`, `REVIEW` | `claude-opus-5` | output ships as the mission's actual deliverable |

M's mission-sizing (above) can further downgrade a planner-tier task to the fast tier for trivial missions via `Task.metadata["model_hint"]`.

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

Optional (for web research by LEITER and INTELLIGENCE):

```bash
export BRAVE_API_KEY=...         # uses Brave Search; falls back to DuckDuckGo
```

Search works keyless via the DuckDuckGo fallback, but a Brave key makes it reliable — worth setting, since LEITER's whole job depends on it. Page reading (`fetch_url`) needs no key.

---

## Usage

### Run a mission

```bash
cressida run brief.md
```

`brief.md` is a plain-text description of what you want built. Mission artifacts land in `cressida/missions/<mission-id>/`; the run prints both the mission directory and the resolved target project on startup.

```bash
# Point the mission at an existing codebase (see Directories, above)
cressida run brief.md --project-dir /path/to/my-app

# Force a specific provider
cressida run brief.md --provider openai

# Use a local Ollama model
cressida run brief.md --provider ollama --ollama-model qwen2.5
```

### Run as a daemon (autonomous mode)

```bash
cressida daemon                       # keyless if Claude Code / opencode CLI is logged in
cressida daemon --provider anthropic  # or pin a provider
cressida daemon --poll-interval 5 --status-port 7437
```

The daemon starts the mission watcher, the stall monitor, and the status server together, and prints the exact directories it watches on startup. It runs until Ctrl-C and uses the **same provider auto-detection** as `cressida run` — so no API key is needed if a CLI provider or Ollama is available.

The daemon watches two directories:

- `cressida/missions/inbox/` — drop a `.yaml` file to trigger a mission immediately
- `cressida/missions/scheduled/` — schedule missions with cron or datetime expressions

**Inbox trigger** (`cressida/missions/inbox/my-task.yaml`):

```yaml
brief: "Build a REST API for a todo app with PostgreSQL"
priority: high
project_dir: "C:/path/to/my-app"    # optional — target codebase
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

### Watch a mission live

Every `run_mission` MCP call spawns the mission in its **own console window** (a real OS subprocess, not silent in-process execution), and prints a running narration as it works — one line per task lifecycle event, no polling required:

```
[12:18:42] [RUN]  Mission mission_20260729_120842 started - Build a CSV to JSON CLI tool
[12:18:42] [....] INTELLIGENCE -> research starting
[12:20:57] [OK]   INTELLIGENCE -> research done (134.6s)
...
```

For a birds-eye view across every mission at once, a local dashboard runs alongside the MCP server (also launchable standalone):

```bash
cressida dashboard --port 7438   # http://localhost:7438
```

It auto-refreshes every 2.5s, showing each mission's phase stepper, current agent, task list with inline error text on failure, recent file activity, and a stall flag — all backed by `core/progress.py`, the same disk-polled state the `mission_progress` MCP tool exposes:

```
mission_progress(mission_id="mission_20260729_120842")   # phase, tasks, files, stalled: bool
```

`mission_progress` infers the mission's phase from which milestone files actually exist on disk (works even before `execution_state.json` is written, during the pre-task research/PRD stretch), so it's the tool to reach for over `mission_status` when you actually want to know *what's happening right now*.

---

## Project structure

```
cressida/
├── agents/          # Agent specs (markdown system prompts) + CONSTITUTION.md
├── autonomy/        # Daemon: watcher, stall monitor, post-mortem analyser
├── cli/             # CLI entry points (run, daemon, resolve-escalation)
├── core/
│   ├── llm_agent.py         # Anthropic agentic loop
│   ├── paths.py             # Canonical path resolution (home vs target project)
│   ├── providers/           # Claude CLI / opencode / OpenAI / Gemini / Groq / Ollama + auto-detect
│   ├── tools/               # Tool definitions and implementations
│   └── agent_factory.py     # Instantiates all 12 agents for a given provider
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
├── install.sh       # curl | bash installer (macOS/Linux/WSL)
├── install.ps1      # irm | iex installer (Windows)
├── packaging/       # Homebrew formula (tap) and other distribution files
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

### Environment variables

| Variable | Effect |
|---|---|
| `CRESSIDA_PROVIDER` | Force a provider, bypassing auto-detection |
| `CRESSIDA_HOME` | Relocate the whole installation (specs, knowledge, missions) |
| `CRESSIDA_MISSIONS_DIR` | Put mission artifacts elsewhere — e.g. outside a repo |
| `CRESSIDA_PROJECT_DIR` | Default target project for missions |
| `CRESSIDA_OBSIDIAN_VAULT` | Vault path for the graph mirror (optional — no-ops if unset) |
| `BRAVE_API_KEY` | Reliable web search for LEITER / INTELLIGENCE |
| `CRESSIDA_CLAUDE_CLI` | Explicit path to the `claude` binary if it isn't on `PATH` |

---

## How BOND gating works

After architecture is complete, BOND runs `bond_approve_plan` as a DAG task. It receives the full architecture document and uses its `approve_phase`, `reject_phase`, or `escalate` tools:

- **approve** — planning and implementation proceed in parallel
- **reject** — `PhaseRejectedError` propagates through the executor; planning is marked FAILED and all dependent tasks are blocked
- **escalate** — execution halts; writes an escalation JSON for human review; resume with `cressida resolve-escalation`

This is a hard gate, not advisory. Nothing downstream runs without BOND's sign-off.

**Implementation is verified, not just trusted**: after `BRANCH` runs, the executor checks that at least one file under the mission or target-project directory actually changed since the task started. A sandboxed CLI subprocess that gets its write access denied returns normal-looking text — it just narrates the code instead of saving it — which used to get silently recorded as a successful implementation. That case is now marked FAILED with an explicit error instead.

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
