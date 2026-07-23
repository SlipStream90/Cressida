from __future__ import annotations

"""Per-agent evolving playbooks — the durable memory that makes agents improve.

Each agent role owns a playbook: a ranked, deduplicated list of learned
heuristics ("when X, do Y", "avoid Z"). The ContextBuilder injects the top
entries into every prompt for that role, so an agent's own accumulated
experience shapes its future behaviour — the core of Hermes-style learning.

Design constraints (aligned with M's token discipline):
- The canonical store is JSON (`<role>.json`) for structured ranking/dedup.
- A human/Obsidian-friendly `<role>.md` mirror is rendered alongside it.
- Prompt injection is *bounded* (top-N by rank) so playbooks never bloat a prompt.
- Entries carry a score and hit-count; reinforcement bumps them, decay/consolidation
  prunes the weak ones. Learning that isn't reused fades.
"""

import json
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any


_MAX_ENTRIES_PER_ROLE = 40      # hard cap kept on disk after consolidation
_DEFAULT_PROMPT_LIMIT = 8       # entries injected into a prompt
_MIN_TEXT_LEN = 8               # ignore trivially short "insights"


def _normalize(text: str) -> str:
    """Lowercase, collapse whitespace/punctuation — used for dedup matching."""
    return re.sub(r"[^a-z0-9 ]+", "", text.lower()).strip()


@dataclass
class PlaybookEntry:
    text: str
    source: str = ""              # e.g. "mission:MSN-1/task:build_api"
    kind: str = "heuristic"       # heuristic | caution | pattern | skill
    score: float = 1.0
    hits: int = 1                 # how many times this lesson has been reinforced
    created: str = field(default_factory=lambda: datetime.now().isoformat())
    updated: str = field(default_factory=lambda: datetime.now().isoformat())
    tags: list[str] = field(default_factory=list)

    def rank(self) -> float:
        """Higher = surfaced first. Rewards reinforcement and recency."""
        try:
            age_days = (datetime.now() - datetime.fromisoformat(self.updated)).days
        except Exception:
            age_days = 0
        recency = 1.0 / (1.0 + max(age_days, 0) / 30.0)   # half-life ~ 1 month
        return self.score * (1.0 + 0.25 * self.hits) * recency


