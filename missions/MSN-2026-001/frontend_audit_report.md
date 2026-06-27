# Frontend-Backend Connection Audit — MSN-2026-001 OpSpyglass

**Auditor:** REVIEW
**Date:** 2026-06-26
**Scope:** Full frontend-backend contract alignment, rendering safety, routing, and configuration

---

## BLOCKERS: 4
## MAJORS: 3
## MINORS: 4

---

## BLOCKER 1 — Style name case mismatch: snake_case vs Title Case

**Category:** wrong_field_name
**Location:** `src/lib/constants.ts:1` — `STYLES` uses `"Suspense", "Dialogue", "Emotional", "Fast-Paced", "Descriptive"`
**Backend truth:** `style_scores` keys are `"suspense", "dialogue", "emotional", "fast_paced", "descriptive"` (from `echo/backend/app/models/user.py:13-19`)
**Frontend assumption:** Components look up `scores["Suspense"]` but backend sends `"suspense"`
**Fix:** Change `STYLES` constant to use snake_case matching the backend: `"suspense", "dialogue", "emotional", "fast_paced", "descriptive"`. Update `STYLE_COLORS`, `STYLE_LABELS` keys accordingly. Update all references in pages (defaultScore objects on homepage and preferences page).

**Affected files (7):**
- `src/lib/constants.ts` — change keys from TitleCase to snake_case
- `src/components/charts/StyleScoreRadar.tsx:29` — `scores[style]` returns 0 for all styles → blank radar
- `src/components/variants/VariantCard.tsx:31` — `STYLE_COLORS[variant.style]` → gray badge/color
- `src/components/audio/AudioPlayer.tsx:129` — `STYLE_COLORS[style]` → gray progress
- `src/components/sessions/SessionTimeline.tsx:29` — `STYLE_COLORS[session.dominant_style]` → gray dots
- `src/components/analytics/DriftAlert.tsx:18-19` — `STYLE_COLORS[...]` → gray drift labels
- `src/app/(listener)/page.tsx:235` and `src/app/(listener)/preferences/page.tsx:442` — defaultScore objects use TitleCase keys

**Estimated lines changed:** ~10

---

## BLOCKER 2 — Missing `GET /abtests` endpoint

**Category:** missing_endpoint
**Location:** `src/lib/api/abtests.ts:7` — `listABTests()` calls `GET /v1/abtests/`
**Backend truth:** No `GET /abtests` route defined in `echo/backend/app/api/v1/abtests.py`. Only `POST /abtests`, `GET /abtests/{test_id}`, `GET /abtests/{test_id}/results`, `GET /abtests/{test_id}/results/raw`, `PATCH /abtests/{test_id}/active` exist.
**Frontend assumption:** Can list all AB test configs
**Fix:** Add `GET /abtests` to backend `abtests.py` that returns all configs via `ab_repository.list_configs()`:
```python
@router.get("")
async def list_ab_tests(api_key: str = Depends(verify_api_key)):
    return [c.to_dict() for c in ab_repository.list_configs()]
```

**File to fix:** `echo/backend/app/api/v1/abtests.py`
**Estimated lines changed:** +7

---

## BLOCKER 3 — Hardcoded non-existent segment ID

**Category:** missing_field
**Location:** `src/app/(listener)/page.tsx:249` — `createSession(DEMO_USER_ID, "seg-001")`
**Backend truth:** No segment with ID `"seg-001"` exists in Supabase. The workflow runs `StoryRepository.get_by_id("seg-001")` which returns `null`, causing `load_context` to raise `ValueError("Segment seg-001 not found")`.
**Frontend assumption:** Session starts successfully → redirects to `/session/{id}`
**Fix:** Replace `"seg-001"` with a valid segment ID from the actual database, or create a `/v1/stories` flow to retrieve available segments first and let the user pick one.
**File to fix:** `src/app/(listener)/page.tsx:249`
**Estimated lines changed:** 1 (value change) or more for a proper segment picker

---

## BLOCKER 4 — Admin sidebar links to 404 pages

