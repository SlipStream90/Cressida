# Product Requirements Document — MSN-2026-001 "ECHO"

## 1. Product Overview

ECHO is a personalized storytelling preference learning system for an audio story platform. It learns how individual listeners prefer stories to be narrated (pacing, suspense, dialogue density, emotional tone, description length) and generates narration variants optimized for each listener.

## 2. User Personas

### Persona A: Casual Listener
- **Name:** Maya, 28
- **Behavior:** Listens during commute (20-30 min sessions), prefers moderate pacing, skips overly descriptive segments
- **Needs:** Stories that match her energy level, seamless experience
- **Signal profile:** High skip rate on slow segments, high completion on dialogue-heavy scenes

### Persona B: Immersive Listener
- **Name:** Elias, 45
- **Behavior:** Listens at home in long sessions (1-2 hours), values atmospheric narration and detailed descriptions
- **Needs:** Rich emotional tone, prefers suspense and horror styles
- **Signal profile:** High completion on atmospheric segments, replays favorite scenes

### Persona C: Power Listener
- **Name:** Nina, 32
- **Behavior:** Listens across multiple sessions/day, genre-agnostic, style-adaptive
- **Needs:** Fast-paced narratives during work, relaxed narration evenings
- **Signal profile:** Varies by time of day, high engagement with fast-paced morning segments

### Persona D: Creator (V3)
- **Name:** Alex, 38
- **Behavior:** Produces stories for the platform, wants to optimize engagement
- **Needs:** Dashboard showing predicted engagement per narration style before release
- **Signal profile:** N/A — uses creator dashboard

## 3. User Stories

### V1 — Core Preference Learning

| ID | Story | Acceptance Criteria | Priority |
|---|---|---|---|
| US-001 | As a listener, I want the system to learn my pacing preferences so that stories feel naturally paced to me | Reward model predicts preferred pacing within 5 sessions | P0 |
| US-002 | As a listener, I want narration adapted to my preferred style (suspense, dialogue, etc.) | LoRA adapter selected/blended per reward model output | P0 |
| US-003 | As a listener, I want to give 👍/👎 feedback on segments | Feedback recorded in <500ms, stored in RewardStore | P0 |
| US-004 | As a listener, I want to rate segments 1-5 | Rating stored with timestamp + segment context | P0 |
| US-005 | As a system, I want to collect implicit signals (replay, skip, pause, completion) | All signals logged with timestamps, correlated to segment | P0 |
| US-006 | As a listener, I want multiple narration variants per session | At least 2 variants generated per segment | P0 |
| US-007 | As a listener, I want seamless voice synthesis of my preferred variant | ElevenLabs TTS latency <2s p95 | P1 |

### V2 — Advanced Features

| ID | Story | Acceptance Criteria | Priority |
|---|---|---|---|
| US-008 | As a listener, I want the system to adapt within a session (not just across sessions) | Reward model updates within 3 segment feedback events | P1 |
| US-009 | As a listener, I want style blending (e.g., suspenseful dialogue) | Adapter blending produces coherent mixed styles | P1 |
| US-010 | As a system, I want A/B testing of variant generation strategies | A/B framework: control vs treatment, statistical significance reporting | P1 |
| US-011 | As a listener, I want to see why a variant was chosen for me (transparency) | "Why this narration?" modal shows top 3 preference signals | P2 |

### V3 — Creator Platform

| ID | Story | Acceptance Criteria | Priority |
|---|---|---|---|
| US-012 | As a creator, I want synthetic listener archetypes to preview engagement | Persona LoRA system generates predictions for each archetype | P2 |
| US-013 | As a creator, I want a dashboard showing predicted engagement per narration style | Dashboard: 5 style predictions, engagement scores, confidence intervals | P2 |

## 4. Feature Priority Matrix

| Feature | Value | Effort | Risk | Priority |
|---|---|---|---|---|
| Reward model training pipeline | Critical | High | Medium | P0 |
| LoRA adapter training (5 styles) | Critical | High | Low | P0 |
| Implicit signal collection | High | Low | Low | P0 |
| Explicit feedback (👍/👎, 1-5) | High | Low | Low | P0 |
| Multi-variant generation | High | Medium | Low | P0 |
| ElevenLabs TTS integration | High | Medium | Low | P0 |
| LangGraph workflow | High | Medium | Low | P0 |
| Adapter blending at inference | High | Medium | Medium | P1 |
| In-session adaptation | Medium | High | Medium | P1 |
| A/B testing framework | Medium | Medium | Low | P1 |
| Creator dashboard | Low | High | Medium | P2 |
| Persona LoRA system | Low | Very High | High | P2 |

## 5. Success Metrics

| Metric | Target | Measurement Method | Tracking |
|---|---|---|---|
| Reward model correlation | >85% with user ratings | Hold-out test set, Pearson r | Per release |
| Variant generation latency | <2s p95 | LangGraph trace spans | Per session |
| LoRA adapter switch time | <100ms | vLLM S-LoRA metrics | Per request |
| User session engagement lift | >20% | A/B test (ECHO vs baseline) | Weekly |
| Implicit signal accuracy | >75% match with explicit | Correlation analysis | Per cohort |
| Active listener adoption | >60% of MAU | Feature flag tracking | Monthly |
| Feedback submission rate | >30% of sessions | Event analytics | Weekly |

## 6. Open Questions (Resolved from Dossier)

| Question | Decision |
|---|---|
| Q1: Segment length | **150-300 words** per segment (3-5 min audio at ~150 wpm) |
| Q2: Variants per segment | **3 variants** per segment (balance of quality vs latency) |
| Q3: Initial listener count | **5,000** beta users for training data collection |
| Q4: Llama 3 variant | **Llama 3 8B** (sufficient for narration; 70B adds latency without proportional quality gain) |
| Q5: ElevenLabs rate limits | **Pro plan** (60k chars/min) with local TTS caching layer |
| Q6: LangGraph persistence | **MemorySaver** for dev, **PostgresSaver** for production |
| Q7: V3 timeline | **Gated behind V2** — creator features require proven reward model accuracy |
