# Architecture Decision Records

## ADR-001: Intelligence Layer in Markdown
- **Status:** Accepted
- **Context:** Agent behavior must remain human-editable and interpretable
- **Decision:** All agent specifications are pure Markdown files
- **Consequences:** Agents are documents, not classes; Python never encodes agent logic

## ADR-002: Event-Driven Communication
- **Status:** Accepted
- **Context:** Agents must communicate without direct coupling
- **Decision:** All inter-agent communication flows through async EventBus
- **Consequences:** Full audit trail via event history; loose coupling

## ADR-003: Pydantic for State Validation
- **Status:** Accepted
- **Context:** Shared state must be type-safe and validated
- **Decision:** All state models use Pydantic BaseModel
- **Consequences:** Automatic validation; serialization; clear schemas

## ADR-004: Three-Layer Memory Architecture
- **Status:** Accepted (updated 2026-06-24)
- **Context:** Different retention scopes needed; agents could not query memory; writes were raw file appends
- **Decision:** Strategic (file-persisted), Mission (in-memory), Agent (scratch). Added memory/retrieval.py with keyword + semantic query modes. Added memory/system.py write() and query() structured interfaces.
- **Consequences:** Every write stores metadata (content, timestamp, mission_id, agent, task_id, tags). Agents can query memory and get ranked relevant chunks.

## ADR-005: Dependency Graph for Scheduling
- **Status:** Accepted
- **Context:** Tasks have complex dependencies requiring parallel execution
- **Decision:** DAG-based dependency graph with topological sort
- **Consequences:** Optimal parallelization; cycle detection; critical path analysis

## ADR-006: RLHF-Compatible Reward Storage
- **Status:** Accepted (updated 2026-06-24)
- **Context:** Feedback was never collected; human_feedback was always null. No feedback loop existed for reward model training.
- **Decision:** Added FeedbackCollector with CLI commands. RewardStore listens for FeedbackReceived events and persists (State, Action, Outcome, Reward) tuples.
- **Consequences:** CLI commands: cressida feedback <task_id> <score> "<comment>", cressida rewards list, cressida rewards export. Full RLHF pipeline ready.

## ADR-007: Agent Registry Pattern
- **Status:** Accepted
- **Context:** Agents must be discoverable and swappable
- **Decision:** Registry maps AgentRole to Agent implementations
- **Consequences:** Loose coupling; runtime agent swapping; testability

## ADR-008: Agent Consolidation (11 → 8)
- **Status:** Accepted
- **Context:** 11 agents at current manual-execution scale created overhead without proportional value. GREENWAY+M overlapped. ARGUS+SENTINEL overlapped. BOND was overloaded with 10 responsibilities.
- **Decision:** Merged GREENWAY+M → INTELLIGENCE. Merged ARGUS+SENTINEL → REVIEW. Redistributed BOND responsibilities across TANNER (dependency graph, parallelization, scheduling), MONEYPENNY (progress tracking, runtime bottleneck detection), and Executor (retry logic, failure recovery).
- **Consequences:** Agent count reduced to 8. BOND's spec now explicitly states what it does NOT do. All agent specs rewritten.

## ADR-009: Context Builder Module
- **Status:** Accepted
- **Context:** Every agent prompt said READ: <file> but no mechanism existed to inject file content into agent context. CRESSIDA claimed autonomy it did not have.
- **Decision:** Built orchestration/context_builder.py that reads agent specs, READ: dependencies, and relevant memory, then assembles full prompt strings.
- **Consequences:** ContextBuilder resolves reads[] at execution time. TANNER populates reads[] and writes[] in backlog.json.

## ADR-010: Backlog Task Schema with reads[] and writes[]
- **Status:** Accepted
- **Context:** Tasks lacked explicit context dependencies and output specifications. Agents worked without knowing what to read or produce.
- **Decision:** Every backlog task now has reads[], writes[], dependencies, complexity, and output_artifact fields.
- **Consequences:** TANNER populates these at planning time. Executor and ContextBuilder resolve them at execution time. Full traceability from planning to artifact.


