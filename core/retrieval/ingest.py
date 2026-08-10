from __future__ import annotations

"""Ingestion paths into the RetrievalStore.

Two paths share one index (plan §4.2):
  (a) `ingest_text` — arbitrary (text, source, tags) tuples. Used directly by
      `core/retrieval/router.py::RetrievalRouter._fallback_to_web` for
      web-search write-back, and available for any other caller.
  (b) `ingest_learning_insights` / `ingest_playbook_store` — pulls from the
      existing learning layer (learning/reflection.py, learning/playbook.py)
      so mission experience becomes searchable automatically, without a
      separate crawler.

Wiring note: this module intentionally does NOT call itself automatically
from anywhere in orchestration/. `orchestration/coordinator.py` already calls
`_learn_from_mission` (which drives `ReflectionEngine.reflect_on_mission`)
and is explicitly off-limits for this workstream (a parallel workstream owns
it this session — see CRESSIDA_ROBUSTNESS_AND_RETRIEVAL_PLAN.md's header).
The natural call site, once this lands, is right after
`ReflectionEngine.reflect_on_mission(...)` returns its `list[Insight]` inside
`coordinator.py::_learn_from_mission`:

    insights = reflection_engine.reflect_on_mission(state, ...)
    from cressida.core.retrieval.ingest import ingest_learning_insights
    ingest_learning_insights(insights)

`ingest_playbook_store` is for a one-off/periodic backfill of everything
already accumulated in `knowledge/playbooks/*.json` (e.g. run once after
adopting this module, or from a maintenance script) — it is not meant to run
on every mission the way `ingest_learning_insights` is.
"""

from typing import Any

from .router import classify_topic
from .store import RetrievalStore


def ingest_text(
    text: str,
    source: str = "",
    tags: list[str] | None = None,
    store: RetrievalStore | None = None,
) -> int:
    """Ingest an arbitrary (text, source, tags) tuple. Topic is classified
    from the text itself so staleness routing (router.py) has something to
    key off later. Returns the store-assigned doc id."""
    store = store or RetrievalStore()
    topic = classify_topic(text)
    return store.ingest(text=text, source=source, tags=tags or [], topic=topic)


def ingest_learning_insights(insights: list[Any], store: RetrievalStore | None = None) -> int:
    """Turn a batch of `learning/reflection.py::Insight` objects (or
    equivalent dicts with role/text/source/tags) into searchable RAG
    documents. Returns how many were ingested. Best-effort: a malformed
    insight is skipped, not fatal to the batch, matching ReflectionEngine's
    own "never break mission finalisation" posture.
    """
    store = store or RetrievalStore()
    count = 0
    for ins in insights:
        text = getattr(ins, "text", None)
        if text is None and isinstance(ins, dict):
            text = ins.get("text")
        text = (text or "").strip()
        if not text:
            continue

        role = getattr(ins, "role", None)
        if role is None and isinstance(ins, dict):
            role = ins.get("role")
        role = str(role or "").strip()

        source = getattr(ins, "source", None)
        if source is None and isinstance(ins, dict):
            source = ins.get("source")

        tags = getattr(ins, "tags", None)
        if tags is None and isinstance(ins, dict):
            tags = ins.get("tags")
        tags = list(tags or []) + ["learning"]

        labeled = f"[{role}] {text}" if role else text
        ingest_text(labeled, source=source or "learning:reflection", tags=tags, store=store)
        count += 1
    return count


def ingest_playbook_store(playbook_store: Any, store: RetrievalStore | None = None) -> int:
    """Bulk-ingest every role's current playbook entries
    (`learning/playbook.py::PlaybookStore`) into the RAG index — a backfill
    for knowledge that accumulated before this module existed, or a periodic
    resync. Returns how many entries were ingested."""
    store = store or RetrievalStore()
    count = 0
    for role in playbook_store.all_roles():
        for entry in playbook_store.entries(role):
            text = f"[{role}] {entry.text}"
            tags = list(getattr(entry, "tags", None) or []) + ["playbook", role.lower()]
            source = getattr(entry, "source", None) or f"playbook:{role}"
            ingest_text(text, source=source, tags=tags, store=store)
            count += 1
    return count
