from __future__ import annotations

"""Local live dashboard for watching Cressida missions run.

Serves one auto-refreshing HTML page plus a small JSON API, both backed by
``core/progress.py``'s disk-polled mission state — the same source
``mission_status``/``mission_progress`` read via MCP, so the dashboard always
matches what those tools report, just continuously and visually instead of
one request at a time.

No new dependency: stdlib ``http.server`` only, same pattern as
``autonomy/monitor.py``'s StatusServer.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import unquote

from cressida.core.progress import get_all_mission_progress, get_mission_progress

DEFAULT_DASHBOARD_PORT = 7438


_PAGE = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Cressida — Live Missions</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 24px; background: #0f1115; color: #e6e8eb;
    font: 14px/1.5 -apple-system, Segoe UI, sans-serif;
  }
  h1 { font-size: 18px; font-weight: 600; margin: 0 0 4px; }
  .sub { color: #8b93a1; font-size: 12px; margin-bottom: 20px; }
  .mission {
    background: #171a21; border: 1px solid #262b36; border-radius: 8px;
    padding: 14px 16px; margin-bottom: 12px;
  }
  .mission.stalled { border-color: #7a4a1a; }
  .mission.completed { border-color: #1f4d2e; }
  .mission.failed { border-color: #5c1f1f; }
  .head { cursor: pointer; }
  .row { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
  .id { font-weight: 600; }
  .brief { color: #8b93a1; font-size: 12px; margin-top: 3px; max-width: 560px; }
  .phase-line { display: flex; align-items: baseline; gap: 8px; margin-top: 6px; }
  .phase { color: #9db4ff; font-size: 12px; font-weight: 600; }
  .agent-now { color: #ffcf6b; font-size: 12px; }
  .badge {
    font-size: 11px; padding: 2px 8px; border-radius: 10px; background: #262b36; color: #b8c0cc;
    white-space: nowrap;
  }
  .badge.stalled { background: #4a2e0d; color: #ffb96b; }
  .badge.completed { background: #123522; color: #6fdb9a; }
  .badge.failed { background: #3a1414; color: #ff8a8a; }
  .steps { display: flex; gap: 3px; margin-top: 10px; }
  .step { flex: 1; height: 5px; border-radius: 3px; background: #262b36; }
  .step.done { background: #5b7cff; }
  .step.current { background: #ffcf6b; }
  .step-labels { display: flex; justify-content: space-between; font-size: 10px; color: #565d6b; margin-top: 3px; }
  .counts { display: flex; gap: 10px; font-size: 12px; color: #8b93a1; margin-top: 8px; flex-wrap: wrap; }
  .detail { display: none; margin-top: 12px; border-top: 1px solid #262b36; padding-top: 10px; }
  .detail.open { display: block; }
  .detail h4 { margin: 10px 0 4px; font-size: 11px; color: #8b93a1; text-transform: uppercase; letter-spacing: .05em; }
  .task-row, .file-row { display: flex; justify-content: space-between; gap: 10px; font-size: 12px; padding: 3px 0; color: #c7cdd6; border-bottom: 1px solid #1c202a; }
  .task-row:last-child, .file-row:last-child { border-bottom: none; }
  .task-name { color: #8b93a1; }
  .task-status { font-weight: 600; white-space: nowrap; }
  .task-status.completed { color: #6fdb9a; }
  .task-status.failed, .task-status.blocked { color: #ff8a8a; }
  .task-status.in_progress, .task-status.assigned { color: #ffcf6b; }
  .task-status.pending { color: #565d6b; }
  .file-path { color: #c7cdd6; font-family: ui-monospace, Consolas, monospace; }
  .file-meta { color: #565d6b; white-space: nowrap; }
  .escalation, .task-error {
    background: #3a1414; color: #ffb0b0; padding: 8px 10px; border-radius: 6px; font-size: 12px; margin-top: 6px;
  }
  .task-error .task-error-id { color: #ff8a8a; font-weight: 600; }
  .empty { color: #8b93a1; padding: 40px 0; text-align: center; }
  .toggle-hint { color: #565d6b; font-size: 11px; }
</style>
</head>
<body>
  <h1>Cressida — Live Missions</h1>
  <div class="sub" id="meta">loading…</div>
  <div id="missions"></div>

<script>
const open = new Set();

function esc(s) { return (s ?? "").toString().replace(/[&<>]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;"}[c])); }

function fmtAgo(sec) {
  if (sec == null) return "—";
  if (sec < 5) return "just now";
  if (sec < 60) return Math.round(sec) + "s ago";
  if (sec < 3600) return Math.round(sec / 60) + "m ago";
  return (sec / 3600).toFixed(1) + "h ago";
}

function fmtDuration(sec) {
  if (sec == null) return "—";
  const m = Math.floor(sec / 60), h = Math.floor(m / 60);
  if (h > 0) return `${h}h ${m % 60}m`;
  if (m > 0) return `${m}m ${Math.round(sec % 60)}s`;
  return `${Math.round(sec)}s`;
}

function fmtSize(bytes) {
  if (bytes == null) return "";
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / (1024 * 1024)).toFixed(1) + " MB";
}

function statusClass(m) {
  if (m.status === "completed") return "completed";
  if (m.status === "failed") return "failed";
  if (m.stalled) return "stalled";
  return "";
}

function render(missions) {
  const el = document.getElementById("missions");
  document.getElementById("meta").textContent =
    missions.length + " mission(s) · refreshed " + new Date().toLocaleTimeString();

  if (!missions.length) {
    el.innerHTML = '<div class="empty">No missions yet — run one with run_mission.</div>';
    return;
  }

  el.innerHTML = missions.map(m => {
    const cls = statusClass(m);
    const isOpen = open.has(m.mission_id);
    const counts = Object.entries(m.task_counts || {}).map(([k, v]) => `${k}: ${v}`).join("  ·  ");

    const steps = (m.milestones || []).map((ms, i) => {
      const stepCls = ms.reached
        ? (i === (m.phase_index - 1) ? "step current" : "step done")
        : "step";
      return `<div class="${stepCls}" title="${esc(ms.label)}"></div>`;
    }).join("");

    const agentNow = m.current_agent
      ? `<span class="agent-now">→ ${esc(m.current_agent)} working now</span>`
      : "";

    const briefLine = m.brief_preview
      ? `<div class="brief">${esc(m.brief_preview)}</div>`
      : "";

    const tasks = (m.tasks || []).map(t => `
      <div class="task-row">
        <span>${esc(t.id)}<span class="task-name">${t.name ? " — " + esc(t.name) : ""}${t.agent ? " (" + esc(t.agent) + ")" : ""}</span></span>
        <span class="task-status ${esc((t.status||"").toLowerCase())}">${esc(t.status)}</span>
      </div>`
    ).join("") || '<div class="task-row"><span>No tasks recorded yet — still in pre-task research/planning.</span></div>';

    const failedTasks = (m.failed_tasks || []).map(t => `
      <div class="task-error"><span class="task-error-id">${esc(t.id)} (${esc(t.agent)}):</span> ${esc(t.error)}</div>
    `).join("");

    const files = (m.recent_files || []).slice(0, 10).map(f => `
      <div class="file-row">
        <span class="file-path">${esc(f.path)}</span>
        <span class="file-meta">${fmtSize(f.size)} · ${fmtAgo((Date.now()/1000) - f.modified)}</span>
      </div>`
    ).join("") || '<div class="file-row"><span>No files yet</span></div>';

    const escalations = (m.escalations || []).map(e =>
      `<div class="escalation">⚠ Awaiting decision: ${esc(e)}</div>`
    ).join("");

    return `
      <div class="mission ${cls}">
        <div class="head" onclick="toggle('${m.mission_id}')">
          <div class="row">
            <div>
              <span class="id">${esc(m.mission_id)}</span>
              ${briefLine}
            </div>
            <span class="badge ${cls}">${m.stalled ? "STALLED" : esc(m.status)}</span>
          </div>
          <div class="phase-line">
            <span class="phase">${esc(m.phase)}</span>
            ${agentNow}
          </div>
          <div class="steps">${steps}</div>
          <div class="counts">
            <span>${counts || "no tasks yet"}</span>
            <span>running ${fmtDuration(m.elapsed_seconds)}</span>
            <span>last activity ${fmtAgo(m.seconds_since_activity)}</span>
            <span class="toggle-hint">${isOpen ? "▲ click to collapse" : "▼ click for tasks & files"}</span>
          </div>
        </div>
        ${escalations}
        ${failedTasks}
        <div class="detail ${isOpen ? "open" : ""}" id="detail-${m.mission_id}">
          <h4>Tasks (${m.total_tasks || 0})</h4>${tasks}
          <h4>Recent files (${m.file_count || 0} total)</h4>${files}
        </div>
      </div>`;
  }).join("");
}

function toggle(id) {
  if (open.has(id)) open.delete(id); else open.add(id);
  render(window.__lastMissions || []);
}

async function tick() {
  try {
    const res = await fetch("/api/missions");
    const data = await res.json();
    window.__lastMissions = data;
    render(data);
  } catch (e) {
    document.getElementById("meta").textContent = "connection lost — retrying…";
  }
}

tick();
setInterval(tick, 2500);
</script>
</body>
</html>
"""


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path in ("/", "/index.html"):
            self._send(200, _PAGE.encode("utf-8"), "text/html; charset=utf-8")
        elif self.path == "/api/missions":
            data = get_all_mission_progress()
            self._send(200, json.dumps(data).encode(), "application/json")
        elif self.path.startswith("/api/missions/"):
            mission_id = unquote(self.path.split("/api/missions/", 1)[1])
            data = get_mission_progress(mission_id)
            self._send(200, json.dumps(data).encode(), "application/json")
        else:
            self._send(404, b'{"error": "not found"}', "application/json")

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: Any) -> None:  # suppress access log
        pass


def serve_dashboard(port: int = DEFAULT_DASHBOARD_PORT, host: str = "") -> HTTPServer:
    return HTTPServer((host, port), _Handler)


def run_dashboard_blocking(port: int = DEFAULT_DASHBOARD_PORT) -> None:
    """Run the dashboard in the foreground (used by `cressida dashboard`)."""
    server = serve_dashboard(port)
    print(f"[DASHBOARD] Cressida dashboard running at http://localhost:{port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


def start_dashboard_background(port: int = DEFAULT_DASHBOARD_PORT) -> threading.Thread | None:
    """Start the dashboard on a daemon thread. Returns None if the port is
    already taken (e.g. a dashboard is already running) rather than raising —
    callers that start this opportunistically (the MCP server) shouldn't crash
    over it."""
    try:
        server = serve_dashboard(port)
    except OSError as exc:
        print(f"[DASHBOARD] Could not bind port {port}: {exc}")
        return None
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"[DASHBOARD] Cressida dashboard running at http://localhost:{port}/")
    return thread
