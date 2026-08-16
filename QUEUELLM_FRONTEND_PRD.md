# QueueLLM — Frontend UI Implementation PRD

**Version:** 1.1
**Scope:** Frontend UI/UX implementation only
**Product:** QueueLLM — Ephemeral GPU LLMOps & Intelligent Inference Scheduling Platform

---

# 1. Objective

Build the complete QueueLLM frontend as a **modern, highly interactive LLMOps control plane**.

The frontend should not feel like a generic admin dashboard. It should visually communicate:

- GPU availability
- queue state
- scheduling decisions
- active inference
- GPU leases
- model/adapter locality
- inference performance
- costs
- logs
- deployments
- training jobs
- system health

The interface should be highly animated and responsive to real system state.

---

# 2. Approved Frontend Resources

The implementation should use the previously established frontend resource set:

### Anime.js

For complex animation timelines, coordinated sequences, GPU/job lifecycle animations, and advanced visual choreography. Anime.js provides animation, timeline, draggable, layout, SVG, text and easing capabilities.

### Motion

For React interaction, layout transitions, hover/tap states, scroll animation, gestures, springs, page transitions, and reduced-motion handling.

### Kokonut UI

For the primary modern application UI/component language.

### Bklit UI

For dashboards, analytics and data visualization. Bklit provides composable charts including line, area, bar, live-line, gauge, heatmap, radar, ring, scatter and Sankey visualizations.

Bklit's charts also support animated transitions, hover interactions and smooth data updates, which are particularly appropriate for QueueLLM's real-time metrics.

### Three.js

**Three.js should be added specifically as the 3D visualization engine.**

It should not become a general UI library. Its role is to render the QueueLLM infrastructure/GPU environment.

Three.js provides WebGL capability detection, allowing the application to determine whether the user's browser can support the 3D experience.

### Important constraint

Do not introduce additional UI, animation, chart, or visual-effect libraries.

The responsibilities should remain:

```text
Kokonut UI → UI components
Bklit UI   → charts / analytics
Motion     → interaction / transitions
Anime.js   → complex animation sequences
Three.js   → 3D infrastructure visualization
```

---

# 3. Overall Design Direction

The UI should feel like:

> **A live operating system for ephemeral AI infrastructure.**

The design should combine:

- dark technical aesthetic
- strong visual hierarchy
- subtle motion
- real-time state changes
- high information density
- large graphical elements
- interactive dashboards
- 3D infrastructure visualization
- responsive layouts

Avoid making the application look like a conventional CRUD SaaS product.

---

# 4. Application Structure

Primary navigation:

```text
QueueLLM
Overview
Queue
GPU Fleet
Inference
Training
Models
Adapters
Deployments
Experiments
Metrics
Logs
Costs
Settings
```

The sidebar should support:

- collapsed mode
- expanded mode
- mobile drawer
- active route animation
- hover states
- keyboard navigation

---

# 5. Main Dashboard

The Overview page is the command center.

It should contain:

```text
┌──────────────────────────────────────────────────────┐
│ QueueLLM                              ● System Healthy│
├──────────────────────────────────────────────────────┤
│                                                      │
│ Active Jobs     Queue       GPUs      Utilization    │
│    12             7          3          82%          │
│                                                      │
├──────────────────────────────────────────────────────┤
│                                                      │
│              3D GPU INFRASTRUCTURE                  │
│                                                      │
│        ● GPU 1          ● GPU 2          ● GPU 3     │
│           ╲              │               ╱           │
│            ╲             │              ╱            │
│                 SCHEDULER                            │
│                    │                                 │
│                 QUEUE                                │
│                                                      │
├─────────────────────────┬────────────────────────────┤
│ Queue Depth             │ GPU Utilization            │
│                         │                            │
│        GRAPH            │           GRAPH            │
├─────────────────────────┼────────────────────────────┤
│ Latency                 │ Cost                       │
│                         │                            │
│        GRAPH            │           GRAPH            │
└─────────────────────────┴────────────────────────────┘
```

