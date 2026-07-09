# Research Report — mission_20260709_095951 "Python CLI Calculator"

## 1. Python CLI Frameworks

### Problem Space
Need a command-line interface for a calculator that accepts operation type and two operands via flags.

### Approaches Compared

| Framework | Pros | Cons | Verdict |
|-----------|------|------|---------|
| **argparse** (stdlib) | No dependencies, well-documented, handles type conversion, auto-generates help | Verbose setup, no decorator syntax | **Recommended** |
| click | Decorator-based, composable, excellent docs | External dependency, overkill for simple CLI | Not needed |
| typer | Modern, type-hint driven, built on click | External dependency, adds complexity | Not needed |
| sys.argv | Minimal, no framework | Manual parsing, no help generation, error-prone | Rejected |

### Key Findings
- argparse is explicitly requested in the mission brief (`--op, --a, --b`)
- For 3 flags with type validation, argparse is optimal
- Division-by-zero is a runtime error, not a parsing error — handle in logic layer

### Recommendation
Use **argparse** (stdlib). Zero dependencies, meets requirements exactly.

---

## 2. Testing Framework

### Problem Space
Need 5+ pytest tests covering calculator operations and edge cases.

### Approaches Compared

| Framework | Pros | Cons | Verdict |
|-----------|------|------|---------|
| **pytest** | Concise syntax, fixtures, parametrize, widely adopted | External dependency (but specified in brief) | **Recommended** |
| unittest | Stdlib, no dependencies | Verbose, boilerplate-heavy, class-based | Rejected |
| nose2 | Extends unittest, plugins | Less popular, heavier | Rejected |

### Key Findings
- pytest is explicitly requested in the mission brief
- Parametrize decorator ideal for testing multiple operations
- Fixtures useful for calculator instance setup

### Recommendation
Use **pytest** as specified. Leverage `@pytest.mark.parametrize` for operation coverage.

---

## 3. Project Structure

### Problem Space
Single-file calculator vs package structure.

### Approaches Compared

| Structure | Pros | Cons | Verdict |
|-----------|------|------|---------|
| **Single module** (`calculator.py`) | Simple, matches brief scope, easy to test | Limited extensibility | **Recommended** |
| Package (`calculator/`) | Modular, scalable | Overengineered for 4 operations | Not needed |

### Key Findings
- Brief specifies `test_calculator.py` — implies flat structure
- 4 operations + CLI = ~50-80 lines total
- No imports from external modules needed

### Recommendation
Single `calculator.py` module with `calculator.py` and `test_calculator.py` at project root.

---

## 4. Error Handling Patterns

### Problem Space
Division by zero must be handled gracefully.

### Approaches Compared

| Pattern | Pros | Cons | Verdict |
|---------|------|------|---------|
| **Raise ValueError** | Standard Pythonic, testable, clear semantics | Caller must catch | **Recommended** |
| Return None/sentinel | No exceptions | Silent failures, hard to test | Rejected |
| sys.exit(1) | Immediate termination | Untestable, kills process | Rejected |

### Key Findings
- ValueError with descriptive message is Pythonic and testable
- argparse can catch and reformat for CLI output
- Test can assert `pytest.raises(ValueError)`

### Recommendation
Raise `ValueError("Cannot divide by zero")` in logic layer. Catch in CLI layer for user-friendly output.

---

## 5. Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| Division by zero not tested | Medium | Explicit test case with `pytest.raises` |
| Non-numeric input handling | Low | argparse type=int/float handles validation |
| Invalid operation input | Low | argparse choices parameter limits valid ops |
| No requirements.txt | Low | Only stdlib + pytest (dev dependency) |

---

## 6. Alternatives Considered (Not Recommended)

| Alternative | Reason Rejected |
|-------------|-----------------|
| click/typer | External dependencies not justified for 3-flag CLI |
| Package structure | Overengineered for single-module calculator |
| unittest | pytest specified in brief, more concise |
| JSON config for operations | Unnecessary complexity for 4 fixed operations |