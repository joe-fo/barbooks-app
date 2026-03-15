import re
from typing import Optional

from .domain import AnswerSource, ChatRequest, Page

# Regex rules for the deterministic short-circuit layer.
# Keys are (book_id, page_id) where page_id matches the Page # from the spreadsheet.
# Page 9 = "NFL All-Time Touchdown Leaders" (espn.com/nfl/history/leaders)
RULES_DB: dict[tuple[str, str], list[tuple[str, str]]] = {
    ("nfl", "9"): [
        (r"(?i)\brandy\s*moss\b", "Yes, Randy Moss is 4th on the list with 157 TD's."),
        (r"(?i)\bjerry\s*rice\b", "Yes, Jerry Rice is 1st on the list with 208 TD's."),
        (r"(?i)\bemmitt\s*smith\b", "Yes, Emmitt Smith is 2nd on the list with 175 TD's."),
        (r"(?i)\btom\s*brady\b", "No, Tom Brady is not on this list."),
    ]
}


def deterministic_match(book_id: str, page_id: str, user_message: str) -> Optional[str]:
    """
    Checks user_message against predefined regex rules for (book_id, page_id).
    Returns a formatted answer on confident match, otherwise None.
    """
    rules = RULES_DB.get((book_id, page_id), [])
    for pattern, answer in rules:
        if re.search(pattern, user_message):
            return answer
    return None


class DeterministicAnswerSource(AnswerSource):
    """AnswerSource adapter wrapping the regex-based deterministic short-circuit."""

    async def answer(self, request: ChatRequest, page: Page, context: str) -> Optional[str]:
        return deterministic_match(request.book_id, request.page_id, request.user_message)
