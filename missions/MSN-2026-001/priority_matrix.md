# Priority Matrix — MSN-2026-001 "ECHO"

## Critical Path (must not be delayed)

The critical path determines the minimum mission duration. Every day of delay on these tasks pushes the mission end date.

```
T-A-001 (Scaffolding) →
  T-A-002 (Models) →
    T-A-006 (API Framework) →
      T-B-002 (Reward Model Predict) →
        T-B-004 (Variant Gen Service) →
          T-C-003 (Reward Model Training Pipeline) →
            T-D-001 (Adapter Blending) →
              T-D-002 (In-Session Adaptation) →
                T-D-003 (A/B Testing) →
                  T-D-004 (Performance Optimization) →
                    T-F-002 (Load Tests) →
                      T-F-005 (Prod Readiness Review) →
                        T-F-006 (BOND Approval)
```

**Critical path length: 13 tasks (sequential)**
**Total tasks: 32**
**Parallelization allows 12 batches → effective 2.67x speedup**

---

## Parallelization Map

### Batch 1 — Foundation seed
| Task | Agent | Est. Days |
|------|-------|-----------|
| T-A-001 Project scaffolding | BOOTHROYD | 0.5 |

### Batch 2 — Parallel foundation (4 workers)
| Task | Agent | Est. Days |
|------|-------|-----------|
| T-A-002 Pydantic models | BRANCH | 1 |
| T-A-004 Redis setup | BOOTHROYD | 0.5 |
| T-A-005 Qdrant setup | BOOTHROYD | 0.5 |
| T-A-007 Docker Compose | BOOTHROYD | 1 |

### Batch 3 — Max parallelism (7 workers)
| Task | Agent | Est. Days |
|------|-------|-----------|
| T-A-003 PostgreSQL schema | BOOTHROYD | 1 |
| T-A-006 Base API framework | BRANCH | 1.5 |
| T-A-008 API Gateway config | BOOTHROYD | 0.5 |
| T-B-001 LangGraph state schema | BRANCH | 1 |
| T-B-003 LoRA + vLLM S-LoRA | BRANCH | 3 |
| T-B-005 ElevenLabs TTS | BRANCH | 1 |
| T-C-005 MLflow setup | BOOTHROYD | 0.5 |

### Batch 4 — Dual track
| Task | Agent | Est. Days |
|------|-------|-----------|
| T-B-002 Reward model predict | BRANCH | 2 |
| T-C-001 Feedback endpoints | BRANCH | 1 |

### Batch 5 — Dependent parallel
| Task | Agent | Est. Days |
|------|-------|-----------|
| T-B-004 Variant gen service | BRANCH | 3 |
| T-C-002 Implicit signal pipeline | BRANCH | 2 |

### Batch 6 — Heavy parallel
| Task | Agent | Est. Days |
|------|-------|-----------|
| T-B-006 Variant merger | BRANCH | 1 |
| T-C-003 Reward model training pipeline | BRANCH | 4 |
| T-F-003 K8s manifests | BOOTHROYD | 2 |

### Batch 7 — Training + prep
| Task | Agent | Est. Days |
|------|-------|-----------|
| T-C-004 Training trigger | BRANCH | 0.5 |
| T-D-001 Adapter blending | BRANCH | 2 |
| T-E-001 Persona LoRA system | BRANCH | 4 |

### Batch 8 — Single task
| Task | Agent | Est. Days |
|------|-------|-----------|
| T-D-002 In-session adaptation | BRANCH | 2 |

### Batch 9 — Dual feature
| Task | Agent | Est. Days |
|------|-------|-----------|
| T-D-003 A/B testing framework | BRANCH | 2 |
| T-E-002 Dashboard backend | BRANCH | 2 |

### Batch 10 — Max parallelism (agent diversity)
| Task | Agent | Est. Days |
|------|-------|-----------|
| T-D-004 Performance optimization | BRANCH | 2 |
| T-E-003 Dashboard frontend | ROOK | 3 |
| T-F-001 Integration tests | REVIEW | 3 |
| T-F-004 CI/CD pipeline | BOOTHROYD | 1 |

### Batch 11 — Review consolidation
| Task | Agent | Est. Days |
|------|-------|-----------|
| T-F-002 Load tests | REVIEW | 1.5 |
| T-F-005 Prod readiness review | REVIEW | 1 |

### Batch 12 — Final gate
| Task | Agent | Est. Days |
|------|-------|-----------|
| T-F-006 BOND approval | BOND | 0.5 |

---

## High Risk Tasks

