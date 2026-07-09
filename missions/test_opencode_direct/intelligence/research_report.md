# Research Report — test_opencode_direct "Hello World API"

## 1. Web Framework Selection

### Problem Space
Build a minimal REST API with two GET endpoints, Pydantic response models, and pytest tests. The framework must be lightweight, fast to develop, and well-documented.

### Approaches Compared

| Framework | Pros | Cons | Verdict |
|---|---|---|---|
| **FastAPI** | Native Pydantic support, async, auto OpenAPI docs, high performance (Starlette/Uvicorn) | Slightly more setup than Flask | **Recommended** |
| **Flask** | Minimal, huge ecosystem, simple | No native Pydantic, manual serialization, no async by default | Acceptable alternative |
| **Litestar** | Modern, Pydantic v2 native, performance | Smaller community, less documentation | Not suitable for smoke test |

**Recommendation:** FastAPI — native Pydantic integration eliminates boilerplate, auto-generates OpenAPI docs, and has excellent testing support via `TestClient`.

## 2. ASGI Server

| Server | Performance | Config Complexity | Verdict |
|---|---|---|---|
| **Uvicorn** | High (libuv) | Minimal | **Recommended** |
| Hypercorn | Moderate | Moderate | Not needed |
| Granian | High (Rust) | Low | Overkill for this scope |

**Recommendation:** Uvicorn — de facto standard for FastAPI development, single dependency.

## 3. Testing Strategy

### Framework Choice

| Tool | Pros | Cons | Verdict |
|---|---|---|---|
| **pytest + httpx** | FastAPI's `TestClient` is httpx-based, sync/async support, fixtures | Extra dependency (httpx) | **Recommended** |
| pytest + requests | Familiar | No async, not native to FastAPI | Not recommended |
| unittest | Built-in | Verbose, no fixtures | Not recommended |

**Recommendation:** pytest with FastAPI's `TestClient` (backed by httpx). This is the officially documented approach.

### Test Structure
```
tests/
  test_api.py     # Endpoint tests
```

Single test file with 3 test functions:
1. `test_health_returns_ok` — verify /health response
2. `test_hello_returns_greeting` — verify /hello/{name} response
3. `test_hello_path_parameter` — verify path parameter extraction

## 4. Project Structure

```
project/
  main.py          # FastAPI app + endpoints + Pydantic models
  requirements.txt # Dependencies
  tests/
    test_api.py    # Pytest tests
```

**3-4 files total** as specified in the brief.

## 5. Dependency Analysis

| Package | Version Constraint | Purpose |
|---|---|---|
| fastapi | >=0.100.0 | Web framework |
| uvicorn | >=0.23.0 | ASGI server |
| pydantic | (bundled with FastAPI) | Response models |
| httpx | >=0.24.0 | TestClient backend |
| pytest | >=7.0.0 | Test framework |

All are mature, well-maintained packages with active communities.

## 6. Risk Assessment

| Risk | Severity | Mitigation |
|---|---|---|
| Python version incompatibility | Low | FastAPI requires Python 3.8+; all modern envs satisfy this |
| Pydantic v1 vs v2 confusion | Low | FastAPI >=0.100.0 uses Pydantic v2 by default |
| TestClient async issues | Low | Use synchronous `TestClient` for simplicity |
| Port conflicts in tests | Low | `TestClient` doesn't bind to a port |

**Overall risk: Minimal** — this is a well-trodden path with first-class framework support.

## 7. Alternatives Considered (Not Recommended)

| Alternative | Reason Rejected |
|---|---|
| Flask + marshmallow | More boilerplate, no auto-docs |
| Django REST framework | Heavyweight for a 2-endpoint API |
| gRPC | Overkill, not REST, harder to test |
| Starlette directly | FastAPI provides more value (validation, docs) at no cost |