## ADR-011: Llama 3 8B as Base Model
- **Status:** Accepted
- **Context:** ECHO needs a base LLM for narration generation with LoRA adapters
- **Decision:** Use Llama 3 8B
- **Alternatives:** Llama 3 70B (rejected: latency), Mistral 7B (rejected: weaker LoRA ecosystem)
- **Consequences:** 16GB GPU sufficient; faster inference; 5 styles manageable

## ADR-012: Reward Model as Lightweight MLP
- **Status:** Accepted
- **Context:** Reward model must be fast to train and serve; input is structured (128-dim)
- **Decision:** 3-layer MLP (128->64->32->1) with Bradley-Terry loss
- **Alternatives:** Transformer (overkill for structured input), Random Forest (slower training)
- **Consequences:** CPU inference <5ms; daily training feasible; interpretable via gradients

## ADR-013: vLLM + S-LoRA for Multi-Adapter Serving
- **Status:** Accepted
- **Context:** ECHO needs 5 LoRA adapters served concurrently with blending
- **Decision:** vLLM with S-LoRA extension
- **Alternatives:** Hugging Face PEFT (manual switching overhead), TGI (less flexible blending)
- **Consequences:** Single GPU serves all 5 adapters; adapter blending via linear weight interpolation

## ADR-014: LangGraph for Workflow Orchestration
- **Status:** Accepted
- **Context:** Variant generation involves sequential + parallel steps with state management
- **Decision:** LangGraph with Send API for parallel LoRA branches
- **Alternatives:** LangChain (linear only), Temporal (too heavy for V1), Custom DAG (redundant)
- **Consequences:** Tight LangChain coupling; native checkpointing for resilience

## ADR-015: ElevenLabs for Voice Synthesis
- **Status:** Accepted
- **Context:** High-quality narrative TTS required for listener engagement
- **Decision:** ElevenLabs with Streaming API and audio caching
- **Alternatives:** AWS Polly (lower quality), Coqui (self-hosted but inferior)
- **Consequences:** External dependency; rate limits mitigated via caching layer

## ADR-016: PostgreSQL + Redis + Qdrant for Storage
- **Status:** Accepted
- **Context:** ECHO needs relational (feedback), fast-cache (variants), and vector (profiles) storage
- **Decision:** PostgreSQL (primary) + Redis (cache) + Qdrant (vector)
- **Alternatives:** MongoDB (weaker relational queries), pgvector (sufficient for 64d)
- **Consequences:** Three storage systems to operate; clear separation of concerns

# MSN-2026-001 — Technical Stack Decisions
Date: 2026-06-24
Authority: Mission Director
Status: BINDING — overrides any prior architectural assumptions

## Decision 1 — LLM Provider
Selected: Google Gemini API
Model: gemini-1.5-pro
Embedding model: models/text-embedding-004 (768-dim)
SDK: google-generativeai
Rationale: API-only deployment, no local model infrastructure required
Alternatives rejected: OpenAI GPT-4o, local Llama 3
Consequence: All LLM calls use Gemini SDK. No other LLM provider is used anywhere in this mission.

## Decision 2 — Voice Synthesis
Selected: ElevenLabs API
SDK: elevenlabs
Rationale: Best-in-class voice quality for narrative audio
Consequence: All audio synthesis routes through ElevenLabs. Voice IDs configured via environment variables.

## Decision 3 — Workflow Orchestration
Selected: LangGraph
Rationale: Native support for stateful multi-step AI pipelines, built-in checkpointing, async node execution
Consequence: All pipeline orchestration uses LangGraph graph compilation. No other orchestration framework used.

