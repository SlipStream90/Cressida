# Reusable Patterns

## Execution Patterns

### Pipeline Pattern
Sequential phases of execution where each phase completes before the next begins.

```
Phase 1 (Planning): GREENWAY → M → Q → TANNER → BOND
Phase 2 (Implementation): BRANCH ║ ROOK ║ BOOTHROYD
Phase 3 (Review): ARGUS → SENTINEL → BOND
Phase 4 (Completion): BOND → CRESSIDA COMMAND
```

### Parallel Fan-Out Pattern
A single task fans out to multiple agents executing in parallel.

```
Planning → [Backend, Frontend, Infrastructure] → Review
```

### Review Gate Pattern
Implementation outputs must pass review gates before proceeding to the next phase.

```
Implementation → ARGUS Review → SENTINEL Tests → BOND Approval → Next Phase
```

## Data Patterns

### Command Pattern for Agent Messages
Each message has a sender, recipient, subject, and body. Agents respond to messages via event bus.

### Snapshot Pattern
State snapshots at mission phase boundaries enable rollback and audit.

## Intelligence Patterns

### Agent Spec Template
All agents follow the same template: Mission, Responsibilities, Inputs, Outputs, Decision Framework, Success Criteria, Communication Rules, Escalation Rules, Failure Handling, Examples.

### Memory Retrieval Before Execution
Agents always read relevant memory before starting work and write decisions after completing.
