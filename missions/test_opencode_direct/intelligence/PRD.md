# Product Requirements Document — test_opencode_direct "Hello World API"

## 1. Product Overview

A minimal FastAPI service to verify the Cressida pipeline works end-to-end. Two GET endpoints with Pydantic response models and pytest coverage. Smoke test only — no persistence, no auth, no external services.

## 2. User Personas

### Persona: Developer (Pipeline Verifier)
- **Name:** Aditya
- **Behavior:** Runs the pipeline, expects working endpoints and passing tests
- **Needs:** Verify Cressida can produce a working codebase from a brief
- **Success criteria:** All tests pass, endpoints respond correctly

## 3. User Stories

| ID | Story | Acceptance Criteria | Priority |
|---|---|---|---|
| US-001 | As a developer, I want a GET /health endpoint so I can verify the service is running | Returns `{"status": "ok"}` with 200 status | P0 |
| US-002 | As a developer, I want a GET /hello/{name} endpoint so I can verify path parameters work | Returns `{"message": "Hello, {name}!"}` with 200 status | P0 |
| US-003 | As a developer, I want Pydantic response models so I can verify type-safe serialization | Both endpoints use Pydantic BaseModel for response validation | P0 |
| US-004 | As a developer, I want pytest tests so I can verify the test infrastructure works | All tests pass with `pytest` | P0 |

## 4. Feature Specification

### Endpoint 1: GET /health
- **Path:** `/health`
- **Method:** GET
- **Response Model:** `HealthResponse`
  ```python
  class HealthResponse(BaseModel):
      status: str
  ```
- **Response Body:** `{"status": "ok"}`
- **Status Code:** 200

### Endpoint 2: GET /hello/{name}
- **Path:** `/hello/{name}`
- **Method:** GET
- **Path Parameter:** `name` (string, required)
- **Response Model:** `HelloResponse`
  ```python
  class HelloResponse(BaseModel):
      message: str
  ```
- **Response Body:** `{"message": "Hello, {name}!"}`
- **Status Code:** 200

## 5. File Structure

| File | Purpose | Lines (est.) |
|---|---|---|
| `main.py` | FastAPI app, endpoints, Pydantic models | ~25 |
| `requirements.txt` | Dependencies | 4-5 |
| `tests/test_api.py` | Pytest endpoint tests | ~25 |

**Total:** 3 files, ~55 lines of code.

## 6. Success Metrics

| Metric | Target | Measurement |
|---|---|---|
| Test pass rate | 100% | `pytest` exit code 0 |
| Endpoint response time | <100ms | Manual or simple timing |
| Code coverage | >80% | `pytest --cov` (optional) |

## 7. Out of Scope

- Authentication/authorization
- Database/persistence
- Docker/containerization
- CI/CD configuration
- Logging/monitoring
- Rate limiting
- CORS configuration
- Request validation beyond path parameters

## 8. Acceptance Criteria

1. `main.py` defines a FastAPI app with both endpoints
2. Both endpoints use Pydantic `response_model`
3. `GET /health` returns `{"status": "ok"}`
4. `GET /hello/{name}` returns `{"message": "Hello, {name}!"}` for any name
5. `pytest` runs all tests with 100% pass rate
6. No external dependencies beyond FastAPI ecosystem
