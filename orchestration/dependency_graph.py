from __future__ import annotations

from typing import Any


class CyclicDependencyError(Exception):
    pass


class DependencyGraph:
    def __init__(self) -> None:
        self._nodes: dict[str, dict[str, Any]] = {}
        self._forward: dict[str, list[str]] = {}
        self._reverse: dict[str, list[str]] = {}

    def add_node(self, node_id: str, **metadata: Any) -> None:
        if node_id not in self._nodes:
            self._nodes[node_id] = metadata
            self._forward.setdefault(node_id, [])
            self._reverse.setdefault(node_id, [])

    def add_dependency(self, node: str, depends_on: str) -> None:
        if node not in self._nodes:
            self.add_node(node)
        if depends_on not in self._nodes:
            self.add_node(depends_on)
        if node not in self._forward[depends_on]:
            self._forward[depends_on].append(node)
        if depends_on not in self._reverse[node]:
            self._reverse[node].append(depends_on)

    def remove_node(self, node_id: str) -> None:
        self._nodes.pop(node_id, None)
        self._forward.pop(node_id, None)
        self._reverse.pop(node_id, None)
        for deps in self._forward.values():
            if node_id in deps:
                deps.remove(node_id)
        for rdeps in self._reverse.values():
            if node_id in rdeps:
                rdeps.remove(node_id)

    def get_dependencies(self, node_id: str) -> list[str]:
        return list(self._reverse.get(node_id, []))

    def get_dependents(self, node_id: str) -> list[str]:
        return list(self._forward.get(node_id, []))

    def get_ready_nodes(self, completed: set[str]) -> list[str]:
        ready = []
        for node_id in self._nodes:
            if node_id in completed:
                continue
            deps = set(self._reverse.get(node_id, []))
            if deps.issubset(completed):
                ready.append(node_id)
        return ready

    def topological_sort(self) -> list[str]:
        visited: set[str] = set()
        temp: set[str] = set()
        order: list[str] = []

        def dfs(node: str) -> None:
            if node in temp:
                raise CyclicDependencyError(f"Cycle detected involving node: {node}")
            if node in visited:
                return
            temp.add(node)
            for dep in self._reverse.get(node, []):
                dfs(dep)
            temp.remove(node)
            visited.add(node)
            order.append(node)

        for node in self._nodes:
            if node not in visited:
                dfs(node)

        return order

    def get_parallel_batches(self) -> list[list[str]]:
        completed: set[str] = set()
        batches: list[list[str]] = []

        while len(completed) < len(self._nodes):
            batch = []
            for node_id in self._nodes:
                if node_id in completed:
                    continue
                deps = set(self._reverse.get(node_id, []))
                if deps.issubset(completed):
                    batch.append(node_id)
            if not batch:
                break
            batches.append(batch)
            completed.update(batch)

        return batches

    @property
    def nodes(self) -> dict[str, dict[str, Any]]:
        return dict(self._nodes)

    @property
    def size(self) -> int:
        return len(self._nodes)

    def clear(self) -> None:
        self._nodes.clear()
        self._forward.clear()
        self._reverse.clear()
