"""Canonical domain models for Barbooks."""

from pydantic import BaseModel, Field


class LineItemAnswer(BaseModel):
    """A single structured answer for a rank-based line-item lookup.

    Returned by the short-circuit layer when a user asks "Who is #N?" or the
    full answer key is requested. ``correct`` is always True for items returned
    from deterministic lookups (reserved for future "check my answer" use).
    """

    rank: int
    name: str
    stat: str
    correct: bool = True


class AnswerKey(BaseModel):
    """The full ordered answer key for a page, returned as a structured object.

    Returned by the short-circuit layer when a user asks "show me the answers"
    or "give me the answer key".
    """

    items: list[LineItemAnswer]


class PageItem(BaseModel):
    """A single item (row) within a page's answer list.

    For rank-based pages: rank is the 1-based position, key is the player/team name,
    stat_value is the numeric stat (e.g. TDs, yards), stat_label names the stat.
    For year-based pages: rank is None, key is the year (as string), stat_value is None.
    """

    rank: int | None = None  # 1-based rank for rank-ordered lists; None for year lists
    key: str = ""  # The clue key: year string or rank label ("#1", "2024", etc.)
    name: str = ""  # Player / team name — the answer to reveal
    stat_value: str = ""  # Numeric stat (e.g. "157", "1,846") as string; "" if N/A
    stat_label: str = ""  # Human-readable stat name (e.g. "TDs", "rushing yards")


class Page(BaseModel):
    """A single row in a book's spreadsheet, identified by a QR-code-scanned page_id."""

    page_id: str
    url: str
    title: str = ""
    description: str = ""
    type: str = "list"
    clue_style: str = ""
    clue_type: str = ""  # "rank" | "year" | "team" | "matchup" | ""
    item_count: int = 0  # Number of items on this page
    stat_label: str = (
        ""  # Canonical stat label for this page ("TDs", "rushing yards", …)
    )
    items: list[
        PageItem
    ] = []  # Ordered list of items; populated from Answer sheet or scrape


class Book(BaseModel):
    """A book loaded from a spreadsheet file, containing a collection of Pages."""

    id: str
    pages: dict[str, Page]  # page_id -> Page


class ChatRequest(BaseModel):
    """The incoming user request — chat message plus the scanned book/page context."""

    user_message: str = Field(..., max_length=150, description="The user's query")
    book_id: str = Field(..., description="ID of the book")
    page_id: str = Field(..., description="ID of the target page")


class ChatResponse(BaseModel):
    """The validated answer returned to the user, with attribution to the source.

    ``answer`` is a plain string for LLM/system responses, a ``LineItemAnswer``
    for rank-based lookups, or an ``AnswerKey`` for full answer-key requests.
    ``source`` is one of: "short_circuit", "llm", "system".
    """

    answer: LineItemAnswer | AnswerKey | str
    source: str


class QRCodeRef(BaseModel):
    """The structured reference encoded in a QR code.

    Maps to a specific (book_id, page_id).
    """

    book_id: str
    page_id: str
