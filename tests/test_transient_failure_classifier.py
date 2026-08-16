"""Regression tests for TaskExecutor._is_transient_failure — the gate on the
retry loop in orchestration/executor.py::execute_task.

The marker list originally held only the "-1"/4294967295 process-kill exit
codes. Upstream gateway timeouts exit *1* and so were classified permanent,
which meant the fully-built retry loop never engaged for them: three QueueLLM
frontend missions were written off on the first attempt (INTELLIGENCE, LEITER
and TANNER respectively) by a 504 the provider itself had flagged
`"isRetryable":true`.

The negative cases matter as much as the positive ones. A classifier that is
too eager turns a genuine failure — bad auth, a task that really did run past
its deadline — into a silent 3x retry loop that burns tokens and still fails.
"""

from __future__ import annotations

import pytest

from cressida.orchestration.executor import TaskExecutor


# Verbatim from missions/20260817-queuellm-frontend-02 and -03 logs.
KILO_IDLE_TIMEOUT = (
    "Kilo Code CLI exited 1 for role INTELLIGENCE.\n"
    "stderr: Error: Upstream idle timeout exceeded"
)
OPENROUTER_504_BODY = (
    'OpenCode CLI exited 1 for role TANNER.\nstderr: '
    '{"code":504,"message":"Upstream idle timeout exceeded",'
    '"metadata":{"error_type":"timeout"},"isRetryable":true}'
)


@pytest.mark.parametrize(
    "error",
    [
        pytest.param(KILO_IDLE_TIMEOUT, id="kilocode-idle-timeout"),
        pytest.param(OPENROUTER_504_BODY, id="openrouter-504-isretryable"),
        pytest.param("Claude CLI exited -1 for role Q.", id="process-kill-minus-1"),
        pytest.param("Claude CLI exited 4294967295 for role BRANCH.", id="windows-0xFFFFFFFF"),
        pytest.param("Error: socket hang up", id="socket-hang-up"),
        pytest.param("read ECONNRESET", id="econnreset"),
        pytest.param("502 Bad Gateway", id="502"),
        pytest.param("503 Service Unavailable", id="503"),
    ],
)
def test_environmental_failures_are_transient(error: str) -> None:
    assert TaskExecutor._is_transient_failure(error) is True


@pytest.mark.parametrize(
    "error",
    [
        # The task genuinely outran cressida.yaml's task_timeout_seconds. Retrying
        # just spends the same budget again — this is why a bare "timeout" is
        # deliberately not in the marker list.
        pytest.param("task_timeout_seconds exceeded: timeout after 3600s", id="legit-task-timeout"),
        # Credentials, not transport. Retrying loops until the cap, every time.
        pytest.param(
            "Failed to authenticate: OAuth session expired and could not be refreshed",
            id="expired-oauth",
        ),
        pytest.param("OpenCode CLI exited 1 ... Unexpected server error.", id="opencode-no-credentials"),
        # Logic failures from the executor's own output guards.
        pytest.param("Task research produced no usable declared outputs", id="no-usable-output"),
        pytest.param("No agent registered for role: BRANCH", id="registry-miss"),
    ],
)
def test_permanent_failures_are_not_transient(error: str) -> None:
    assert TaskExecutor._is_transient_failure(error) is False


def test_classification_is_case_insensitive() -> None:
    assert TaskExecutor._is_transient_failure("UPSTREAM IDLE TIMEOUT EXCEEDED") is True


def test_bare_exit_1_alone_is_not_transient() -> None:
    """`exited 1` is the ordinary CLI failure code and carries no information
    about *why*. Only the accompanying gateway signature makes it retryable."""
    assert TaskExecutor._is_transient_failure("Kilo Code CLI exited 1 for role Q.") is False
