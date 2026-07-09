All five architecture artifacts are drafted and queued — they're waiting on your approval to write to `missions/mission_pathtest/architecture/`. Once approved they'll land as:

- **`ARCHITECTURE.md`** — overview, single-service decomposition (with diagram), API contract, `HealthResponse` data model, confirmed stack, repo layout, NFRs, assumptions, and a dependency-ordered handoff to TANNER.
- **`openapi.yaml`** — machine-readable OpenAPI 3.1 contract for `GET /health` with the `HealthResponse` schema (`status` const `"ok"`).
- **`adr/ADR-0001`** — FastAPI + uvicorn (alternatives: Flask, raw Starlette, hypercorn).
- **`adr/ADR-0002`** — single deployable, no decomposition (rejected: separate monitoring service).
- **`adr/ADR-0003`** — Pydantic `HealthResponse` response model (rejected default: bare dict).

**ARCHITECTURE — mission_pathtest / architecture: ready to publish.**

**Handoff to TANNER (build order):**
1. `requirements.txt` — `fastapi`, `uvicorn[standard]`, `pytest`, `httpx`
2. `app.py` — FastAPI app, `HealthResponse(BaseModel)`, `GET /health → {"status":"ok"}` (200)
3. `test_health.py` — assert status **200 AND** body `== {"status":"ok"}`
4. Verify — `pytest` green; `uvicorn app:app` serves `/health`

**Decisions:** All API contracts have request/response schemas (machine-readable in `openapi.yaml`). Data model is a single trivial DTO — normalized and extensible. Feasible in one build iteration.

**Escalations:** None. No architecture conflict with existing systems; security surface is nil (public health endpoint, no input, no data store) — concurs with GREENWAY's risk table, so no ARGUS review required. Design is aligned with the PRD and Roadmap V1.

Please approve the writes (or the `architecture/` directory) and I'll finalize, then it's ready for TANNER to begin planning.