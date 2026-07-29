from __future__ import annotations

"""Canonical path resolution for CRESSIDA.

Why this module exists
----------------------
Cressida used to resolve its own directories three different ways:

  * ``Path.cwd()``                            — provider output writing, tools
  * ``Path(__file__).parent.parent.parent``   — coordinator, MCP server, watcher
  * ``cressida_root`` (defaulting to ``"."``) — context builder, agent specs

Those three only agree when the process happens to be launched from the package
directory. Run a mission from anywhere else and the mission split in two: the
coordinator wrote ``execution_state.json`` to one tree while agents wrote their
artifacts to another, so downstream agents' ``reads`` resolved to nothing and
each phase re-derived context that had in fact been written — just somewhere
else. The ``.parent.parent.parent`` anchors were doubly wrong: they climbed one
level above the repository root and wrote missions outside the repo.

Every path decision now goes through this module, so Cressida behaves the same
regardless of the working directory it was launched from.

Layout
------
``CRESSIDA_HOME`` is the package directory (``…/Cressida/cressida``) — the
repository root, and the directory that actually contains the tracked
``agents/``, ``knowledge/``, and ``missions/`` trees. It is *not* the import
root: the import root is its parent, since the package is imported as
``cressida.*``.

Environment overrides
---------------------
``CRESSIDA_HOME``         — relocate the whole installation.
``CRESSIDA_MISSIONS_DIR`` — put mission artifacts elsewhere (e.g. off a repo).
``CRESSIDA_PROJECT_DIR``  — default target project for missions.
"""

import os
from pathlib import Path


# …/Cressida/cressida/core/paths.py -> …/Cressida/cressida
_PACKAGE_DIR = Path(__file__).resolve().parent.parent


def _env_path(name: str) -> Path | None:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    try:
        return Path(raw).expanduser().resolve()
    except Exception:
        return None


def cressida_home() -> Path:
    """Root of the Cressida installation (contains agents/, knowledge/, missions/)."""
    return _env_path("CRESSIDA_HOME") or _PACKAGE_DIR


def agents_dir() -> Path:
    return cressida_home() / "agents"


def knowledge_dir() -> Path:
    return cressida_home() / "knowledge"


def missions_root() -> Path:
    """Directory holding all mission trees."""
    return _env_path("CRESSIDA_MISSIONS_DIR") or (cressida_home() / "missions")


def default_vault_dir() -> Path:
    """Fallback markdown export dir used when no Obsidian vault is configured.

    Same folder layout and plain-markdown-with-frontmatter format as a real
    Obsidian vault (see cressida.obsidian.bridge) — readable with any text
    editor, just not opened inside the Obsidian app.
    """
    return _env_path("CRESSIDA_VAULT_DIR") or (cressida_home() / "vault")


def mission_dir(mission_id: str) -> Path:
    return missions_root() / mission_id


# Directories a mission must never be pointed at. Agents now run with
# --permission-mode bypassPermissions (see core/providers/claude_cli_agent.py),
# which skips Claude Code's own approval prompts entirely — so --add-dir, built
# from this value, is the *only* remaining boundary on what the Read/Write/Edit/
# Glob tools can touch directly. A mission accidentally (or via a bad brief)
# targeting a drive root or a system directory would hand those tools free rein
# over the OS. This does not — and cannot — constrain Bash: package managers
# (pip/uv/npm) reach global site-packages/caches the same way they always have,
# since Bash subprocesses are OS-level and were never gated by --add-dir.
_FORBIDDEN_SYSTEM_DIRS = {
    # Windows
    "c:\\windows", "c:\\program files", "c:\\program files (x86)",
    "c:\\programdata", "c:\\system volume information",
    # Unix
    "/etc", "/usr", "/bin", "/sbin", "/boot", "/system", "/library", "/root",
    "/var", "/dev", "/proc",
}


class UnsafeProjectDirError(ValueError):
    """Raised when a mission's resolved project_dir is a system path, a drive/
    filesystem root, the bare home directory, or the Cressida install itself."""


def _check_project_dir_is_safe(resolved: Path) -> None:
    normalized = str(resolved).rstrip("\\/").lower() or str(resolved).lower()

    if resolved.parent == resolved:
        raise UnsafeProjectDirError(
            f"Refusing to target a filesystem/drive root as a mission's project_dir: {resolved}"
        )
    if normalized in _FORBIDDEN_SYSTEM_DIRS:
        raise UnsafeProjectDirError(
            f"Refusing to target a system directory as a mission's project_dir: {resolved}"
        )
    home: Path | None
    try:
        home = Path.home().resolve()
    except Exception:
        home = None
    if home is not None and resolved == home:
        raise UnsafeProjectDirError(
            f"Refusing to target the bare home directory as a mission's project_dir: {resolved}. "
            "Point it at a specific project folder instead."
        )

    if resolved == _PACKAGE_DIR or resolved in _PACKAGE_DIR.parents:
        raise UnsafeProjectDirError(
            f"Refusing to target the Cressida install itself as a mission's project_dir: {resolved}"
        )


def project_dir(state: object | None = None) -> Path:
    """The mission's target project directory — where implementation code goes.

    Resolution order: the mission's own ``metadata["project_dir"]``, then
    ``CRESSIDA_PROJECT_DIR``, then the process working directory. Falling back to
    the CWD keeps the common "run Cressida inside the project I'm working on"
    case working with no configuration.

    Raises ``UnsafeProjectDirError`` if the resolved path is a drive/filesystem
    root, a well-known system directory, the bare home directory, or the
    Cressida install itself — see ``_FORBIDDEN_SYSTEM_DIRS`` above for why this
    check exists now that agents run with permissions bypassed.
    """
    resolved: Path | None = None
    meta = getattr(state, "metadata", None)
    if isinstance(meta, dict):
        raw = str(meta.get("project_dir") or "").strip()
        if raw:
            try:
                resolved = Path(raw).expanduser().resolve()
            except Exception:
                resolved = None

    if resolved is None:
        resolved = _env_path("CRESSIDA_PROJECT_DIR") or Path.cwd().resolve()

    _check_project_dir_is_safe(resolved)
    return resolved


def resolve_under_home(path: str | Path) -> Path:
    """Resolve a path that Cressida owns.

    Absolute paths pass through untouched — that is how a mission writes into an
    external target project. Relative paths are anchored to ``cressida_home()``
    rather than the working directory, so ``missions/<id>/x.md`` always means the
    same file no matter where the process was launched from.
    """
    p = Path(path).expanduser()
    if p.is_absolute():
        return p
    return cressida_home() / p


def resolve_mission_path(path: str | Path, mission_id: str = "") -> Path:
    """Resolve a path that may be mission-relative.

    Tries, in order: as-is under ``cressida_home()``, then relative to the
    mission directory. Absolute paths pass through untouched.
    """
    p = Path(path).expanduser()
    if p.is_absolute():
        return p
    direct = resolve_under_home(p)
    if direct.exists():
        return direct
    if mission_id:
        candidate = mission_dir(mission_id) / p
        if candidate.exists():
            return candidate
    return direct
