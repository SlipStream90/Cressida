# MISSION DOSSIER — MSN-2026-001 "ECHO"

**Codename:** ECHO (Expressive Customized Hyper-narrative Orchestrator)
**Classification:** CRESSIDA Internal
**Status:** INITIALIZED

---

## Mission Brief

Build a Personalized Storytelling Preference Learning system for an audio story platform.

## Objectives

| ID | Objective | Priority |
|---|---|---|
| OBJ-01 | Learn storytelling mechanics per listener (pacing, suspense, dialogue density, emotional tone, description length) — not genre tags | CRITICAL |
| OBJ-02 | Generate multiple narration variants of each story segment per session | HIGH |
| OBJ-03 | Collect explicit feedback (👍/👎, 1–5 rating) and implicit signals (replay, skip, pause timestamp, completion) | HIGH |
| OBJ-04 | Train a reward model: f(user_profile, story_features, variant) → reward_score | CRITICAL |
| OBJ-05 | Implement LoRA adapters on Llama 3 for narration styles: Suspense, Dialogue, Horror, Emotional, Fast-Paced | HIGH |
| OBJ-06 | Select/blend LoRA adapters at inference time based on reward model output | HIGH |
| OBJ-07 | Use LangGraph for workflow orchestration | MEDIUM |
| OBJ-08 | Use ElevenLabs for voice synthesis | MEDIUM |
| OBJ-09 | [V3] Persona LoRA system — synthetic listener archetypes trained from RLHF data, exposed as creator dashboard | LOW |

## Scope

- Preference learning engine (mechanics-level, not genre-level)
- Multi-variant narration generation pipeline
- Feedback collection system (explicit + implicit signals)
- Reward model training pipeline
- LoRA adapter management (training + inference blending)
- LangGraph workflow definitions
- ElevenLabs voice synthesis integration
- V3: Persona LoRA + creator dashboard (stretch)

## Out of Scope

- Story content creation or editing tools
- User account management or authentication
- Payment/billing systems
- Mobile app development
- Non-English language support (V1)
- General-purpose LLM fine-tuning (LoRA only)

## Success Metrics

| Metric | Target | Measurement |
|---|---|---|
| Reward model accuracy | >85% correlation with user ratings | Hold-out test set |
| Variant generation latency | <2s per segment | P95 latency |
| LoRA adapter switch time | <100ms | Inference time |
| User engagement lift | >20% increase in session time | A/B test |
| Implicit signal prediction | >75% match with explicit feedback | Correlation analysis |

## Constraints

- LoRA adapters on Llama 3 only (no full fine-tuning)
- LangGraph for all workflow orchestration
- ElevenLabs for TTS (no alternatives in V1)
- All model training must produce RLHF-compatible (State, Action, Outcome, Reward) tuples
- System must support A/B testing of narration variants
- Privacy: no raw audio or transcript storage beyond session

## Scope Additions

### SA-001 — Next.js Frontend
**Date:** 2026-06-24
**Authority:** Mission Director
**Status:** APPROVED

**Frontend:** Next.js application
**Surfaces:**
  1. Listener UI — end-user facing product
  2. Admin Dashboard — internal monitoring and analytics
**Users:** Listeners (end users) + Mission Director (admin)
**Quality:** Production-ready UI, not prototype
**Framework:** Next.js (App Router)
**Styling:** Tailwind CSS + shadcn/ui
**State:** React Query for server state, Zustand for client state
**Audio:** Howler.js for audio playback

## Open Questions

- Q1: What is the target segment length for variant generation (words/segment)?
- Q2: How many variants per segment per session (2, 3, 5)?
- Q3: What is the initial listener count for training data collection?
- Q4: Which Llama 3 variant (8B, 70B)?
- Q5: ElevenLabs API rate limits — sufficient for target concurrency?
- Q6: LangGraph persistence backend (in-memory vs PostgreSQL)?
- Q7: V3 timeline — gated behind V2 completion or parallel track?

## Phase 1 — Planning Pipeline

```
GREENWAY (Research) → M (Product Definition) → Q (Architecture) → TANNER (Task Graph) → BOND (Approval)
```

## Strategic Memory References

- ADR-001: Intelligence Layer in Markdown
- ADR-006: RLHF-Compatible Reward Storage
- Patterns: Pipeline Pattern, Parallel Fan-Out Pattern, Review Gate Pattern
