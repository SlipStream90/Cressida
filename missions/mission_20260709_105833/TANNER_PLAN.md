# TANNER Agent Plan — mission_20260709_105833

## Task Decomposition & Execution Backlog

**Mission:** FastAPI Hello World API  
**Agent:** TANNER (Planning)  
**Date:** 2026-07-09

---

## 1. Mission Summary

Build a minimal FastAPI service with 2 GET endpoints, Pydantic response models, and pytest tests as a pipeline smoke test for the Cressida multi-agent framework.

**Deliverables:**
- `main.py` - FastAPI application with routes and models
- `test_api.py` - Pytest tests using TestClient
- `requirements.txt` - Dependencies

**Success Criteria:**
- GET /health → {"status": "ok"}
- GET /hello/{name} → {"message": "Hello, {name}!"}
- Pydantic models used as response_model
- pytest test_api.py passes (2+ tests)
- GET /docs returns Swagger UI
- Total file count ≤ 4

---

## 2. Task Breakdown

### TASK-001: Create requirements.txt
**Description:** Define project dependencies in requirements.txt  
**Dependencies:** None (first task)  
**Estimated Time:** 1 minute  
**Output:** `requirements.txt` file with:
```
fastapi>=0.100.0
uvicorn[standard]>=0.23.0
pydantic>=2.0.0
pytest>=7.0.0
```

### TASK-002: Create main.py - Import statements
**Description:** Add import statements for FastAPI and Pydantic  
**Dependencies:** TASK-001  
**Estimated Time:** 1 minute  
**Output:** Initial main.py with imports:
```python
from fastapi import FastAPI
from pydantic import BaseModel
```

### TASK-003: Create main.py - FastAPI app instance
**Description:** Initialize the FastAPI application  
**Dependencies:** TASK-002  
**Estimated Time:** 1 minute  
**Output:** App instance in main.py:
```python
app = FastAPI(title="Hello World API")
```

### TASK-004: Create main.py - Pydantic models
**Description:** Define HealthResponse and HelloResponse models  
**Dependencies:** TASK-002  
**Estimated Time:** 2 minutes  
**Output:** Pydantic models in main.py:
```python
class HealthResponse(BaseModel):
    status: str

class HelloResponse(BaseModel):
    message: str
```

### TASK-005: Create main.py - Route handlers
**Description:** Implement GET /health and GET /hello/{name} endpoints  
**Dependencies:** TASK-003, TASK-004  
**Estimated Time:** 3 minutes  
**Output:** Route handlers in main.py:
```python
@app.get("/health", response_model=HealthResponse)
def health_check():
    return HealthResponse(status="ok")

@app.get("/hello/{name}", response_model=HelloResponse)
def hello_name(name: str):
    return HelloResponse(message=f"Hello, {name}!")
```

### TASK-006: Create test_api.py - Imports and TestClient setup
**Description:** Set up test file with imports and TestClient  
**Dependencies:** TASK-005  
**Estimated Time:** 2 minutes  
**Output:** Initial test_api.py:
```python
import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)
```

### TASK-007: Create test_api.py - Test functions
**Description:** Write pytest test functions for both endpoints  
**Dependencies:** TASK-006  
**Estimated Time:** 3 minutes  
**Output:** Test functions in test_api.py:
- `test_health_endpoint()`
- `test_hello_endpoint()`
- `test_hello_endpoint_with_different_name()`

### TASK-008: Verify implementation
**Description:** Install dependencies, run tests, and manually verify  
**Dependencies:** TASK-007  
**Estimated Time:** 5 minutes  
**Output:** Verified working implementation

**Verification Steps:**
1. `pip install -r requirements.txt`
2. `pytest test_api.py -v`
3. `uvicorn main:app --reload`
4. Manual curl tests for /health, /hello/{name}, /docs

---

## 3. Dependency Graph

