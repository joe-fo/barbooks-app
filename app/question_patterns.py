"""Canonical question pattern library for the deterministic short-circuit layer.

Defines regex patterns and intent matchers for the question archetypes that
arise on Barbooks trivia pages. These patterns enable the short-circuit layer
to answer common queries without hitting the LLM.

Pattern conventions
-------------------
- re.IGNORECASE is applied at search time — no inline (?i) flags needed.
- Named capture groups (e.g. (?P<rank>\\d+)) expose parsed parameters.
- A pattern that matches but whose captured group is empty should fall through
  to the LLM (ambiguous input).

Usage::

    from app.question_patterns import classify_question, QuestionIntent

    intent, params = classify_question("Who is number 3 on the list?")
    # -> (QuestionIntent.RANK_LOOKUP, {"rank": "3"})
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any


class QuestionIntent(Enum):
    # Deterministically answerable — short-circuit can handle
    EXISTENCE = "existence"  # "Is [name] on this list?"
    RANK_LOOKUP = "rank_lookup"  # "Who is #N?" / "What is ranked 3rd?"
    REVERSE_RANK = "reverse_rank"  # "What rank is [name]?"
    STAT_LOOKUP = "stat_lookup"  # "How many TDs does [name] have?"
    YEAR_LOOKUP = "year_lookup"  # "Who won in 2020?"
    REVERSE_YEAR = "reverse_year"  # "What year did [name] win?"
    FREQUENCY = "frequency"  # "How many times does [name] appear?"
    CONFIRMATION = "confirmation"  # "Is the answer [name]?" / just "[name]?"
    COUNT = "count"  # "How many items are on this list?"
    HINT = "hint"  # "Give me a hint" / "What's the clue for #N?"
    PAGE_META = "page_meta"  # "What is this page about?"

    # Block — never answer; redirect or refuse
    REVEAL = "reveal"  # "Show me the answers" / "Tell me the list"

    # Must go to LLM — too ambiguous or open-ended
    UNKNOWN = "unknown"


@dataclass
class PatternEntry:
    intent: QuestionIntent
    # Each element is one alternative pattern string; matched with re.IGNORECASE.
    alternatives: list[str]
    group_names: list[str]  # which named capture groups to extract

    def match(self, text: str) -> dict[str, Any] | None:
        """Return dict of captured params if any alternative matches, else None."""
        for pat in self.alternatives:
            m = re.search(pat, text, re.IGNORECASE)
            if m is None:
                continue
            params: dict[str, Any] = {}
            for k in self.group_names:
                try:
                    v = m.group(k)
                except IndexError:
                    v = None
                if v is not None:
                    params[k] = v
            return params
        return None


# ---------------------------------------------------------------------------
# Pattern registry — evaluated in order; first match wins.
# ---------------------------------------------------------------------------
PATTERNS: list[PatternEntry] = [
    # -----------------------------------------------------------------------
    # REVEAL — checked first so "show me the answer to #3" doesn't become
    # a rank_lookup.
    # -----------------------------------------------------------------------
    PatternEntry(
        intent=QuestionIntent.REVEAL,
        alternatives=[
            r"\b(?:show|reveal)\s+(?:me\s+)?(?:all\s+)?(?:the\s+)?(?:answers?|full\s+list|list|solutions?)\b",
            r"\btell\s+me\s+(?:all\s+)?(?:the\s+)?(?:answers?|list|solutions?)\b",
            r"\bwhat\s+are\s+all\s+(?:the\s+)?answers?\b",
            r"\bspoi[lr]\b",
            r"\bgive\s+(?:me\s+)?(?:all\s+)?(?:the\s+)?answers?\b",
        ],
        group_names=[],
    ),
    # -----------------------------------------------------------------------
    # PAGE_META — "what is this list/page about?"
    # -----------------------------------------------------------------------
    PatternEntry(
        intent=QuestionIntent.PAGE_META,
        alternatives=[
            r"\bwhat\s+is\s+this\s+(?:list|page|about|trivia)?\b",
            r"\bwhat\s+(?:page|list)\s+(?:is\s+this|am\s+i\s+(?:on|looking\s+at))\b",
            r"\bwhat\s+am\s+i\s+looking\s+at\b",
            r"\bwhat\s+are\s+we\s+(?:doing|playing)\b",
            r"\bexplain\s+(?:this\s+)?(?:page|list|trivia)\b",
            r"\bwhat\s+is\s+the\s+(?:topic|subject|category)\b",
        ],
        group_names=[],
    ),
    # -----------------------------------------------------------------------
    # COUNT — "how many items are on this list?"
    # -----------------------------------------------------------------------
    PatternEntry(
        intent=QuestionIntent.COUNT,
        alternatives=[
            r"\bhow\s+long\s+is\s+(?:this\s+)?(?:list|page)\b",
            r"\bhow\s+many\s+(?:items?|players?|names?|entries?|questions?|answers?)\s+"
            r"(?:are\s+(?:on|in)\s+(?:this\s+)?(?:list|page)|does\s+this\s+(?:list|page)\s+have)\b",
        ],
        group_names=[],
    ),
    # -----------------------------------------------------------------------
    # HINT — "give me a hint" / "what's the clue for #3?"
    # -----------------------------------------------------------------------
    PatternEntry(
        intent=QuestionIntent.HINT,
        alternatives=[
            r"\bgive\s+(?:me\s+)?(?:a\s+)?hint\b",
            r"\bneed\s+a\s+hint\b",
            r"\bclue\s+(?:for|to)\s+#?\s*(?P<rank>\d+)\b",
            r"\bhint\s+(?:for|on)\s+#?\s*(?P<rank>\d+)\b",
        ],
        group_names=["rank"],
    ),
    # -----------------------------------------------------------------------
    # YEAR_LOOKUP — "who won in 2020?" / "who was MVP in 2019?"
    # -----------------------------------------------------------------------
    PatternEntry(
        intent=QuestionIntent.YEAR_LOOKUP,
        alternatives=[
            r"\bwho\s+(?:won|was|is|got)\s+(?:it\s+)?(?:in|for|during|the)?\s*"
            r"(?:year\s+)?(?P<year>20\d\d|199\d|1[89]\d\d)\b",
            r"\b(?P<year>20\d\d|199\d|1[89]\d\d)\s+(?:winner|MVP|champion|award|OPOY|DPOY)\b",
        ],
        group_names=["year"],
    ),
    # -----------------------------------------------------------------------
    # REVERSE_YEAR — "what year did [name] win?"
    # -----------------------------------------------------------------------
    PatternEntry(
        intent=QuestionIntent.REVERSE_YEAR,
        alternatives=[
            r"\b(?:what|which)\s+year\s+(?:did\s+)?(?P<name>.+?)\s+"
            r"(?:win|get|receive|earn|was\s+(?:the\s+)?(?:MVP|winner|champion))\b",
            r"\bwhen\s+(?:did|was)\s+(?P<name>.+?)\s+"
            r"(?:win|the\s+(?:MVP|winner|OPOY|DPOY))\b",
        ],
        group_names=["name"],
    ),
    # -----------------------------------------------------------------------
    # RANK_LOOKUP — "who is #3?" / "what is ranked 5th?" / "#9"
    # -----------------------------------------------------------------------
    PatternEntry(
        intent=QuestionIntent.RANK_LOOKUP,
        alternatives=[
            r"\bwho\s+is\s+(?:number|#|ranked?|no\.?)\s*(?P<rank>\d{1,2})(?:st|nd|rd|th)?\b",
            r"\bwhat\s+(?:is|was)\s+(?:number|#|ranked?|no\.?)\s*(?P<rank>\d{1,2})(?:st|nd|rd|th)?\b",
            r"\b(?:number|no\.?)\s*(?P<rank>\d{1,2})(?:st|nd|rd|th)?\b",
            r"^#(?P<rank>\d{1,2})\b",
            r"\b(?:ranked?)\s+(?P<rank>\d{1,2})(?:st|nd|rd|th)?\b",
        ],
        group_names=["rank"],
    ),
    # -----------------------------------------------------------------------
    # REVERSE_RANK — "what rank is [name]?" / "where does [name] fall?"
    # -----------------------------------------------------------------------
    PatternEntry(
        intent=QuestionIntent.REVERSE_RANK,
        alternatives=[
            r"\bwhat\s+(?:rank|number|position|spot|place)\s+is\s+(?P<name>.+?)\s*\??$",
            r"\bwhere\s+(?:is|does)\s+(?P<name>.+?)\s+"
            r"(?:rank|appear|fall|land|sit|show\s+up)\b",
            r"\b(?P<name>.+?)(?:'s|s'|['''])?\s+rank(?:ing)?\b",
        ],
        group_names=["name"],
    ),
    # -----------------------------------------------------------------------
    # FREQUENCY — "how many times does [name] appear?"
    # -----------------------------------------------------------------------
    PatternEntry(
        intent=QuestionIntent.FREQUENCY,
        alternatives=[
            r"\bhow\s+many\s+times\s+(?:does|is|did)\s+"
            r"(?P<name>.+?)\s+(?:appear|show\s+up|listed)\b",
            r"\b(?:does|is)\s+(?P<name>.+?)\s+"
            r"(?:appear|show\s+up|listed)\s+(?:more\s+than\s+once|multiple\s+times|twice)\b",
            r"\b(?P<name>.+?)\s+(?:appear|listed)\s+(?:twice|more\s+than\s+once)\b",
        ],
        group_names=["name"],
    ),
    # -----------------------------------------------------------------------
    # STAT_LOOKUP — "how many TDs does [name] have?" / "[name]'s rushing yards?"
    # -----------------------------------------------------------------------
    PatternEntry(
        intent=QuestionIntent.STAT_LOOKUP,
        alternatives=[
            # "how many TDs does Randy Moss have?" — stat before name
            r"\bhow\s+many\s+(?P<stat>\w+(?:\s+\w+){0,2})\s+"
            r"(?:does|did|has|had)\s+(?P<name>.+?)\s+(?:have|had|recorded|score|scored)\b",
            # "what is Randy Moss's rushing yards?" — possessive before stat
            r"\bwhat\s+(?:is|was|are|were)\s+(?P<name>.+?)(?:'s|s'|['''])\s+(?P<stat>\w+(?:\s+\w+){0,2})\b",
        ],
        group_names=["stat", "name"],
    ),
    # -----------------------------------------------------------------------
    # EXISTENCE — "is [name] on this list?" / "does [name] appear here?"
    # -----------------------------------------------------------------------
    PatternEntry(
        intent=QuestionIntent.EXISTENCE,
        alternatives=[
            r"\bis\s+(?P<name>.+?)\s+"
            r"(?:on\s+(?:this\s+)?(?:list|page)|in\s+(?:this|here)|here|included)\b",
            r"\bdoes\s+(?P<name>.+?)\s+"
            r"(?:appear|show\s+up|make\s+(?:the\s+)?(?:list|cut))\b",
            r"\b(?P<name>.+?)\s+"
            r"(?:on\s+(?:this\s+)?(?:list|page)|in\s+(?:the\s+)?top)\b",
        ],
        group_names=["name"],
    ),
    # -----------------------------------------------------------------------
    # CONFIRMATION — "is the answer Randy Moss?" / "is it Jerry Rice?"
    # Must come after EXISTENCE so "Is Randy Moss on the list?" doesn't
    # accidentally match as confirmation.
    # Name capture uses (?-i:...) so [A-Z] requires actual uppercase — prevents
    # matching multi-word sentences like "Why is football great?" as a name.
    # -----------------------------------------------------------------------
    PatternEntry(
        intent=QuestionIntent.CONFIRMATION,
        alternatives=[
            r"\bis\s+(?:it|the\s+answer|the\s+one)\s+(?P<name>.+?)\s*\??$",
            # bare name as question: "Randy Moss?" — only matches 1-3 word names
            # to avoid false positives
            r"^(?P<name>\w+(?:\s+\w+){0,2})\s*\?\s*$",
        ],
        group_names=["name"],
    ),
]


_POSSESSIVE_STRIP = re.compile(r"[''']s\s*$|s[''']\s*$")


def _normalize_name(raw: str) -> str:
    """Strip trailing possessives/punctuation and title-case a name."""
    name = _POSSESSIVE_STRIP.sub("", raw).strip().rstrip("?!.,")
    return name.title()


def classify_question(text: str) -> tuple[QuestionIntent, dict[str, Any]]:
    """Classify user input into a QuestionIntent with extracted parameters.

    Returns (intent, params) where params is a dict of named capture groups.
    - ``name`` values are normalized to Title Case with possessives stripped.
    - ``rank`` values are plain digit strings (e.g. ``"3"``).
    - ``year`` values are 4-digit strings (e.g. ``"2020"``).
    - ``stat`` values are lowercase strings.
    For UNKNOWN, returns empty params — caller should route to LLM.

    >>> classify_question("Is Randy Moss on this list?")
    (<QuestionIntent.EXISTENCE: 'existence'>, {'name': 'Randy Moss'})
    >>> classify_question("Who is #3 on the list?")
    (<QuestionIntent.RANK_LOOKUP: 'rank_lookup'>, {'rank': '3'})
    >>> classify_question("Show me the answers")
    (<QuestionIntent.REVEAL: 'reveal'>, {})
    """
    for entry in PATTERNS:
        params = entry.match(text)
        if params is not None:
            if "name" in params:
                params["name"] = _normalize_name(params["name"])
            if "stat" in params:
                params["stat"] = params["stat"].lower().strip()
            return entry.intent, params
    return QuestionIntent.UNKNOWN, {}
