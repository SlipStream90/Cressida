from __future__ import annotations

"""Tier routing: RAG-first, staleness-checked, falling through to live web +
extraction + summarization + write-back
(CRESSIDA_ROBUSTNESS_AND_RETRIEVAL_PLAN.md §4.3). Deliberately a heuristic,
not a learned router — explicitly deferred by the plan; query volume doesn't
justify one yet.

This is the layer `core/tools/implementations.py::_query_memory` calls into,
so LEITER/INTELLIGENCE get the RAG/web split with no new tool grant (§4.4).
"""

import re
from datetime import datetime
from typing import Any, Callable

from .store import RetrievalStore
from .summarize import summarize_page


# Per-topic staleness limits (days). Library/version docs go stale fast;
# architectural/pattern knowledge barely does. Keyword-based classification
# is the plan's stated v1 simplification (no learned router).
_TOPIC_STALENESS_DAYS: dict[str, int] = {
    "library_version": 14,
    "architecture": 365,
    "general": 90,
}

_LIBRARY_KEYWORDS = (
    "version", "release", "changelog", "npm install", "pip install",
    "latest", "package", "dependency", "cve", "deprecated", "migration guide",
)
_ARCHITECTURE_KEYWORDS = (
    "architecture", "design pattern", "adr", "decision record", "principle",
    "methodology", "best practice", "convention",
)

# Cosine similarity on hashed bag-of-words vectors (see store.py::embed_text)
# runs lower than a real embedding model's would for genuinely-related text,
# since it only rewards literal token overlap — tuned low deliberately so a
# reasonable keyword match still counts as a RAG hit.
_DEFAULT_SIMILARITY_THRESHOLD = 0.15


def classify_topic(text: str) -> str:
    lower = (text or "").lower()
    if any(kw in lower for kw in _LIBRARY_KEYWORDS):
        return "library_version"
    if any(kw in lower for kw in _ARCHITECTURE_KEYWORDS):
        return "architecture"
    return "general"


def rerank(query: str, candidates: list[dict[str, Any]], text_key: str = "text") -> list[dict[str, Any]]:
    """Cheap keyword-overlap rerank (plan §4.1/§4.7) — run over multi-result
    web_search output before any fetch happens, so a low-relevance hit
    doesn't burn a fetch+summarize cycle, and again over RAG hits before the
    staleness check picks a winner."""
    terms = set(re.findall(r"\w+", (query or "").lower()))
    if not terms:
        return list(candidates)

    def score(c: dict[str, Any]) -> int:
        text = str(c.get(text_key) or "").lower()
        return sum(text.count(t) for t in terms)

    return sorted(candidates, key=score, reverse=True)


def _age_days(iso_timestamp: str) -> float:
    try:
        dt = datetime.fromisoformat(iso_timestamp)
    except Exception:
        return float("inf")  # unparseable timestamp -> treat as maximally stale
    return (datetime.now() - dt).total_seconds() / 86400.0


def _parse_search_results(raw: str) -> list[dict[str, str]]:
    """Parse `_web_search`'s plaintext output back into structured candidates.

    Brave results are '**title**\\nurl\\ndescription' blocks separated by a
    blank line; the DuckDuckGo fallback omits the URL entirely
    ('**title**\\nsnippet'). Candidates without a URL are still returned
    (rerank still works on snippet text) but get skipped at fetch time since
    there's nothing to fetch — see `_fallback_to_web`.
    """
    candidates: list[dict[str, str]] = []
    for block in (raw or "").split("\n\n"):
        block = block.strip()
        if not block:
            continue
        lines = block.split("\n")
        title_match = re.match(r"^\*\*(.*?)\*\*$", lines[0].strip())
        if not title_match:
            continue
        title = title_match.group(1)
        rest = lines[1:]
        url = ""
        if rest and rest[0].strip().lower().startswith(("http://", "https://")):
            url = rest[0].strip()
            rest = rest[1:]
        snippet = " ".join(l.strip() for l in rest if l.strip())
        candidates.append({"title": title, "url": url, "snippet": snippet})
    return candidates


