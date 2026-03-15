"""Tests for the deterministic short-circuit layer (mock_db)."""

from app.domain.models import ChatRequest, Page
from app.mock_db import DeterministicAnswerSource, deterministic_match


class TestDeterministicMatch:
    def test_randy_moss_match(self):
        result = deterministic_match("nfl", "9", "Is Randy Moss on this list?")
        assert result is not None
        assert "Randy Moss" in result
        assert "4th" in result

    def test_jerry_rice_match(self):
        result = deterministic_match("nfl", "9", "What about Jerry Rice?")
        assert result is not None
        assert "Jerry Rice" in result
        assert "1st" in result

    def test_emmitt_smith_match(self):
        result = deterministic_match("nfl", "9", "emmitt smith")
        assert result is not None
        assert "Emmitt Smith" in result

    def test_tom_brady_negative_match(self):
        result = deterministic_match("nfl", "9", "Is Tom Brady on this list?")
        assert result is not None
        assert "not on this list" in result

    def test_no_match_returns_none(self):
        result = deterministic_match("nfl", "9", "Who is Peyton Manning?")
        assert result is None

    def test_unknown_book_returns_none(self):
        result = deterministic_match("nba", "9", "Is Randy Moss on this list?")
        assert result is None

    def test_unknown_page_returns_none(self):
        result = deterministic_match("nfl", "99", "Is Randy Moss on this list?")
        assert result is None

    def test_case_insensitive_match(self):
        assert deterministic_match("nfl", "9", "RANDY MOSS") is not None
        assert deterministic_match("nfl", "9", "randy moss") is not None
        assert deterministic_match("nfl", "9", "Randy Moss") is not None

    def test_whitespace_variations(self):
        # Pattern allows optional whitespace between first/last name
        assert deterministic_match("nfl", "9", "Randy  Moss") is not None

    def test_partial_name_match(self):
        # \s* allows zero spaces, so "randymoss" still matches
        assert deterministic_match("nfl", "9", "randymoss") is not None
        # A completely unrelated name does not match
        assert deterministic_match("nfl", "9", "Dan Marino") is None

    def test_empty_message_returns_none(self):
        assert deterministic_match("nfl", "9", "") is None


class TestDeterministicAnswerSource:
    async def test_answer_returns_match(self):
        source = DeterministicAnswerSource()
        request = ChatRequest(
            user_message="Is Jerry Rice on this list?", book_id="nfl", page_id="9"
        )
        page = Page(page_id="9", url="http://example.com")
        result = await source.answer(request, page, "")
        assert result is not None
        assert "Jerry Rice" in result

    async def test_answer_returns_none_for_no_match(self):
        source = DeterministicAnswerSource()
        request = ChatRequest(
            user_message="What is the weather?", book_id="nfl", page_id="9"
        )
        page = Page(page_id="9", url="http://example.com")
        result = await source.answer(request, page, "")
        assert result is None

    async def test_answer_unknown_book_returns_none(self):
        source = DeterministicAnswerSource()
        request = ChatRequest(
            user_message="Is Randy Moss here?", book_id="nba", page_id="9"
        )
        page = Page(page_id="9", url="http://example.com")
        result = await source.answer(request, page, "")
        assert result is None
