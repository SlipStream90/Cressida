"""Tests for core/retrieval/extract.py's readability-style HTML extractor."""

from __future__ import annotations

from cressida.core.retrieval.extract import extract_main_content


_SAMPLE_HTML = """
<!doctype html>
<html>
<head><title>Test Page</title><style>body { color: red; }</style></head>
<body>
  <nav class="site-nav">
    <ul><li><a href="/">Home</a></li><li><a href="/about">About</a></li></ul>
  </nav>
  <header class="page-header">Cool Site</header>
  <script>console.log("tracking pixel fired");</script>
  <main>
    <article>
      <h1>Widgets Are Great</h1>
      <p>This article explains why widgets are the best invention since sliced bread.</p>
      <p>Widgets come in many shapes and colors, and everyone should own at least one.</p>
    </article>
  </main>
  <aside class="sidebar">Related links go here.</aside>
  <footer class="site-footer">Copyright 2026. All rights reserved.</footer>
</body>
</html>
"""


def test_extract_strips_script_and_style_content():
    result = extract_main_content(_SAMPLE_HTML)
    assert "console.log" not in result
    assert "tracking pixel" not in result
    assert "color: red" not in result


def test_extract_strips_nav_boilerplate():
    result = extract_main_content(_SAMPLE_HTML)
    assert "Home" not in result
    assert "About" not in result


def test_extract_strips_footer_and_sidebar_boilerplate():
    result = extract_main_content(_SAMPLE_HTML)
    assert "Copyright 2026" not in result
    assert "Related links go here" not in result


def test_extract_keeps_main_body_text():
    result = extract_main_content(_SAMPLE_HTML)
    assert "Widgets Are Great" in result
    assert "best invention since sliced bread" in result
    assert "many shapes and colors" in result


def test_extract_handles_empty_input():
    assert extract_main_content("") == ""
    assert extract_main_content(None) == ""  # type: ignore[arg-type]
