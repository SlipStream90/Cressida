# CRESSIDA Documentation

## Overview
CRESSIDA is an autonomous multi-agent software engineering intelligence framework.

## Getting Started
See `agents/` for agent specifications and `core/` for framework primitives.

## Architecture
See `knowledge/architecture.md` for system architecture.

## Extending
- Create new agents in `agents/` as Markdown specs
- Register agent implementations in code via `AgentRegistry`
- Add custom routes via `TaskRouter.register_route()`
