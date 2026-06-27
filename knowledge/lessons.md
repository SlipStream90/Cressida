# Lessons Learned

## Architectural Lessons

### 1. Separate Intelligence from Infrastructure
Mixing agent logic with Python code makes the system opaque and hard to modify. Keeping agents as Markdown specs and infrastructure as Python preserves clarity and extensibility.

### 2. State Must Be Centralized
Distributed state leads to inconsistency. Centralized SharedState with event-driven updates ensures all agents have a coherent view.

### 3. Async from Day One
Parallel execution is the core value proposition. Building on asyncio from the start avoids costly refactoring later.

### 4. Document Decisions Immediately
Architectural context decays rapidly. Writing ADRs at decision time preserves rationale that would otherwise be lost.

### 5. Favor Composition Over Inheritance
Agents compose capabilities through shared state and event bus rather than class hierarchies. This keeps the system flexible as new agent types emerge.

## Engineering Lessons

### 6. Cycle Detection is Mandatory
Dependency graphs inevitably form cycles during complex missions. Early detection prevents deadlock.

### 7. Retry Logic Must Be Bounded
Unbounded retries mask underlying issues. Three retries with exponential backoff provides resilience without hiding failures.

### 8. Memory Systems Need Explicit Contracts
Each memory layer must define clear read/write contracts. Agents must know what context to expect and when to persist.
