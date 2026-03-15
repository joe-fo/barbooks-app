"""Canonical domain models for Barbooks."""

from pydantic import BaseModel, Field


class Page(BaseModel):
    """A single row in a book's spreadsheet, identified by a QR-code-scanned page_id."""

    page_id: str
    url: str
    title: str = ""
    description: str = ""
    type: str = "list"
    clue_style: str = ""


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
    """The validated answer returned to the user, with attribution to the source."""

    answer: str
    source: str


class QRCodeRef(BaseModel):
    """The structured reference encoded in a QR code.

    Maps to a specific (book_id, page_id).
    """

    book_id: str
    page_id: str