**Category:** missing_endpoint
**Location:** `src/app/(admin)/layout.tsx:23-29` — sidebar links to `/admin/users`, `/admin/abtests`, `/admin/drift`, `/admin/analytics`, `/admin/evaluations`
**Backend truth:** Only two admin page files exist: `/admin/page.tsx` and `/admin/login/page.tsx`
**Frontend assumption:** Navigation links lead to valid pages
**Fix:** Either create the missing page files or remove non-existent links from the sidebar navigation.
**File to fix:** `src/app/(admin)/layout.tsx`
**Estimated lines changed:** 5+ (remove 5 nav items) or 5 new page files

---

## MAJOR 1 — Audio URL path is relative, not proxied to backend

**Category:** wrong_path
**Location:** `src/components/audio/AudioPlayer.tsx:47` — `new Howl({ src: [src] })` where `src = variant.audio_url = "/audio/{hash}.mp3"`
**Backend truth:** `_save_audio` in `nodes.py:203` returns `f"/audio/{filename}"` — a relative path served from the backend process at port 8000
**Frontend assumption:** The URL is absolute or will be proxied
**Fix:** Either (a) make the backend serve audio files via FastAPI static mount + return full URL, or (b) configure `next.config.js` with a rewrite rule to proxy `/audio/*` → `http://localhost:8000/audio/*`. Option (b) is immediate:
```js
// next.config.js
async rewrites() {
  return [{ source: '/audio/:path*', destination: `${process.env.NEXT_PUBLIC_API_URL}/audio/:path*` }]
}
```
Also need to add static file serving on the backend: `app.mount("/audio", StaticFiles(directory=settings.audio_cache_dir), name="audio")`

**Files to fix:** `echo/frontend/next.config.js`, `echo/backend/app/main.py`
**Estimated lines changed:** +8

---

## MAJOR 2 — `createABTest` sends params as comma-separated string, not FastAPI list

**Category:** type_mismatch
**Location:** `src/lib/api/abtests.ts:23` — `encodeURIComponent(stylesUnderTest.join(","))`
**Backend truth:** FastAPI expects `POST /abtests?name=X&styles_under_test=a&styles_under_test=b&assignment_strategy=round_robin` (repeated `styles_under_test` param, not comma-separated)
**Frontend assumption:** A single comma-separated value works
**Fix:** Update the `createABTest` call to pass `styles_under_test` correctly. Change the query param construction to use multiple `styles_under_test` parameters instead of a joined string. Best approach: make the API accept JSON body instead of query params.
```python
# Backend: change to request body
class CreateABTestRequest(BaseModel):
    name: str
    styles_under_test: list[str]
    assignment_strategy: str = "round_robin"

@router.post("")
async def create_ab_test(request: CreateABTestRequest, ...):
```

**File to fix:** `echo/backend/app/api/v1/abtests.py`, `src/lib/api/abtests.ts`
**Estimated lines changed:** +15

---

## MAJOR 3 — Hardcoded `.env.local` API key won't match backend validation

**Category:** env_var_missing
**Location:** `echo/frontend/.env.local:2` — `NEXT_PUBLIC_API_KEY=test`
**Backend truth:** `deps.py` validates `X-API-Key` against `API_KEY` env var. If backend's `API_KEY` is not "test", all API calls return 401.
**Fix:** Sync the API key values between backend and frontend `.env` files. Document in `README.md`.

**File to fix:** `echo/frontend/.env.local`, `echo/backend/.env.example` (if exists)
**Estimated lines changed:** 1

---

## MINOR 1 — `FeedbackButtons` silently swallows all errors

**Category:** wrong_auth (not applicable — error handling)
**Location:** `src/components/feedback/FeedbackButtons.tsx:33` — empty `catch {}` block
**Fix:** Add user-visible error handling:
```tsx
catch (e) {
  setError("Failed to submit feedback. Please try again.")
}
```

**File to fix:** `src/components/feedback/FeedbackButtons.tsx`
**Estimated lines changed:** +4

---

## MINOR 2 — `useStyleHistory` select function creates scores with backend's snake_case keys but components expect TitleCase

