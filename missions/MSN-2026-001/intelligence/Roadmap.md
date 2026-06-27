# Roadmap — MSN-2026-001 "ECHO"

## Release Phases

### Phase V1 — Core Preference Engine (Weeks 1-8)

**Theme:** Learn, generate, collect feedback.

| Week | Milestone | Deliverables | Dependencies |
|---|---|---|---|
| 1-2 | Infrastructure setup | LangGraph skeleton, ElevenLabs integration, Llama 3 + LoRA serving (vLLM + S-LoRA) | Q architecture spec |
| 2-3 | Implicit signal collection | Event pipeline for replay/skip/pause/completion | Infrastructure ready |
| 3-4 | LoRA adapter training (batch 1) | Suspense + Dialogue adapters trained and validated | Training data prepared |
| 4-5 | Reward model v1 | MLP reward model: f(user, story, variant) → score | LoRA adapters available |
| 5-6 | Multi-variant generation pipeline | LangGraph workflow: segment → 3 variants → TTS → feedback | All components integrated |
| 6-7 | LoRA adapter training (batch 2) | Horror + Emotional + Fast-Paced adapters | Batch 1 methodology validated |
| 7-8 | Beta launch (5k users) | End-to-end working system, A/B test framework | All V1 components stable |

**V1 Success Gate:** Reward model >80% correlation with explicit ratings across 5k beta users.

### Phase V2 — Adaptive Intelligence (Weeks 9-14)

**Theme:** Real-time adaptation, quality, scale.

| Week | Milestone | Deliverables | Dependencies |
|---|---|---|---|
| 9-10 | In-session adaptation | Reward model updates within-session (3-segment window) | V1 beta data |
| 10-11 | Adapter blending at inference | Linear interpolation of LoRA weights from reward model | Multi-LoRA serving stable |
| 11-12 | A/B testing framework | Statistical significance reporting, treatment/control assignment | In-session adaptation working |
| 12-13 | Performance optimization | <2s p95 variant generation, <100ms adapter switch | Profiling data |
| 13-14 | Scale to 50k users | PostgresSaver, caching layer, rate limit management | Performance validated |

**V2 Success Gate:** >20% engagement lift in A/B test, 50k active users.

### Phase V3 — Creator Platform (Weeks 15-20)

**Theme:** Empower creators, predict engagement.

| Week | Milestone | Deliverables | Dependencies |
|---|---|---|---|
| 15-16 | Persona LoRA system design | Archetype definition, synthetic data generation strategy | V2 reward model |
| 17-18 | Persona LoRA training | Train 5 synthetic listener archetypes from RLHF data | Persona design complete |
| 19 | Creator dashboard v1 | Predicted engagement per archetype per narration style | Persona LoRA system |
| 20 | Creator beta | Dashboard exposed to 100 creators, feedback collection | Creator dashboard v1 |

**V3 Success Gate:** Creator dashboard adoption >60% of invited creators.

## Dependency Graph

```
V1 Infrastructure (wk 1-2)
    ↓
V1 Signal Collection (wk 2-3)
    ↓
V1 LoRA Batch 1 (wk 3-4)  ←── V1 Reward Model (wk 4-5)
    ↓                                ↓
V1 Multi-Variant Pipeline (wk 5-6)
    ↓
V1 LoRA Batch 2 (wk 6-7)
    ↓
V1 Beta Launch (wk 7-8)
    ↓
V2 In-Session Adaptation (wk 9-10)  ←── V1 Beta Data
    ↓
V2 Adapter Blending (wk 10-11)
    ↓
V2 A/B Testing (wk 11-12)
    ↓
V2 Scale (wk 13-14)
    ↓
V3 Persona Design (wk 15-16)
    ↓
V3 Persona Training (wk 17-18)
    ↓
V3 Creator Dashboard (wk 19-20)
```

## Parallel Tracks

Where dependencies allow, these tracks run in parallel:

| Track A | Track B | Track C |
|---|---|---|
| LoRA training (5 styles) | LangGraph pipeline | ElevenLabs integration |
| Reward model training | Implicit signal pipeline | Audio caching layer |
| Persona LoRA system | Creator dashboard | A/B testing infra |

## Risk Mitigation Timeline

| Risk | Trigger | Response | By Week |
|---|---|---|---|
| Reward model <70% accuracy | 2 weeks after training start | Increase training data, add feature engineering | 6 |
| LoRA adapter interference | Adapter blending produces incoherent output | Orthogonal initialization, style-specific training isolation | 5 |
| ElevenLabs latency >2s | P95 latency exceeds 2s | Add streaming, audio caching, fallback voice | 3 |
| LangGraph persistence bottleneck | PostgresSaver query latency >50ms | Add read replicas, query optimization | 11 |
| Low beta user engagement | <30% active after 2 weeks | Onboarding improvements, explore/exploit tuning | 9 |
