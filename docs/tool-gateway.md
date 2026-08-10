# Tool Gateway — implementation plan

Adding external services (web search via Firecrawl, image generation via
fal.ai, text-to-speech via OpenAI, cloud browser automation via Browser Use)
as tools agents can call, in the style of "Hermes"-style gateways: a small
set of named external capabilities, requestable through the same governance
path as everything else, not a bespoke integration per service.

## Where this fits — the key finding

CRESSIDA already has a generic path for exactly this, so the gateway is not
new infrastructure — it's four functions dropped into two existing
mechanisms.

**1. `core/tools/` (direct-API providers: anthropic/openai/gemini/groq)**
Flat dispatch table, no base class:
- `core/tools/definitions.py` — Claude-format JSON schemas, one per tool, plus
  a `_ROLE_TOOLS: dict[role, list[schema]]` map controlling which agent role
  can see which tool.
- `core/tools/implementations.py` — matching Python functions in an
  `_IMPLEMENTATIONS` dict, dispatched by `execute_tool(name, inputs,
  mission_id)`. Existing `_web_search`/`_fetch_url` are the pattern to copy:
  plain sync functions, stdlib `urllib.request` (no extra dependency),
  errors returned as strings rather than raised, one env var per service
  checked at call time with a clear "unavailable: set X" message if unset.

**2. CRESSIDA's own MCP server (`mcp_server.py`) — claude_cli/opencode agents**
This is the more interesting path, and it's why "Tool Gateway" is cheap here:
- `onboard.py` already registers this server at **user scope** with both
  Claude Code and opencode (`_register_claude`/`_register_opencode`).
- Mission agents that run through the `claude`/`opencode` CLI (not the
  direct-API path) get tool access via `--allowedTools`, built from a fixed
  floor (`claude_cli_agent.py:_ALLOWED_TOOLS`) plus whatever BOND
  dynamically approves for that mission.
- The dynamic-approval pipeline (`0b97f30`, "tiered allowlist and BOND-gated
  dynamic tool grants") is **generic over any `mcp__<server>__<tool>`
  name**: Q requests a tool in `missions/<id>/architecture/
  mcp_tool_requests.json`, BOND independently re-classifies each request and
  records `approved_mcp_tools` in its decision file, `coordinator.py`'s
  `_check_bond_gate()` re-runs `filter_dynamic_tools()` (a hardcoded
  dangerous-keyword denylist — `send`, `delete`, `deploy`, `merge_branch`,
  etc.) as a backstop, and the survivors get appended to `--allowedTools`.
- Since `mcp__cressida__*` isn't in the exclusion list and none of
  `firecrawl_search` / `fal_generate_image` / `openai_tts` /
  `browser_use_run` match a denylisted keyword, **adding four `@mcp.tool()`
  functions to the existing `mcp_server.py` makes them both immediately
  usable standalone (any Claude Code/opencode session, no mission needed)
  and automatically requestable by mission agents through the existing BOND
  flow — with zero changes to `claude_cli_agent.py`, `coordinator.py`, or
  BOND's prompt.**

No new MCP server, no new registration step, no new dependency (all four
services have a plain REST API reachable with stdlib `urllib.request` —
`fal-client`/`firecrawl-py`/`browser-use` SDKs are unnecessary weight for
one call each).

## The four integrations

| Service | Env var | Shape |
|---|---|---|
| Firecrawl (search) | `FIRECRAWL_API_KEY` | `POST https://api.firecrawl.dev/v2/search`, `Authorization: Bearer <key>`, body `{"query", "limit"}` → sync JSON `{"data": {"web": [{"url","title","description"}]}}` |
| fal.ai (image gen) | `FAL_KEY` | `POST https://fal.run/<model>` (e.g. `fal-ai/flux/schnell`), `Authorization: Key <key>`, body `{"prompt"}` → sync JSON, image URL(s) in the response (exact field varies by model — code defensively, don't assume one shape) |
| OpenAI (TTS) | `OPENAI_API_KEY` (reuses the key already used for the `openai` LLM provider, if set) | `POST https://api.openai.com/v1/audio/speech`, `Authorization: Bearer <key>`, body `{"model":"tts-1","voice","input"}` → raw mp3 bytes, write to `cressida_home()/generated/` and return the path |
| Browser Use (cloud browser) | `BROWSER_USE_API_KEY` | `POST https://api.browser-use.com/api/v3/sessions`, header `X-Browser-Use-API-Key`, body `{"task"}` → session id; **asynchronous** — poll `GET .../sessions/<id>` until `status` is `finished`/`failed`/etc. or a timeout elapses |

Firecrawl and Browser Use contracts above are confirmed against current
docs. fal.ai's docs page 429'd during research — the response-field
assumption should be re-verified (or coded defensively against multiple
possible shapes, checking `images[].url` and `image.url`) before relying on
it in production.

## Suggested role wiring (`_ROLE_TOOLS` in `definitions.py`)

- `INTELLIGENCE`, `LEITER`: add `firecrawl_search` alongside the existing
  `web_search` (Firecrawl as the higher-quality option when the key is set,
  `web_search`'s Brave/DuckDuckGo path stays as the keyless fallback).
- `LEITER`: add `browser_use_run` — fits its existing "lives on the open
  internet" role, for pages `fetch_url` can't handle (logins, JS-rendered
  content, multi-step flows).
- `BRANCH`: add `fal_generate_image` and `openai_tts` — asset generation
  during implementation.

Not proposed for `_BASE` (every role) — these are paid, opt-in services;
scoping to the roles that plausibly need them keeps the schema list (and
token cost) down for roles that don't.

## Build sequencing

1. `core/tools/gateway.py` — four functions + a `GATEWAY_IMPLEMENTATIONS`
   dict, matching `implementations.py`'s existing style exactly. Each
   function's own `demo()`/`__main__` check: assert it fails closed with a
   clear message when its env var is unset (no traceback) — the standard
   check for non-trivial logic per this repo's convention.
2. Merge `GATEWAY_IMPLEMENTATIONS` into `implementations.py`'s
   `_IMPLEMENTATIONS`; add the four schemas to `definitions.py` and wire
   them into `_ROLE_TOOLS` per above. This covers the direct-API provider
   path.
3. Add four thin `@mcp.tool()` wrappers to `mcp_server.py` that call the
   same `core/tools/gateway.py` functions — covers the standalone and
   claude_cli/opencode-mission-agent paths.
4. Document the four env vars in `README.md` (the `BRAVE_API_KEY` section
   and the env-var table are the existing pattern to follow) — no config
   file, no loader; this repo's convention is plain env vars, README as the
   source of truth for names.
5. No `pyproject.toml` change needed — no new dependency.

## What this does *not* need

- A new MCP server process, a new registration step in `onboard.py`, or any
  change to the BOND-gating pipeline itself — all of that is already generic
  enough to absorb four more tool names.
- New SDK dependencies — plain HTTP covers all four services for the
  single-call-per-invocation use case here.
