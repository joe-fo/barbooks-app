"""Unit tests for llm_service system prompt enrichment."""

import pytest

from app.domain.models import Page, PageItem
from app.llm_service import _build_system_prompt


class TestBuildSystemPromptNoItems:
    def test_falls_back_to_context_when_no_page(self):
        prompt = _build_system_prompt("Some context text", page=None)
        assert "Some context text" in prompt
        assert "Correct!" in prompt

    def test_falls_back_to_context_when_page_has_no_items(self):
        page = Page(page_id="1", url="", title="Top 10 TDs", description="")
        prompt = _build_system_prompt("Some context text", page=page)
        assert "Some context text" in prompt
        assert "Correct!" in prompt


class TestBuildSystemPromptWithItems:
    @pytest.fixture
    def page_with_items(self):
        def _item(rank, name, stat):
            return PageItem(
                rank=rank,
                key=f"#{rank}",
                name=name,
                stat_value=stat,
                stat_label="Passing Yards",
            )

        return Page(
            page_id="15",
            url="",
            title="NFC East — Top 10 Career Passing Yards",
            description="Career passing yards leaders in the NFC East.",
            items=[
                _item(1, "Tony Romo", "34,183"),
                _item(2, "Eli Manning", "57,023"),
                _item(3, "Donovan McNabb", "37,276"),
                _item(4, "Phil Simms", "33,462"),
                _item(5, "Mark Brunell", "32,072"),
                _item(6, "Drew Bledsoe", "29,657"),
            ],
        )

    def test_includes_page_title(self, page_with_items):
        prompt = _build_system_prompt("raw context", page=page_with_items)
        assert "NFC East" in prompt
        assert "Top 10 Career Passing Yards" in prompt

    def test_includes_ranked_list(self, page_with_items):
        prompt = _build_system_prompt("raw context", page=page_with_items)
        assert "#1" in prompt
        assert "Tony Romo" in prompt
        assert "#6" in prompt
        assert "Drew Bledsoe" in prompt

    def test_includes_stat_values(self, page_with_items):
        prompt = _build_system_prompt("raw context", page=page_with_items)
        assert "34,183" in prompt
        assert "Passing Yards" in prompt

    def test_rank_instruction_present(self, page_with_items):
        prompt = _build_system_prompt("raw context", page=page_with_items)
        assert "who is #N" in prompt.lower() or "#N" in prompt

    def test_correct_not_an_allowed_reply(self, page_with_items):
        """'Correct!' must not appear as an allowed reply option (only negation)."""
        prompt = _build_system_prompt("raw context", page=page_with_items)
        # Must NOT list 'Correct!' as an allowed option
        assert "MUST be one of: 'Yes', 'No', or 'Correct!'" not in prompt

    def test_raw_context_not_included_when_items_present(self, page_with_items):
        """Raw scraped text not in prompt when structured list is available."""
        prompt = _build_system_prompt("raw context sentinel xyz", page=page_with_items)
        assert "raw context sentinel xyz" not in prompt

    def test_answer_count_truncates_ranked_list(self):
        """LLM prompt only includes items up to answer_count when set."""

        def _item(rank, name):
            return PageItem(
                rank=rank, key=f"#{rank}", name=name, stat_value="", stat_label=""
            )

        page = Page(
            page_id="5",
            url="",
            title="Top 3 Career Passing Yards",
            description="",
            answer_count=3,
            items=[_item(i, f"Player {i}") for i in range(1, 6)],
        )
        prompt = _build_system_prompt("ctx", page=page)
        assert "Player 1" in prompt
        assert "Player 3" in prompt
        assert "Player 4" not in prompt
        assert "Player 5" not in prompt

    def test_answer_count_zero_includes_all_items(self, page_with_items):
        """answer_count=0 means no restriction — all items are included."""
        prompt = _build_system_prompt("ctx", page=page_with_items)
        assert "Drew Bledsoe" in prompt  # rank 6, beyond any top-N restriction
