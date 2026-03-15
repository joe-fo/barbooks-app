"""Loads book/page data from spreadsheets in the books/ directory."""
import os
import pandas as pd
from typing import Optional

# In-memory store: book_id -> page_id (str) -> page config dict
_page_db: dict[str, dict[str, dict]] = {}


def load_books(books_dir: str) -> None:
    """Scan books_dir for subdirectories, load xlsx files into _page_db."""
    global _page_db
    _page_db = {}

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
    """Load a single book's xlsx file (Pages sheet) into _page_db."""
    df = pd.read_excel(xlsx_path, sheet_name="Pages", header=3)

    pages: dict[str, dict] = {}
    for _, row in df.iterrows():
        page_num = row.get("Page #")
        url = row.get("Answer Key URL")

        if pd.isna(page_num) or pd.isna(url):
            continue

        page_id = str(int(page_num))
        pages[page_id] = {
            "url": str(url),
            "title": str(row.get("Title", "")),
            "description": str(row.get("Description", "")),
            "type": str(row.get("Type", "list")),
            "clue_style": str(row.get("# Items / Clue Style", "")),
        }

    _page_db[book_id] = pages


def get_page_url(book_id: str, page_id: str) -> Optional[str]:
    """Return the Answer Key URL for a given (book_id, page_id)."""
    page = _page_db.get(book_id, {}).get(page_id)
    return page["url"] if page else None


def get_page_config(book_id: str, page_id: str) -> Optional[dict]:
    """Return full page config for a given (book_id, page_id)."""
    return _page_db.get(book_id, {}).get(page_id)


def all_pages() -> list[tuple[str, str, str]]:
    """Return list of (book_id, page_id, url) for all loaded pages."""
    result = []
    for book_id, pages in _page_db.items():
        for page_id, config in pages.items():
            url = config.get("url", "")
            if url:
                result.append((book_id, page_id, url))
    return result
