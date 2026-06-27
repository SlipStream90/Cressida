# Research Report — MSN-2026-001 "ECHO"

## 1. Storytelling Preference Learning

### Problem Space
Traditional recommendation systems operate at the content level (genre, author, tags). ECHO operates at the *mechanics* level: how a story is told, not what it is about. This is a fundamentally different ML problem — instead of recommending items, we are *generating* personalized narration experiences.

### Approaches Compared

| Approach | Pros | Cons | Verdict |
|---|---|---|---|
| **Matrix factorization on mechanics** | Simple, interpretable | Cannot generalize to cold-start listeners | Falls short |
| **RLHF-based reward model** | Learns from implicit + explicit signals; generalizes; RLHF-ready | Requires online data collection; reward hacking risk | **Recommended** |
| **Supervised fine-tuning on preferences** | Straightforward | Requires labeled dataset; no exploration | Not suitable |
| **Bayesian preference modeling** | Handles uncertainty well | Complex to deploy at scale | Research track |

**Recommendation:** RLHF-based reward model with implicit signal proxy labels for cold-start.

## 2. LoRA Adapters for Narration Style

### Technical Analysis
Parameter-efficient fine-tuning via Low-Rank Adaptation (LoRA) attaches rank-decomposition matrices to attention layers. For narration style control, we need 5 adapters:

| Style | LoRA Rank | Target Modules | Training Data Requirements |
|---|---|---|---|
| Suspense | r=16 | Q, V projections | ~500 short suspense narratives |
| Dialogue | r=16 | Q, V projections | ~500 dialogue-heavy transcripts |
| Horror | r=16 | Q, V projections | ~500 atmospheric horror segments |
| Emotional | r=16 | Q, V projections | ~500 emotionally charged scenes |
| Fast-Paced | r=8 | Q, V projections | ~500 action/quick-cut narratives |

### Key Findings
- **r=16** is sufficient for style differentiation; higher ranks (r=32+) show diminishing returns (Hu et al., 2021)
- **Multi-LoRA serving** is well-studied: S-LoRA, Punica, and PetS support >1000 concurrent adapters
- **Adapter blending**: linear interpolation of LoRA weights at inference (weighted average of delta_W) enables smooth style mixing
- **Quantization**: 4-bit NF4 quantization (QLoRA) reduces memory by ~4x with <1% quality loss

### Recommendation
- Use `peft` library for LoRA training and inference
- Deploy with vLLM + S-LoRA for multi-adapter serving
- Adapter blending via `W = W_base + sum(alpha_i * delta_W_i)` where alpha_i comes from reward model

## 3. LangGraph for Workflow Orchestration

### Architecture Analysis

| Feature | LangGraph | LangChain | Custom DAG |
|---|---|---|---|
| State machine | Built-in (graph-based) | Linear chains only | Must build from scratch |
| Parallel branches | Native support | Via `RunnableParallel` | Manual |
| Human-in-the-loop | Checkpoint/resume | Limited | Custom |
| Persistence | MemorySaver, PostgresSaver | Via callbacks | Custom |
| Streaming | Native | Native | Custom |

### Recommended Graph Structure

```
[Segment In] → Reward Model (predicts best style blend)
                     ↓
          ┌─── Adapter Selector ───┐
          │    (blend weights)      │
          ↓         ↓         ↓
    [Suspense] [Dialogue] [Emotional]  ← parallel LoRA inference
          ↓         ↓         ↓
          └─── Variant Merger ────┘
                     ↓
              [ElevenLabs TTS]
                     ↓
              [Feedback Collect]
```

### Key Considerations
- **State persistence**: Use `MemorySaver` for dev, `PostgresSaver` for production
- **Checkpointing**: Every segment variant generation is a checkpoint node
- **Parallelism**: LangGraph `Send` API for fan-out to parallel adapter branches

## 4. ElevenLabs Voice Synthesis

### API Capabilities

| Feature | Availability | Notes |
|---|---|---|
| Text-to-Speech | ✅ | 11 multilingual voices, custom voice cloning |
| Voice Cloning | ✅ | Instant + Professional cloning |
| Sound Effects | ✅ (gen) | Optional for V2 |
| Dubbing | ✅ | Not needed for V1 |
| Latency (p50) | ~750ms for 30s audio | Streaming reduces perceived latency |
| Rate Limits | 10k chars/min (Starter) | Scales with plan |

### Integration Pattern
1. Send narration text → receive audio buffer
2. Stream if segment is long (>30s)
3. Cache commonly narrated segments (same text + same voice = same hash)
4. Voice selection per listener preference (stored in user profile)

### Recommendation
- Use ElevenLabs Streaming API for <1s perceived latency
- Implement audio caching layer (MD5 of text + voice_id)
- Start with "Rachel" as default; expand to style-matched voices in V2

## 5. Reward Model Architecture

### Model Design

```
Input: [user_embedding (64d) || story_features (32d) || variant_embedding (32d)]
                                          ↓
                              MLP: 128 → 64 → 32 → 1
                                          ↓
                                 reward_score (scalar)
```

### Training Strategy
- **Phase 1 (offline)**: Train on synthetic preference pairs from heuristic rules
- **Phase 2 (online)**: Continual learning from real user feedback
- **Loss**: Bradley-Terry preference loss for pairwise comparisons
- **Implicit signals**: Train proxy model to predict explicit rating from implicit signals (replay, skip, pause, completion)

### RLHF Pipeline
1. Collect (state, action, outcome) tuples via existing RewardStore
2. Human annotators (or implicit signals) provide reward scores
3. Train reward model: `f(user_profile, story_features, variant) → reward_score`
4. Reward model selects/blends LoRA adapters at inference

## 6. Risk Assessment

| Risk | Severity | Mitigation |
|---|---|---|
| Reward model overfits to explicit feedback | High | Regularization, implicit signal regularization |
| LoRA adapter interference (negative interference between styles) | Medium | Orthogonal initialization, style-specific training data isolation |
| ElevenLabs rate limits at scale | Medium | Caching layer, request batching, multi-voice fallback |
| LangGraph state persistence bottleneck | Low | Use PostgresSaver, partition by session |
| Cold-start listener (no preference data) | Medium | Default profile with heuristic rules, exploration epsilon |

## 7. Alternatives Considered (Not Recommended)

| Alternative | Reason Rejected |
|---|---|
| **Full fine-tuning of Llama 3** | Too expensive; 5 styles × full fine-tuning = 5 separate models |
| **No RLHF — rule-based style selection** | Cannot personalize; static experience |
| **AWS Polly instead of ElevenLabs** | Inferior voice quality for narrative storytelling |
| **Reward model as part of LLM** | Coupled; harder to iterate on reward model independently |
| **Redis-backed LangGraph** | Works for dev but Postgres gives audit trail needed for RLHF |
