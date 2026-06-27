from __future__ import annotations

import json
import os
import subprocess
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


# ── Sentinel exceptions ──────────────────────────────────────────────────────

class PhaseRejectedError(Exception):
    """Raised by BOND's reject_phase tool — propagates through the executor to fail the gate task."""


class PhaseEscalatedError(Exception):
    """Raised by BOND's escalate tool — writes escalation file then blocks like a rejection."""


# ── Tool implementations ─────────────────────────────────────────────────────

def _read_file(path: str, mission_id: str = "") -> str:
    candidates = [Path(path)]
    if mission_id:
        candidates.insert(0, Path("missions") / mission_id / path)
    for p in candidates:
        if p.exists() and p.is_file():
            try:
                return p.read_text(encoding="utf-8")
            except Exception as exc:
                return f"ERROR reading {p}: {exc}"
    return f"File not found: {path}"


def _write_file(path: str, content: str, mission_id: str = "") -> str:
    p = Path(path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"Written {len(content)} chars to {p}"
    except Exception as exc:
        return f"ERROR writing {p}: {exc}"


def _list_dir(path: str, mission_id: str = "") -> str:
    candidates = [Path(path)]
    if mission_id:
        candidates.insert(0, Path("missions") / mission_id / path)
    for p in candidates:
        if p.exists() and p.is_dir():
            entries = sorted(p.iterdir())
            lines = [f"{'/' if e.is_dir() else ' '} {e.name}" for e in entries]
            return f"{p}/\n" + "\n".join(lines)
    return f"Directory not found: {path}"


def _web_search(query: str, num_results: int = 5, mission_id: str = "") -> str:
    api_key = os.environ.get("BRAVE_API_KEY", "")
    if api_key:
        try:
            encoded = urllib.parse.quote(query)
            url = f"https://api.search.brave.com/res/v1/web/search?q={encoded}&count={min(num_results, 10)}"
            req = urllib.request.Request(
                url,
                headers={"Accept": "application/json", "X-Subscription-Token": api_key},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            results = data.get("web", {}).get("results", [])[:num_results]
            parts = [f"**{r.get('title','')}**\n{r.get('url','')}\n{r.get('description','')}" for r in results]
            return "\n\n".join(parts) or "No results."
        except Exception as exc:
            return f"Brave Search error: {exc}"

    # DuckDuckGo HTML fallback — no API key needed
    try:
        import re
        encoded = urllib.parse.quote(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
        titles = re.findall(r'class="result__a"[^>]*>([^<]+)<', html)[:num_results]
        snippets = re.findall(r'class="result__snippet"[^>]*>([^<]+)<', html)[:num_results]
        parts = [f"**{t.strip()}**\n{s.strip()}" for t, s in zip(titles, snippets)]
        return "\n\n".join(parts) or f"No results for: {query}"
    except Exception as exc:
        return (
            f"Web search unavailable ({exc}). "
            "Set BRAVE_API_KEY environment variable for reliable web search."
        )


def _run_shell(command: str, cwd: str | None = None, timeout: int = 60, mission_id: str = "") -> str:
    try:
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd or None,
        )
        combined = (proc.stdout + proc.stderr).strip()
        return f"exit={proc.returncode}\n{combined[:4000]}"
    except subprocess.TimeoutExpired:
        return f"Timed out after {timeout}s: {command}"
    except Exception as exc:
        return f"Shell error: {exc}"


def _query_memory(keywords: list[str], task_type: str = "", top_k: int = 5, mission_id: str = "") -> str:
    parts: list[str] = []

    # 1. Internal strategic memory
    try:
        from cressida.memory.retrieval import MemoryRetrieval
        retrieval = MemoryRetrieval()
        results = retrieval.query(
            task_type=task_type,
            keywords=keywords,
            top_k=top_k,
            include_mission_id=mission_id,
        )
        for r in results:
            parts.append(f"[memory:{r.get('source', '?')}]\n{r.get('content', '')[:600]}")
    except Exception:
        pass

    # 2. Obsidian vault (if configured)
    try:
        from cressida.obsidian.bridge import get_bridge
        bridge = get_bridge()
        if bridge:
            query = " ".join(keywords)
            vault_results = bridge.search(query, max_results=top_k)
            for r in vault_results:
                parts.append(
                    f"[vault:{r['path']}]\n**{r['title']}**\n{r['excerpt']}"
                )
    except Exception:
        pass

    if not parts:
        return "No relevant memory or vault notes found."
    return "\n\n---\n\n".join(parts)


def _approve_phase(
    phase: str,
    confidence: float,
    rationale: str,
    conditions: list[str] | None = None,
    mission_id: str = "",
) -> str:
    record: dict[str, Any] = {
        "decision": "APPROVED",
        "phase": phase,
        "confidence": confidence,
        "rationale": rationale,
        "conditions": conditions or [],
        "timestamp": datetime.now().isoformat(),
    }
    if mission_id:
        p = Path("missions") / mission_id / "bond_decisions" / f"approve_{phase}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(record, indent=2), encoding="utf-8")
    # Also persist to strategic memory
    try:
        from cressida.memory.strategic import StrategicMemory
        mem = StrategicMemory()
        mem.record_decision(
            decision_id=f"bond_approve_{phase}_{mission_id}",
            title=f"BOND approved phase: {phase}",
            description=rationale,
            alternatives=[],
            chosen="APPROVE",
            rationale=rationale,
            author="BOND",
            tags=["bond", "approval", phase, mission_id],
        )
    except Exception:
        pass
    cond_note = f" Conditions: {conditions}" if conditions else ""
    return f"APPROVED phase='{phase}' confidence={confidence:.2f}.{cond_note} {rationale}"


def _reject_phase(
    phase: str,
    reason: str,
    required_corrections: list[str] | None = None,
    mission_id: str = "",
) -> str:
    record: dict[str, Any] = {
        "decision": "REJECTED",
        "phase": phase,
        "reason": reason,
        "required_corrections": required_corrections or [],
        "timestamp": datetime.now().isoformat(),
    }
    if mission_id:
        p = Path("missions") / mission_id / "bond_decisions" / f"reject_{phase}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(record, indent=2), encoding="utf-8")
    raise PhaseRejectedError(
        f"BOND rejected phase='{phase}': {reason}. "
        f"Required corrections: {required_corrections or []}"
    )


def _escalate(
    issue: str,
    context: str,
    recommended_action: str = "",
    mission_id: str = "",
) -> str:
    record: dict[str, Any] = {
        "type": "ESCALATION",
        "issue": issue,
        "context": context,
        "recommended_action": recommended_action,
        "created_at": datetime.now().isoformat(),
        "status": "PENDING",
        "resolve_instructions": (
            f"To unblock this mission, create the file: "
            f"missions/{mission_id}/escalations/resolution.json "
            f'with content {{"resolved": true, "action": "<your decision>"}}'
        ),
    }
    if mission_id:
        esc_dir = Path("missions") / mission_id / "escalations"
        esc_dir.mkdir(parents=True, exist_ok=True)
        fname = f"escalation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        (esc_dir / fname).write_text(json.dumps(record, indent=2), encoding="utf-8")
    raise PhaseEscalatedError(
        f"BOND escalated to CRESSIDA COMMAND: {issue}. "
        f"See missions/{mission_id}/escalations/ to resolve."
    )


# ── Dispatch table ───────────────────────────────────────────────────────────

_IMPLEMENTATIONS: dict[str, Any] = {
    "read_file":    _read_file,
    "write_file":   _write_file,
    "list_dir":     _list_dir,
    "web_search":   _web_search,
    "run_shell":    _run_shell,
    "query_memory": _query_memory,
    "approve_phase": _approve_phase,
    "reject_phase": _reject_phase,
    "escalate":     _escalate,
}


def execute_tool(name: str, inputs: dict[str, Any], mission_id: str = "") -> str:
    """Dispatch a tool call from the LLM agentic loop.

    PhaseRejectedError and PhaseEscalatedError are intentionally NOT caught here —
    they must propagate through LLMAgent.execute() to the TaskExecutor so the
    gate task is correctly marked FAILED (blocking all downstream tasks).
    """
    impl = _IMPLEMENTATIONS.get(name)
    if impl is None:
        return f"Unknown tool: '{name}'. Available: {list(_IMPLEMENTATIONS)}"
    return impl(**inputs, mission_id=mission_id)
