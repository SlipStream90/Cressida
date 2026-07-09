The writes need your approval. Please grant permission for the three files under `missions/mission_20260708_225533/architecture/` and I'll finalize them:

- **`ARCHITECTURE.md`** — component decomposition (`app.js`/`server.js`/test split), stack table, API contract, data model (static), NFR posture, directory layout for TANNER, and PRD traceability.
- **`openapi.yaml`** — machine-readable contract for `GET /status` → `200 {"status":"ok"}` with the `StatusResponse` schema.
- **`ADRs.md`** — 5 ADRs (Node 20 + ESM, Express 5, `node:test`+supertest, single-process app/server split, `/status` path) each with rationale and rejected alternatives.

Once approved, here's the summary I'll publish to shared state:

## ARCHITECTURE — Design Complete

**Mission:** `mission_20260708_225533` — Node.js REST API returning `{"status":"ok"}`

**Decisions ratified:**
- **Decomposition:** single stateless process; internal `app.js` (routing) / `server.js` (listen) split — the one split that buys in-process testability. No microservices (ADR-0004).
- **Stack:** Node 20 LTS · ESM · Express 5.x *(fallback core `node:http` only if zero-dep mandated)* · `node:test` + `supertest`.
- **Path:** `/status` ratified (Q override authority exercised; `/health`, `/healthz`, `/` recorded as rejected — ADR-0005).
- **Data model:** none — response is a static constant `{"status":"ok"}`, schema pinned via `enum:[ok]`, `additionalProperties:false`.
- **Config:** `PORT` env, default `3000`.

**Contracts:** `GET /status` → `200`, `Content-Type: application/json; charset=utf-8`, body `{"status":"ok"}`. Full schema in `openapi.yaml`.

**Directory contract for TANNER:** `package.json` (type:module) · `src/app.js` · `src/server.js` · `test/status.test.js` · `README.md`.

**Flags/escalations:** None blocking. Security surface is nil (no input/state/auth); non-root + network-scoping noted to ARGUS as informational only. Feasible in one iteration (~20 LOC src + ~15 LOC test).

**Ready for TANNER to begin planning.**