from __future__ import annotations

"""Query-aware page summarizer for the retrieval layer.

Design note / documented v1 tradeoff
-------------------------------------
The plan (CRESSIDA_ROBUSTNESS_AND_RETRIEVAL_PLAN.md §4.1) calls for an LLM
map-reduce summarizer: chunk, summarize each chunk against the query via an
LLM call, then a combine pass. This codebase's only LLM call paths are
core/providers/*Agent, and every one of them is built for a full agentic
*task turn* (spec loading, context injection, output writing), not a cheap
"string in, string out" utility call this module could invoke synchronously
and repeatedly inside a single web_search/fetch_url round:
  - ClaudeCLIAgent shells out to the `claude` binary per call — several
    seconds of subprocess + CLI startup overhead per fetched page, and
    calling it recursively from inside a tool an *agent* invokes (itself
    possibly already running through the CLI) risks nested-subprocess and
    timeout issues neither this module nor claude_cli_agent.py's design
    accounts for.
  - The anthropic/openai/gemini/groq providers need an API key in the
    environment, which is not guaranteed to be set (the CLI path exists
    specifically because it isn't, in this environment).
Standing up a new minimal "cheap completion" provider integration was out of
this pass's explicit scope. So this is a documented extractive fallback:
keyword/position-scored sentence extraction, run map-reduce style over
chunks for long text, per the plan's explicit allowance for this tradeoff.
It is NOT a semantic summary — it is a shortening that keeps the sentences
most relevant to the query. The (text, query) -> str contract is stable, so
swapping this module's internals for a real LLM call later needs no changes
in callers (core/retrieval/router.py, core/tools/implementations.py).
"""

import re


# ~4k tokens at a ~4-chars/token rule of thumb, per the plan's stated
# map-reduce threshold.
_CHUNK_CHAR_THRESHOLD = 16_000

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")
_WORD_RE = re.compile(r"\w+")


def _split_sentences(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []
    parts = _SENTENCE_RE.split(text)
    out: list[str] = []
    for p in parts:
        # Also split on newlines within a "sentence" so bullet lists / headings
        # (which often lack terminal punctuation) still score as separate units.
        out.extend(s.strip() for s in p.split("\n") if s.strip())
    return out or [text]


def _chunk_text(text: str, max_chars: int = _CHUNK_CHAR_THRESHOLD) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            # Prefer breaking on a paragraph boundary near the cut point.
            cut = text.rfind("\n\n", start, end)
            if cut > start + max_chars // 2:
                end = cut
        chunks.append(text[start:end])
        start = end
    return chunks


def _score_sentence(sentence: str, query_terms: set[str], position: int, total: int) -> float:
    words = _WORD_RE.findall(sentence.lower())
    if not words:
        return 0.0
    overlap = sum(1 for w in words if w in query_terms)
    keyword_score = overlap / max(len(query_terms), 1)
    # Lead bias: opening sentences of a page/chunk disproportionately state
    # what the page is about (titles, intros, TL;DRs).
    position_score = 1.0 - (position / max(total, 1)) * 0.5
    length_penalty = 1.0 if 6 <= len(words) <= 60 else 0.6
    return (keyword_score * 3.0 + position_score) * length_penalty


def _extract_top_sentences(text: str, query: str, max_sentences: int) -> str:
    sentences = _split_sentences(text)
    if len(sentences) <= max_sentences:
        return " ".join(sentences)
    query_terms = set(_WORD_RE.findall((query or "").lower()))
    scored = [
        (_score_sentence(s, query_terms, i, len(sentences)), i, s)
        for i, s in enumerate(sentences)
    ]
    top = sorted(scored, key=lambda x: x[0], reverse=True)[:max_sentences]
    top.sort(key=lambda x: x[1])  # restore original order so it reads coherently
    return " ".join(s for _, _, s in top)


def summarize_page(text: str, query: str, max_sentences: int = 8) -> str:
    """Shorten `text` to the sentences most relevant to `query`.

    Single-pass extraction for text under the map-reduce threshold. For
    longer text: chunk, extract each chunk's top sentences against the query
    (map), then run one more extraction pass over the concatenated chunk
    summaries to fit the final `max_sentences` budget (reduce) — the
    map-reduce shape the plan calls for; see module docstring for why the
    "summarize" step is extractive rather than an LLM call in this pass.
    """
    text = (text or "").strip()
    if not text:
        return ""
    if len(text) <= _CHUNK_CHAR_THRESHOLD:
        return _extract_top_sentences(text, query, max_sentences)

    chunks = _chunk_text(text)
    per_chunk_budget = max(2, max_sentences // 2)
    mapped = [_extract_top_sentences(c, query, per_chunk_budget) for c in chunks]
    combined = "\n".join(m for m in mapped if m)
    return _extract_top_sentences(combined, query, max_sentences)
