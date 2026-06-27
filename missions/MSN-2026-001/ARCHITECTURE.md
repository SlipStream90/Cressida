# Architecture Document — MSN-2026-001 "ECHO" (OpSpyglass Revision)

## 1. Architecture Overview

ECHO is an API-only personalized audio narration system. It receives story segments, generates multiple narration variants via prompt-engineered Gemini API calls, synthesizes audio via ElevenLabs, collects feedback signals, and updates listener preference scores — all without any local model inference, GPU infrastructure, or fine-tuning.

### High-Level Diagram

```
┌───────────────────────────────────────────────────────────────┐
│                         CLIENT LAYER                           │
│              Audio Player / Feedback UI                        │
└─────────────────────────┬─────────────────────────────────────┘
                          │ HTTP / WebSocket
┌─────────────────────────▼─────────────────────────────────────┐
│                      API SERVICE (FastAPI)                      │
│              Ingress → Routes → Middleware → Handlers           │
└──┬──────────┬──────────┬──────────┬────────────────────────────┘
   │          │          │          │
┌──▼──────────▼──┐ ┌────▼──────────▼───────────────────────────┐
│  LANGGRAPH     │ │       PREFERENCE ENGINE                     │
│  WORKFLOW      │ │                                             │
│                │ │  FAISS (per-user indexes)                   │
│  load_context  │ │  reward_service.py (weighted scoring)       │
│  retrieve_pref │ │  Gemini Embedding API                       │
│  generate_vari │ │                                             │
│  synthesize_au │ └─────────────────────────────────────────────┘
│  collect_fb    │
│  update_pref   │
└───────┬────────┘
        │
┌───────▼───────────────────────────────────────────────────────┐
│                    EXTERNAL APIs                                │
│  Gemini API (LLM + Embeddings) / ElevenLabs API (TTS)          │
└───────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────┐
│                      STORAGE LAYER                             │
│  Supabase (PostgreSQL) — Redis Cloud — FAISS (local disk)     │
│  Audio cache (local disk)                                      │
└───────────────────────────────────────────────────────────────┘
```

### LangGraph Workflow

```
[Segment In] → load_context → retrieve_preference
                                       │
                         ┌─────────────┼─────────────┐
                         ▼             ▼             ▼
                   Gemini(Suspense)  Gemini(Dialogue)  Gemini(Emotional)
                         │             │             │
                         └─────────────┼─────────────┘
                                       ▼
                              select_best_variant
                                       │
                              ElevenLabs TTS (selected)
                                       │
                              collect_feedback
                                       │
                              update_preference_scores
                                       │
                                   [Done]
```

---

## 2. Service Decomposition

### 2.1 API Service

| Property | Value |
|---|---|
| **Name** | `api-svc` |
| **Responsibility** | Receive story segments, user sessions, feedback events; route to LangGraph workflow |
| **Technology** | Python 3.12, FastAPI, LangGraph, google-generativeai, elevenlabs, supabase-py, redis-py, faiss-cpu |
| **Interfaces** | REST: `/v1/variants/generate`, `/v1/feedback/explicit`, `/v1/feedback/implicit`, `/health` |

### 2.2 Narration Workflow (LangGraph)

| Property | Value |
|---|---|
| **Nodes** | `load_context` → `retrieve_preference` → `generate_variants` → `synthesize_audio` → `collect_feedback` → `update_preference` → `complete` |
| **State** | `WorkflowState` (TypedDict) |
| **Checkpointing** | Redis Cloud via LangGraph checkpointer |

### 2.3 Preference Engine

| Property | Value |
|---|---|
| **FAISS** | Per-user index for segment similarity retrieval; 768-dim embeddings from Gemini Embedding API |
| **Reward Scoring** | `reward_service.py` — weighted scoring function updating style preference scores per feedback event |

---

## 3. LangGraph Workflow

### 3.1 State Schema

```python
from typing import TypedDict, Optional

class WorkflowState(TypedDict):
    segment_id: str
    segment_text: str
    user_id: str
    session_id: str
    style_scores: dict[str, float]        # Current preference scores per style
    variants: list[dict]                  # Generated narration variants
    selected_variant: Optional[dict]      # Best variant chosen
    audio_url: Optional[str]              # ElevenLabs audio URL
    feedback_collected: bool
    preference_updated: bool
```

