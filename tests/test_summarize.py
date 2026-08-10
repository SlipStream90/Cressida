"""Tests for core/retrieval/summarize.py's extractive summarizer.

The summarizer is a documented extractive (keyword/position-scored sentence
selection) fallback, not an LLM call — see summarize.py's module docstring
for why. These tests hold it to what that design can actually promise:
shorter output for long input, and query-relevant sentences survive.
"""

from __future__ import annotations

from cressida.core.retrieval.summarize import summarize_page


_FILLER_SENTENCE = (
    "The weather today was mild with a light breeze from the northwest. "
)


def _make_long_text(keyword_sentence: str, repeats: int = 400) -> str:
    # ~16000+ char threshold triggers map-reduce chunking in summarize_page.
    filler = _FILLER_SENTENCE * repeats
    # Bury the relevant sentence roughly in the middle.
    half = len(filler) // 2
    return filler[:half] + " " + keyword_sentence + " " + filler[half:]


def test_summary_is_shorter_than_long_input():
    text = _make_long_text("Kubernetes pod eviction happens when nodes run out of memory.")
    query = "kubernetes pod eviction memory"
    summary = summarize_page(text, query)
    assert len(text) > 16000
    assert len(summary) < len(text)


def test_summary_preserves_query_relevant_keywords():
    keyword_sentence = "Kubernetes pod eviction happens when nodes run out of memory."
    text = _make_long_text(keyword_sentence)
    query = "kubernetes pod eviction memory"
    summary = summarize_page(text, query)
    lowered = summary.lower()
    assert "kubernetes" in lowered
    assert "eviction" in lowered


def test_short_text_single_pass_still_shortens_when_over_budget():
    sentences = [f"Sentence number {i} talks about apples and oranges." for i in range(30)]
    sentences.insert(15, "Bananas are the best fruit for potassium intake.")
    text = " ".join(sentences)
    summary = summarize_page(text, "bananas potassium", max_sentences=5)
    assert len(summary) < len(text)
    assert "banana" in summary.lower()


def test_empty_text_returns_empty_summary():
    assert summarize_page("", "anything") == ""
    assert summarize_page(None, "anything") == ""  # type: ignore[arg-type]


def test_short_text_under_sentence_budget_is_returned_whole():
    text = "One sentence only."
    assert summarize_page(text, "sentence", max_sentences=8) == text