The dashboard should be information-rich without becoming visually cluttered.

---

# 6. Three.js Infrastructure Visualization

Three.js should be used to create a **3D GPU infrastructure scene**.

Conceptually:

```text
                         USERS
                           │
                           ▼
                     API GATEWAY
                           │
                           ▼
                       QUEUE
                           │
                           ▼
                      SCHEDULER
                    ╱      │      ╲
                   ╱       │       ╲
                  ▼        ▼        ▼
               GPU #1    GPU #2    GPU #3
```

But the actual interface should represent this as a dynamic 3D scene.

---

# 7. 3D GPU Nodes

Each GPU should be represented as a 3D object.

Display:

```text
GPU #01
● ACTIVE
Model
Qwen 7B
Adapter
coding-v2
VRAM
78%
GPU
84%
Lease
14:32
```

The visual appearance should change according to state.

### OFF

Dim/inactive.

### PROVISIONING

Animated construction/loading state.

### READY

Stable active state.

### BUSY

Increased activity.

### HIGH UTILIZATION

More intense visual activity.

### ERROR

Distinct error state.

### TERMINATING

Shutdown animation.

---

# 8. 3D Request Flow

Requests should visually travel through:

```text
User
 ↓
Gateway
 ↓
Queue
 ↓
Scheduler
 ↓
GPU
 ↓
Model
 ↓
Response
```

Requests can be represented by moving particles or lightweight 3D objects.

The animation should communicate:

- traffic volume
- request direction
- successful requests
- failed requests
- routing
- GPU selection

The 3D scene should consume **real backend state**.

It must not be a decorative animation disconnected from QueueLLM.

---

# 9. 3D GPU Lifecycle

When a GPU is provisioned:

```text
OFF
 ↓
PROVISIONING
 ↓
BOOTING
 ↓
CONNECTING
 ↓
LOADING MODEL
 ↓
READY
```

Anime.js should orchestrate complex lifecycle sequences.

Motion should handle ordinary React state transitions around the 3D scene.

---

# 10. WebGL Fallback

Three.js must not become a single point of failure.

If WebGL is unavailable:

```text
3D unavailable
Switching to 2D infrastructure view...
```

The application should provide a 2D representation of:

- queue
- scheduler
- GPUs
- active jobs
- request flow

Three.js provides WebGL capability detection that can be used for this fallback.

---

# 11. Dark Mode Toggle

Implement a proper dark/light mode toggle.

Default:

**Dark mode.**

The toggle should have a smooth visual transition.

Requirements:

- remember user preference
- respect system preference on first visit
- update charts
- update 3D scene
- update UI surfaces
- update text contrast
- avoid flashing the wrong theme during initial load

Bklit charts support separate light/dark CSS-variable theming, making the chart layer compatible with this requirement.

---

# 12. Cookie Banner

Add a simple cookie/privacy banner.

It should be intentionally minimal.

Example:

```text
🍪
We use cookies to improve QueueLLM
and understand product usage.
[Accept] [Preferences]
```

Requirements:

- non-intrusive
- mobile-friendly
- dismissible
- persists decision
- does not cover important controls

---

# 13. Site Search

Implement global search.

Keyboard shortcut:

```text
Ctrl + K
```

Search should cover:

- jobs
- models
- adapters
- GPUs
- deployments
- logs
- users/projects
- settings

Example:

```text
Search QueueLLM...
⌘K
Jobs
  job_1932
Models
  Qwen 7B
Adapters
  coding-v2
GPUs
  GPU #02
Logs
  Request timeout
```

Results should animate into the command palette.

---

# 14. Back to Top Button

Implement a floating **↑ Top** button.

Behavior:

- hidden near top
- appears after scrolling
- smooth scroll to top
- animated entrance/exit
- mobile-friendly

Use Motion for visibility and transition behavior.

---

# 15. Mobile Menus

The desktop sidebar should become a mobile navigation drawer.

Mobile:

