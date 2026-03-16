"""Loads book/page data from spreadsheets in the books/ directory."""

import os
from typing import Optional

import pandas as pd

from .domain import Book, Page

# In-memory store: book_id -> Book
_books: dict[str, Book] = {}


def load_books(books_dir: str) -> None:
    """Scan books_dir for subdirectories, load xlsx files into _books."""
    global _books
    _books = {}

    if not os.path.isdir(books_dir):
        return

    for book_id in os.listdir(books_dir):
        book_path = os.path.join(books_dir, book_id)
        if not os.path.isdir(book_path):
            continue

        for filename in os.listdir(book_path):
            if filename.endswith(".xlsx"):
                xlsx_path = os.path.join(book_path, filename)
                _load_book(book_id, xlsx_path)
                break


def _load_book(book_id: str, xlsx_path: str) -> None:
    """Load a single book's xlsx file (Pages sheet) into _books."""
    df = pd.read_excel(xlsx_path, sheet_name="Pages", header=3)

    pages: dict[str, Page] = {}
    for _, row in df.iterrows():
        page_num = row.get("Page #")
        url = row.get("Answer Key URL")

        if pd.isna(page_num) or pd.isna(url):
            continue

        page_id = str(int(page_num))
        pages[page_id] = Page(
            page_id=page_id,
            url=str(url),
            title=str(row.get("Title", "")),
            description=str(row.get("Description", "")),
            type=str(row.get("Type", "list")),
            clue_style=str(row.get("# Items / Clue Style", "")),
        )

    _books[book_id] = Book(id=book_id, pages=pages)


def get_book(book_id: str) -> Optional[Book]:
    """Return the Book for a given book_id, or None if not found."""
    return _books.get(book_id)


def get_page(book_id: str, page_id: str) -> Optional[Page]:
    """Return the Page for a given (book_id, page_id), or None if not found."""
    book = _books.get(book_id)
    return book.pages.get(page_id) if book else None


def get_page_url(book_id: str, page_id: str) -> Optional[str]:
    """Return the Answer Key URL for a given (book_id, page_id)."""
    page = get_page(book_id, page_id)
    return page.url if page else None


def update_page_items(book_id: str, page_id: str, items: list) -> None:
    """Attach parsed items to an existing Page (called after startup URL fetch)."""
    book = _books.get(book_id)
    if book and page_id in book.pages:
        book.pages[page_id].items = items


def all_pages() -> list[tuple[str, str, str]]:
    """Return list of (book_id, page_id, url) for all loaded pages."""
    result = []
    for book_id, book in _books.items():
        for page_id, page in book.pages.items():
            if page.url:
                result.append((book_id, page_id, page.url))
    return result
