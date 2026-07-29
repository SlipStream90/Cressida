"""Obsidian ↔ Cressida bridge.

Bidirectional sync between Cressida and an Obsidian vault:

  VAULT → CRESSIDA
    - Inbox folder: drop a .md note with YAML frontmatter (cressida: true) to
      trigger a mission. The watcher polls this folder every N seconds.
    - Knowledge reads: query_memory searches vault .md files alongside
      Cressida's internal strategic memory.

  CRESSIDA → VAULT
    - Mission artifacts are mirrored to Vault/Cressida/Missions/<id>/
    - Lessons and patterns sync to Vault/Cressida/Knowledge/
    - BOND decisions land in Vault/Cressida/BOND Decisions/

Vault folder layout (all under the configured cressida_folder, default "Cressida"):

    Vault/
    └── Cressida/
        ├── Inbox/            ← write briefs here
        ├── Missions/
        │   └── MSN-2026-001/
        │       ├── Brief.md
        │       ├── Research Report.md
        │       ├── PRD.md
        │       ├── Architecture.md
        │       └── Review.md
        ├── Knowledge/
        │   ├── lessons.md
        │   ├── patterns.md
        │   └── decisions.md
        └── BOND Decisions/

Config (in cressida.yaml):

    obsidian:
      vault_path: "C:/Users/you/Documents/MyVault"
      cressida_folder: "Cressida"
      inbox_folder: "Inbox"
      poll_interval_seconds: 15

Or via environment variable:
    CRESSIDA_OBSIDIAN_VAULT=C:/Users/you/Documents/MyVault
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Awaitable

try:
    import yaml as _yaml
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False


# ── Frontmatter helpers ───────────────────────────────────────────────────────

_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Return (frontmatter_dict, body_text). frontmatter_dict is {} if absent."""
    m = _FM_RE.match(text)
    if not m or not _YAML_AVAILABLE:
        return {}, text
    try:
        fm = _yaml.safe_load(m.group(1)) or {}
        body = text[m.end():]
        return fm, body
    except Exception:
        return {}, text


def _sanitize_filename(title: str) -> str:
    """Make a title safe to use as an Obsidian note filename (no path chars)."""
    cleaned = re.sub(r'[\\/:*?"<>|#^\[\]]', "-", title).strip().strip(".")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned[:120] or "untitled"


def _render_note(frontmatter: dict[str, Any], body: str) -> str:
    """Render a note with YAML frontmatter."""
    if not _YAML_AVAILABLE:
        return body
    fm_str = _yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True).strip()
    return f"---\n{fm_str}\n---\n\n{body}"


# ── Vault search ──────────────────────────────────────────────────────────────

def _score(text_lower: str, keywords: list[str]) -> int:
    return sum(text_lower.count(kw.lower()) for kw in keywords if kw)


def search_vault(vault_path: Path, query: str, max_results: int = 8) -> list[dict[str, str]]:
    """Full-text keyword search across all .md files in the vault.

    Returns a list of dicts with keys: path (relative), title, excerpt, score.
    """
    keywords = [w for w in re.split(r"\W+", query) if len(w) > 2]
    if not keywords:
        return []

    results: list[tuple[int, str, str, str]] = []
    for md_file in vault_path.rglob("*.md"):
        try:
            text = md_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        _, body = _parse_frontmatter(text)
        score = _score(body.lower(), keywords)
        if score == 0:
            continue
        title = md_file.stem
        # grab first matching paragraph as excerpt
        excerpt = ""
        for line in body.splitlines():
            if any(kw.lower() in line.lower() for kw in keywords):
                excerpt = line.strip()[:300]
                break
        rel = str(md_file.relative_to(vault_path))
        results.append((score, rel, title, excerpt))

    results.sort(key=lambda x: x[0], reverse=True)
    return [
        {"path": r, "title": t, "excerpt": e, "score": s}
        for s, r, t, e in results[:max_results]
    ]


# ── Bridge class ──────────────────────────────────────────────────────────────

