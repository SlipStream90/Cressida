from __future__ import annotations

from cressida.core.types import AgentRole, Task


class RoutingError(Exception):
    pass


TASK_TYPE_ROUTE: dict[str, AgentRole] = {
    "commission": AgentRole.M,
    "dispatch": AgentRole.M,
    "orchestrate": AgentRole.M,
    "agent_selection": AgentRole.M,
    "research": AgentRole.INTELLIGENCE,
    "research_report": AgentRole.INTELLIGENCE,
    "product_definition": AgentRole.INTELLIGENCE,
    "prd": AgentRole.INTELLIGENCE,
    "roadmap": AgentRole.INTELLIGENCE,
    "architecture": AgentRole.Q,
    "api_design": AgentRole.Q,
    "planning": AgentRole.TANNER,
    "task_decomposition": AgentRole.TANNER,
    "dependency_graph": AgentRole.TANNER,
    "backend": AgentRole.BRANCH,
    "api": AgentRole.BRANCH,
    "database": AgentRole.BRANCH,
    "frontend": AgentRole.ROOK,
    "ui": AgentRole.ROOK,
    "component": AgentRole.ROOK,
    "infrastructure": AgentRole.BOOTHROYD,
    "deployment": AgentRole.BOOTHROYD,
    "docker": AgentRole.BOOTHROYD,
    "ci_cd": AgentRole.BOOTHROYD,
    "knowledge": AgentRole.MONEYPENNY,
    "memory": AgentRole.MONEYPENNY,
    "tracking": AgentRole.MONEYPENNY,
    "testing": AgentRole.REVIEW,
    "qa": AgentRole.REVIEW,
    "review": AgentRole.REVIEW,
    "security": AgentRole.REVIEW,
    "code_review": AgentRole.REVIEW,
    "coverage": AgentRole.REVIEW,
}


class TaskRouter:
    def __init__(self) -> None:
        self._routes: dict[str, AgentRole] = dict(TASK_TYPE_ROUTE)

    def route(self, task: Task) -> AgentRole:
        if task.agent is not None:
            return task.agent
        for tag in task.metadata.get("tags", []):
            tag_lower = tag.lower()
            if tag_lower in self._routes:
                return self._routes[tag_lower]
        name_lower = task.name.lower()
        for keyword, role in self._routes.items():
            if keyword in name_lower:
                return role
        description_lower = task.description.lower()
        for keyword, role in self._routes.items():
            if keyword in description_lower:
                return role
        raise RoutingError(f"Cannot route task '{task.id}' ({task.name}): no matching agent")

    def register_route(self, keyword: str, role: AgentRole) -> None:
        self._routes[keyword] = role

    def get_route_for_role(self, role: AgentRole) -> list[str]:
        return [k for k, v in self._routes.items() if v == role]
