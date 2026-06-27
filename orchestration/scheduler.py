from __future__ import annotations

from typing import Any

from .dependency_graph import DependencyGraph


class ScheduleResult:
    def __init__(
        self,
        order: list[str],
        parallel_batches: list[list[str]],
        critical_path: list[str],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.order = order
        self.parallel_batches = parallel_batches
        self.critical_path = critical_path
        self.metadata = metadata or {}

    @property
    def estimated_duration(self) -> float:
        return self.metadata.get("estimated_duration", 0.0)

    @property
    def parallelization_ratio(self) -> float:
        total = len(self.order)
        if total <= 1:
            return 0.0
        batches = len(self.parallel_batches)
        return 1.0 - (batches / total) if total > 0 else 0.0


class Scheduler:
    def __init__(self, graph: DependencyGraph) -> None:
        self._graph = graph

    def compute_schedule(self) -> ScheduleResult:
        order = self._graph.topological_sort()
        batches = self._graph.get_parallel_batches()
        critical_path = self._compute_critical_path()
        return ScheduleResult(
            order=order,
            parallel_batches=batches,
            critical_path=critical_path,
            metadata={
                "total_tasks": len(order),
                "total_batches": len(batches),
                "parallel_batches": sum(1 for b in batches if len(b) > 1),
            },
        )

    def _compute_critical_path(self) -> list[str]:
        dist: dict[str, float] = {}
        predecessor: dict[str, str | None] = {}

        for node in self._graph.topological_sort():
            dist[node] = dist.get(node, 0.0)
            for dep in self._graph.get_dependents(node):
                weight = self._graph.nodes.get(dep, {}).get("weight", 1.0)
                if dist.get(dep, 0.0) < dist[node] + weight:
                    dist[dep] = dist[node] + weight
                    predecessor[dep] = node

        if not dist:
            return []

        end_node = max(dist, key=lambda k: dist[k])
        path: list[str] = []
        current: str | None = end_node
        while current is not None:
            path.append(current)
            current = predecessor.get(current)
        path.reverse()
        return path

    def get_next_batch(self, completed: set[str]) -> list[str]:
        return self._graph.get_ready_nodes(completed)