class ObsidianBridge:
    """Bidirectional Obsidian ↔ Cressida integration.

    Pass an instance to start_daemon() and to query_memory() for full
    read/write vault access from agents and the daemon.
    """

    def __init__(
        self,
        vault_path: str | Path | None = None,
        cressida_folder: str = "Cressida",
        inbox_folder: str = "Inbox",
        poll_interval: float = 15.0,
    ) -> None:
        resolved = vault_path or os.environ.get("CRESSIDA_OBSIDIAN_VAULT", "")
        if not resolved:
            raise ValueError(
                "Obsidian vault path not set. "
                "Pass vault_path= or set CRESSIDA_OBSIDIAN_VAULT env var."
            )
        self.vault = Path(resolved).expanduser().resolve()
        self.cressida_folder = cressida_folder
        self.inbox_folder = inbox_folder
        self.poll_interval = poll_interval
        self._ensure_structure()

    # ── Directory helpers ─────────────────────────────────────────────────────

    def _root(self) -> Path:
        return self.vault / self.cressida_folder

    def inbox_dir(self) -> Path:
        return self._root() / self.inbox_folder

    def missions_dir(self) -> Path:
        return self._root() / "Missions"

    def knowledge_dir(self) -> Path:
        return self._root() / "Knowledge"

    def bond_dir(self) -> Path:
        return self._root() / "BOND Decisions"

    # Main knowledge-graph branches. Every stored memory lands as a *subnode*
    # under one of these, linked back to the branch's Map-of-Content (MOC) note
    # so Obsidian's graph view renders branch → subnode trees.
    BRANCHES: dict[str, str] = {
        "knowledge":    "Knowledge",
        "mission":      "Mission Memory",
        "logs":         "Logs",
        # "Decision Log", not "Decisions" — a mission's own architecture decisions
        # already live in Knowledge/decisions.md; a second "Decisions.md" note
        # would collide on basename and make [[Decisions]] links ambiguous.
        "decisions":    "Decision Log",
        "escalations":  "Escalations",
        "postmortems":  "Post-Mortems",
    }

    def branch_dir(self, branch: str) -> Path:
        """Folder for a main branch. Unknown keys fall under a 'Misc' branch."""
        folder = self.BRANCHES.get(branch.lower().strip(), branch.strip() or "Misc")
        return self._root() / folder

    def _branch_moc_path(self, branch: str) -> Path:
        """The Map-of-Content index note that sits at the root of a branch."""
        d = self.branch_dir(branch)
        folder = d.name
        return d / f"{folder}.md"

    def _ensure_structure(self) -> None:
        for d in (self.inbox_dir(), self.missions_dir(), self.knowledge_dir(), self.bond_dir()):
            d.mkdir(parents=True, exist_ok=True)
        self._ensure_branches()

    def _ensure_branches(self) -> None:
        """Create each main branch folder and its MOC index note if missing."""
        for key, folder in self.BRANCHES.items():
            (self._root() / folder).mkdir(parents=True, exist_ok=True)
            moc = self._branch_moc_path(key)
            if not moc.exists():
                fm = {
                    "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "node_type": "branch",
                    "tags": ["cressida", "moc", "branch", key],
                }
                body = (
                    f"# {folder}\n\n"
                    f"Main knowledge branch. Every {folder.lower()} memory is stored "
                    f"as a subnode below and linked here.\n\n"
                    f"## Subnodes\n"
                )
                moc.write_text(_render_note(fm, body), encoding="utf-8")

    # ── Subnode memory storage ────────────────────────────────────────────────

    def store_subnode(
        self,
        branch: str,
        title: str,
        content: str,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Path:
        """Store a memory as a subnode under a main branch and link it from the MOC.

        This is the single chokepoint for *all* memory that should live in the
        Obsidian graph — knowledge, mission memory, logs, decisions, etc. The
        subnode carries an ``up: "[[<Branch>]]"`` link and the branch MOC gains a
        ``[[<subnode>]]`` backlink, so the vault graph shows a branch → subnodes
        tree.

        Returns the path to the written subnode note.
        """
        self._ensure_branches()
        folder = self.branch_dir(branch)
        folder.mkdir(parents=True, exist_ok=True)

        branch_folder = folder.name
        safe_title = _sanitize_filename(title)

        fm: dict[str, Any] = {
            "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "node_type": "subnode",
            "branch": branch_folder,
            "up": f"[[{branch_folder}]]",
            "tags": ["cressida", "subnode", branch.lower().strip()] + (tags or []),
        }
        meta = metadata or {}
        for k in ("mission_id", "agent", "task_id"):
            if meta.get(k):
                fm[k] = meta[k]

        # Body opens with an explicit link up to the branch so the edge exists
        # even for readers that ignore frontmatter.
        body = f"Up: [[{branch_folder}]]\n\n{content}"
        path = folder / f"{safe_title}.md"
        path.write_text(_render_note(fm, body), encoding="utf-8")

        self._register_in_moc(branch, safe_title)
        return path

    def _register_in_moc(self, branch: str, subnode_title: str) -> None:
        """Add an idempotent ``[[subnode]]`` backlink under the branch MOC."""
        moc = self._branch_moc_path(branch)
        if not moc.exists():
            self._ensure_branches()
        text = moc.read_text(encoding="utf-8", errors="replace")
        link = f"- [[{subnode_title}]]"
        if link in text:
            return  # already registered
        if "## Subnodes" in text:
            text = text.rstrip() + f"\n{link}\n"
        else:
            text = text.rstrip() + f"\n\n## Subnodes\n{link}\n"
        moc.write_text(text, encoding="utf-8")

    # ── Writing artifacts to vault ────────────────────────────────────────────

    def write_artifact(
        self,
        mission_id: str,
        title: str,
        content: str,
        tags: list[str] | None = None,
        agent: str = "",
    ) -> Path:
        """Write a mission output note to Vault/Missions/<id>/<mission_id> — <title>.md.

        The filename is prefixed with mission_id so it can never collide with an
        agent or knowledge note of the same generic title (e.g. "Architecture",
        "Review") — Obsidian resolves [[links]] by basename vault-wide, and an
        unqualified name would silently hijack links meant for the other note.
        """
        mission_dir = self.missions_dir() / mission_id
        mission_dir.mkdir(parents=True, exist_ok=True)

        fm: dict[str, Any] = {
            "mission_id": mission_id,
            "title": title,
            "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "tags": ["cressida", "mission", mission_id.lower()] + (tags or []),
        }
        if agent:
            fm["agent"] = agent

        note = _render_note(fm, content)
        safe_title = _sanitize_filename(f"{mission_id} — {title}")
        path = mission_dir / f"{safe_title}.md"
        path.write_text(note, encoding="utf-8")
        return path

    def write_bond_decision(self, mission_id: str, phase: str, decision: dict) -> Path:
        """Write a BOND gate decision to Vault/Cressida/BOND Decisions/."""
        self.bond_dir().mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d")
        title = f"{ts} {mission_id} — {phase}"
        verdict = decision.get("decision", "UNKNOWN")
        body = (
            f"# BOND Decision: {phase}\n\n"
            f"**Verdict:** {verdict}  \n"
            f"**Mission:** {mission_id}  \n"
            f"**Confidence:** {decision.get('confidence', '?')}  \n\n"
            f"## Rationale\n\n{decision.get('rationale', '')}\n"
        )
        if decision.get("conditions"):
            body += "\n## Conditions\n\n" + "\n".join(f"- {c}" for c in decision["conditions"])

        fm = {
            "mission_id": mission_id,
            "phase": phase,
            "verdict": verdict,
            "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "tags": ["cressida", "bond", "decision"],
        }
        path = self.bond_dir() / f"{title}.md"
        path.write_text(_render_note(fm, body), encoding="utf-8")
        return path

    def sync_knowledge(self, knowledge_dir: Path) -> None:
        """Mirror cressida/knowledge/*.md into Vault/Knowledge/Source/.

        Lands in a "Source" subfolder, not directly in Knowledge/, because the
        raw framework files (architecture.md, decisions.md, lessons.md,
        patterns.md) share basenames with hand-curated Obsidian notes that live
        directly under Knowledge/ — copying straight into Knowledge/ would
        silently clobber the curated notes on every mission task completion.
        """
        if not knowledge_dir.exists():
            return
        dst_dir = self.knowledge_dir() / "Source"
        dst_dir.mkdir(parents=True, exist_ok=True)
        for src in knowledge_dir.glob("*.md"):
            dst = dst_dir / src.name
            shutil.copy2(src, dst)

    def sync_mission_outputs(self, mission_id: str, missions_base: Path) -> None:
        """Mirror key output files from missions/<id>/ into the vault."""
        src_dir = missions_base / mission_id
        if not src_dir.exists():
            return

        # Map source filename → vault title. Titles are generic ("Architecture",
        # "Review", ...) and *will* collide with agent/knowledge notes that share
        # the same basename elsewhere in the vault — Obsidian resolves [[links]]
        # by basename across the whole vault, so an unqualified "Architecture.md"
        # here silently steals every [[Architecture]] link meant for the agent
        # roster's knowledge note. write_artifact() prefixes with mission_id to
        # keep every mission's notes globally unique.
        file_map = {
            "dossier.md":              "Brief",
            "ARCHITECTURE.md":         "Architecture",
            "review_report.md":        "Review",
            "bond_review.md":          "BOND Review",
            "bond_checkpoint_verdict.md": "BOND Checkpoint",
            "priority_matrix.md":      "Priority Matrix",
            "coverage_report.md":      "Coverage Report",
            "intelligence/PRD.md":     "PRD",
            "intelligence/research_report.md": "Research Report",
            "intelligence/Roadmap.md": "Roadmap",
            "intelligence/methodology_brief.md": "Methodology Brief",
            "intelligence/sources.md": "Sources",
            "playwright_report.md":    "Playwright Report",
        }
        for rel, title in file_map.items():
            src = src_dir / rel
            if src.exists():
                content = src.read_text(encoding="utf-8", errors="replace")
                # Strip any existing frontmatter before re-wrapping
                _, body = _parse_frontmatter(content)
                self.write_artifact(mission_id, title, body)

    # ── Reading / searching vault ─────────────────────────────────────────────

    def search(self, query: str, max_results: int = 8) -> list[dict[str, str]]:
        """Full-text keyword search across the entire vault."""
        return search_vault(self.vault, query, max_results=max_results)

    def read_note(self, relative_path: str) -> str:
        """Read a note by its vault-relative path. Returns '' if not found."""
        p = self.vault / relative_path
        if not p.exists():
            return ""
        return p.read_text(encoding="utf-8", errors="replace")

    def list_notes(self, subfolder: str = "") -> list[str]:
        """List all .md file paths under vault/subfolder, relative to vault root."""
        base = self.vault / subfolder if subfolder else self.vault
        if not base.exists():
            return []
        return sorted(str(f.relative_to(self.vault)) for f in base.rglob("*.md"))

    # ── Inbox watcher ─────────────────────────────────────────────────────────

    async def watch_inbox(
        self,
        on_brief: Callable[[str, dict], Awaitable[None]],
    ) -> None:
        """Async loop — poll vault inbox folder, trigger on_brief(brief_text, metadata)."""
        processed = self.inbox_dir() / "_processed"
        processed.mkdir(exist_ok=True)

        while True:
            for note in list(self.inbox_dir().glob("*.md")):
                if note.parent.name == "_processed":
                    continue
                try:
                    text = note.read_text(encoding="utf-8")
                    fm, body = _parse_frontmatter(text)

                    # Must have cressida: true frontmatter flag
                    if not fm.get("cressida"):
                        continue

                    brief = fm.get("brief") or body.strip()
                    metadata = {
                        "priority":  fm.get("priority", "medium"),
                        "provider":  fm.get("provider", "auto"),
                        "source":    str(note),
                        "title":     note.stem,
                    }

                    await on_brief(brief, metadata)

                    # Move to processed
                    dst = processed / note.name
                    note.rename(dst)

                except Exception as exc:
                    print(f"[ObsidianBridge] inbox error reading {note.name}: {exc}")

            await asyncio.sleep(self.poll_interval)

    # ── Event-driven vault sync ───────────────────────────────────────────────

    def subscribe_to_events(self, event_bus: Any, missions_base: Path, knowledge_dir: Path) -> None:
        """Subscribe to TASK_COMPLETED / MISSION_COMPLETED so every run's outputs
        sync to the vault (or its local markdown fallback) with no manual step."""
        from cressida.core.events import Event, EventType

        async def _on_event(event: Event) -> None:
            try:
                mission_id = event.data.get("mission_id", "")
                if not mission_id:
                    return
                self.sync_mission_outputs(mission_id, missions_base)
                self.sync_knowledge(knowledge_dir)
                if event.type == EventType.MISSION_COMPLETED:
                    self._write_mission_index(mission_id, missions_base)
            except Exception as exc:
                print(f"[ObsidianBridge] event sync error: {exc}")

        event_bus.subscribe(EventType.TASK_COMPLETED, _on_event)
        event_bus.subscribe(EventType.MISSION_COMPLETED, _on_event)

    def _write_mission_index(self, mission_id: str, missions_base: Path) -> None:
        """Write a summary index note for a completed mission.

        Named "<mission_id> Artifacts.md", not the bare "Index.md" this used to
        be — every mission would otherwise write a file with the exact same
        basename, and Obsidian resolves [[Index]] links by basename across the
        whole vault, so only the most-recently-synced mission's index would ever
        be reachable. ("Artifacts" also avoids colliding with any hand-curated
        "<mission_id> Index" overview note that names the mission itself.)
        """
        mission_dir = self.missions_dir() / mission_id
        title = f"{mission_id} Artifacts"
        files = sorted(
            f for f in mission_dir.glob("*.md") if f.stem != title
        ) if mission_dir.exists() else []
        links = "\n".join(f"- [[{f.stem}]]" for f in files)
        body = f"# {mission_id}\n\n**Completed:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n## Artifacts\n\n{links}\n"
        fm = {
            "mission_id": mission_id,
            "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "tags": ["cressida", "mission-index"],
        }
        idx = self.missions_dir() / mission_id / f"{title}.md"
        idx.write_text(_render_note(fm, body), encoding="utf-8")


# ── Module-level singleton (lazy) ─────────────────────────────────────────────

_bridge: ObsidianBridge | None = None


def get_bridge() -> ObsidianBridge | None:
    """Return the active bridge — a real Obsidian vault if configured, otherwise a
    plain-markdown export folder so non-Obsidian users still get the same
    per-mission notes and knowledge sync, just as .md files on disk.

    Returns None only if even the local fallback folder can't be created.
    """
    global _bridge
    if _bridge is not None:
        return _bridge
    vault = os.environ.get("CRESSIDA_OBSIDIAN_VAULT", "")
    if not vault:
        from cressida.core.paths import default_vault_dir
        vault = str(default_vault_dir())
    # CRESSIDA_OBSIDIAN_FOLDER overrides the "Cressida" subfolder Cressida
    # normally owns inside the vault. Set it to "" to write flat at the vault
    # root instead — e.g. when the vault's Missions/Knowledge/Agents folders
    # were already established at the top level before Cressida was wired in.
    folder = os.environ.get("CRESSIDA_OBSIDIAN_FOLDER")
    kwargs = {"cressida_folder": folder} if folder is not None else {}
    try:
        _bridge = ObsidianBridge(vault_path=vault, **kwargs)
    except Exception:
        pass
    return _bridge


def init_bridge(vault_path: str, **kwargs) -> ObsidianBridge:
    """Initialise the module-level bridge (call from daemon startup)."""
    global _bridge
    _bridge = ObsidianBridge(vault_path=vault_path, **kwargs)
    return _bridge