class PlaybookStore:
    """Loads/saves per-role playbooks and renders them for prompts."""

    def __init__(self, base_path: str | Path = "knowledge/playbooks") -> None:
        self._base = Path(base_path)
        self._base.mkdir(parents=True, exist_ok=True)

    # ── paths ────────────────────────────────────────────────────────────────

    def _json_path(self, role: str) -> Path:
        return self._base / f"{str(role).lower()}.json"

    def _md_path(self, role: str) -> Path:
        return self._base / f"{str(role).lower()}.md"

    # ── load / save ──────────────────────────────────────────────────────────

    def entries(self, role: str) -> list[PlaybookEntry]:
        path = self._json_path(role)
        if not path.exists():
            return []
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []
        out: list[PlaybookEntry] = []
        for item in raw:
            try:
                out.append(PlaybookEntry(**item))
            except TypeError:
                # tolerate schema drift — keep whatever fields match
                out.append(PlaybookEntry(text=str(item.get("text", "")).strip()))
        return [e for e in out if e.text]

    def _save(self, role: str, entries: list[PlaybookEntry]) -> None:
        self._json_path(role).write_text(
            json.dumps([asdict(e) for e in entries], indent=2, default=str),
            encoding="utf-8",
        )
        self._md_path(role).write_text(self._render_markdown(role, entries), encoding="utf-8")

    # ── mutation ─────────────────────────────────────────────────────────────

    def add_entry(
        self,
        role: str,
        text: str,
        source: str = "",
        kind: str = "heuristic",
        score: float = 1.0,
        tags: list[str] | None = None,
    ) -> bool:
        """Add a learned heuristic. Deduplicates: a near-identical existing entry
        is *reinforced* (hit++, score bumped) instead of duplicated. Returns True
        if a new entry was created, False if it reinforced an existing one."""
        text = (text or "").strip()
        if len(text) < _MIN_TEXT_LEN:
            return False

        entries = self.entries(role)
        norm = _normalize(text)
        for e in entries:
            if _normalize(e.text) == norm:
                e.hits += 1
                e.score = round(min(e.score + 0.5, 10.0), 3)
                e.updated = datetime.now().isoformat()
                if source and source not in e.source:
                    e.source = (e.source + "; " + source).strip("; ")
                self._save(role, entries)
                return False

        entries.append(PlaybookEntry(
            text=text, source=source, kind=kind, score=score, tags=tags or [],
        ))
        entries = self._consolidate(entries)
        self._save(role, entries)
        return True

    def reinforce(self, role: str, text: str, delta: float = 0.5) -> None:
        """Bump the score of the entry closest to `text` (used by reward signals)."""
        entries = self.entries(role)
        norm = _normalize(text)
        for e in entries:
            if norm and norm in _normalize(e.text):
                e.score = round(min(e.score + delta, 10.0), 3)
                e.hits += 1
                e.updated = datetime.now().isoformat()
                self._save(role, entries)
                return

    def consolidate(self, role: str, max_entries: int = _MAX_ENTRIES_PER_ROLE) -> int:
        """Prune/merge a role's playbook. Returns the number of entries dropped."""
        entries = self.entries(role)
        before = len(entries)
        kept = self._consolidate(entries, max_entries=max_entries)
        self._save(role, kept)
        return before - len(kept)

    def decay(self, role: str, factor: float = 0.95) -> None:
        """Gently decay every score so unreinforced lessons fade over time."""
        entries = self.entries(role)
        for e in entries:
            e.score = round(e.score * factor, 3)
        self._save(role, entries)

    @staticmethod
    def _consolidate(
        entries: list[PlaybookEntry],
        max_entries: int = _MAX_ENTRIES_PER_ROLE,
    ) -> list[PlaybookEntry]:
        # merge exact-normalized duplicates
        merged: dict[str, PlaybookEntry] = {}
        for e in entries:
            key = _normalize(e.text)
            if not key:
                continue
            if key in merged:
                m = merged[key]
                m.hits += e.hits
                m.score = round(min(m.score + e.score / 2, 10.0), 3)
                m.updated = max(m.updated, e.updated)
            else:
                merged[key] = e
        ranked = sorted(merged.values(), key=lambda x: x.rank(), reverse=True)
        return ranked[:max_entries]

    # ── rendering ────────────────────────────────────────────────────────────

    def render_for_prompt(self, role: str, limit: int = _DEFAULT_PROMPT_LIMIT) -> str:
        """Bounded, prompt-ready bullet list of the highest-ranked lessons.

        Returns "" when a role has no playbook yet, so callers can skip the
        section entirely and spend no tokens on it.
        """
        entries = sorted(self.entries(role), key=lambda x: x.rank(), reverse=True)[:limit]
        if not entries:
            return ""
        lines = []
        for e in entries:
            marker = {"caution": "AVOID", "skill": "SKILL", "pattern": "PATTERN"}.get(e.kind, "")
            prefix = f"[{marker}] " if marker else ""
            lines.append(f"- {prefix}{e.text}")
        return "\n".join(lines)

    def _render_markdown(self, role: str, entries: list[PlaybookEntry]) -> str:
        ranked = sorted(entries, key=lambda x: x.rank(), reverse=True)
        lines = [
            f"# {str(role).upper()} — Learned Playbook",
            "",
            "_Accumulated automatically by CRESSIDA's learning loop (agent R). "
            "Highest-ranked lessons are injected into this agent's future prompts._",
            "",
        ]
        for e in ranked:
            tag = f" · _{', '.join(e.tags)}_" if e.tags else ""
            lines.append(
                f"- **[{e.kind}]** {e.text}  \n"
                f"  <sub>score={e.score} · reinforced×{e.hits} · {e.source or 'n/a'}{tag}</sub>"
            )
        if not ranked:
            lines.append("_No lessons recorded yet._")
        return "\n".join(lines) + "\n"

    def all_roles(self) -> list[str]:
        return sorted({p.stem for p in self._base.glob("*.json")})

    def summary(self) -> dict[str, Any]:
        return {role: len(self.entries(role)) for role in self.all_roles()}
