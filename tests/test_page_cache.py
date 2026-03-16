"""Unit tests for page_cache deserialization."""

import json

from app.domain.models import LineItemAnswer
from app.page_cache import _deserialize_items, _load_cache


def test_deserialize_items_coerces_dicts():
    raw = [
        {"rank": 1, "name": "Alice", "stat": "100"},
        {"rank": 2, "name": "Bob", "stat": "90"},
    ]
    result = _deserialize_items(raw)
    assert all(isinstance(item, LineItemAnswer) for item in result)
    assert result[0].rank == 1
    assert result[0].name == "Alice"
    assert result[0].stat == "100"


def test_deserialize_items_passes_through_instances():
    instances = [LineItemAnswer(rank=1, name="Alice", stat="100")]
    result = _deserialize_items(instances)
    assert result == instances


def test_deserialize_items_empty():
    assert _deserialize_items([]) == []


def test_load_cache_returns_line_item_answers(tmp_path):
    cache_file = tmp_path / "book1_page1.json"
    payload = {
        "url": "http://example.com",
        "fetched_at": "2026-01-01T00:00:00+00:00",
        "text": "some text",
        "items": [
            {"rank": 1, "name": "Alice", "stat": "100"},
            {"rank": 2, "name": "Bob", "stat": "90"},
        ],
    }
    cache_file.write_text(json.dumps(payload), encoding="utf-8")

    result = _load_cache(cache_file)
    assert result is not None
    text, items = result
    assert text == "some text"
    assert len(items) == 2
    assert all(isinstance(item, LineItemAnswer) for item in items)
    assert items[0].rank == 1
    assert items[1].name == "Bob"
