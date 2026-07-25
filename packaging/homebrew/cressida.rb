# Homebrew formula for CRESSIDA.
#
# LIVE at https://github.com/SlipStream90/homebrew-cressida (Formula/cressida.rb).
# This copy is kept in-repo for reference/history — edit the tap directly (or
# push here and mirror over) when cutting a new release. Friends install with:
#
#   brew tap SlipStream90/cressida
#   brew install cressida
#
# To cut a new version:
#   1. git tag vX.Y.Z && git push origin vX.Y.Z
#   2. curl -sL https://github.com/SlipStream90/Cressida/archive/refs/tags/vX.Y.Z.tar.gz | shasum -a 256
#   3. Bump `url` and `sha256` below (and in the tap repo).
#
# Note on dependency resolution: this installs into an isolated venv via pip
# rather than Homebrew's `Language::Python::Virtualenv` + `resource` blocks
# mechanism (the latter needs `brew update-python-resources`, run from a
# machine with Homebrew installed, which wasn't available when this was
# authored). It's still fully isolated — it just fetches deps from PyPI at
# install time instead of vendoring them. A contribution to migrate to
# `resource` blocks for fully hermetic/offline builds is welcome.
class Cressida < Formula
  desc "Autonomous multi-agent software engineering intelligence framework"
  homepage "https://github.com/SlipStream90/Cressida"
  url "https://github.com/SlipStream90/Cressida/archive/refs/tags/v0.1.0.tar.gz"
  sha256 "1354a2f2c4ab06f5280304b287e7280e6b5b6c172474dc3fee3244b0d45a9650"
  license "MIT"

  depends_on "python@3.12"

  def install
    python3 = Formula["python@3.12"].opt_bin/"python3.12"
    venv = libexec
    system python3, "-m", "venv", venv
    system venv/"bin/pip", "install", "--upgrade", "pip"
    system venv/"bin/pip", "install", "."

    bin.install_symlink venv/"bin/cressida"
    bin.install_symlink venv/"bin/cressida-mcp"
  end

  def caveats
    <<~EOS
      CRESSIDA is keyless if you already have the Claude Code or opencode
      CLI installed and logged in. Otherwise set a provider key, e.g.:
        export ANTHROPIC_API_KEY=sk-...

      Register the MCP server with Claude Code:
        claude mcp add-json cressida '{"command":"#{opt_bin}/cressida-mcp","args":[]}' --scope user

      Then restart Claude Code and call the cressida_status tool.
    EOS
  end

  test do
    assert_match "0.1.0", shell_output("#{bin}/cressida --version")
  end
end