### 3.2 Node Definitions

| Node | Input | Output | Implementation |
|---|---|---|---|
| `load_context` | WorkflowState | WorkflowState (context loaded) | Load segment from Supabase |
| `retrieve_preference` | WorkflowState | WorkflowState (style_scores filled) | FAISS query + reward_service |
| `generate_variants` | WorkflowState | WorkflowState (3 variants) | Gemini API with 3 style presets |
| `select_best` | WorkflowState | WorkflowState (selected_variant) | Pick highest-scored style |
| `synthesize_audio` | WorkflowState | WorkflowState (audio_url set) | ElevenLabs API |
| `collect_feedback` | WorkflowState | WorkflowState (feedback collected) | Wait for user feedback event |
| `update_preference` | WorkflowState | WorkflowState (scores updated) | reward_service.update() |
| `complete` | WorkflowState | — | Save state, emit event |

### 3.3 Edge Definitions

```python
graph.add_edge("load_context", "retrieve_preference")
graph.add_conditional_edges(
    "retrieve_preference",
    router=lambda state: "generate_variants",
)
# generate_variants fans out to 3 parallel Gemini calls
graph.add_edge("generate_variants", "select_best")
graph.add_edge("select_best", "synthesize_audio")
graph.add_edge("synthesize_audio", "collect_feedback")
graph.add_edge("collect_feedback", "update_preference")
graph.add_edge("update_preference", "complete")
```

---

## 4. Style Adaptation (Prompt Engineering)

### 4.1 Style Presets

Five style presets defined in `app/config/style_presets.yaml`:

| Style | System Prompt Key | Description |
|---|---|---|
| Suspense | `STYLE_SUSPENSE` | Short sentences, rising tension, dramatic pauses |
| Dialogue | `STYLE_DIALOGUE` | Heavy dialogue, minimal description, quick exchanges |
| Emotional | `STYLE_EMOTIONAL` | Rich emotional language, internal monologue |
| Fast-Paced | `STYLE_FAST_PACED` | Quick narration, minimal description, action-forward |
| Descriptive | `STYLE_DESCRIPTIVE` | Detailed atmospheric description, slower pace |

### 4.2 Style Selection

```python
def select_style_presets(style_scores: dict[str, float]) -> list[str]:
    sorted_styles = sorted(style_scores.items(), key=lambda x: x[1], reverse=True)
    return [style for style, _ in sorted_styles[:3]]
```

Three variants are generated in parallel via LangGraph's Send API using the top-3 scored style presets.

---

## 5. Reward Scoring Function

### 5.1 Scoring Weights

```python
SCORING_WEIGHTS = {
    "explicit_positive": 0.15,   # Rating 4-5
    "explicit_negative": -0.10,  # Rating 1-2
    "replay":            0.08,
    "skip":             -0.06,
    "completion":        0.05,
    "pause_long":       -0.03,   # Pause > 30 seconds
}
```

### 5.2 Update Logic

```python
def update_style_scores(current: dict[str, float], style: str, signals: list[str]) -> dict[str, float]:
    updated = dict(current)
    for signal in signals:
        if signal in SCORING_WEIGHTS:
            updated[style] = max(0.0, updated.get(style, 0.5) + SCORING_WEIGHTS[signal])
    total = sum(updated.values())
    if total > 0:
        for k in updated:
            updated[k] /= total
    return updated
```

---

## 6. Data Models (Pydantic Schemas)

