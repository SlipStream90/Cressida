from __future__ import annotations

"""Layer 5 — Self-Monitoring: stall detection + live status server.

StallMonitor:
  Background asyncio task that inspects EventBus history every `check_interval`
  seconds. If a TASK_STARTED event has no corresponding TASK_COMPLETED or
  TASK_FAILED within `stall_threshold` seconds, it publishes a TASK_STALLED
  event and records the failure pattern in strategic memory.

StatusServer:
  Minimal HTTP server (stdlib only, no FastAPI dependency) that serves a live
  status JSON at http://localhost:<port>/status. Also writes missions/status.json
  on every check cycle so the status is accessible without the HTTP server.
"""

import asyncio
import json
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

from cressida.core.events import Event, EventBus, EventType
from cressida.memory.strategic import StrategicMemory


_DEFAULT_STALL_THRESHOLD = 1800.0   # 30 minutes
_DEFAULT_CHECK_INTERVAL  = 60.0     # 1 minute
_DEFAULT_STATUS_PORT     = 7437


class StallMonitor:
    """Detects stalled tasks and publishes TASK_STALLED events."""

    def __init__(
        self,
        event_bus: EventBus,
        memory: StrategicMemory | None = None,
        stall_threshold: float = _DEFAULT_STALL_THRESHOLD,
        check_interval: float = _DEFAULT_CHECK_INTERVAL,
    ) -> None:
        self._bus = event_bus
        self._memory = memory or StrategicMemory()
        self._stall_threshold = stall_threshold
        self._check_interval = check_interval
        self._alerted: set[str] = set()  # task IDs already alerted this session

    async def run(self) -> None:
        print(f"[MONITOR] Stall monitor active (threshold={self._stall_threshold}s, check={self._check_interval}s)")
        while True:
            await asyncio.sleep(self._check_interval)
            try:
                await self._check()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(f"[MONITOR] Check error: {exc}")

    async def _check(self) -> None:
        now = datetime.now()

        started_events = self._bus.get_history(EventType.TASK_STARTED, limit=500)
        completed_ids = {
            e.data.get("task_id")
            for e in self._bus.get_history(EventType.TASK_COMPLETED, limit=500)
        }
        failed_ids = {
            e.data.get("task_id")
            for e in self._bus.get_history(EventType.TASK_FAILED, limit=500)
        }
        resolved_ids = completed_ids | failed_ids

        for event in started_events:
            task_id = event.data.get("task_id", "")
            if not task_id or task_id in resolved_ids or task_id in self._alerted:
                continue
            elapsed = (now - event.timestamp).total_seconds()
            if elapsed >= self._stall_threshold:
                self._alerted.add(task_id)
                mission_id = event.data.get("mission_id", "")
                print(f"[MONITOR] STALL detected: task={task_id} mission={mission_id} elapsed={elapsed:.0f}s")
                await self._bus.publish(Event(
                    type=EventType.TASK_STALLED,
                    data={
                        "task_id": task_id,
                        "mission_id": mission_id,
                        "elapsed_seconds": elapsed,
                        "agent": event.data.get("agent", ""),
                    },
                    source="stall_monitor",
                ))
                self._record_stall_pattern(task_id, mission_id, elapsed)

    def _record_stall_pattern(self, task_id: str, mission_id: str, elapsed: float) -> None:
        try:
            self._memory.record_pattern(
                pattern=f"Task stalled: {task_id}",
                context=f"mission={mission_id}, elapsed={elapsed:.0f}s",
                success=False,
            )
        except Exception:
            pass


class StatusServer:
    """Serves live mission status over HTTP (stdlib, no extra deps).

    GET /status   → JSON with event counts, stall alerts, and active missions
    GET /health   → {"ok": true}
    """

    def __init__(
        self,
        event_bus: EventBus,
        port: int = _DEFAULT_STATUS_PORT,
        status_file: str | Path = "missions/status.json",
    ) -> None:
        self._bus = event_bus
        self._port = port
        self._status_file = Path(status_file)
        self._server: HTTPServer | None = None

    def _build_status(self) -> dict[str, Any]:
        history = self._bus.get_history(limit=1000)
        completed_ids = {e.data.get("task_id") for e in history if e.type == EventType.TASK_COMPLETED}
        failed_ids    = {e.data.get("task_id") for e in history if e.type == EventType.TASK_FAILED}
        started_ids   = {e.data.get("task_id") for e in history if e.type == EventType.TASK_STARTED}
        stalled_ids   = {e.data.get("task_id") for e in history if e.type == EventType.TASK_STALLED}
        mission_ids   = list({e.data.get("mission_id") for e in history if e.data.get("mission_id")})

        return {
            "generated_at": datetime.now().isoformat(),
            "missions": mission_ids,
            "tasks": {
                "started":   len(started_ids),
                "completed": len(completed_ids),
                "failed":    len(failed_ids),
                "stalled":   len(stalled_ids),
                "in_progress": len(started_ids - completed_ids - failed_ids),
            },
            "stalled_task_ids": list(stalled_ids),
            "event_count": len(history),
        }

    def _write_status_file(self, status: dict[str, Any]) -> None:
        try:
            self._status_file.parent.mkdir(parents=True, exist_ok=True)
            self._status_file.write_text(json.dumps(status, indent=2), encoding="utf-8")
        except Exception:
            pass

    async def run(self) -> None:
        """Continuously refresh the status file and optionally serve HTTP."""
        bus = self._bus
        port = self._port
        status_file = self._status_file
        build_fn = self._build_status
        write_fn = self._write_status_file

        class _Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                if self.path == "/health":
                    body = b'{"ok": true}'
                else:
                    body = json.dumps(build_fn(), indent=2).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, fmt: str, *args: Any) -> None:  # suppress access log
                pass

        try:
            server = HTTPServer(("", port), _Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            print(f"[STATUS] HTTP status server running on http://localhost:{port}/status")
        except OSError as exc:
            print(f"[STATUS] Could not bind port {port}: {exc}. Status file only.")
            server = None

        while True:
            await asyncio.sleep(30)
            status = build_fn()
            write_fn(status)
