from __future__ import annotations

"""Lightweight readability-style HTML content extractor.

Stdlib-only (re + html), matching core/tools/implementations.py's existing
extraction style (that module has zero third-party HTML/HTTP deps — just
urllib + re) rather than pulling in readability-lxml or BeautifulSoup. This
runs once per fetched page inside an agent's tool call, not over a batch
crawl, so a bounded regex heuristic is proportionate to the job.

Two passes:
  1. Structural removal — drop entire boilerplate containers (script/style/
     nav/header/footer/aside/form/iframe/button/select/template) and any
     element whose class/id looks like chrome (nav, menu, sidebar, footer,
     ad, cookie, banner, social, share, comment, breadcrumb, pagination)
     before any text is extracted, so their contents never reach the output.
  2. Block-to-newline conversion + tag stripping (same shape as the previous
     inline logic in _fetch_url), so paragraph/heading structure survives as
     line breaks.

This is a heuristic, not a real DOM parser: `_BOILERPLATE_CLASS_RE`'s
backreference match assumes non-nested (or shallowly nested, handled by
repeated passes) matching same-tag-name blocks. It will not correctly find
the single "main article" on a complex page the way a true readability
algorithm (content-density scoring over a DOM tree) would — it only removes
obvious chrome. Good enough to stop a summarizer from spending tokens on nav
links and cookie banners, which is the actual problem this exists to solve.
"""

import html as _html
import re


_BOILERPLATE_TAGS: tuple[str, ...] = (
    "script", "style", "noscript", "svg", "head", "nav", "header", "footer",
    "aside", "form", "iframe", "button", "select", "template",
)

_BOILERPLATE_CLASS_RE = re.compile(
    r"(?is)<(div|section|ul|li|span)\b[^>]*"
    r"(?:class|id)\s*=\s*[\"'][^\"']*"
    r"(nav|menu|sidebar|footer|header|advert|banner|cookie|social|share|"
    r"comment|breadcrumb|pagination)[^\"']*[\"'][^>]*>.*?</\1>"
)


def _strip_boilerplate_tags(text: str) -> str:
    for tag in _BOILERPLATE_TAGS:
        text = re.sub(rf"(?is)<{tag}\b.*?</{tag}>", " ", text)
        text = re.sub(rf"(?is)<{tag}\b[^>]*/?>", " ", text)  # stray self-closing/unclosed
    return text


def _strip_boilerplate_by_class(text: str, passes: int = 3) -> str:
    """Repeated non-nested-regex passes approximate removing shallowly nested
    boilerplate (e.g. a nav <div> containing a nav <ul>) without a real DOM
    tree — each pass removes what it can see; we stop once nothing changes."""
    for _ in range(passes):
        new_text = _BOILERPLATE_CLASS_RE.sub(" ", text)
        if new_text == text:
            break
        text = new_text
    return text


def extract_main_content(html_text: str) -> str:
    """Strip boilerplate chrome from an HTML page and return readable body text.

    Not full readability (no content-density scoring / DOM tree) — see module
    docstring for the tradeoff. Falls back gracefully on malformed HTML since
    every step is a regex substitution, never a strict parse.
    """
    text = html_text or ""
    text = re.sub(r"(?is)<!--.*?-->", " ", text)
    text = _strip_boilerplate_by_class(text)
    text = _strip_boilerplate_tags(text)
    text = re.sub(r"(?i)<(br|/p|/div|/li|/h[1-6]|/tr|/article|/section)\s*/?>", "\n", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = _html.unescape(text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    text = "\n".join(line.strip() for line in text.split("\n")).strip()
    return text
