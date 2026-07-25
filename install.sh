#!/usr/bin/env bash
# CRESSIDA one-line installer (macOS / Linux / WSL / Git-Bash).
#
#   curl -fsSL https://raw.githubusercontent.com/SlipStream90/Cressida/main/install.sh | bash
#
# Clones the repo into ~/.cressida/src, builds an isolated virtualenv,
# installs CRESSIDA, and wires up the MCP server for Claude Code.
#
# Overridable via env vars:
#   CRESSIDA_REPO      git URL           (default: the public GitHub repo)
#   CRESSIDA_BRANCH    branch/tag        (default: the repo's default branch)
#   CRESSIDA_HOME      install dir       (default: ~/.cressida)
#   CRESSIDA_PROVIDER  provider extra    (anthropic|openai|gemini|groq|all; default: none)
set -euo pipefail

REPO="${CRESSIDA_REPO:-https://github.com/SlipStream90/Cressida.git}"
BRANCH="${CRESSIDA_BRANCH:-}"   # empty = follow the remote's default branch
HOME_DIR="${CRESSIDA_HOME:-$HOME/.cressida}"
PROVIDER="${CRESSIDA_PROVIDER:-}"
SRC="$HOME_DIR/src"
VENV="$HOME_DIR/venv"

c() { printf '\033[1;36m[cressida]\033[0m %s\n' "$1"; }
die() { printf '\033[1;31m[cressida] %s\033[0m\n' "$1" >&2; exit 1; }

command -v git >/dev/null 2>&1 || die "git is required."

# Pick the first candidate that actually runs and is >= 3.11. (On Windows/Git-Bash
# `python3` may be a Microsoft Store stub that isn't a real interpreter, so we
# verify each candidate rather than trust `command -v`.)
PY=""
for cand in python3 python python3.13 python3.12 python3.11; do
  command -v "$cand" >/dev/null 2>&1 || continue
  if "$cand" -c 'import sys; sys.exit(0 if sys.version_info>=(3,11) else 1)' >/dev/null 2>&1; then
    PY="$cand"; break
  fi
done
[ -n "$PY" ] || die "Python 3.11+ is required (no working interpreter found)."

mkdir -p "$HOME_DIR"
if [ -d "$SRC/.git" ]; then
  if [ -n "$BRANCH" ]; then
    c "Updating checkout at $SRC ($BRANCH)"
    git -C "$SRC" fetch --depth 1 origin "$BRANCH"
    git -C "$SRC" checkout -q "$BRANCH"
    git -C "$SRC" reset -q --hard "origin/$BRANCH"
  else
    c "Updating checkout at $SRC"
    git -C "$SRC" fetch --depth 1 origin
    git -C "$SRC" reset -q --hard FETCH_HEAD
  fi
else
  c "Cloning $REPO${BRANCH:+ ($BRANCH)}"
  if [ -n "$BRANCH" ]; then
    git clone --branch "$BRANCH" --depth 1 "$REPO" "$SRC"
  else
    git clone --depth 1 "$REPO" "$SRC"   # follows the remote's default branch
  fi
fi

c "Creating virtualenv at $VENV"
"$PY" -m venv "$VENV"
VPY="$VENV/bin/python"
[ -x "$VPY" ] || VPY="$VENV/Scripts/python.exe"   # Windows layout under Git-Bash

"$VPY" -m pip install --quiet --upgrade pip
TARGET="$SRC"
[ -n "$PROVIDER" ] && TARGET="$SRC[$PROVIDER]"
c "Installing CRESSIDA${PROVIDER:+ (+$PROVIDER)}"
"$VPY" -m pip install --quiet -e "$TARGET"

# Put the `cressida` CLI on PATH if a standard user bin dir exists.
if [ -d "$HOME/.local/bin" ]; then
  ln -sf "$(dirname "$VPY")/cressida" "$HOME/.local/bin/cressida" 2>/dev/null || true
  c "Linked cressida -> ~/.local/bin/cressida"
fi

c "Wiring up the MCP server"
"$VPY" "$SRC/onboard.py" --skip-install --register

c "Done. Installed at $HOME_DIR"
echo "  CLI:    $(dirname "$VPY")/cressida run brief.md"
echo "  MCP:    restart Claude Code, then call the cressida_status tool"
echo "  Update: re-run this installer any time (it pulls the latest and reinstalls)"
