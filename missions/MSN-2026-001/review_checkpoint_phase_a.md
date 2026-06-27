# Review Checkpoint — Phase A (MSN-2026-001 OpSpyglass)

**Reviewer:** REVIEW
**Date:** 2026-06-24
**Scope:** Framework rectification, MONEYPENNY stack decisions, Phase A implementation

---

## Dimension 1 — Framework Integrity

### knowledge/decisions.md
| Severity | Finding | Expected | Actual |
|----------|---------|----------|--------|
| PASS | All 8 binding stack decisions | Present, complete, dated | ✓ |
| PASS | Dropped scope list | Unambiguous list | ✓ (19 items) |
| PASS | Mission scope statement | Single paragraph | ✓ |

### ARCHITECTURE.md
| Severity | Finding | Expected | Actual |
|----------|---------|----------|--------|
| PASS | LoRA references | Removed | ✓ |
| PASS | PersonaLoRa → StylePreset | Replaced everywhere | ✓ |
| PASS | Reward model | Weighted scoring | ✓ (Section 5) |
| PASS | Vector store | FAISS | ✓ (Section 8.3) |
| PASS | Database | Supabase | ✓ (Section 8.1) |
| PASS | Cache | Redis Cloud | ✓ (Section 8.2) |
| PASS | Creator dashboard / Persona system | Removed | ✓ |
| MINOR | LangGraph node count | 7 (per review spec) | 8 nodes defined. Spec outdated — 8 is correct. |

### backlog.json
| Severity | Finding | Expected | Actual |
|----------|---------|----------|--------|
| PASS | Voided task markers | `VOIDED` + `void_reason` | ✓ |
| PASS | Active task reads[]/writes[] | Both populated | ✓ |
| MINOR | Summary completed count | 3 (T-A-002, T-A-006, T-A-003) | 2 (T-A-003 not reflected) |
| MINOR | Summary remaining count | 20 | 21 |

### execution_graph.json
| Severity | Finding | Expected | Actual |
|----------|---------|----------|--------|
| PASS | Voided tasks removed | 0 nodes for voided IDs | ✓ (23 nodes, no voided) |
| PASS | Dangling references | None | ✓ |
| PASS | Cycle check | 0 cycles | ✓ |

### execution_state.json
| Severity | Finding | Expected | Actual |
|----------|---------|----------|--------|
| PASS | Constraints block | Complete | ✓ (14 constraints) |
| PASS | T-A-002 / T-A-006 status | completed | ✓ |
| PASS | T-A-003 status | completed | ✓ |
| PASS | T-A-008 status | pending | ✓ |

### mission_log.txt
| Severity | Finding | Expected | Actual |
|----------|---------|----------|--------|
| PASS | All completed tasks logged | Agent, timestamp, artifact | ✓ (8 entries) |
| PASS | STACK_DECISIONS entry | Present | ✓ |

---

## Dimension 2 — Phase A Code Review

### T-A-002 Models

| File | Severity | Finding | Expected | Actual |
|------|----------|---------|----------|--------|
| user.py | PASS | style_scores | dict[str, float] | ✓ |
| user.py | MINOR | Default style_scores | Uniform 0.2 per style | `{}` empty dict — first `update_style_scores()` call defaults correctly in code, but model default is empty |
| user.py | PASS | No adapter_weights | Not present | ✓ |
| feedback.py | PASS | event_type coverage | explicit + implicit | ✓ |
| feedback.py | PASS | pause_duration | signal_value covers it | ✓ |
| feedback.py | PASS | session_id | Present | ✓ |
| story.py | PASS | narrative features | word_count, features dict | ✓ |
| story.py | PASS | No LoRA references | None | ✓ |
| **variant.py** | **MAJOR** | **blend_weights field** | **Not present — Decision 7 forbids adapter blending** | `blend_weights: dict[str, float]` present on line 9 |
| variant.py | PASS | audio_url | Present | ✓ |
| variant.py | MINOR | style field | Should be `style_prompt_key` per ARCHITECTURE.md | Uses `style` — functionally equivalent, name mismatch with spec |
| evaluation.py | PASS | Schema matches | task_id, agent, outcome, review_score, architecture_compliance, human_feedback | ✓ |
| persona.py | PASS | PersonaLoRa removed | StylePreset only | ✓ |
| persona.py | PASS | StylePreset fields | style_id, name, description, system_prompt | ✓ |
| persona.py | MINOR | embedding field | 768-dim style embedding | Present — not strictly needed for prompt-only approach, but harmless |
| **reward.py** | **MAJOR** | **RewardModelInput fields** | **Should have user_id, feedback_type, feedback_value, session_id, timestamp per ARCHITECTURE.md** | Has user_profile (768-dim), story_features (32-dim), variant_features (32-dim) — legacy MLP input shape |
| reward.py | PASS | No 128-dim pipeline | None | ✓ (768 + 32 + 32) |

### T-A-006 FastAPI Framework

