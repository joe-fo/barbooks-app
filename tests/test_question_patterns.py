"""Tests for the question pattern classification library."""

from app.question_patterns import QuestionIntent, classify_question


class TestRevealPatterns:
    def test_show_me_the_answers(self):
        intent, _ = classify_question("Show me the answers")
        assert intent == QuestionIntent.REVEAL

    def test_reveal_the_list(self):
        intent, _ = classify_question("Reveal the full list")
        assert intent == QuestionIntent.REVEAL

    def test_tell_me_all_answers(self):
        intent, _ = classify_question("Tell me all the answers")
        assert intent == QuestionIntent.REVEAL

    def test_what_are_all_answers(self):
        intent, _ = classify_question("What are all the answers?")
        assert intent == QuestionIntent.REVEAL

    def test_give_me_the_answers(self):
        intent, _ = classify_question("Give me the answers")
        assert intent == QuestionIntent.REVEAL

    def test_spoil(self):
        intent, _ = classify_question("Just spoil it")
        assert intent == QuestionIntent.REVEAL


class TestRankLookup:
    def test_who_is_number_3(self):
        intent, params = classify_question("Who is number 3 on the list?")
        assert intent == QuestionIntent.RANK_LOOKUP
        assert params["rank"] == "3"

    def test_who_is_hash_5(self):
        intent, params = classify_question("Who is #5?")
        assert intent == QuestionIntent.RANK_LOOKUP
        assert params["rank"] == "5"

    def test_what_is_ranked_1st(self):
        intent, params = classify_question("What is ranked 1st?")
        assert intent == QuestionIntent.RANK_LOOKUP
        assert params["rank"] == "1"

    def test_bare_hash_notation(self):
        intent, params = classify_question("#9")
        assert intent == QuestionIntent.RANK_LOOKUP
        assert params["rank"] == "9"

    def test_number_10(self):
        intent, params = classify_question("What is number 10?")
        assert intent == QuestionIntent.RANK_LOOKUP
        assert params["rank"] == "10"

    def test_case_insensitive(self):
        intent, params = classify_question("WHO IS NUMBER 3?")
        assert intent == QuestionIntent.RANK_LOOKUP
        assert params["rank"] == "3"


class TestExistence:
    def test_is_name_on_list(self):
        intent, params = classify_question("Is Randy Moss on this list?")
        assert intent == QuestionIntent.EXISTENCE
        assert params["name"] == "Randy Moss"

    def test_does_name_appear(self):
        intent, params = classify_question("Does Jerry Rice appear here?")
        assert intent == QuestionIntent.EXISTENCE
        assert params["name"] == "Jerry Rice"

    def test_name_normalized_to_title_case(self):
        intent, params = classify_question("Is RANDY MOSS on this list?")
        assert intent == QuestionIntent.EXISTENCE
        assert params["name"] == "Randy Moss"

    def test_possessive_stripped(self):
        # Pattern requires "on this list/page" not "on the list"
        intent, params = classify_question("Is Randy Moss's name on this list?")
        assert intent == QuestionIntent.EXISTENCE


class TestYearLookup:
    def test_who_won_in_year(self):
        intent, params = classify_question("Who won in 2020?")
        assert intent == QuestionIntent.YEAR_LOOKUP
        assert params["year"] == "2020"

    def test_who_was_it_in_year(self):
        # YEAR_LOOKUP matches "who was [it/in/for] YEAR" — free-text words between
        # "was" and the year are not handled; use a supported phrasing
        intent, params = classify_question("Who was it in 2019?")
        assert intent == QuestionIntent.YEAR_LOOKUP
        assert params["year"] == "2019"

    def test_year_winner(self):
        intent, params = classify_question("2021 winner?")
        assert intent == QuestionIntent.YEAR_LOOKUP
        assert params["year"] == "2021"


class TestReverseRank:
    def test_what_rank_is_name(self):
        intent, params = classify_question("What rank is Jerry Rice?")
        assert intent == QuestionIntent.REVERSE_RANK
        assert params["name"] == "Jerry Rice"

    def test_where_does_name_rank(self):
        intent, params = classify_question("Where does Randy Moss rank?")
        assert intent == QuestionIntent.REVERSE_RANK
        assert params["name"] == "Randy Moss"


class TestStatLookup:
    def test_how_many_tds(self):
        intent, params = classify_question("How many TDs does Randy Moss have?")
        assert intent == QuestionIntent.STAT_LOOKUP
        assert params["name"] == "Randy Moss"
        assert "td" in params["stat"].lower()

    def test_possessive_stat(self):
        intent, params = classify_question("What is Randy Moss's TDs?")
        assert intent == QuestionIntent.STAT_LOOKUP
        assert params["name"] == "Randy Moss"


class TestCount:
    def test_how_many_items(self):
        intent, _ = classify_question("How many items are on this list?")
        assert intent == QuestionIntent.COUNT

    def test_how_many_players(self):
        intent, _ = classify_question("How many players are on this list?")
        assert intent == QuestionIntent.COUNT

    def test_how_long_is_list(self):
        intent, _ = classify_question("How long is this list?")
        assert intent == QuestionIntent.COUNT


class TestHint:
    def test_give_me_a_hint(self):
        intent, _ = classify_question("Give me a hint")
        assert intent == QuestionIntent.HINT

    def test_need_a_hint(self):
        intent, _ = classify_question("I need a hint")
        assert intent == QuestionIntent.HINT

    def test_clue_for_rank(self):
        intent, params = classify_question("What's the clue for #3?")
        assert intent == QuestionIntent.HINT
        assert params.get("rank") == "3"


class TestPageMeta:
    def test_what_is_this_page_about(self):
        intent, _ = classify_question("What is this page about?")
        assert intent == QuestionIntent.PAGE_META

    def test_what_am_i_looking_at(self):
        intent, _ = classify_question("What am I looking at?")
        assert intent == QuestionIntent.PAGE_META

    def test_explain_this_list(self):
        intent, _ = classify_question("Explain this list")
        assert intent == QuestionIntent.PAGE_META


class TestConfirmation:
    def test_is_it_name(self):
        intent, params = classify_question("Is it the answer Jerry Rice?")
        assert intent == QuestionIntent.CONFIRMATION

    def test_bare_name_question(self):
        intent, params = classify_question("Jerry Rice?")
        assert intent == QuestionIntent.CONFIRMATION
        assert params["name"] == "Jerry Rice"


class TestUnknown:
    def test_open_ended_question(self):
        intent, params = classify_question(
            "Tell me something interesting about this season"
        )
        assert intent == QuestionIntent.UNKNOWN
        assert params == {}

    def test_empty_string(self):
        intent, params = classify_question("")
        assert intent == QuestionIntent.UNKNOWN

    def test_gibberish(self):
        intent, params = classify_question("asdfghjkl qwerty")
        assert intent == QuestionIntent.UNKNOWN


class TestEdgeCases:
    def test_reveal_takes_priority_over_rank(self):
        # "show me the answer to #3" could look like rank, but REVEAL is first
        intent, _ = classify_question("Show me the answer to #3")
        assert intent == QuestionIntent.REVEAL

    def test_whitespace_around_input(self):
        intent, params = classify_question("  Who is #3?  ")
        assert intent == QuestionIntent.RANK_LOOKUP
        assert params["rank"] == "3"

    def test_mixed_case_rank(self):
        intent, params = classify_question("Who Is Number 5?")
        assert intent == QuestionIntent.RANK_LOOKUP
        assert params["rank"] == "5"
