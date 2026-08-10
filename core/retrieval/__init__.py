from __future__ import annotations

"""Two-tier RAG + web search + summarizer retrieval layer.

See CRESSIDA_ROBUSTNESS_AND_RETRIEVAL_PLAN.md §4 for the design this package
implements: a persistent FAISS-backed store (Tier 2, "stable knowledge") that
is checked first, a staleness/similarity heuristic that decides whether a hit
is trustworthy, and a fall-through to live web search + extraction +
summarization (Tier 1, "volatile/current") when it isn't — writing the result
back into the store so the next query is a cache hit.

Wired in behind `core/tools/implementations.py::_query_memory` — LEITER and
INTELLIGENCE need no new tool grant to get this.
"""

from .extract import extract_main_content
from .summarize import summarize_page
from .store import RetrievalStore, embed_text
from .router import RetrievalRouter, classify_topic, rerank
from .ingest import ingest_text, ingest_learning_insights, ingest_playbook_store

__all__ = [
    "extract_main_content",
    "summarize_page",
    "RetrievalStore",
    "embed_text",
    "RetrievalRouter",
    "classify_topic",
    "rerank",
    "ingest_text",
    "ingest_learning_insights",
    "ingest_playbook_store",
]
