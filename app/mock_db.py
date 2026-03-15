import re
from typing import Optional, Tuple

# Mock data mapping (book_id, page_id) to the target external URL
URL_DB = {
    ("nfl", "1"): "https://www.espn.com/nfl/history/leaders/_/stat/touchdown",
    ("nfl", "touchdown"): "https://www.espn.com/nfl/history/leaders/_/stat/touchdown"
}

# Mock data mapping (book_id, page_id) to a list of regex patterns and deterministic answers
MOCK_RULES_DB = {
    ("nfl", "touchdown"): [
        # Regex to catch specific players and return hardcoded placement
        (r"(?i)\brandy\s*moss\b", "Yes, Randy Moss is 4th on the list with 157 TD's."),
        (r"(?i)\bjerry\s*rice\b", "Yes, Jerry Rice is 1st on the list with 208 TD's."),
        (r"(?i)\bemmitt\s*smith\b", "Yes, Emmitt Smith is 2nd on the list with 175 TD's."),
        (r"(?i)\btom\s*brady\b", "No, Tom Brady is not on this list.")
    ]
}

def get_page_url(book_id: str, page_id: str) -> Optional[str]:
    """Returns the external URL for a given book and page, or None if not found."""
    return URL_DB.get((book_id, page_id))

def deterministic_match(book_id: str, page_id: str, user_message: str) -> Optional[str]:
    """
    Checks if the user_message matches any predefined deterministic rules.
    Returns the mapped answer if a match is found, otherwise None.
    """
    rules = MOCK_RULES_DB.get((book_id, page_id), [])
    for pattern, answer in rules:
        if re.search(pattern, user_message):
            return answer
    return None
