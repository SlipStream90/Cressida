# Regression Tests — MSN-2026-001 OpSpyglass (UPDATED)

**File:** `echo/backend/tests/test_regression.py` (15 regression tests)  
**Suite size:** 147 tests total across 14 test files, all passing

---

## REGRESSION-001 through REGRESSION-015

| ID | Name | Module | What It Catches |
|----|------|--------|-----------------|
| 001 | Gemini empty input | `gemini_service.generate_variant` | Regresses if Gemini API throws on empty text |
| 002 | ElevenLabs empty text | `elevenlabs_service.synthesize` | Regresses if ElevenLabs API throws on empty text |
| 003 | Reward unknown signal | `reward_service.resolve_signals` | Returns `[]` for unknown signals — regresses if exception is thrown |
| 004 | FAISS cold start | `vector_service.VectorService.search_similar` | Returns empty list for new user — regresses if crash |
| 005 | Cache miss | `cache_service.get_cached_profile` | Returns None for missing key — regresses if exception or stale data |
| 006 | Workflow cold start | `workflow.state.WorkflowState` | TypedDict works with empty defaults — regresses if schema changes |
| 007 | Session no UserProfile write | `session_adapter.SessionStyleState` | No "profile" methods exist — regresses if UserProfile coupling added |
| 008 | AB engagement bounded | `ab_service.ABTestResult` | Engagement score starts at 0.0 and is bounded [0,1] — regresses if validation removed |
| 009 | Drift insufficient history | `drift_service.detect_drift` | Returns None for <3 data points — regresses if threshold changes |
| 010 | Feedback API key required | `feedback/explicit` endpoint | 401 on missing/empty key, 200 on valid — regresses if auth removed |
| 011 | Style scores normalize | `reward_service.update_style_scores` | Always sums to 1.0 — regresses if normalization logic changes |
| 012 | FAISS persistence | `vector_service.VectorService` | Index survives VectorService reload — regresses if serialization breaks |
| 013 | AB round-robin balanced | `ab_service.get_ab_assignment` | 60 assignments split evenly across 2 variants — regresses if strategy changes |
| 014 | Cache miss/hit | `cache_service.get_cached_profile` | Returns None for miss, dict for hit — regresses if redis layer changes |
| 015 | Drift report | `drift_service.DriftReport` | to_dict() returns expected schema — regresses if report fields change |

## Regression Safety Net Coverage

| Category | Tests | Safety Net |
|----------|-------|------------|
| API resilience (empty/missing input) | REGRESSION-001, 002, 003, 005 | Prevents crashes on edge-case inputs |
| Cold start (no data yet) | REGRESSION-004, 006, 009 | Prevents crashes on empty state |
| Data integrity (normalization, bounding) | REGRESSION-008, 011 | Prevents invalid state |
| Auth enforcement | REGRESSION-010 | Prevents auth bypass regressions |
| Persistence (disk/redis) | REGRESSION-005, 012, 014 | Prevents data loss regressions |
| Distribution fairness | REGRESSION-013 | Prevents AB test bias regressions |
| Schema stability | REGRESSION-007, 015 | Prevents silent API contract breaks |

## Combined Test Suite Summary

| Test File | Tests | Purpose |
|-----------|-------|---------|
| `test_health.py` | 2 | Health endpoint (preserved) |
| `test_integration.py` | 39 | Models + Services + Config |
| `test_wiring.py` | 9 | All routes wired |
| `test_services_gemini.py` | 8 | Gemini + ElevenLabs |
| `test_services_faiss.py` | 9 | VectorService |
| `test_services_redis.py` | 6 | Redis cache functions |
| `test_services_reward.py` | 23 | Reward service |
| `test_ab_testing.py` | 9 | AB service |
| `test_drift_detection.py` | 5 | Drift service |
| `test_session_adapter.py` | 6 | Session adapter |
| `test_workflow_langgraph.py` | 9 | LangGraph workflow |
| `test_feedback_endpoints.py` | 5 | Feedback HTTP endpoints |
| `test_full_system.py` | 1 | 13-step integration |
| `test_regression.py` | 17 | REGRESSION-001..015 |
| **Total** | **147** | **All passing** |