```text
┌─────────────────────────┐
│ QueueLLM            ☰   │
├─────────────────────────┤
│                         │
│ Dashboard               │
│ Queue                   │
│ GPU Fleet               │
│ Inference               │
│ Training                │
│ Models                  │
│ Adapters                │
│ Metrics                 │
│ Logs                    │
│ Costs                   │
│ Settings                │
│                         │
└─────────────────────────┘
```

The menu should:

- slide in smoothly
- trap focus appropriately
- close when navigation occurs
- close via overlay
- support Escape
- work across mobile widths

---

# 16. Loading Animations

Every asynchronous operation needs an intentional loading state.

Examples:

### Dashboard

Skeleton KPI cards + chart loading.

### Queue

Animated queue placeholders.

### GPU

Animated GPU state.

### Logs

Streaming skeleton.

### Deployment

Progressive lifecycle.

### Model

Model loading state.

Bklit components should be used for chart loading states where appropriate. Bklit's chart system includes shimmer loading states and reduced-motion-aware loading behavior.

---

# 17. Hover States

Every interactive component must have an intentional hover state.

Components include:

- buttons
- cards
- GPU nodes
- queue entries
- table rows
- charts
- navigation
- logs
- model cards
- adapter cards

Hover should communicate hierarchy rather than simply changing color.

Possible effects:

- elevation
- slight movement
- expansion
- glow
- contextual information
- connected-node highlighting

Use Motion for these interactions.

---

# 18. Scroll Progress Bars

Long pages should display a scroll progress indicator.

Examples:

- Model details
- Deployment details
- Training run
- Evaluation report
- Documentation
- Logs analysis

The progress bar should respond continuously to scroll position.

Motion provides scroll-related motion values and hooks for this type of interaction.

---

# 19. Copy Button

Implement reusable copy buttons throughout the application.

Use cases:

- Job ID
- Request ID
- Trace ID
- API key
- model name
- adapter name
- command
- configuration
- generated output
- logs

State:

```text
Copy
 ↓
Copied ✓
```

The transition should be animated.

---

# 20. Print Stylesheet

Add a dedicated print stylesheet.

Printable views:

- job report
- deployment report
- evaluation report
- metrics report
- cost report
- experiment results

The print version should:

- hide navigation
- hide interactive controls
- hide 3D scene
- preserve important charts
- preserve tables
- preserve timestamps
- include QueueLLM branding
- include last updated date

---

# 21. Sticky Headers

Important sections should use sticky headers.

Examples:

### Logs

```text
Search | Filters | Export
─────────────────────────
logs...
```

### Queue

```text
Queue | Filters | Scheduler
─────────────────────────
jobs...
```

### Model

```text
Model | Metrics | Versions | Adapters
──────────────────────────────────────
content...
```

Sticky headers should remain visually lightweight.

---

# 22. Skip to Content

Add an accessibility-first:

**Skip to content ↓**

control.

It should become visible when focused via keyboard.

The first focusable interaction should allow keyboard users to bypass navigation.

---

# 23. Password Visibility Toggle

All password/API-secret inputs requiring hidden values should support:

```text
••••••••••••   👁
```

Toggle:

```text
••••••••••••
      ↓
sk_live_abc123
```

The button must have an accessible label.

For API keys, visibility should be temporary and intentional.

---

# 24. UTM Tracking

Support UTM tracking for acquisition and campaign analytics.

Recognize:

```text
utm_source
utm_medium
utm_campaign
utm_term
utm_content
```

Example:

```text
https://queuellm.example?utm_source=github&utm_medium=readme&utm_campaign=launch
```

Persist campaign attribution according to the application's privacy/cookie policy.

Do not expose UTM values unnecessarily in the application UI.

---

# 25. Form Success States

Every important form needs an explicit success state.

Example:

```text
✓ Deployment Created
Qwen 7B is now queued for deployment.
Job:
job_19382
```

The state should animate from the submitted form into the confirmation state.

Use Motion for the component transition.

---

# 26. Form Error States

Errors should be contextual.

Bad:

```text
Something went wrong.
```

Better:

```text
GPU requirement cannot be satisfied.
Required:
24 GB VRAM
Available:
16 GB
Try selecting an A10G or larger GPU.
```

Error states should:

- appear near the relevant field
- preserve user input
- clearly explain the problem
- provide recovery actions
- animate subtly

Do not use aggressive error animations.

---

# 27. Confirmation Modals

Use confirmation modals for destructive actions.

Examples:

### Terminate GPU

```text
Terminate GPU?
GPU #03 is currently running Qwen 7B.
The active lease will be terminated.
[Cancel] [Terminate GPU]
```

### Cancel Job

```text
Cancel job_1932?
This will remove the job from the queue.
[Keep Job] [Cancel Job]
```

### Delete Adapter

Require explicit confirmation.

Motion should handle modal entry/exit.

---

# 28. Last Updated Date

Important dashboards and reports should display:

```text
Last updated:
August 16, 2026 · 05:42 IST
```

For live dashboards:

```text
● Live
Updated 3 seconds ago
```

For static reports:

```text
Last updated:
August 16, 2026
```

The timestamp should be clearly distinguishable from the actual data timestamp.

---

# 29. Expandable FAQ

Add an FAQ component for:

- GPU leases
- queueing
- model loading
- LoRA adapters
- GPU billing
- runtime limits
- training
- inference
- checkpoints
- GPU termination

Example:

```text
What happens when my GPU lease expires?
                                  +
How does QueueLLM choose a GPU?
                                  +
Can I use my own LoRA adapter?
                                  +
```

Clicking an item expands its answer with a smooth Motion layout transition.

---

# 30. Floating Contact Button

Provide a floating contact/help button.

Example:

```text
                         ┌───────┐
                         │  ?    │
                         └───────┘
```

Click opens:

```text
Need help?
Documentation
Report an issue
Contact support
```

The button should:

- remain accessible
- avoid covering important controls
- reposition on mobile
- hide when conflicting with dialogs/modals

---

# 31. Queue Page

The Queue page should be one of the most important screens.

Display:

```text
INFERENCE QUEUE
#1  Qwen + Coding       3m
#2  Llama + RAG         5m
#3  YOU                 7m
#4  Qwen + SQL          8m
```

Each row should show:

- position
- user/project
- model
- adapter
- priority
- estimated runtime
- estimated wait
- resource requirement
- status

Rows should animate when their position changes.

---

# 32. Active Job View

When a job becomes active:

```text
GPU ACTIVE
Qwen 7B
coding-v2
GPU Utilization
██████████████░░ 82%
VRAM
████████████░░░░ 71%
KV Cache
3.1 GB
Tokens Generated
14,281
Tokens/sec
47.8
TTFT
184ms
Lease
14:21 remaining
```

Include:

- stop button
- logs
- metrics
- request stream
- trace
- GPU information

---

# 33. GPU Fleet Page

The GPU fleet should visually represent:

```text
GPU #01
● BUSY
GPU #02
● READY
GPU #03
◌ PROVISIONING
GPU #04
○ OFF
```

Use 3D visualization as the primary visual layer.

Provide a 2D/table view for detailed inspection.

---

# 34. Scheduler Decision UI

One of QueueLLM's most important differentiators should be visible in the frontend.

For a selected job:

```text
Why was GPU #02 selected?
✓ Qwen already loaded
✓ Coding-v2 already loaded
✓ 10 GB VRAM available
✓ Expected runtime fits lease
✓ Lowest switching cost
Score
92 / 100
```

This makes the scheduler explainable.

---

# 35. Metrics Dashboard

Use Bklit UI for the primary data visualization layer.

Metrics:

- queue depth
- wait time
- GPU utilization
- VRAM
- tokens/sec
- TTFT
- P50 latency
- P95 latency
- P99 latency
- cost
- model load time
- adapter load time

Bklit supports interactive charts with tooltips, hover behavior and smooth updates, making it suitable for these live observability screens.

---

# 36. Recommended Chart Mapping