## Decision 4 — Database
Selected: Supabase (PostgreSQL)
SDK: supabase-py
Rationale: Managed PostgreSQL with built-in RLS, auth, and real-time — no infrastructure to maintain
Alternatives rejected: Local PostgreSQL, Docker DB container
Consequence: All persistent storage uses Supabase client. No local database. No Docker database container. Migrations run against Supabase directly.

## Decision 5 — Cache
Selected: Redis Cloud
SDK: redis-py
Connection: via REDIS_URL environment variable
Rationale: Managed Redis, zero infrastructure overhead
Consequence: All caching and LangGraph checkpointing use Redis Cloud. No local Redis container.

## Decision 6 — Vector Store
Selected: FAISS (local)
SDK: faiss-cpu
Embedding source: Gemini Embedding API
Index storage: echo/faiss_index/<user_id>.index
Rationale: No managed vector DB needed at current scale. FAISS sufficient for per-user segment retrieval.
Alternatives rejected: Pinecone, Qdrant, Chroma
Consequence: All vector operations use FAISS locally. No managed vector DB at any phase of this mission.

## Decision 7 — Narration Style Adaptation
Selected: Prompt engineering via Gemini system prompt variants
Implementation: 5 style templates in app/config/style_presets.yaml
Styles: Suspense, Dialogue, Emotional, Fast-Paced, Descriptive
Rationale: LoRA fine-tuning requires GPU infrastructure which is out of scope for this mission
Alternatives rejected: LoRA adapters, HuggingFace PEFT, model fine-tuning of any kind
Consequence: No model weights are modified at any point. Style adaptation is purely prompt-based. StylePreset model replaces PersonaLoRA model throughout.

## Decision 8 — Reward Model
Selected: Lightweight weighted scoring function
Implementation: app/services/reward_service.py
Scoring weights:
  Explicit positive (4-5): +0.15 to selected style
  Explicit negative (1-2): -0.10 to selected style
  Replay signal:           +0.08
  Skip signal:             -0.06
  Completion signal:       +0.05
  Pause > 30s signal:      -0.03
  All scores normalized to sum 1.0 after each update
Rationale: Neural reward model requires training data volume not available at MVP stage. Weighted scoring is deterministic, debuggable, and upgradeable.
Alternatives rejected: Bradley-Terry model, neural reward model, contrastive learning approach
Consequence: No neural reward model trained at any phase. reward_service.py is the single scoring authority.

## DROPPED SCOPE — Permanent removals from MSN-2026-001
The following items are permanently out of scope. No agent may reintroduce, suggest, or plan for these:
- LoRA adapters
- HuggingFace PEFT library
- Model fine-tuning of any kind
- TRL / OpenRLHF frameworks
- Local model weights of any kind
- GPU infrastructure
- Persona LoRA system
- Creator dashboard (was V3, dependent on Persona LoRA)
- Managed vector databases (Pinecone, Qdrant, Chroma)
- Local PostgreSQL or Docker database containers
- Any LLM provider other than Google Gemini

## ADR-009: Frontend Added to MSN-2026-001
- **Status:** Accepted
- **Date:** 2026-06-24
- **Authority:** Mission Director
- **Decision:** Add a Next.js frontend with two surfaces: Listener UI (story player, feedback, preferences) and Admin Dashboard (user analytics, A/B test management, drift reports, evaluation records).
- **Stack:** Next.js 14 App Router, Tailwind CSS + shadcn/ui, React Query + Zustand, Howler.js, Recharts, React Hook Form + Zod
- **Tasks:** T-F-009 through T-F-013, assigned to ROOK
- **Consequences:** 5 new Phase F tasks. ROOK activated as implementing agent. Frontend architecture appended to ARCHITECTURE.md. Scope addition SA-001 registered in dossier.md.

## MISSION SCOPE STATEMENT
This mission delivers an API-only personalized audio narration system. All intelligence comes from API calls. No model training, no GPU, no local inference. Deployable on standard compute.
