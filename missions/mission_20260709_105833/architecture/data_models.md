# Data Models — FastAPI Hello World API

## Pydantic Response Models

### HealthResponse

**Purpose:** Structured response for health check endpoint

**Location:** `main.py` (embedded in application module)

**Definition:**
```python
from pydantic import BaseModel

class HealthResponse(BaseModel):
    """Response model for health check endpoint."""
    status: str
```

**Fields:**
| Field | Type | Required | Description | Example |
|-------|------|----------|-------------|---------|
| `status` | `str` | Yes | Health status indicator | `"ok"` |

**JSON Schema:**
```json
{
  "type": "object",
  "properties": {
    "status": {
      "type": "string",
      "title": "Status",
      "description": "Health status indicator"
    }
  },
  "required": ["status"],
  "title": "HealthResponse"
}
```

**Usage in Endpoint:**
```python
@app.get("/health", response_model=HealthResponse)
def health_check():
    return HealthResponse(status="ok")
```

**Validation Rules:**
- Field is required
- Must be a string
- No length constraints
- No pattern validation

---

### HelloResponse

**Purpose:** Structured response for hello endpoint

**Location:** `main.py` (embedded in application module)

**Definition:**
```python
from pydantic import BaseModel

class HelloResponse(BaseModel):
    """Response model for hello endpoint."""
    message: str
```

**Fields:**
| Field | Type | Required | Description | Example |
|-------|------|----------|-------------|---------|
| `message` | `str` | Yes | Personalized greeting message | `"Hello, Alice!"` |

**JSON Schema:**
```json
{
  "type": "object",
  "properties": {
    "message": {
      "type": "string",
      "title": "Message",
      "description": "Personalized greeting message"
    }
  },
  "required": ["message"],
  "title": "HelloResponse"
}
```

**Usage in Endpoint:**
```python
@app.get("/hello/{name}", response_model=HelloResponse)
def hello_name(name: str):
    return HelloResponse(message=f"Hello, {name}!")
```

**Validation Rules:**
- Field is required
- Must be a string
- No length constraints
- No pattern validation

---

## Model Relationships

```
HealthResponse
    └── status: str

HelloResponse
    └── message: str
```

Both models are independent and share no common fields or inheritance.

## Serialization Behavior

### Response Serialization

When using `response_model=` parameter in FastAPI:

1. **Automatic Validation:** Response data is validated against the Pydantic model
2. **JSON Serialization:** Model is serialized to JSON with proper field names
3. **Schema Generation:** OpenAPI schema is auto-generated from model definition
4. **Error Handling:** Invalid responses raise 500 Internal Server Error

### Example Serialization

**HealthResponse:**
```python
# Python object
HealthResponse(status="ok")

# JSON output
{"status": "ok"}
```

**HelloResponse:**
```python
# Python object
HelloResponse(message="Hello, Alice!")

# JSON output
{"message": "Hello, Alice!"}
```

## Validation Rules

### Field Constraints

| Model | Field | Type | Required | Min Length | Max Length | Pattern |
|-------|-------|------|----------|------------|------------|---------|
| HealthResponse | status | str | Yes | - | - | - |
| HelloResponse | message | str | Yes | - | - | - |

### Type Coercion

Pydantic v2 performs strict type validation:
- `status` must be a string (no automatic conversion)
- `message` must be a string (no automatic conversion)

## Error Scenarios

### Invalid Response Data

If endpoint returns data that doesn't match model:

```python
# Invalid: status is not a string
return {"status": 123}  # Raises ValidationError

# Invalid: missing required field
return {}  # Raises ValidationError
```

### FastAPI Error Response

```json
{
  "detail": [
    {
      "type": "string_type",
      "loc": ["body", "status"],
      "msg": "Input should be a valid string"
    }
  ]
}
```

## Testing Considerations

### Test Validation

```python
def test_health_response_model():
    response = HealthResponse(status="ok")
    assert response.status == "ok"
    assert response.model_dump() == {"status": "ok"}

def test_hello_response_model():
    response = HelloResponse(message="Hello, World!")
    assert response.message == "Hello, World!"
    assert response.model_dump() == {"message": "Hello, World!"}
```

### Test Client Validation

```python
def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data == {"status": "ok"}
    # Validate against model
    HealthResponse(**data)
```

## Future Enhancements

### Potential Extensions

1. **Add Validation Rules:**
   ```python
   class HelloResponse(BaseModel):
       message: str = Field(..., min_length=1, max_length=100)
   ```

2. **Add Example Values:**
   ```python
   class HealthResponse(BaseModel):
       status: str = Field(..., examples=["ok", "degraded", "error"])
   ```

3. **Add Field Descriptions:**
   ```python
   class HelloResponse(BaseModel):
       message: str = Field(..., description="Personalized greeting message")
   ```

### Not Recommended for This Scope

- Complex validation logic
- Nested models
- Custom validators
- Model inheritance

---

**Document Version:** 1.0  
**Last Updated:** 2026-07-09  
**Status:** Approved for Implementation