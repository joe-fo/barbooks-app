"""Shared test fixtures."""

import pytest

from app import main as app_main
from app import spreadsheet_store


@pytest.fixture(autouse=True)
def reset_stores():
    """Reset global mutable state between tests."""
    spreadsheet_store._books = {}
    app_main._context_cache.clear()
    yield
    spreadsheet_store._books = {}
    app_main._context_cache.clear()