| Risk Level | Task | Risk | Mitigation |
|------------|------|------|------------|
| 🔴 **CRITICAL** | T-B-003 LoRA + vLLM S-LoRA | S-LoRA integration with vLLM is complex; dependency for variant gen and blending | Start early (Batch 3); have PEFT fallback |
| 🔴 **CRITICAL** | T-C-003 Reward model training pipeline | Core learning loop; delay blocks 10 downstream tasks | Prototype with synthetic data in Week 1 |
| 🔴 **CRITICAL** | T-B-004 Variant gen service | Most complex service; LangGraph + LoRA + reward model integration | Spike LangGraph integration before full build |
| 🟠 **HIGH** | T-E-001 Persona LoRA system | Novel synthetic archetype training; unclear data requirements | Gate behind V2; prototype with offline data first |
| 🟠 **HIGH** | T-D-001 Adapter blending | Linear interpolation may degrade output quality | Build coherence validation; have single-adapter fallback |
| 🟠 **HIGH** | T-B-002 Reward model predict | Cold start: no user data to train on | Heuristic rules + epsilon-greedy exploration |
| 🟡 **MEDIUM** | T-F-001 Integration tests | Spans 6 services; complex orchestration | Start writing test harness in Phase A |
| 🟡 **MEDIUM** | T-A-007 Docker Compose | vLLM GPU passthrough in Docker is tricky | Test GPU forwarding early; document nvidia-container-toolkit |

---

## Quick Wins

| Task | Est. Days | Impact | Why Quick |
|------|-----------|--------|-----------|
| T-A-001 Scaffolding | 0.5 | Foundation for all tasks | Just project setup, no logic |
| T-A-004 Redis setup | 0.5 | Cache for all services | Standard library, documented patterns |
| T-A-005 Qdrant setup | 0.5 | Vector storage ready | Simple client init, no custom logic |
| T-A-008 API Gateway | 0.5 | Security perimeter | Template-based nginx config |
| T-C-004 Training trigger | 0.5 | Automates training | 3 if-statements, no complex logic |
| T-F-006 BOND approval | 0.5 | Mission closure | Checklist review, no code |

---

## Agent Workload Breakdown

| Agent | Task Count | Est. Total Days | Phases | Bottleneck Risk |
|-------|-----------|----------------|--------|-----------------|
| **BRANCH** | 18 tasks | 34.5 days | A, B, C, D, E | 🔴 **SEVERE** — owns 56% of tasks; critical path runs entirely through BRANCH |
| **BOOTHROYD** | 8 tasks | 6.5 days | A, C, F | 🟢 Low — infrastructure tasks front-loaded in Phase A |
| **REVIEW** | 3 tasks | 5.5 days | F | 🟢 Low — only active in Phase F |
| **ROOK** | 1 task | 3 days | E | 🟢 Low — single frontend task in V3 |
| **BOND** | 1 task | 0.5 days | F | 🟢 Minimal — approval gate only |

### BRANCH Decompression Strategy

BRANCH is the critical bottleneck. Recommended actions:
1. **Phase A**: BRANCH only owns T-A-002 (models) and T-A-006 (API framework) — 2.5 days total
2. **Phase B-C**: BRANCH peaks at 9 parallel-consecutive tasks (T-B-001 through T-C-003)
3. **Delegation**: T-B-005 (ElevenLabs TTS) could be delegated to BOOTHROYD if needed
4. **Parallel assist**: T-C-005 (MLflow) is already BOOTHROYD
5. **Review assist**: T-F-001 (Integration tests) is already REVIEW — reduces BRANCH load in Phase F

---

## Phase Summary

| Phase | Tasks | Est. Days (seq) | Est. Days (parallel) | Agents |
|-------|-------|-----------------|---------------------|--------|
| **A** Foundation | 8 | 6 | 4 | BRANCH, BOOTHROYD |
| **B** Variant Gen + LangGraph | 6 | 15 | 8 | BRANCH |
| **C** Feedback + Reward Training | 5 | 10.5 | 7 | BRANCH, BOOTHROYD |
| **D** LoRA Adapter Switching | 4 | 8 | 6 | BRANCH |
| **E** Persona LoRA + Dashboard | 3 | 9 | 5 | BRANCH, ROOK |
| **F** Integration + Deployment | 6 | 11 | 6 | REVIEW, BOOTHROYD, BOND |

**Total sequential estimate:** ~59.5 days
**Total parallel estimate:** ~36 days (1.65x speedup from parallelism)
**Bottleneck:** BRANCH (34.5 of 59.5 days = 58% of total effort)
