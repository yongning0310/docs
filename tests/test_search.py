"""Unit tests for search utilities and sentence splitting."""

from app.services.embeddings import split_into_sentences
from app.services.search import search_text


class TestSearchText:
    def test_basic_match(self):
        content = "The quick brown fox jumps over the lazy dog"
        snippets = search_text(content, "brown fox", context_chars=10)
        assert len(snippets) == 1
        assert snippets[0].text == "brown fox"
        assert snippets[0].position == 10
        assert "quick " in snippets[0].context_before
        assert " jumps" in snippets[0].context_after

    def test_case_insensitive(self):
        content = "Agreement between Party A and PARTY B"
        snippets = search_text(content, "party", context_chars=10)
        assert len(snippets) == 2

    def test_no_matches(self):
        snippets = search_text("Hello world", "xyz", context_chars=10)
        assert snippets == []

    def test_multiple_matches(self):
        content = "cat and cat and cat"
        snippets = search_text(content, "cat", context_chars=5)
        assert len(snippets) == 3
        assert [s.position for s in snippets] == [0, 8, 16]

    def test_context_at_boundaries(self):
        content = "start middle end"
        snippets = search_text(content, "start", context_chars=10)
        assert snippets[0].context_before == ""  # no context before start

    def test_special_regex_characters(self):
        content = "Price is $100.00 (USD)"
        snippets = search_text(content, "$100.00", context_chars=5)
        assert len(snippets) == 1
        assert snippets[0].text == "$100.00"


class TestSplitIntoSentences:
    """Tests for sentence splitting."""

    def test_basic_sentences(self):
        text = "This is the first complete sentence here. This is the second sentence now. And this is the third one."
        sentences = split_into_sentences(text)
        assert len(sentences) == 3
        assert "first complete sentence" in sentences[0][0]
        assert "second sentence" in sentences[1][0]

    def test_question_and_exclamation(self):
        text = "Is this agreement legally binding today? Yes it absolutely is binding! And here is a final statement."
        sentences = split_into_sentences(text)
        assert len(sentences) == 3

    def test_strips_html(self):
        text = "<strong>Bold text</strong> in a sentence. <em>Another</em> sentence here."
        sentences = split_into_sentences(text)
        assert len(sentences) == 2
        assert "<strong>" not in sentences[0][0]

    def test_merges_short_fragments(self):
        text = "Long enough sentence here. Ok. Another long sentence follows."
        sentences = split_into_sentences(text, min_length=20)
        # "Ok." is too short and should be merged
        assert all(len(s[0]) >= 20 for s in sentences)

    def test_empty_content(self):
        assert split_into_sentences("") == []