| File | Severity | Finding | Expected | Actual |
|------|----------|---------|----------|--------|
| main.py | PASS | CORS | Configured | ✓ |
| main.py | PASS | Error handler | Global handler | ✓ |
| main.py | PASS | Routers wired | At least health | ✓ |
| main.py | MINOR | Exception import | At top of file | Import inside handler (works, unconventional) |
| config.py | PASS | pydantic-settings | Yes | ✓ |
| config.py | PASS | .env loading | Configured | ✓ |
| config.py | PASS | No hardcoded secrets | None | ✓ |
| config.py | **MAJOR** | **Missing placeholder fields** | GEMINI_MODEL, SUPABASE_SERVICE_KEY, FAISS_INDEX_DIR, AUDIO_CACHE_DIR | Only has gemini_api_key, elevenlabs_api_key, supabase_url, supabase_key, redis_url |
| deps.py | PASS | API key auth | `verify_api_key()` | ✓ |
| health.py | PASS | Response shape | status, name, version, uptime | ✓ |
| test_health.py | PASS | Both passing | ✓ | ✓ (2/2) |

### T-A-003 Migrations

| File | Severity | Finding | Expected | Actual |
|------|----------|---------|----------|--------|
| 001-008 | PASS | All 8 files present | Yes | ✓ |
| Per-file | PASS | CREATE TABLE + RLS | Each | ✓ |
| Per-file | PASS | Rollback comment | Present | ✓ |
| 008 | PASS | All required indexes | Per spec | ✓ |
| style_presets | PASS | Prompt template columns | Yes, not weights | ✓ |
| schema.sql | PASS | Consolidated schema | Present | ✓ |
| schema.sql | PASS | Matches migrations | Identical | ✓ |

---

## Dimension 3 — Phase B Readiness

| # | Item | Status |
|---|------|--------|
| 1 | app/models/ — 8 models exist, scope-correct | **⚠️ CONDITIONAL** — 2 MAJOR issues in variant.py and reward.py |
| 2 | app/core/config.py — Phase B API key placeholders | **⚠️ CONDITIONAL** — 4 missing fields |
| 3 | app/main.py — router structure ready | ✓ |
| 4 | app/api/deps.py — auth dependency available | ✓ |
| 5 | echo/db/migrations/ — schema in place | ✓ |
| 6 | echo/db/schema.sql — consolidated schema | ✓ |
| 7 | knowledge/decisions.md — stack decisions written | ✓ |
| 8 | ARCHITECTURE.md — LoRA fully removed | ✓ |
| 9 | backlog.json — voided tasks marked, reads/writes populated | ✓ |
| 10 | execution_state.json — constraints block present | ✓ |

### Phase B Blocker Assessment
- **BLOCKERS:** 0
- **MUST-FIX before Phase B:** 3 MAJOR items
- **CARRY as debt:** 6 MINOR items

---

## Summary

```json
{
  "blockers": 0,
  "majors": 3,
  "minors": 7,
  "phase_b_ready": false,
  "majors_require_fix_before_phase_b": true
}
```

### MAJOR Findings
1. **variant.py:9** — `blend_weights` field must be removed (adapter blending out of scope per Decision 7)
2. **reward.py:4-12** — `RewardModelInput` has legacy MLP features (768+32+32 dims) instead of the required fields from ARCHITECTURE.md (user_id, style_selected, feedback_type, feedback_value, session_id, timestamp). Must be redesigned for weighted scoring.
3. **config.py** — Missing 4 Phase B placeholder fields: `GEMINI_MODEL`, `SUPABASE_SERVICE_KEY`, `FAISS_INDEX_DIR`, `AUDIO_CACHE_DIR`

### MINOR Findings
1. `UserProfile.style_scores` default is `{}` — should default to uniform `0.2` per style
2. `NarrationVariant.style` field name mismatches ARCHITECTURE.md `style_prompt_key` — functionally OK but inconsistent
3. `main.py` exception handler imports inside function — unconventional, move to top
4. `backlog.json` summary counts not updated for T-A-003 completion (shows 2 completed, not 3)
5. `priority_matrix.md` references voided tasks and broken critical path — not updated for binding stack decisions
6. `StylePreset.embedding` field is decorative (not used by prompt-only approach) — not harmful but confusing
7. Review spec mentions 7 LangGraph nodes but architecture has 8 — spec is outdated

---

## Agent Performance Assessment

| Agent | Phase A Tasks | Score | Notes |
|-------|--------------|-------|-------|
| **BRANCH** | T-A-002 (models), T-A-006 (API framework) | 8/10 | Models are complete but had 2 MAJOR scope alignment issues (blend_weights, RewardModelInput). Framework is solid — all architecture checks pass. |
| **BOOTHROYD** | T-A-003 (migrations) | 10/10 | 8 migrations + schema. Correct scope, correct columns, no LoRA references, RLS policies on every table. |
| **MONEYPENNY** | Stack decisions, code alignment | 9/10 | Decisions.md comprehensive. ARCHITECTURE.md correctly rewritten. Code edits caught most issues but missed blend_weights and RewardModelInput legacy shape. |

---

**Handing to BOND for verdict.**
