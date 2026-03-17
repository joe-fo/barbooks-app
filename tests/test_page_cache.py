"""Unit tests for page_cache deserialization."""

import json

from app.domain.models import PageItem
from app.page_cache import _deserialize_items, _load_cache


def test_deserialize_items_coerces_dicts():
    raw = [
        {
            "rank": 1,
            "key": "#1",
            "name": "Alice",
            "stat_value": "100",
            "stat_label": "Yards",
        },
        {
            "rank": 2,
            "key": "#2",
            "name": "Bob",
            "stat_value": "90",
            "stat_label": "Yards",
        },
    ]
    result = _deserialize_items(raw)
    assert all(isinstance(item, PageItem) for item in result)
    assert result[0].rank == 1
    assert result[0].name == "Alice"
    assert result[0].stat_value == "100"


def test_deserialize_items_passes_through_instances():
    instances = [PageItem(rank=1, key="#1", name="Alice", stat_value="100")]
    result = _deserialize_items(instances)
    assert result == instances


def test_deserialize_items_empty():
    assert _deserialize_items([]) == []


def test_deserialize_items_cleans_duplicate_names():
    """Stale cache entries with concatenated names are cleaned on read."""
    raw = [
        {
            "rank": 1,
            "key": "#1",
            "name": "Eli ManningE. Manning",
            "stat_value": "57,023",
            "stat_label": "Yards",
        },
        {
            "rank": 2,
            "key": "#2",
            "name": "Dak PrescottD. Prescott",
            "stat_value": "35,989",
            "stat_label": "Yards",
        },
        {
            "rank": 3,
            "key": "#3",
            "name": "Jerry Rice",
            "stat_value": "22,895",
            "stat_label": "Yards",
        },
    ]
    result = _deserialize_items(raw)
    assert result[0].name == "Eli Manning"
    assert result[1].name == "Dak Prescott"
    assert result[2].name == "Jerry Rice"


def test_load_cache_returns_page_items(tmp_path):
    cache_file = tmp_path / "book1_page1.json"
    payload = {
        "url": "http://example.com",
        "fetched_at": "2026-01-01T00:00:00+00:00",
        "text": "some text",
        "items": [
            {
                "rank": 1,
                "key": "#1",
                "name": "Alice",
                "stat_value": "100",
                "stat_label": "Yards",
            },
            {
                "rank": 2,
                "key": "#2",
                "name": "Bob",
                "stat_value": "90",
                "stat_label": "Yards",
            },
        ],
    }
    cache_file.write_text(json.dumps(payload), encoding="utf-8")

    result = _load_cache(cache_file)
    assert result is not None
    text, items = result
    assert text == "some text"
    assert len(items) == 2
    assert all(isinstance(item, PageItem) for item in items)
    assert items[0].rank == 1
    assert items[1].name == "Bob"


def test_load_cache_cleans_stale_duplicate_names(tmp_path):
    """Cache files written before the name-dedup fix are cleaned on read."""
    cache_file = tmp_path / "nfl_15.json"
    payload = {
        "url": "http://example.com/nfl/15",
        "fetched_at": "2026-01-01T00:00:00+00:00",
        "text": "some text",
        "items": [
            {
                "rank": 1,
                "key": "#1",
                "name": "Eli ManningE. Manning",
                "stat_value": "57,023",
                "stat_label": "Yards",
            },
            {
                "rank": 2,
                "key": "#2",
                "name": "Donovan McNabbD. McNabb",
                "stat_value": "36,250",
                "stat_label": "Yards",
            },
        ],
    }
    cache_file.write_text(json.dumps(payload), encoding="utf-8")

    result = _load_cache(cache_file)
    assert result is not None
    _, items = result
    assert items[0].name == "Eli Manning"
    assert items[1].name == "Donovan McNabb"
