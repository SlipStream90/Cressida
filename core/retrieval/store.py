from __future__ import annotations

"""FAISS-backed persistent retrieval store — the Tier-2 "stable knowledge"
half of the two-tier RAG design (CRESSIDA_ROBUSTNESS_AND_RETRIEVAL_PLAN.md
§4.2).

Embeddings: a deterministic feature-hashing bag-of-words vector, not a
learned embedding model. The plan's intent was "embed query -> FAISS
similarity search"; a real sentence-embedding model (sentence-transformers +
torch, or a hosted embeddings API) would give better recall, but it's a heavy
new dependency for a project whose existing tool implementations are
deliberately stdlib-first (core/tools/implementations.py has zero
third-party HTTP/HTML deps — just urllib + re), and this is explicitly a
single-user, local-first store where "good enough" nearest-neighbor recall
over recent web fetches and playbook text matters more than embedding-model
fidelity. Feature hashing (the trick behind scikit-learn's
HashingVectorizer) gives a stable, model-free, dependency-free vector: token
counts hashed into a fixed number of signed buckets, L2-normalized, compared
by cosine similarity via FAISS's inner-product index. It captures
lexical/keyword overlap, not deep semantics. `embed_text` is the one function
to swap for a real embedding model later — the FAISS index format
(IndexIDMap2 over IndexFlatIP, fixed `dim`) and every caller are unaffected
since nobody but this module touches raw vectors.

Storage layout (under `base_path`; default resolves to
``cressida_home() / "knowledge/retrieval"`` via ``_default_store_path``, so it
is independent of the process working directory — see that function's note about
why a bare relative default would break the write-back cache):
    index.faiss   — the FAISS IndexIDMap2(IndexFlatIP) index
    meta.sqlite3  — text/source/tags/topic/timestamp per doc, keyed by the
                    same int id used in the FAISS index

Single-user, single-writer — no locking/concurrency handling, per the plan's
explicit scope ("Single-user, local-first — no concurrency/multi-writer
concerns").
"""

import hashlib
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import faiss


DEFAULT_DIM = 256
_DEFAULT_STORE_REL = "knowledge/retrieval"
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _default_store_path() -> Path:
    """Resolve the RAG store's base directory through the package's canonical
    path logic (core/paths.cressida_home) instead of a bare relative path.

    A relative default would be resolved against the process working directory,
    so the FAISS index + SQLite sidecar would land in whatever folder Cressida
    happened to be launched from — and, worse, a *different* folder each time
    (the user's project, the CWD, …), which silently defeats the whole point of
    the write-back cache ("the next call on this topic is a RAG hit"). Every
    other stateful path in the package goes through core/paths, so this does too.
    """
    from cressida.core.paths import cressida_home

    return cressida_home() / _DEFAULT_STORE_REL


def embed_text(text: str, dim: int = DEFAULT_DIM) -> np.ndarray:
    """Deterministic feature-hashing bag-of-words embedding.

    Each token hashes (via blake2b, not Python's salted `hash()`, so this is
    stable across process restarts and PYTHONHASHSEED values — important
    since the FAISS index is persisted to disk and re-embedding the same
    query later must land in the same buckets) to a bucket in [0, dim) with a
    pseudo-random sign, then the accumulated vector is L2-normalized so FAISS
    inner-product search behaves as cosine similarity. See module docstring
    for why this isn't a learned embedding model.
    """
    vec = np.zeros(dim, dtype="float32")
    tokens = _TOKEN_RE.findall((text or "").lower())
    for tok in tokens:
        digest = hashlib.blake2b(tok.encode("utf-8"), digest_size=8).digest()
        bucket = int.from_bytes(digest[:4], "big") % dim
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vec[bucket] += sign
    norm = float(np.linalg.norm(vec))
    if norm > 0:
        vec /= norm
    return vec


class RetrievalStore:
    """Local FAISS index + SQLite metadata sidecar."""

    def __init__(self, base_path: str | Path | None = None, dim: int = DEFAULT_DIM) -> None:
        self._base = Path(base_path) if base_path is not None else _default_store_path()
        self._base.mkdir(parents=True, exist_ok=True)
        self._dim = dim
        self._index_path = self._base / "index.faiss"
        self._db_path = self._base / "meta.sqlite3"
        self._index = self._load_or_create_index()
        self._conn = sqlite3.connect(str(self._db_path))
        self._init_db()

    def _load_or_create_index(self) -> "faiss.Index":
        if self._index_path.exists():
            try:
                return faiss.read_index(str(self._index_path))
            except Exception:
                pass  # corrupt/foreign index file — rebuild rather than crash the caller
        return faiss.IndexIDMap2(faiss.IndexFlatIP(self._dim))

    def _init_db(self) -> None:
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS docs ("
            "id INTEGER PRIMARY KEY, text TEXT, source TEXT, tags TEXT, "
            "topic TEXT, created_at TEXT)"
        )
        self._conn.commit()

    def _next_id(self) -> int:
        row = self._conn.execute("SELECT COALESCE(MAX(id), -1) FROM docs").fetchone()
        return int(row[0]) + 1

    def ingest(
        self,
        text: str,
        source: str = "",
        tags: list[str] | None = None,
        topic: str = "general",
    ) -> int:
        """Add a (text, source, tags) document to the index. Returns its id.

        Persists to disk on every call (index.write + sqlite commit) rather
        than batching — this is a single-user local store, not a high-QPS
        write path, so the simplicity of "always durable" wins over the
        complexity of a flush/batch API nobody here needs yet.
        """
        doc_id = self._next_id()
        vec = embed_text(text, self._dim).reshape(1, -1)
        self._index.add_with_ids(vec, np.array([doc_id], dtype="int64"))
        self._conn.execute(
            "INSERT INTO docs (id, text, source, tags, topic, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (doc_id, text, source, json.dumps(tags or []), topic, datetime.now().isoformat()),
        )
        self._conn.commit()
        self._save_index()
        return doc_id

    def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Cosine-similarity search. Returns docs sorted by descending score,
        each carrying `score` (inner product of L2-normalized vectors, i.e.
        cosine similarity in [-1, 1]) plus its stored metadata."""
        if self._index.ntotal == 0:
            return []
        vec = embed_text(query, self._dim).reshape(1, -1)
        k = min(top_k, self._index.ntotal)
        scores, ids = self._index.search(vec, k)
        results: list[dict[str, Any]] = []
        for score, doc_id in zip(scores[0], ids[0]):
            if doc_id < 0:
                continue
            row = self._conn.execute(
                "SELECT text, source, tags, topic, created_at FROM docs WHERE id = ?",
                (int(doc_id),),
            ).fetchone()
            if row is None:
                continue
            text, source, tags_json, topic, created_at = row
            results.append({
                "id": int(doc_id),
                "score": float(score),
                "text": text,
                "source": source,
                "tags": json.loads(tags_json or "[]"),
                "topic": topic,
                "created_at": created_at,
            })
        return results

    def _save_index(self) -> None:
        faiss.write_index(self._index, str(self._index_path))

    def count(self) -> int:
        return int(self._index.ntotal)
