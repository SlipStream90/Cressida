"""Tests for the retrieval store (FAISS + SQLite) and the RAG/web router.

No live network calls: web_search/fetch_url are always passed in as fakes
via RetrievalRouter.route(..., web_search_fn=..., fetch_url_fn=...) rather
than letting the router import the real cressida.core.tools.implementations
functions, which would hit Brave/DuckDuckGo over HTTP.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from cressida.core.retrieval.store import RetrievalStore, embed_text
from cressida.core.retrieval.router import (
    RetrievalRouter,
    classify_topic,
    rerank,
    _parse_search_results,
)
from cressida.core.retrieval.ingest import ingest_text, ingest_learning_insights


# ── store round-trip ─────────────────────────────────────────────────────────

def test_store_ingest_then_search_returns_ingested_item(tmp_path):
    store = RetrievalStore(base_path=tmp_path / "rag")
    doc_id = store.ingest(
        text="React hooks let you use state in function components.",
        source="https://example.com/react-hooks",
        tags=["react", "hooks"],
        topic="library_version",
    )
    assert isinstance(doc_id, int)

    results = store.search("react hooks function components", top_k=3)
    assert results, "expected at least one hit"
    top = results[0]
    assert top["id"] == doc_id
    assert top["source"] == "https://example.com/react-hooks"
    assert "React hooks" in top["text"]
    assert top["topic"] == "library_version"


def test_store_persists_across_reopen(tmp_path):
    base = tmp_path / "rag"
    store1 = RetrievalStore(base_path=base)
    store1.ingest(text="Cressida uses a BOND gate to approve mission phases.", source="internal")

    store2 = RetrievalStore(base_path=base)
    results = store2.search("BOND gate approve mission phases", top_k=3)
    assert results
    assert "BOND gate" in results[0]["text"]


def test_empty_store_search_returns_no_results(tmp_path):
    store = RetrievalStore(base_path=tmp_path / "rag_empty")
    assert store.search("anything at all") == []


def test_embed_text_is_deterministic_and_normalized():
    v1 = embed_text("hello world")
    v2 = embed_text("hello world")
    assert (v1 == v2).all()
    norm = float((v1 ** 2).sum() ** 0.5)
    assert abs(norm - 1.0) < 1e-5 or norm == 0.0


# ── topic classification / rerank ────────────────────────────────────────────

def test_classify_topic_library_version():
    assert classify_topic("what is the latest npm install version of react") == "library_version"


def test_classify_topic_architecture():
    assert classify_topic("what design pattern and architecture principle applies here") == "architecture"


def test_classify_topic_general_fallback():
    assert classify_topic("how do birds migrate south for winter") == "general"


def test_rerank_orders_by_keyword_overlap():
    candidates = [
        {"text": "completely unrelated content about gardening"},
        {"text": "kubernetes pod eviction memory pressure kubernetes kubernetes"},
        {"text": "kubernetes basics overview"},
    ]
    ranked = rerank("kubernetes pod eviction memory", candidates, text_key="text")
    assert ranked[0]["text"].startswith("kubernetes pod eviction")


def test_parse_search_results_brave_style_with_url():
    raw = "**Title One**\nhttps://example.com/one\nSome description text.\n\n**Title Two**\nhttps://example.com/two\nMore description."
    parsed = _parse_search_results(raw)
    assert len(parsed) == 2
    assert parsed[0]["url"] == "https://example.com/one"
    assert parsed[0]["title"] == "Title One"


def test_parse_search_results_duckduckgo_style_without_url():
    raw = "**Title One**\nSnippet with no url line at all."
    parsed = _parse_search_results(raw)
    assert len(parsed) == 1
    assert parsed[0]["url"] == ""


# ── staleness routing ────────────────────────────────────────────────────────

def _fake_web_search(query, num_results=5, mission_id=""):
    return "**Fresh Result**\nhttps://example.com/fresh\nThis snippet is about " + query


def _fake_fetch_url(url, max_chars=12000, mission_id=""):
    return f"# Fetched: {url}\n\nFull page content discussing the query topic in depth. " * 3


def test_router_uses_rag_hit_when_fresh_and_similar(tmp_path):
    store = RetrievalStore(base_path=tmp_path / "rag")
    store.ingest(
        text="Docker containers isolate processes using Linux namespaces and cgroups.",
        source="internal-note",
        tags=["docker"],
        topic="general",
    )
    router = RetrievalRouter(store=store, similarity_threshold=0.1)

    called = {"web": False}

    def fail_if_called(*a, **kw):
        called["web"] = True
        return "should not be called"

    result = router.route(
        "docker containers isolate processes namespaces cgroups",
        web_search_fn=fail_if_called,
        fetch_url_fn=fail_if_called,
    )
    assert called["web"] is False
    assert "Docker containers isolate processes" in result
    assert result.startswith("[rag:")


def test_router_falls_through_to_web_when_store_empty(tmp_path):
    store = RetrievalStore(base_path=tmp_path / "rag_empty")
    router = RetrievalRouter(store=store, similarity_threshold=0.1)

    result = router.route(
        "some brand new query nothing knows about",
        mission_id="",
        web_search_fn=_fake_web_search,
        fetch_url_fn=_fake_fetch_url,
    )
    assert "[web:https://example.com/fresh]" in result
    # write-back happened — the store should now have the summarized page.
    assert store.count() == 1


def test_router_falls_through_to_web_when_rag_hit_is_stale(tmp_path):
    store = RetrievalStore(base_path=tmp_path / "rag_stale")
    doc_id = store.ingest(
        text="React 17 release notes and migration guide for the new JSX transform.",
        source="https://example.com/react17",
        tags=["react"],
        topic="library_version",
    )
    # Force the row's created_at far in the past — library_version staleness
    # limit is 14 days, so 400 days ago is well past it.
    old_ts = (datetime.now() - timedelta(days=400)).isoformat()
    store._conn.execute("UPDATE docs SET created_at = ? WHERE id = ?", (old_ts, doc_id))
    store._conn.commit()

    router = RetrievalRouter(store=store, similarity_threshold=0.1)
    result = router.route(
        "react latest version release notes migration guide",
        web_search_fn=_fake_web_search,
        fetch_url_fn=_fake_fetch_url,
    )
    assert "[web:https://example.com/fresh]" in result


def test_router_never_raises_on_web_search_exception(tmp_path):
    store = RetrievalStore(base_path=tmp_path / "rag_err")
    router = RetrievalRouter(store=store)

    def boom(*a, **kw):
        raise RuntimeError("network down")

    result = router.route("anything", web_search_fn=boom, fetch_url_fn=boom)
    assert "error" in result.lower()


# ── ingestion paths ──────────────────────────────────────────────────────────

def test_ingest_text_writes_to_store_and_is_retrievable(tmp_path):
    store = RetrievalStore(base_path=tmp_path / "rag")
    ingest_text("GraphQL uses a single endpoint for all queries.", source="notes", store=store)
    results = store.search("graphql single endpoint queries")
    assert results
    assert "GraphQL" in results[0]["text"]


class _FakeInsight:
    def __init__(self, role, text, source="", tags=None):
        self.role = role
        self.text = text
        self.source = source
        self.tags = tags or []


def test_ingest_learning_insights_batches_into_store(tmp_path):
    store = RetrievalStore(base_path=tmp_path / "rag")
    insights = [
        _FakeInsight("LEITER", "Prefer official docs over blog posts for API references.", source="mission:m1"),
        _FakeInsight("BOND", "Watch out: rejected plans lacking rollback steps.", source="mission:m1"),
        _FakeInsight("EMPTY", ""),  # malformed/blank — should be skipped
    ]
    count = ingest_learning_insights(insights, store=store)
    assert count == 2
    assert store.count() == 2
    results = store.search("official docs API references")
    assert results
    assert "official docs" in results[0]["text"].lower()