```python
from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class UserProfile(BaseModel):
    user_id: str
    embedding: list[float]           # 768-dim from Gemini Embedding
    style_scores: dict[str, float]   # Current preference per style
    preferred_voice: str = "Rachel"
    created_at: datetime
    updated_at: datetime
    session_count: int = 0
    total_feedback_count: int = 0


class FeedbackEvent(BaseModel):
    event_id: str
    user_id: str
    session_id: str
    segment_id: str
    variant_id: str
    event_type: str                  # "explicit_rating" | "implicit_signal"
    rating: Optional[int]            # 1-5 for explicit
    signal_type: Optional[str]       # "replay" | "skip" | "pause" | "completion"
    signal_value: Optional[float]
    timestamp: datetime
    client_ts: datetime


class StorySegment(BaseModel):
    segment_id: str
    story_id: str
    segment_index: int
    text: str
    word_count: int
    features: dict[str, float]


class NarrationVariant(BaseModel):
    variant_id: str
    segment_id: str
    style: str                       # "suspense" | "dialogue" | "emotional" | "fast_paced" | "descriptive"
    style_prompt_key: str
    generated_text: str
    audio_url: Optional[str]
    generation_latency_ms: float
    model_version: str               # Always "gemini-1.5-pro"


class EvaluationRecord(BaseModel):
    record_id: str
    task_id: str
    agent: str
    execution_time_s: float
    outcome: str
    review_score: Optional[float]
    tests_passed: Optional[bool]
    architecture_compliance: float
    human_feedback: Optional[str]
    timestamp: datetime


class StylePreset(BaseModel):
    style_id: str
    name: str
    description: str
    system_prompt: str
    embedding: list[float]           # 768-dim style embedding


class RewardModelInput(BaseModel):
    user_profile: list[float]        # 768-dim
    story_features: list[float]      # 32-dim
    variant_features: list[float]    # 32-dim


class RewardModelOutput(BaseModel):
    reward_score: float
    confidence: float
    style: str
    model_version: str               # "weighted-scoring-v1"
```

---

## 7. API Contracts

### 7.1 Public API

| Method | Path | Request | Response | Auth |
|---|---|---|---|---|
| `POST` | `/v1/variants/generate` | `{user_id, session_id, segment_id}` | `{variants: [], selected_idx: int}` | API key |
| `POST` | `/v1/feedback/explicit` | `{user_id, session_id, segment_id, variant_id, rating}` | `{event_id, status}` | API key |
| `POST` | `/v1/feedback/implicit` | `{user_id, session_id, segment_id, variant_id, signal_type, signal_value}` | `{event_id, status}` | API key |
| `GET` | `/v1/user/{user_id}/profile` | — | `UserProfile` | API key |
| `POST` | `/v1/variants/generate` | WorkflowState | `{variants, selected_idx, audio_url}` | Internal |
| `GET` | `/health` | — | `{status, version, uptime}` | None |

### 7.2 Auth Scheme

- API Gateway validates Bearer token for all public endpoints
- Internal API calls use mTLS
- No user authentication (out of scope for V1)

---

## 8. Storage Architecture

### 8.1 Supabase (PostgreSQL)

```sql
CREATE TABLE user_profiles (
    user_id         TEXT PRIMARY KEY,
    embedding       FLOAT[] NOT NULL,          -- 768d from Gemini
    style_scores    JSONB NOT NULL DEFAULT '{}',
    preferred_voice TEXT DEFAULT 'Rachel',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE story_segments (
    segment_id      TEXT PRIMARY KEY,
    story_id        TEXT NOT NULL,
    segment_index   INT NOT NULL,
    text            TEXT NOT NULL,
    word_count      INT NOT NULL,
    features        JSONB NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE feedback_events (
    event_id        TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL REFERENCES user_profiles(user_id),
    session_id      TEXT NOT NULL,
    segment_id      TEXT NOT NULL REFERENCES story_segments(segment_id),
    variant_id      TEXT,
    event_type      TEXT NOT NULL,
    rating          INT CHECK (rating >= 1 AND rating <= 5),
    signal_type     TEXT,
    signal_value    FLOAT,
    timestamp       TIMESTAMPTZ NOT NULL,
    client_ts       TIMESTAMPTZ NOT NULL
);

CREATE TABLE narration_variants (
    variant_id        TEXT PRIMARY KEY,
    segment_id        TEXT NOT NULL REFERENCES story_segments(segment_id),
    style             TEXT NOT NULL,
    style_prompt_key  TEXT NOT NULL,
    generated_text    TEXT NOT NULL,
    audio_url         TEXT,
    generation_latency_ms FLOAT,
    model_version     TEXT,
    created_at        TIMESTAMPTZ DEFAULT NOW()
);
```

### 8.2 Redis Cloud