**Category:** type_mismatch
**Location:** `src/hooks/useStyleHistory.ts:28-32` — passes through scores dict with snake_case keys from backend
**Fix:** This is resolved by BLOCKER-1 fix (change `STYLES` to snake_case). No additional changes needed if BLOCKER-1 is applied.

**File to fix:** none (resolved by BLOCKER-1)
**Estimated lines changed:** 0

---

## MINOR 3 — Admin panel uses hardcoded mock data

**Category:** missing_endpoint
**Location:** `src/app/(admin)/admin/page.tsx` — stat cards show hardcoded values (`"1,247"` users, `"89"` sessions), hardcoded recentActivity array, hardcoded drift detections
**Fix:** Wire stat cards to actual API endpoints once admin pages are built. Currently harmless as no corresponding backend endpoints exist for these aggregates.

**File to fix:** `src/app/(admin)/admin/page.tsx`
**Estimated lines changed:** 20+ (when backend endpoints exist)

---

## MINOR 4 — `style` vs `story_segment_id` field inconsistency in WorkflowState

**Category:** wrong_field_name
**Location:** `echo/backend/app/workflow/state.py:3` — defines both `segment_id` and `story_segment_id` as separate fields
**Backend truth:** `sessions.py:31-32` initializes both to the same value: `"story_segment_id": request.story_segment_id, "segment_id": request.story_segment_id`
**Fix:** Consolidate to a single field to avoid confusion. Remove `story_segment_id` from `WorkflowState` and `NarrationVariant`, keep only `segment_id`.

**File to fix:** `echo/backend/app/workflow/state.py`, `echo/backend/app/workflow/nodes.py:36-37`, `echo/backend/app/api/v1/sessions.py:31`
**Estimated lines changed:** +5

---

## CRITICAL PATH ASSESSMENT

| Step | Result | Reason |
|------|--------|--------|
| 1. Can user visit `/`? | **PASS** | Page renders. Style radar shows all zeros (BLOCKER-1 cosmetic) but doesn't crash. |
| 2. Can user start a session? | **FAIL** | Hardcoded `seg-001` doesn't exist in DB (BLOCKER-3). Workflow raises ValueError. Falls back to `/session/new` showing infinite spinner. |
| 3. Can user see variants? | **FAIL** | Depends on BLOCKER-3 (session creation fails first). Even if session existed, variant colors are gray (BLOCKER-1 cosmetic). |
| 4. Can user submit feedback? | **PASS** | Feedback routes work correctly. Error is silently swallowed (MINOR-1) but feedback IS recorded. |
| 5. Can admin visit `/admin`? | **PASS** | Login page works. Overview page renders. All sidebar links return 404 (BLOCKER-4). |

**Core user flow is BROKEN** — cannot start a session (BLOCKER-3).

---

## PRIORITIZED FIX LIST

| Priority | File | Fix | Est. Lines |
|----------|------|-----|------------|
| 1 | `src/app/(listener)/page.tsx:249` | Replace `"seg-001"` with valid segment ID | 1 |
| 2 | `src/lib/constants.ts` | Change to snake_case: `suspense`, `dialogue`, `emotional`, `fast_paced`, `descriptive` | 10 |
| 3 | `echo/backend/app/api/v1/abtests.py` | Add `GET /abtests` route | 7 |
| 4 | `echo/backend/app/main.py` + `echo/frontend/next.config.js` | Add static file mount for audio + rewrite rule | 8 |
| 5 | `echo/backend/app/api/v1/abtests.py` + `src/lib/api/abtests.ts` | Change createABTest to use request body | 15 |
| 6 | `src/app/(admin)/layout.tsx` | Remove 404 sidebar links or create missing pages | 5 |
| 7 | `echo/frontend/.env.local` | Sync API key with backend | 1 |
| 8 | `src/components/feedback/FeedbackButtons.tsx:33` | Add user-visible error handling | 4 |
| 9 | `echo/backend/app/workflow/state.py:3` | Consolidate `segment_id`/`story_segment_id` | 5 |
