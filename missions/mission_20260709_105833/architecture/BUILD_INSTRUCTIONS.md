# Build Instructions — FastAPI Hello World API

## Overview

This document provides step-by-step instructions for the BUILD agent to implement the FastAPI Hello World API based on the architecture defined in `ARCHITECTURE.md`.

## Implementation Requirements

### 1. File Structure

Create exactly 3 files in the mission directory root:

```
mission_20260709_105833/
├── main.py          # FastAPI application
├── test_api.py      # Pytest tests
└── requirements.txt # Dependencies
```

### 2. main.py Implementation

#### 2.1 Imports

```python
from fastapi import FastAPI
from pydantic import BaseModel
```

#### 2.2 App Instance

```python
app = FastAPI(title="Hello World API")
```

#### 2.3 Pydantic Models

```python
class HealthResponse(BaseModel):
    status: str

class HelloResponse(BaseModel):
    message: str
```

#### 2.4 Route Handlers

```python
@app.get("/health", response_model=HealthResponse)
def health_check():
    return HealthResponse(status="ok")

@app.get("/hello/{name}", response_model=HelloResponse)
def hello_name(name: str):
    return HelloResponse(message=f"Hello, {name}!")
```

### 3. test_api.py Implementation

#### 3.1 Imports

```python
import pytest
from fastapi.testclient import TestClient
from main import app
```

#### 3.2 Test Client

```python
client = TestClient(app)
```

#### 3.3 Test Functions

```python
def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data == {"status": "ok"}
    assert "status" in data
    assert data["status"] == "ok"

def test_hello_endpoint():
    response = client.get("/hello/Alice")
    assert response.status_code == 200
    data = response.json()
    assert data == {"message": "Hello, Alice!"}
    assert "message" in data
    assert data["message"] == "Hello, Alice!"

def test_hello_endpoint_with_different_name():
    response = client.get("/hello/Bob")
    assert response.status_code == 200
    data = response.json()
    assert data == {"message": "Hello, Bob!"}
```

### 4. requirements.txt

```
fastapi>=0.100.0
uvicorn[standard]>=0.23.0
pydantic>=2.0.0
pytest>=7.0.0
```

## Verification Steps

### Step 1: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 2: Run Tests

```bash
pytest test_api.py -v
```

**Expected Output:**
```
test_api.py::test_health_endpoint PASSED
test_api.py::test_hello_endpoint PASSED
test_api.py::test_hello_endpoint_with_different_name PASSED

========================= 3 passed in 0.05s =========================
```

### Step 3: Start Server

```bash
uvicorn main:app --reload
```

### Step 4: Manual Verification

```bash
# Health check
curl http://localhost:8000/health
# Expected: {"status":"ok"}

# Hello endpoint
curl http://localhost:8000/hello/Alice
# Expected: {"message":"Hello, Alice!"}

# Swagger docs
curl http://localhost:8000/docs
# Expected: HTML page with Swagger UI
```

## Quality Checklist

### Code Quality

- [ ] PEP 8 compliant
- [ ] No unused imports
- [ ] Proper function naming
- [ ] Docstrings optional (not required for smoke test)

### Functionality

- [ ] `GET /health` returns `{"status": "ok"}`
- [ ] `GET /hello/{name}` returns `{"message": "Hello, {name}!"}`  - [ ] Pydantic models used as `response_model`
- [ ] Auto-generated Swagger docs at `/docs`

### Testing

- [ ] 2+ pytest tests passing
- [ ] Tests cover both endpoints
- [ ] Tests validate response structure
- [ ] Tests validate response content

### Dependencies

- [ ] All dependencies in requirements.txt
- [ ] No unnecessary dependencies
- [ ] Version constraints specified

## Common Pitfalls

### 1. Import Errors

**Problem:** `ModuleNotFoundError: No module named 'main'`

**Solution:** Ensure `test_api.py` is in the same directory as `main.py`

### 2. Pydantic Version

**Problem:** `ValidationError` with Pydantic v1 syntax

**Solution:** Use Pydantic v2 syntax (already specified in requirements.txt)

### 3. TestClient Import

**Problem:** `ImportError: cannot import name 'TestClient'`

**Solution:** Use `from fastapi.testclient import TestClient`

### 4. Response Model Validation

**Problem:** Response doesn't match model schema

**Solution:** Ensure return value matches Pydantic model fields exactly

## Success Criteria

### Must Have

1. ✅ `main.py` with FastAPI app and two endpoints
2. ✅ Pydantic `HealthResponse` and `HelloResponse` models
3. ✅ `response_model=` parameter on both endpoints
4. ✅ `test_api.py` with 2+ passing tests
5. ✅ `requirements.txt` with all dependencies

### Nice to Have

1. ✅ Additional test for different name parameter
2. ✅ Proper error handling (automatic via FastAPI)
3. ✅ Clean code structure

### Must NOT Have

1. ❌ More than 4 files total
2. ❌ Database integration
3. ❌ Authentication/authorization
4. ❌ POST/PUT/DELETE endpoints
5. ❌ Docker/containerization

## Implementation Time Estimate

- **Coding:** 5-10 minutes
- **Testing:** 2-3 minutes
- **Verification:** 2-3 minutes
- **Total:** 10-15 minutes

---

**Instructions Version:** 1.0  
**Last Updated:** 2026-07-09  
**Status:** Ready for Implementation