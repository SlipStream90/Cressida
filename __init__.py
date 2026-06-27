"""
CRESSIDA — Autonomous Multi-Agent Software Engineering Intelligence Framework
"""

__version__ = "0.1.0"

from cressida.core import (
    AgentAssignment,
    AgentMessage,
    AgentRole,
    ArchitectureDecision,
    EvaluationRecord,
    MissionState,
    MissionStatus,
    Priority,
    RLHFRecord,
    ReviewReport,
    Task,
    TaskStatus,
)
from cressida.memory.system import MemorySystem
from cressida.orchestration.coordinator import Coordinator
from cressida.orchestration.dependency_graph import DependencyGraph
from cressida.orchestration.executor import TaskExecutor
from cressida.orchestration.router import TaskRouter
from cressida.orchestration.scheduler import Scheduler
from cressida.state import MissionStateModel, ExecutionState, AgentState, SharedState

__all__ = [
    "AgentAssignment",
    "AgentMessage",
    "AgentRole",
    "ArchitectureDecision",
    "EvaluationRecord",
    "MissionState",
    "MissionStatus",
    "Priority",
    "RLHFRecord",
    "ReviewReport",
    "Task",
    "TaskStatus",
    "MemorySystem",
    "Coordinator",
    "DependencyGraph",
    "TaskExecutor",
    "TaskRouter",
    "Scheduler",
    "MissionStateModel",
    "ExecutionState",
    "AgentState",
    "SharedState",
]