```
TASK-001 (requirements.txt)
    ↓
TASK-002 (Imports)
    ↓
┌────┴────┐
↓         ↓
TASK-003  TASK-004
(App)     (Models)
    ↓         ↓
    └────┬────┘
         ↓
     TASK-005 (Routes)
         ↓
     TASK-006 (Test Setup)
         ↓
     TASK-007 (Test Functions)
         ↓
     TASK-008 (Verification)
```

**Critical Path:** TASK-001 → TASK-002 → TASK-003 → TASK-005 → TASK-006 → TASK-007 → TASK-008

**Parallel Opportunities:**
- TASK-003 and TASK-004 can be executed in parallel after TASK-002

---

## 4. Execution Backlog

| Task ID | Description | Dependencies | Est. Time | Status |
|---------|-------------|--------------|-----------|--------|
| TASK-001 | Create requirements.txt | None | 1 min | Pending |
| TASK-002 | Add import statements to main.py | TASK-001 | 1 min | Pending |
| TASK-003 | Create FastAPI app instance | TASK-002 | 1 min | Pending |
| TASK-004 | Define Pydantic models | TASK-002 | 2 min | Pending |
| TASK-005 | Implement route handlers | TASK-003, TASK-004 | 3 min | Pending |
| TASK-006 | Set up test_api.py | TASK-005 | 2 min | Pending |
| TASK-007 | Write pytest test functions | TASK-006 | 3 min | Pending |
| TASK-008 | Verify implementation | TASK-007 | 5 min | Pending |

**Total Estimated Time:** 18 minutes

---

## 5. Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| Import path errors | Low | Use `from fastapi.testclient import TestClient` |
| Pydantic version mismatch | Low | Specify v2 in requirements.txt |
| TestClient import issues | Low | Follow BUILD_INSTRUCTIONS.md exactly |
| File count exceeds limit | Low | Stick to 3-file structure |

---

## 6. Quality Gates

### Gate 1: After TASK-005
- [ ] main.py is syntactically correct
- [ ] All imports are present
- [ ] App instance is created
- [ ] Both route handlers are implemented

### Gate 2: After TASK-007
- [ ] test_api.py is syntactically correct
- [ ] TestClient is properly configured
- [ ] All test functions are implemented

### Gate 3: After TASK-008
- [ ] `pip install -r requirements.txt` succeeds
- [ ] `pytest test_api.py -v` passes (3/3 tests)
- [ ] `uvicorn main:app --reload` starts without errors
- [ ] Manual curl tests return expected responses
- [ ] GET /docs returns Swagger UI

---

## 7. Implementation Notes

### Code Style Requirements
- PEP 8 compliant
- No unused imports
- Proper function naming
- Docstrings optional (not required for smoke test)

### File Structure (Final)
```
mission_20260709_105833/
├── intelligence/          # PRD, roadmap, research
├── architecture/          # Architecture docs
├── main.py               # FastAPI application
├── test_api.py           # Pytest tests
├── requirements.txt      # Dependencies
└── TANNER_PLAN.md        # This document
```

### Dependencies (External)
- fastapi >= 0.100.0
- uvicorn[standard] >= 0.23.0
- pydantic >= 2.0.0
- pytest >= 7.0.0

---

## 8. Success Metrics

| Metric | Target | Actual |
|--------|--------|--------|
| Test pass rate | 100% | - |
| Test count | ≥2 | 3 planned |
| Endpoints implemented | 2/2 | - |
| Pydantic models | 2 | - |
| File count | ≤4 | 3 planned |
| External dependencies | 4 | 4 |

---

## 9. Next Steps for BUILD Agent

1. **Read this plan** to understand task breakdown and dependencies
2. **Follow tasks sequentially** (respecting dependencies)
3. **Execute TASK-001 first** (create requirements.txt)
4. **Complete TASK-002 through TASK-007** (implement main.py and test_api.py)
5. **Finish with TASK-008** (verification)
6. **Report completion** with test results

---

**Plan Version:** 1.0  
**Last Updated:** 2026-07-09  
**Status:** Ready for BUILD agent execution