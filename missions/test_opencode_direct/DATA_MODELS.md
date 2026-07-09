# Data Models — test_opencode_direct "Hello World API"

## Pydantic Models

### HealthResponse

```python
from pydantic import BaseModel

class HealthResponse(BaseModel):
    """Response model for GET /health endpoint."""
    
    status: str
```

**Fields:**
| Field | Type | Required | Description | Example |
|---|---|---|---|---|
| `status` | `str` | Yes | Service health status | `"ok"` |

**Constraints:**
- `status` must be a non-empty string
- For this smoke test, always returns `"ok"`

---

### HelloResponse

```python
from pydantic import BaseModel

class HelloResponse(BaseModel):
    """Response model for GET /hello/{name} endpoint."""
    
    message: str
```

**Fields:**
| Field | Type | Required | Description | Example |
|---|---|---|---|---|
| `message` | `str` | Yes | Personalized greeting message | `"Hello, World!"` |

**Constraints:**
- `message` must be a non-empty string
- Format: `"Hello, {name}!"` where `{name}` is the path parameter

---

## Model Usage in FastAPI

```python
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class HealthResponse(BaseModel):
    status: str

class HelloResponse(BaseModel):
    message: str

@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(status="ok")

@app.get("/hello/{name}", response_model=HelloResponse)
async def hello(name: str):
    return HelloResponse(message=f"Hello, {name}!")
```

## Schema Generation

Pydantic v2 automatically generates JSON Schema for both models:

### HealthResponse JSON Schema
```json
{
  "properties": {
    "status": {
      "title": "Status",
      "type": "string"
    }
  },
  "required": ["status"],
  "title": "HealthResponse",
  "type": "object"
}
```

### HelloResponse JSON Schema
```json
{
  "properties": {
    "message": {
      "title": "Message",
      "type": "string"
    }
  },
  "required": ["message"],
  "title": "HelloResponse",
  "type": "object"
}
```

## Design Decisions

1. **Minimal fields:** Each model has exactly one field, matching the PRD requirements
2. **No Optional fields:** Both fields are required for this smoke test
3. **No validation rules:** No regex patterns or constraints beyond type checking
4. **No custom validators:** Not needed for simple string fields
5. **No inheritance:** Models are independent, no base class needed
6. **No serialization config:** Default Pydantic v2 serialization is sufficient
