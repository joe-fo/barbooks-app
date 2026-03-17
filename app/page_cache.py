"""File-based page cache with TTL and offline mode support.

Cache files are stored at BARBOOKS_CACHE_DIR (default: cache/pages/) as JSON:
  {book_id}_{page_id}.json → { url, fetched_at, text, items }

Environment variables:
  BARBOOKS_CACHE_DIR       Override default cache directory (cache/pages/)
  BARBOOKS_CACHE_TTL_HOURS Override default 24-hour TTL
  BARBOOKS_CACHE_MODE      Set to "offline" to disable live fetches
"""

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

CACHE_DIR = os.getenv("BARBOOKS_CACHE_DIR", "cache/pages")
CACHE_TTL_HOURS = int(os.getenv("BARBOOKS_CACHE_TTL_HOURS", "24"))
CACHE_MODE = os.getenv("BARBOOKS_CACHE_MODE", "normal")  # "normal" | "offline"


def _deserialize_items(raw: list) -> list:
    """Coerce each dict to PageItem with name cleaning; pass through existing instances.

    Cache files are written as PageItem dicts (rank, key, name, stat_value,
    stat_label).  Applying _clean_name here ensures that stale cache entries
    written before the name-deduplication fix are transparently cleaned on read.
    """
    from .domain.models import PageItem
    from .scraper import _clean_name

    result = []
    for i in raw:
        if isinstance(i, dict):
            cleaned = dict(i)
            if "name" in cleaned:
                cleaned["name"] = _clean_name(cleaned["name"])
            result.append(PageItem(**cleaned))
        else:
            result.append(i)
    return result


def _cache_path(book_id: str, page_id: str) -> Path:
    return Path(CACHE_DIR) / f"{book_id}_{page_id}.json"


def _is_stale(fetched_at_iso: str) -> bool:
    fetched_at = datetime.fromisoformat(fetched_at_iso).replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - fetched_at > timedelta(hours=CACHE_TTL_HOURS)


def _load_cache(path: Path) -> tuple[str, list] | None:
    """Return (text, items) from a cache file, or None if unreadable."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data["text"], _deserialize_items(data.get("items", []))
    except Exception as e:
        logger.warning("Failed to read cache file %s: %s", path, e)
        return None


def _write_cache(path: Path, url: str, text: str, items: list) -> None:
    """Write (text, items) to a cache file atomically."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "url": url,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "text": text,
            "items": [
                item.model_dump() if hasattr(item, "model_dump") else item
                for item in items
            ],
        }
        content = json.dumps(payload, ensure_ascii=False, indent=2)
        path.write_text(content, encoding="utf-8")
    except Exception as e:
        logger.warning("Failed to write cache file %s: %s", path, e)


async def get_or_fetch(
    book_id: str,
    page_id: str,
    url: str,
    refresh: bool = False,
) -> tuple[str, list]:
    """Return (text, items) from cache or live fetch.

    refresh=True forces a live fetch regardless of TTL.
    BARBOOKS_CACHE_MODE=offline serves from cache only; warns and returns
    ("", []) on a cache miss rather than making a network call.
    """
    from .scraper import fetch_url_content

    path = _cache_path(book_id, page_id)
    offline = CACHE_MODE == "offline"

    if not refresh and path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not _is_stale(data["fetched_at"]):
                logger.debug("Cache hit (fresh) for (%s, %s)", book_id, page_id)
                return data["text"], _deserialize_items(data.get("items", []))
            logger.debug("Cache hit (stale) for (%s, %s)", book_id, page_id)
        except Exception as e:
            logger.warning("Cache read error for (%s, %s): %s", book_id, page_id, e)

    if offline:
        if path.exists():
            result = _load_cache(path)
            if result is not None:
                logger.info(
                    "Offline mode: serving stale cache for (%s, %s)", book_id, page_id
                )
                return result
        logger.warning(
            "Offline mode: no cache for (%s, %s), skipping fetch", book_id, page_id
        )
        return "", []

    logger.info("Fetching live content for (%s, %s) from %s", book_id, page_id, url)
    text, items = await fetch_url_content(url)
    if not text.startswith("Error"):
        _write_cache(path, url, text, items)
    return text, items