| QueueLLM Metric | Visualization |
|---|---|
| Queue depth | Live Line |
| GPU utilization | Area / Line |
| VRAM | Area |
| Cost | Area |
| Provider/model traffic | Bar |
| GPU state | Ring / Gauge |
| Latency distribution | Bar / Scatter |
| P50/P95/P99 | Line |
| Scheduler comparison | Bar |
| Model comparison | Radar |
| GPU fleet distribution | Ring |
| Job states | Pie / Ring |
| Request routing | Sankey where useful |

Bklit provides these chart families and interactive visualization utilities.

---

# 37. Logs UI

The Logs page should resemble a modern infrastructure console.

```text
LIVE LOGS                         ● LIVE
Search logs...
Severity   Service   Model   GPU   Time
INFO      Scheduler  Qwen    GPU2  05:42:01
INFO      Worker     Qwen    GPU2  05:42:02
INFO      vLLM       Qwen    GPU2  05:42:04
WARN      Worker     Qwen    GPU2  05:42:12
```

Features:

- search
- filtering
- live streaming
- expandable entries
- copy
- export
- trace linking
- request linking

---

# 38. Deployment UI

Deployment creation should feel like a guided workflow.

```text
01 Model
   ↓
02 Adapter
   ↓
03 GPU
   ↓
04 Runtime
   ↓
05 Lease
   ↓
06 Review
   ↓
07 Deploy
```

Each step should animate into place.

---

# 39. Training UI

Training should have its own experience.

```text
NEW TRAINING JOB
Base Model
Qwen 7B
Method
QLoRA
Dataset
coding-v3
GPU
A10G
Maximum Runtime
60 minutes
Checkpoint
Every 5 minutes
[ Start Training ]
```

Once started:

```text
TRAINING ACTIVE
Epoch       2 / 3
Loss        0.81
GPU         91%
VRAM        14.8 GB
Time        28:41
Checkpoint  4 minutes ago
```

---

# 40. Model & Adapter UI

Models and adapters should be visually connected.

```text
Qwen 7B
│
├── coding-v2
├── sql-v1
└── support-v3
```

Clicking an adapter should reveal:

- version
- size
- rank
- base model
- training run
- artifact
- usage
- last deployed

---

# 41. Costs UI

Show:

```text
GPU COST
Today
$4.21
This Month
$83.42
Average / Job
$0.19
Idle GPU Cost
$3.12
Inference
$61.32
Training
$22.10
```

Charts should show where GPU spending originates.

---

# 42. Responsive Design

Desktop is the primary experience.

Support:

- 1440p
- 1080p
- laptop
- tablet
- mobile

The interface should not simply shrink.

It should change composition.

---

# 43. Mobile Dashboard

Mobile should prioritize:

```text
System Health
Active Jobs
Queue
GPU Status
Latest Metrics
Alerts
```

The 3D infrastructure view should be simplified for mobile.

The user can switch to the 2D/table representation.

---

# 44. Animation Rules

### Micro interactions

Motion.

### Layout changes

Motion.

### Page transitions

Motion.

### Scroll effects

Motion.

### Complex sequences

Anime.js.

### Chart animation

Bklit UI.

### 3D state transitions

Three.js + Anime.js orchestration where appropriate.

Avoid stacking multiple animation systems on the same element unless there is a clear reason.

---

# 45. Loading Philosophy

The application should never feel frozen.

Every asynchronous action should communicate:

```text
Waiting
 ↓
Processing
 ↓
Success / Error
```

Examples:

```text
Provisioning GPU...
Loading model...
Loading adapter...
Starting runtime...
Health check...
Ready.
```

---

# 46. Accessibility

Required:

- keyboard navigation
- visible focus states
- skip-to-content
- semantic buttons
- accessible labels
- modal focus management
- reduced-motion support
- sufficient contrast
- screen-reader-compatible status messages
- keyboard-accessible charts where possible

Motion provides a reduced-motion hook that should be used for animation-sensitive experiences.

---

# 47. Reduced Motion

When the user prefers reduced motion:

- disable decorative 3D movement
- minimize page transitions
- remove unnecessary hover motion
- simplify loading animations
- retain functional state changes
- retain essential progress indicators