class RetrievalRouter:
    """RAG-first / staleness-checked / web-fallback decision layer."""

    def __init__(
        self,
        store: RetrievalStore | None = None,
        similarity_threshold: float = _DEFAULT_SIMILARITY_THRESHOLD,
        top_k: int = 5,
        max_fetches: int = 2,
    ) -> None:
        self._store = store or RetrievalStore()
        self._similarity_threshold = similarity_threshold
        self._top_k = top_k
        self._max_fetches = max_fetches

    def route(
        self,
        query: str,
        mission_id: str = "",
        web_search_fn: Callable[..., str] | None = None,
        fetch_url_fn: Callable[..., str] | None = None,
    ) -> str:
        """RAG-first: if the store has a fresh, similar-enough match, return
        it. Otherwise fall through to live web search, rerank, fetch the top
        candidates, summarize each against the query, write the summaries
        back into the store (so the next call on this topic is a RAG hit),
        and return them. Never raises — mirrors the existing tool
        implementations' exception-safe, best-effort style.
        """
        try:
            return self._route(query, mission_id, web_search_fn, fetch_url_fn)
        except Exception as exc:
            return f"Retrieval router error: {exc}"

    def _route(
        self,
        query: str,
        mission_id: str,
        web_search_fn: Callable[..., str] | None,
        fetch_url_fn: Callable[..., str] | None,
    ) -> str:
        topic = classify_topic(query)
        max_age_days = _TOPIC_STALENESS_DAYS.get(topic, _TOPIC_STALENESS_DAYS["general"])

        hits = self._store.search(query, top_k=self._top_k)
        fresh_hits = [
            h for h in hits
            if h["score"] >= self._similarity_threshold and _age_days(h["created_at"]) <= max_age_days
        ]
        if fresh_hits:
            fresh_hits = rerank(query, fresh_hits, text_key="text")
            return self._format_rag_hits(fresh_hits)

        return self._fallback_to_web(query, topic, mission_id, web_search_fn, fetch_url_fn)

    def _fallback_to_web(
        self,
        query: str,
        topic: str,
        mission_id: str,
        web_search_fn: Callable[..., str] | None,
        fetch_url_fn: Callable[..., str] | None,
    ) -> str:
        # Lazy imports: core/tools/implementations.py imports this module at
        # module level (to call RetrievalRouter from _query_memory), so
        # importing it back here at module load time would be circular.
        # Deferring to call time breaks the cycle — the same pattern
        # _query_memory itself already uses for cressida.memory.retrieval /
        # cressida.obsidian.bridge.
        if web_search_fn is None:
            from cressida.core.tools.implementations import _web_search as web_search_fn
        if fetch_url_fn is None:
            from cressida.core.tools.implementations import _fetch_url as fetch_url_fn

        raw = web_search_fn(query, num_results=5, mission_id=mission_id)
        candidates = _parse_search_results(raw)
        candidates = rerank(query, candidates, text_key="snippet")

        summaries: list[str] = []
        for candidate in candidates:
            if len(summaries) >= self._max_fetches:
                break
            url = candidate.get("url")
            if not url:
                continue
            page = fetch_url_fn(url, mission_id=mission_id)
            if page.startswith("ERROR") or "extracted no readable text" in page:
                continue
            summary = summarize_page(page, query)
            if not summary:
                continue
            summaries.append(f"[web:{url}]\n{summary}")
            self._store.ingest(summary, source=url, tags=[topic], topic=topic)

        if summaries:
            return "\n\n---\n\n".join(summaries)
        # Nothing fetchable (no URLs — e.g. the DuckDuckGo fallback — or every
        # fetch failed) — still better than nothing: hand back raw snippets.
        return raw or f"No results for: {query}"

    @staticmethod
    def _format_rag_hits(hits: list[dict[str, Any]]) -> str:
        parts = [f"[rag:{h.get('source') or h['id']}]\n{h['text']}" for h in hits]
        return "\n\n---\n\n".join(parts)
