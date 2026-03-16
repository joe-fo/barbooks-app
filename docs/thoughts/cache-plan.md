# Cache Plan: Fetched Website Data

**Issue**: ba-czf
**Status**: Plan only — implementation follows in a separate bead

## Problem

The server currently re-fetches all source URLs on every startup (see `app/main.py` `lifespan`).
For development this means a network round-trip (and potential rate-limit) every `uvicorn` restart.
The `ingest/` CLI also fetches live each run. Both are slow and fragile against network errors or
third-party site changes.

---

## 1. Cache Mechanism Options

### Option A: File-Based Cache (RECOMMENDED)

Store fetched content as JSON files in a `cache/pages/` directory.

- **Key**: `{book_id}_{page_id}.json`, e.g. `nfl_9.json`
- **Content**: `{ "url": "...", "fetched_at": "2026-03-16T22:00:00Z", "text": "...", "items": [...] }`
- **Pros**: No new dependencies; persistent across restarts; human-readable; easy to nuke/inspect
- **Cons**: File I/O on startup (negligible at <100 pages)

### Option B: SQLite

A `cache/barbooks_cache.db` with a `pages` table: `(book_id, page_id, url, fetched_at, text, items_json)`.

- **Pros**: Queryable; atomic writes; easy to add indexes
- **Cons**: New dependency (stdlib `sqlite3`, so no package cost); overkill for simple URL→content mapping at this scale

### Option C: In-Memory Only (Current)

The existing `_context_cache: dict` in `main.py`.

- **Pros**: Zero latency; no disk state
- **Cons**: Lost on every restart; every `uvicorn` reload re-scrapes all URLs; not usable in `ingest/` CLI

### Decision

**Use file-based cache (Option A).** SQLite adds complexity with no benefit at this scale. In-memory
is insufficient because the core complaint is startup cost. File-based cache is simple, auditable,
and portable with zero new runtime dependencies.

---

## 2. Cache Invalidation Strategy

### Default: 24-Hour TTL

On startup, load the file cache. If a cache entry's `fetched_at` is older than 24 hours, re-fetch
and overwrite the file. Otherwise, skip the network call.

```python
import json, hashlib
from datetime import datetime, timezone, timedelta

CACHE_TTL = timedelta(hours=24)

def is_stale(fetched_at_iso: str) -> bool:
    fetched_at = datetime.fromisoformat(fetched_at_iso).replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - fetched_at > CACHE_TTL
```

### Manual Invalidation: `--refresh` Flag

The `ingest/` CLI and/or a management command should accept `--refresh` (or `--no-cache`) to
force a live fetch regardless of TTL. This lets a maintainer update a specific page when the
source site changes its data.

```bash
# Force re-fetch for a specific page:
python -m ingest --url <url> --book nfl --page 9 --refresh

# Or a future management command:
python -m app.manage refresh-cache --book nfl --page 9
```

### Dev Mode: Offline / Cache-Always

An environment variable `BARBOOKS_CACHE_MODE=offline` disables all network fetches and serves
only from file cache. Useful for frequent dev runs when source sites are irrelevant.

```bash
BARBOOKS_CACHE_MODE=offline uvicorn app.main:app --reload
```

If the cache file is missing in offline mode, log a warning and skip that page (rather than failing
startup).

---

## 3. Where Caching Fits in the Pipeline

### Current flow

```
Server startup
  → spreadsheet_store.load_books()
  → for each page: fetch_url_content(url)  ← network each time
  → _context_cache[(book_id, page_id)] = text
```

### Recommended flow

```
Server startup
  → spreadsheet_store.load_books()
  → for each page: page_cache.get_or_fetch(book_id, page_id, url)
                     ├─ hit + fresh: load from cache/pages/{book_id}_{page_id}.json
                     └─ miss or stale: fetch_url_content(url) → write to cache file
  → _context_cache[(book_id, page_id)] = text  (still in-memory for request speed)
```

The `ingest/` CLI should share the same `page_cache` module so it can also read/write the cache,
avoiding duplicate fetches when both tools run on the same machine.

### Cache ownership

The file cache is an **acceleration layer owned by the server startup loader**. It is not the
source of truth — the spreadsheets in `books/` remain authoritative. The cache is purely a
pre-warmed copy of remote content derived from those spreadsheet URLs.

The `ingest/` CLI may optionally read from the cache (using `--no-cache` to bypass), but its
primary job remains validation and spreadsheet writes — not cache management.

---

## 4. Storage Location and `.gitignore`

### Directory layout

```
barbooks_app/
├── cache/
│   └── pages/
│       ├── nfl_9.json
│       ├── nfl_14.json
│       └── ...
├── books/          ← source of truth (spreadsheets, committed)
├── app/
└── ingest/
```

### Gitignore

`cache/` is runtime state and must not be committed. Add to `.gitignore`:

```
# Runtime page cache (local acceleration layer — not source data)
cache/
```

The `.gitignore` currently lists `.cache` (dotfile) but not a top-level `cache/` directory.
This entry needs to be added.

---

## 5. Cache Module Interface (Sketch)

A new module `app/page_cache.py` (or `cache.py`) with a minimal public interface:

```python
CACHE_DIR = os.getenv("BARBOOKS_CACHE_DIR", "cache/pages")
CACHE_TTL_HOURS = int(os.getenv("BARBOOKS_CACHE_TTL_HOURS", "24"))
CACHE_MODE = os.getenv("BARBOOKS_CACHE_MODE", "normal")  # "normal" | "offline"

async def get_or_fetch(
    book_id: str,
    page_id: str,
    url: str,
    refresh: bool = False,
) -> tuple[str, list]:
    """Return (text, items) from cache or live fetch.

    refresh=True forces re-fetch regardless of TTL.
    CACHE_MODE=offline returns cached content only; warns on miss.
    """
    ...
```

`main.py` lifespan replaces the current `fetch_url_content(url)` call with
`page_cache.get_or_fetch(book_id, page_id, url)`. All other logic (populating `_context_cache`,
calling `update_page_items`) stays the same.

---

## Summary

| Decision | Choice | Reason |
|----------|--------|--------|
| Mechanism | File-based JSON | Simple, no dependencies, human-readable |
| Key format | `{book_id}_{page_id}.json` | Matches existing `(book_id, page_id)` domain key |
| TTL | 24 hours | Balances freshness vs. startup cost |
| Manual override | `--refresh` flag | Targeted invalidation without nuking everything |
| Dev shortcut | `BARBOOKS_CACHE_MODE=offline` | Skip all network fetches for fast iteration |
| Cache owner | Server startup loader (`main.py` lifespan) | That's where startup cost lives |
| Storage | `cache/pages/` | Gitignored; local runtime state |
| Source of truth | `books/` spreadsheets | Cache is derived, not authoritative |