Charts should also respect reduced-motion behavior where supported. Bklit's loading states explicitly account for `prefers-reduced-motion`.

---

# 48. Performance Requirements

The 3D experience must not make the application unusable.

Requirements:

- lazy-load Three.js scene
- avoid rendering 3D on pages that do not need it
- reduce geometry complexity
- limit particles
- pause inactive animation
- reduce effects on weak devices
- provide 2D fallback
- virtualize long log lists
- avoid unnecessary chart re-renders
- update only changed real-time data

The main dashboard should remain responsive even when the GPU visualization is active.

---

# 49. Real-Time UI

The frontend should react to backend events such as:

```text
JOB_QUEUED
JOB_SCHEDULED
GPU_PROVISIONING
GPU_READY
MODEL_LOADING
MODEL_READY
ADAPTER_LOADING
JOB_STARTED
TOKEN_GENERATED
JOB_COMPLETED
JOB_FAILED
LEASE_WARNING
LEASE_EXPIRED
GPU_TERMINATING
GPU_TERMINATED
```

These events should drive:

- queue movement
- GPU state
- 3D state
- metrics
- notifications
- job status
- logs

---

# 50. Notification System

Provide a notification center.

Examples:

```text
✓ Job completed
⚠ GPU lease expires in 5 minutes
● GPU #03 is ready
✕ Training job failed
✓ Adapter uploaded
```

Notifications should have:

- timestamp
- severity
- related job
- related GPU
- action
- dismissal

---

# 51. Error Recovery

The frontend should always provide a recovery action.

Examples:

```text
GPU provisioning failed.
[Retry]
[Change GPU]
[Cancel Job]
```

```text
Model could not fit in VRAM.
Required: 18 GB
Available: 16 GB
[Choose Larger GPU]
[Enable Quantization]
[Cancel]
```

---

# 52. Print Support

Printable reports should include:

- QueueLLM title
- report title
- last updated date
- relevant metrics
- tables
- charts
- job information
- model information
- timestamps

Exclude:

- sidebar
- navigation
- floating contact button
- interactive controls
- 3D visualization
- animation

---

# 53. Global Polish Requirements

Every screen must include, where relevant:

- loading state
- empty state
- error state
- success state
- hover state
- focus state
- responsive state
- dark/light state

No screen should be implemented as only the "happy path."

---

# 54. Implementation Phases

## Phase 1 — Foundation

- [ ] Establish global visual system.
- [ ] Implement dark/light mode.
- [ ] Implement navigation.
- [ ] Implement mobile menu.
- [ ] Implement command search.
- [ ] Implement responsive shell.
- [ ] Implement accessibility foundations.
- [ ] Implement cookie banner.
- [ ] Implement UTM handling.

## Phase 2 — Dashboard

- [ ] Main dashboard.
- [ ] KPI cards.
- [ ] Bklit charts.
- [ ] Live metrics.
- [ ] Loading states.
- [ ] Error states.
- [ ] Success states.
- [ ] Scroll progress.
- [ ] Sticky headers.

## Phase 3 — Three.js Infrastructure

- [ ] WebGL detection.
- [ ] 3D GPU scene.
- [ ] GPU nodes.
- [ ] Queue visualization.
- [ ] Scheduler visualization.
- [ ] Request flow.
- [ ] GPU lifecycle.
- [ ] 2D fallback.
- [ ] Mobile simplification.

## Phase 4 — Queue & Jobs

- [ ] Queue page.
- [ ] Job cards.
- [ ] Queue position animation.
- [ ] Estimated wait.
- [ ] Active job page.
- [ ] Lease visualization.
- [ ] Job cancellation.
- [ ] Confirmation modals.

## Phase 5 — GPU Fleet

- [ ] GPU dashboard.
- [ ] GPU details.
- [ ] GPU metrics.
- [ ] 3D interaction.
- [ ] Scheduler decisions.
- [ ] Provisioning lifecycle.

## Phase 6 — Observability

