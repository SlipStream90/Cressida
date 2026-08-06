# No-code automation pipeline tool — design notes

**This is a separate product, only inspired by Cressida — not a Cressida
feature and not built into this repo.** Captured here because the design
grew out of a conversation about Cressida's mission-graph internals, but the
tool itself is standalone.

## Origin

Cressida's `Coordinator`/`DependencyGraph`/`Scheduler`/`TaskExecutor`
already operate on a fully generic task graph: `MissionState.tasks` is a
dict of `Task(id, agent, depends_on, metadata)` nodes, and nothing in the
execution path is specific to Cressida's fixed 7-phase template (research →
methodology → product definition → architecture → BOND gate → planning →
implementation → review, hardcoded in `cli/commands.py`). That observation
is the seed for this tool: a pipeline engine doesn't need new execution
machinery, it needs a way to build a task graph from user-authored config
instead of a hardcoded Python function — same shape, different source.

The pipeline tool takes that idea and runs with it as its own thing, with a
visual layer for **observation only** (watching a running pipeline), not for
authoring — authoring stays declarative/config-driven.

## Node types

**Agent nodes** — run an LLM agent against a prompt, same as Cressida's
existing task shape:

```yaml
- id: architecture
  type: agent
  agent: Q
  depends_on: [research]
  run_if: "{{trivial}} == false"
  prompt: "..."
```

**Tool nodes** — call a tool directly, no LLM in the loop:

```yaml
- id: notify_slack
  type: tool
  tool: mcp__slack__post_message
  args: {channel: "#builds", text: "Mission {{mission_id}} done"}
  depends_on: [review]
```

Tool nodes are what let a pipeline talk to *external* no-code builders
(Gemini Agent Builder, Zapier, Make, n8n, ...) — not via a bespoke SDK
integration per service, but via one generic `http_call(url, method,
headers, json_body)` tool (mirroring the existing `_fetch_url` pattern in
`core/tools/implementations.py`, but POST-capable and header-aware). Auth
secrets are resolved from env vars at execute time, never stored in the
pipeline YAML.

## Conditions

`run_if` / `skip_if` on a node use a small comparator language, not
`eval()`: `{{var}} == literal`, `!=`, boolean checks, resolved against
node outputs and pipeline metadata. Same trust level as Cressida's existing
`trivial` flag — no arbitrary expression execution.

## Open safety question

Tool nodes bypass the equivalent of Cressida's BOND gate (the step where an
agent's tool requests get reviewed before they reach the mission
subprocess). For an automation pipeline that's the point — but it also means
the pipeline author, not a review agent, is the trust boundary. Candidate
mitigation: run tool-node calls through the same dangerous-keyword filter
Cressida applies to BOND-approved tools (`core/providers/claude_cli_agent.py`),
so a tool node can't casually call something destructive.

## Status

Design only — nothing built yet.
