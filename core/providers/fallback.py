"""Provider failover for missions using automatic provider selection."""

from __future__ import annotations

from typing import Any

from cressida.core import AgentRole, MissionState, Task
from cressida.core.events import EventBus
from cressida.core.interfaces import Agent
from cressida.core.paths import resolve_under_home


class ProviderExecutionError(RuntimeError):
    """Raised when a provider returns without producing usable work."""


class FallbackAgent(Agent):
    """Try a sequence of provider agents until one completes the task.

    Providers are intentionally isolated behind the existing Agent contract:
    a provider may fail because its CLI is unauthenticated, rate-limited,
    unavailable, or changed its output format, and the mission can continue
    with the next configured provider.
    """

    _PROVIDER_NAME = "fallback"

    def __init__(self, role: AgentRole, agents: list[Agent], provider_names: list[str]) -> None:
        self.role = role
        self._agents = agents
        self._provider_names = provider_names

    async def execute(
        self, state: MissionState, task: Task, event_bus: EventBus | None = None,
    ) -> Any:
        failures: list[str] = []
        for index, agent in enumerate(self._agents):
            provider = self._provider_names[index]
            try:
                result = await agent.execute(state, task, event_bus=event_bus)
                if not has_usable_output(state, task, result):
                    remove_empty_outputs(state, task)
                    raise ProviderExecutionError(
                        f"{provider} returned no usable output for task {task.id}"
                    )
                if index:
                    print(f"[provider-fallback] {self.role.value}: recovered with {provider}")
                return result
            except Exception as exc:
                failures.append(f"{provider}: {exc}")
                remove_empty_outputs(state, task)
                if index + 1 < len(self._agents):
                    print(
                        f"[provider-fallback] {self.role.value}: {provider} failed; "
                        f"trying {self._provider_names[index + 1]} ({exc})"
                    )

        raise ProviderExecutionError(
            f"All providers failed for {self.role.value}/{task.id}: "
            + " | ".join(failures)
        )

    async def get_capabilities(self) -> list[str]:
        capabilities: list[str] = []
        for agent in self._agents:
            for capability in await agent.get_capabilities():
                if capability not in capabilities:
                    capabilities.append(capability)
        return capabilities


def has_usable_output(state: MissionState, task: Task, result: Any) -> bool:
    writes = task.metadata.get("writes") or []
    if not writes:
        return bool(str(result or "").strip())

    for raw_path in writes:
        resolved = str(raw_path).replace("<mission_id>", state.mission_id)
        path = resolve_under_home(resolved)
        if path.suffix:
            if path.is_file() and path.stat().st_size > 0:
                continue
            return False

        if not path.is_dir():
            return False
        if not any(child.is_file() and child.stat().st_size > 0 for child in path.rglob("*")):
            return False
    return True


def remove_empty_outputs(state: MissionState, task: Task) -> None:
    """Remove only zero-byte declared artifacts before the next provider."""
    for raw_path in task.metadata.get("writes") or []:
        resolved = str(raw_path).replace("<mission_id>", state.mission_id)
        path = resolve_under_home(resolved)
        candidates = [path] if path.suffix else list(path.rglob("*")) if path.is_dir() else []
        for candidate in candidates:
            try:
                if candidate.is_file() and candidate.stat().st_size == 0:
                    candidate.unlink()
            except OSError:
                pass