- [ ] Logs.
- [ ] Live logs.
- [ ] Trace view.
- [ ] Metrics.
- [ ] Cost dashboard.
- [ ] Copy controls.
- [ ] Export controls.

## Phase 7 — Model / Training

- [ ] Model registry.
- [ ] Adapter registry.
- [ ] Deployment flow.
- [ ] Training flow.
- [ ] Checkpoint view.
- [ ] Evaluation view.

## Phase 8 — UX Polish

- [ ] Hover states.
- [ ] Micro-interactions.
- [ ] Page transitions.
- [ ] Loading animations.
- [ ] FAQ.
- [ ] Floating contact.
- [ ] Back-to-top.
- [ ] Print stylesheet.
- [ ] Final mobile optimization.
- [ ] Reduced-motion testing.

---

# 55. Definition of Done

## Navigation & Utility

- [ ] Dark mode toggle.
- [ ] Cookie banner.
- [ ] Site search.
- [ ] Back-to-top button.
- [ ] Mobile navigation.
- [ ] Scroll progress.
- [ ] Copy buttons.
- [ ] Sticky headers.
- [ ] Skip-to-content.
- [ ] Password visibility toggle.
- [ ] UTM tracking.
- [ ] Last updated timestamps.
- [ ] Floating contact.
- [ ] Expandable FAQ.

## Forms

- [ ] Loading states.
- [ ] Success states.
- [ ] Error states.
- [ ] Confirmation modals.
- [ ] Destructive-action confirmation.

## 3D

- [ ] Three.js infrastructure scene.
- [ ] GPU visualization.
- [ ] Queue visualization.
- [ ] Scheduler visualization.
- [ ] Request flow.
- [ ] GPU lifecycle animation.
- [ ] WebGL detection.
- [ ] 2D fallback.
- [ ] Mobile fallback.

## Analytics

- [ ] Queue metrics.
- [ ] GPU metrics.
- [ ] VRAM metrics.
- [ ] Latency metrics.
- [ ] Token metrics.
- [ ] Cost metrics.
- [ ] Scheduler metrics.
- [ ] Model metrics.
- [ ] Bklit charts.
- [ ] Interactive chart states.

## Observability

- [ ] Live logs.
- [ ] Log filtering.
- [ ] Log expansion.
- [ ] Copy.
- [ ] Export.
- [ ] Trace navigation.
- [ ] Request/job linking.

## Accessibility

- [ ] Keyboard navigation.
- [ ] Focus states.
- [ ] Skip-to-content.
- [ ] Reduced-motion mode.
- [ ] Accessible modals.
- [ ] Accessible labels.
- [ ] Mobile accessibility.

## Production UX

- [ ] Print stylesheet.
- [ ] Responsive layouts.
- [ ] Loading/empty/error/success states.
- [ ] Real-time state updates.
- [ ] Performance optimization.
- [ ] 3D graceful degradation.

---

# 56. Final Experience

The finished QueueLLM frontend should communicate this immediately:

```text
                    QueueLLM
          EPHEMERAL GPU LLM INFRASTRUCTURE
                         │
                         ▼
                    ┌─────────┐
                    │  QUEUE  │
                    └────┬────┘
                         │
                         ▼
                   ┌───────────┐
                   │ SCHEDULER │
                   └─────┬─────┘
                         │
             ┌───────────┼───────────┐
             ▼           ▼           ▼
          GPU #1       GPU #2      GPU #3
           BUSY         READY       OFF
             │
             ▼
          QWEN 7B
             +
         CODING-V2
             │
             ▼
          INFERENCE
             │
             ▼
        LEASE: 14:32
```

The user should be able to **see the infrastructure working**, not merely read about it.

The strongest visual differentiator should therefore be:

> **Three.js makes the infrastructure visible. Motion makes the interface responsive. Anime.js makes system-level events feel alive. Bklit makes the telemetry understandable. Kokonut UI provides the application surface around it.**

The result should feel like a **real AI infrastructure control room**, while remaining fast, accessible, responsive and usable even when the 3D experience is disabled.
