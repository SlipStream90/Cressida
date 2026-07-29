from __future__ import annotations

"""Discover Claude Code skills actually installed on this machine.

Before this, ``orchestration/dispatcher.py``'s skill selection only knew about
a small, hand-maintained keyword table (``_SKILL_HINTS``) — a skill installed
later (a new plugin, ponytail before it got an explicit rule) was invisible to
commissioning until someone edited that table. This scans the real skill
sources Claude Code itself reads from and returns what's actually there, so
selection can match against it directly.

Skills are ``<skill-dir>/SKILL.md`` files with YAML frontmatter (``name``,
``description``), found in three places:

  - ``~/.claude/skills/`` — user-installed skills
  - ``~/.claude/plugins/`` — plugin-provided skills (marketplace installs)
  - ``<project>/.claude/skills/`` — project-local skills, when a project_dir
    is given

Cached for the process lifetime: skills don't change mid-mission, and a
plugins-tree scan is the expensive part of this (many cached plugin versions).
"""

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _parse_frontmatter(text: str) -> dict[str, Any]:
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}
    try:
        import yaml
        data = yaml.safe_load(match.group(1))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _scan_dir(root: Path, results: dict[str, str]) -> None:
    if not root.exists():
        return
    try:
        skill_files = list(root.rglob("SKILL.md"))
    except OSError:
        return
    for skill_md in skill_files:
        try:
            fm = _parse_frontmatter(skill_md.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        name = str(fm.get("name", "")).strip()
        description = str(fm.get("description", "")).strip()
        if not name or not description:
            continue
        # Plugin skills are sometimes namespaced ("stitch::react-components") -
        # keep the part after "::" so this matches what's actually listed to
        # the agent by the Skill tool.
        name = name.rsplit("::", 1)[-1]
        if name not in results:  # first hit wins - skip older cached plugin versions
            results[name] = description


@lru_cache(maxsize=8)
def discover_skills(project_dir: str = "") -> dict[str, str]:
    """Return {skill_name: description} for every skill visible on this
    machine. Fails open: any scan error yields fewer skills, never an
    exception - a Dispatcher commission must never break over this."""
    results: dict[str, str] = {}
    try:
        home = Path.home() / ".claude"
        _scan_dir(home / "skills", results)
        _scan_dir(home / "plugins", results)
        if project_dir:
            _scan_dir(Path(project_dir) / ".claude" / "skills", results)
    except Exception:
        pass
    return results
