# Architecture — test_opencode_direct "Hello World API"

## 1. System Overview

Single-process monolithic FastAPI application. No service decomposition required for a 2-endpoint smoke test.

```
┌─────────────────────────────────────────────┐
│              FastAPI Application             │
│                                             │
│  ┌──────────────┐    ┌──────────────────┐   │
│  │  GET /health  │    │ GET /hello/{name}│   │
│  └──────┬───────┘    └────────┬─────────┘   │
│         │                     │             │
│  ┌──────▼─────────────────────▼──────────┐  │
│  │         Pydantic Response Models       │  │
│  │   HealthResponse    HelloResponse      │  │
│  └───────────────────────────────────────┘  │
│                                             │
│              ┌─────────────┐                │
│              │   Uvicorn   │                │
│              │  (ASGI)     │                │
│              └─────────────┘                │
└─────────────────────────────────────────────┘
```

## 2. Technology Stack

| Component | Technology | Version | Rationale |
|---|---|---|---|
| Web framework | FastAPI | >=0.100.0 | Native Pydantic v2, auto OpenAPI docs, async |
| ASGI server | Uvicorn | >=0.23.0 | De facto standard, high performance |
| Validation | Pydantic | (bundled) | Type-safe request/response serialization |
| Testing | pytest | >=7.0.0 | Industry standard, fixture support |
| Test HTTP client | httpx | >=0.24.0 | FastAPI's TestClient backend |

**ADR-001: FastAPI over Flask**
- **Decision:** Use FastAPI as the web framework
- **Alternatives considered:** Flask, Litestar
- **Rationale:** Native Pydantic integration eliminates manual serialization; auto-generates OpenAPI/Swagger docs; officially documented TestClient pattern; async support for future scaling
- **Trade-off:** Slightly more setup than Flask, but the Pydantic integration and auto-docs provide significant value even for a smoke test

**ADR-002: Uvicorn as ASGI server**
- **Decision:** Use Uvicorn for local development and production serving
- **Alternatives considered:** Hypercorn, Granian
- **Rationale:** De facto standard for FastAPI, minimal configuration, single dependency
- **Trade-off:** None significant for this scope

**ADR-003: Pydantic v2 response models**
- **Decision:** Use `response_model` parameter on route decorators instead of returning raw dicts
- **Alternatives considered:** Manual JSON serialization, dataclasses
- **Rationale:** Automatic validation, serialization, and OpenAPI schema generation; enforces contract at code level
- **Trade-off:** Slightly more verbose than raw dicts, but provides type safety

## 3. API Contracts

### 3.1 GET /health

```yaml
openapi: 3.0.0
paths:
  /health:
    get:
      operationId: health
      summary: Health check endpoint
      responses:
        "200":
          description: Service is healthy
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/HealthResponse'
components:
  schemas:
    HealthResponse:
      type: object
      required:
        - status
      properties:
        status:
          type: string
          example: "ok"
```

**Request:** No parameters

**Response (200):**
```json
{
  "status": "ok"
}
```

### 3.2 GET /hello/{name}

```yaml
openapi: 3.0.0
paths:
  /hello/{name}:
    get:
      operationId: hello
      summary: Greeting endpoint
      parameters:
        - name: name
          in: path
          required: true
          schema:
            type: string
      responses:
        "200":
          description: Personalized greeting
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/HelloResponse'
components:
  schemas:
    HelloResponse:
      type: object
      required:
        - message
      properties:
        message:
          type: string
          example: "Hello, World!"
```

**Request:**
- Path parameter: `name` (string, required)

**Response (200):**
```json
{
  "message": "Hello, World!"
}
```

## 4. Data Models

```python
from pydantic import BaseModel

class HealthResponse(BaseModel):
    """Response model for GET /health"""
    status: str

class HelloResponse(BaseModel):
    """Response model for GET /hello/{name}"""
    message: str
```

**Design decisions:**
- Models are minimal with single required fields
- No optional fields needed for this smoke test
- Models live in `main.py` (no separate module needed for 2 models)
- Pydantic v2 is used automatically with FastAPI >=0.100.0

## 5. File Structure

```
missions/test_opencode_direct/
├── intelligence/
│   ├── PRD.md
│   ├── research_report.md
│   └── Roadmap.md
├── ARCHITECTURE.md          # This file
└── (implementation files will be created by TANNER)
```

**Implementation file structure (for TANNER):**
```
project/
├── main.py          # FastAPI app, endpoints, Pydantic models (~25 LOC)
├── requirements.txt # Dependencies (~5 lines)
└── tests/
    └── test_api.py  # Pytest endpoint tests (~25 LOC)
```

## 6. Testing Strategy

### Test Architecture

```python
# tests/test_api.py
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_hello_returns_greeting():
    response = client.get("/hello/World")
    assert response.status_code == 200
    assert response.json() == {"message": "Hello, World!"}

def test_hello_path_parameter():
    response = client.get("/hello/Alice")
    assert response.status_code == 200
    assert response.json()["message"] == "Hello, Alice!"
```

**Key decisions:**
- Use synchronous `TestClient` (no async complexity needed)
- No port binding required (in-process testing)
- 3 test functions covering both endpoints and path parameter extraction
- Direct app import, no fixture for client creation

## 7. Infrastructure Requirements

**Minimal — smoke test only:**
- Python >= 3.8
- pip for dependency installation
- No database, cache, or external services
- No Docker or containerization
- No CI/CD configuration

## 8. Security Considerations

**Out of scope for smoke test:**
- No authentication/authorization
- No CORS configuration
- No rate limiting
- No input validation beyond path parameter type checking
- No secrets or environment variables

## 9. Scalability Notes

While not required for this smoke test, the architecture supports future scaling:
- FastAPI is async-native, supports horizontal scaling
- Uvicorn can run multiple workers via `--workers` flag
- Pydantic models can be extended with validation rules
- TestClient pattern scales to integration test suites

## 10. Architecture Decision Records

| ADR | Decision | Status |
|---|---|---|
| ADR-001 | FastAPI over Flask | Accepted |
| ADR-002 | Uvicorn as ASGI server | Accepted |
| ADR-003 | Pydantic v2 response models | Accepted |
| ADR-004 | Synchronous TestClient for tests | Accepted |
| ADR-005 | Single-file app structure | Accepted |