| Key Pattern | Type | TTL | Purpose |
|---|---|---|---|
| `session:{session_id}` | Hash | 3600s | Active session state |
| `profile:{user_id}:cache` | String | 300s | Cached user profile |
| `variant:{segment_id}:*` | String | 600s | Generated variant cache |
| `audio:{text_hash}:{voice}` | String | 86400s | ElevenLabs audio cache |
| `checkpoint:{thread_id}` | String | 86400s | LangGraph workflow checkpoints |

### 8.3 FAISS (Local Vector Store)

| Index | Dim | Storage Path | Purpose |
|---|---|---|---|
| `user_{user_id}` | 768 | `backend/faiss_index/{user_id}.index` | Per-user segment similarity |

### 8.4 Audio Cache (Local Disk)

```
backend/audio_cache/
└── {md5_hash_of_text}_{voice_id}.mp3
```

---

## 9. Infrastructure

### 9.1 Compute

| Service | CPU | RAM | Storage | Replicas |
|---|---|---|---|---|
| API Service | 2 cores | 4GB | 10GB | 2-4 |
| FAISS index disk | — | — | 5GB | Shared |
| Audio cache disk | — | — | 20GB | Shared |

### 9.2 No GPU Required

All LLM and embedding inference is outsourced to Gemini API. No GPU instances needed at any phase.

### 9.3 Container Architecture

```
Docker Compose (dev):
  - api-svc (FastAPI + LangGraph)
  - No database containers (uses Supabase Cloud + Redis Cloud)

Kubernetes (prod):
  - Deployment: api-svc (2-4 replicas)
  - No StatefulSets for databases
  - Ingress: nginx + cert-manager
```

---

## 10. Decision Log

| # | Decision | Chosen | Alternatives | Justification |
|---|---|---|---|---|
| D1 | LLM | Gemini 1.5 Pro | GPT-4o, Llama 3 | API-only; no local inference |
| D2 | Style adaptation | Prompt engineering | LoRA, fine-tuning | No GPU available |
| D3 | Reward model | Weighted scoring | Neural model, Bradley-Terry | No training data at MVP |
| D4 | Database | Supabase | Local PostgreSQL, Docker DB | Managed, zero infrastructure |
| D5 | Cache | Redis Cloud | Local Redis | Managed, zero infrastructure |
| D6 | Vector store | FAISS (local) | Qdrant, Pinecone, pgvector | Sufficient for per-user indexes |
| D7 | Workflow | LangGraph | LangChain, Temporal, Custom DAG | State machine + checkpointing |
| D8 | Voice | ElevenLabs | AWS Polly, Google TTS | Superior narrative quality |

---

## 11. Frontend Architecture

### 11.1 Application
- **Framework:** Next.js 14 App Router
- **Directory:** frontend/
- **Styling:** Tailwind CSS + shadcn/ui component library
- **State:** React Query (server), Zustand (client)
- **Audio:** Howler.js
- **Charts:** Recharts
- **Forms:** React Hook Form + Zod validation

### 11.2 Route Structure

(listener) group — public/auth-protected:
  /                     → story feed / home
  /session/[id]         → active story session + player
  /history              → past sessions
  /preferences          → style preference visualization

(admin) group — admin-only:
  /admin                → dashboard overview
  /admin/users          → user list + search
  /admin/users/[id]     → user detail: preferences + history
  /admin/abtests        → A/B test list
  /admin/abtests/[id]   → test detail + results
  /admin/drift          → drift reports
  /admin/analytics      → system-wide analytics
  /admin/evaluations    → evaluation records viewer

### 11.3 API Communication
- Base URL from NEXT_PUBLIC_API_URL env var
- All requests include X-API-Key header
- React Query for caching and background refresh
- Optimistic updates on feedback submission

### 11.4 Authentication
- Listener: API key or session token (match backend auth)
- Admin: separate admin API key with elevated scope

### 11.5 Frontend Task IDs
| Task ID | Name | Complexity |
|---------|------|------------|
| T-F-009 | Next.js project setup | S |
| T-F-010 | API client layer | M |
| T-F-011 | Listener UI — core screens | XL |
| T-F-012 | Admin Dashboard — core screens | XL |
| T-F-013 | Shared component library | M |

Execution order: T-F-009 → T-F-013 (parallel) → T-F-010 → T-F-011 ║ T-F-012
