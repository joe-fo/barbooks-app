"""Tests for Streamlit app answer formatting helpers."""

from app.app import format_answer_key, format_line_item, render_answer


class TestFormatAnswerKey:
    def test_basic_formatting(self):
        answer_key = {
            "items": [
                {
                    "rank": 1,
                    "name": "Eli Manning",
                    "stat": "57,023 yds",
                    "correct": True,
                },
                {
                    "rank": 2,
                    "name": "Donovan McNabb",
                    "stat": "36,250 yds",
                    "correct": True,
                },
            ]
        }
        result = format_answer_key(answer_key)
        assert (
            result
            == "1. Eli Manning \u2014 57,023 yds\n2. Donovan McNabb \u2014 36,250 yds"
        )

    def test_no_braces_or_items_key_in_output(self):
        answer_key = {
            "items": [
                {"rank": 1, "name": "Tom Brady", "stat": "89,214 yds", "correct": True},
            ]
        }
        result = format_answer_key(answer_key)
        assert "{" not in result
        assert "}" not in result
        assert "items" not in result

    def test_empty_items(self):
        result = format_answer_key({"items": []})
        assert result == "No answer key available."

    def test_item_without_stat(self):
        answer_key = {
            "items": [{"rank": 1, "name": "Tom Brady", "stat": "", "correct": True}]
        }
        result = format_answer_key(answer_key)
        assert result == "1. Tom Brady"


class TestFormatLineItem:
    def test_basic_formatting(self):
        item = {"rank": 3, "name": "Drew Brees", "stat": "80,358 yds", "correct": True}
        result = format_line_item(item)
        assert result == "#3: Drew Brees \u2014 80,358 yds"

    def test_no_braces_in_output(self):
        item = {"rank": 1, "name": "Tom Brady", "stat": "89,214 yds", "correct": True}
        result = format_line_item(item)
        assert "{" not in result
        assert "}" not in result


class TestRenderAnswer:
    def test_answer_key_dict_is_formatted(self):
        answer = {
            "items": [
                {
                    "rank": 1,
                    "name": "Eli Manning",
                    "stat": "57,023 yds",
                    "correct": True,
                },
                {
                    "rank": 2,
                    "name": "Donovan McNabb",
                    "stat": "36,250 yds",
                    "correct": True,
                },
            ]
        }
        result = render_answer(answer)
        assert "{" not in result
        assert "}" not in result
        assert "items" not in result
        assert "Eli Manning" in result
        assert "Donovan McNabb" in result

    def test_line_item_dict_is_formatted(self):
        answer = {
            "rank": 1,
            "name": "Eli Manning",
            "stat": "57,023 yds",
            "correct": True,
        }
        result = render_answer(answer)
        assert "{" not in result
        assert "}" not in result
        assert "Eli Manning" in result

    def test_string_answer_passthrough(self):
        result = render_answer("Just a plain string answer.")
        assert result == "Just a plain string answer."

    def test_none_answer(self):
        result = render_answer(None)
        assert result == "No answer returned."

    def test_reveal_response_no_raw_json(self):
        """REVEAL intent response must not contain raw JSON characters."""
        answer = {
            "items": [
                {
                    "rank": i,
                    "name": f"Player {i}",
                    "stat": f"{i * 1000} yds",
                    "correct": True,
                }
                for i in range(1, 6)
            ]
        }
        result = render_answer(answer)
        assert "{" not in result
        assert "}" not in result
        assert "items" not in result
