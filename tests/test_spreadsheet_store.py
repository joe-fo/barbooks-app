"""Tests for spreadsheet book/page loading."""

from unittest.mock import patch

import pandas as pd

from app import spreadsheet_store
from app.domain.models import Book


def _make_pages_df(rows):
    """Build a DataFrame with the expected Pages sheet columns."""
    defaults = {
        "Page #": None,
        "Answer Key URL": None,
        "Title": "",
        "Description": "",
        "Type": "list",
        "# Items / Clue Style": "",
    }
    full_rows = [{**defaults, **r} for r in rows]
    return pd.DataFrame(full_rows)


class TestLoadBooks:
    def test_nonexistent_dir_leaves_store_empty(self, tmp_path):
        spreadsheet_store.load_books(str(tmp_path / "nonexistent"))
        assert spreadsheet_store.get_book("any") is None

    def test_empty_dir_leaves_store_empty(self, tmp_path):
        spreadsheet_store.load_books(str(tmp_path))
        assert spreadsheet_store.get_book("nfl") is None

    def test_dir_with_non_xlsx_files_ignored(self, tmp_path):
        book_dir = tmp_path / "nfl"
        book_dir.mkdir()
        (book_dir / "notes.txt").write_text("ignore me")
        spreadsheet_store.load_books(str(tmp_path))
        assert spreadsheet_store.get_book("nfl") is None

    def test_load_books_resets_prior_state(self, tmp_path):
        # Pre-populate _books manually
        spreadsheet_store._books["stale"] = Book(id="stale", pages={})
        spreadsheet_store.load_books(str(tmp_path / "nonexistent"))
        assert spreadsheet_store.get_book("stale") is None


class TestLoadBook:
    def test_parses_valid_rows(self):
        mock_df = _make_pages_df(
            [
                {
                    "Page #": 9,
                    "Answer Key URL": "http://example.com/9",
                    "Title": "TD Leaders",
                },
                {
                    "Page #": 10,
                    "Answer Key URL": "http://example.com/10",
                    "Title": "Rushing Leaders",
                },
            ]
        )
        with patch("pandas.read_excel", return_value=mock_df):
            spreadsheet_store._load_book("nfl", "/fake/nfl.xlsx")

        book = spreadsheet_store.get_book("nfl")
        assert book is not None
        assert isinstance(book, Book)
        assert book.id == "nfl"
        assert set(book.pages.keys()) == {"9", "10"}

    def test_page_fields_populated(self):
        mock_df = _make_pages_df(
            [
                {
                    "Page #": 9,
                    "Answer Key URL": "http://example.com/9",
                    "Title": "TD Leaders",
                    "Description": "All-time TDs",
                    "Type": "list",
                    "# Items / Clue Style": "10 items",
                }
            ]
        )
        with patch("pandas.read_excel", return_value=mock_df):
            spreadsheet_store._load_book("nfl", "/fake/nfl.xlsx")

        page = spreadsheet_store.get_page("nfl", "9")
        assert page is not None
        assert page.page_id == "9"
        assert page.url == "http://example.com/9"
        assert page.title == "TD Leaders"
        assert page.description == "All-time TDs"
        assert page.type == "list"

    def test_skips_nan_page_num(self):
        mock_df = _make_pages_df(
            [
                {
                    "Page #": None,
                    "Answer Key URL": "http://example.com/1",
                    "Title": "Missing Page#",
                },
                {
                    "Page #": 5,
                    "Answer Key URL": "http://example.com/5",
                    "Title": "Valid",
                },
            ]
        )
        with patch("pandas.read_excel", return_value=mock_df):
            spreadsheet_store._load_book("test", "/fake/test.xlsx")

        book = spreadsheet_store.get_book("test")
        assert book is not None
        assert "5" in book.pages
        assert len(book.pages) == 1

    def test_skips_nan_url(self):
        mock_df = _make_pages_df(
            [
                {"Page #": 5, "Answer Key URL": None, "Title": "Missing URL"},
                {
                    "Page #": 7,
                    "Answer Key URL": "http://example.com/7",
                    "Title": "Valid",
                },
            ]
        )
        with patch("pandas.read_excel", return_value=mock_df):
            spreadsheet_store._load_book("test", "/fake/test.xlsx")

        book = spreadsheet_store.get_book("test")
        assert "7" in book.pages
        assert "5" not in book.pages

    def test_empty_sheet_produces_empty_book(self):
        mock_df = _make_pages_df([])
        with patch("pandas.read_excel", return_value=mock_df):
            spreadsheet_store._load_book("empty", "/fake/empty.xlsx")

        book = spreadsheet_store.get_book("empty")
        assert book is not None
        assert book.pages == {}

    def test_page_id_is_integer_string(self):
        mock_df = _make_pages_df(
            [
                {"Page #": 9.0, "Answer Key URL": "http://example.com/9"},
            ]
        )
        with patch("pandas.read_excel", return_value=mock_df):
            spreadsheet_store._load_book("nfl", "/fake/nfl.xlsx")

        assert spreadsheet_store.get_page("nfl", "9") is not None


class TestGetters:
    def setup_method(self):
        mock_df = _make_pages_df(
            [
                {
                    "Page #": 9,
                    "Answer Key URL": "http://example.com/9",
                    "Title": "TD Leaders",
                },
                {
                    "Page #": 10,
                    "Answer Key URL": "http://example.com/10",
                    "Title": "Rushing Leaders",
                },
            ]
        )
        with patch("pandas.read_excel", return_value=mock_df):
            spreadsheet_store._load_book("nfl", "/fake/nfl.xlsx")

    def test_get_book_known(self):
        book = spreadsheet_store.get_book("nfl")
        assert book is not None
        assert book.id == "nfl"

    def test_get_book_unknown(self):
        assert spreadsheet_store.get_book("nba") is None

    def test_get_page_known(self):
        page = spreadsheet_store.get_page("nfl", "9")
        assert page is not None
        assert page.page_id == "9"

    def test_get_page_unknown_book(self):
        assert spreadsheet_store.get_page("nba", "9") is None

    def test_get_page_unknown_page(self):
        assert spreadsheet_store.get_page("nfl", "999") is None

    def test_get_page_url_known(self):
        url = spreadsheet_store.get_page_url("nfl", "9")
        assert url == "http://example.com/9"

    def test_get_page_url_unknown(self):
        assert spreadsheet_store.get_page_url("nfl", "999") is None

    def test_all_pages_returns_all_tuples(self):
        pages = spreadsheet_store.all_pages()
        book_page_pairs = {(b, p) for b, p, _ in pages}
        assert ("nfl", "9") in book_page_pairs
        assert ("nfl", "10") in book_page_pairs

    def test_all_pages_includes_url(self):
        pages = spreadsheet_store.all_pages()
        nfl_9 = next((u for b, p, u in pages if b == "nfl" and p == "9"), None)
        assert nfl_9 == "http://example.com/9"
