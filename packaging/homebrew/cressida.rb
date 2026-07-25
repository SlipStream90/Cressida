# Homebrew formula for CRESSIDA.
#
# This is NOT installable as-is — Homebrew needs a tagged release tarball and a
# tap. To publish it:
#
#   1. Cut a release:   git tag v0.1.0 && git push origin v0.1.0
#      (or create it on GitHub → Releases). This gives the `url` below a real
#      tarball. Then fill in `sha256`:
#         curl -sL https://github.com/SlipStream90/Cressida/archive/refs/tags/v0.1.0.tar.gz | shasum -a 256
#
#   2. Create a tap repo named `homebrew-cressida` under your account and put
#      this file at `Formula/cressida.rb`.
#
#   3. Generate the Python dependency `resource` blocks (Homebrew vendors deps):
#         brew update-python-resources Formula/cressida.rb
#
#   4. Friends then install with:
#         brew tap SlipStream90/cressida
#         brew install cressida
#
class Cressida < Formula
  include Language::Python::Virtualenv

  desc "Autonomous multi-agent software engineering intelligence framework"
  homepage "https://github.com/SlipStream90/Cressida"
  url "https://github.com/SlipStream90/Cressida/archive/refs/tags/v0.1.0.tar.gz"
  sha256 "REPLACE_WITH_TARBALL_SHA256"
  license "MIT"

  depends_on "python@3.12"

  # `brew update-python-resources` fills the `resource "..." do ... end`
  # blocks for mcp, aiohttp, pydantic, pyyaml, rich, click, and their deps here.

  def install
    virtualenv_install_with_resources
  end

  test do
    assert_match "0.1.0", shell_output("#{bin}/cressida --version")
  end
end
