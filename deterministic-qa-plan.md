# Deterministic QA Plan: Ranked-List Short-Circuit Layer

**Issue**: ba-3lf
**Status**: Implementation plan — ready for execution
**Context**: Extends `question_patterns.py` archetypes into a full short-circuit layer
that answers ranked-list questions from `Page.items` data without hitting the LLM.

---

## Background

### Problem (GitHub issue #1)

Three query types fell through to the LLM unnecessarily on page `nfl/15`:

| Input | What happened | Should happen |
|---|---|---|
| `dak prescott` | LLM replied "Correct! 35,989" | `CONFIRMATION` → "Yes, Dak Prescott is on this list (#X, Y passing yards)." |
| `show me the full answer key` | LLM replied with partial dump | `REVEAL` → blocked, redirect to guessing |
| `who's #6 on the list` | LLM replied "Correct! Carson Wentz is at #15..." | `RANK_LOOKUP` → "**#6**: {name}" |

### Current State

- **`question_patterns.py`**: Classifies all 12 `QuestionIntent` archetypes via regex. ✅
- **`domain/models.py`**: `Page` and `PageItem` are defined; `Page.items` is the
  structured answer data source. ✅
- **`mock_db.py`**: Current short-circuit — 4 hardcoded name→string entries for one
  page only. **Does not use `Page.items` or `classify_question()`. ❌**
- **`spreadsheet_store.py`**: Loads `Pages` sheet but **never populates `Page.items`**. ❌
- **`main.py`**: Calls `mock_db.deterministic_match()` then falls to LLM — correct
  flow, but the mock never fires for intent-based queries. ❌

---

## Step 1 — Extend Spreadsheet Loading to Populate `Page.items`

**File**: `app/spreadsheet_store.py`

The `_load_book()` function currently reads only the `Pages` sheet. It must also read an
`Answers` sheet (if present) and populate each `Page.items` list.

### Spreadsheet Schema Requirements

Add a second sheet named `Answers` to each book's `.xlsx` file with these columns:

| Column | Type | Notes |
|---|---|---|
| `Page #` | int | Matches `Page.page_id` |
| `Rank` | int or blank | 1-based rank for rank-type pages; blank for year-type |
| `Year` | str or blank | 4-digit year for year-type pages; blank for rank-type |
| `Name` | str | The answer (player/team name) |
| `Stat Value` | str or blank | Numeric stat as string (e.g. `"157"`, `"1,846"`) |
| `Stat Label` | str or blank | Human-readable stat name (e.g. `"TDs"`, `"rushing yards"`) |

The `Pages` sheet should also gain two new optional columns that help formatting:

| Column | Type | Notes |
|---|---|---|
| `Clue Type` | str | `"rank"` \| `"year"` \| `"team"` \| `"matchup"` |
| `Item Count` | int | Number of items on the page |
| `Stat Label` | str | Canonical stat label for the whole page |

If `Clue Type` is absent it can be inferred from the `# Items / Clue Style` text (already
loaded), but an explicit column is preferred.

### Implementation

```python
# In _load_book(), after building `pages`:
try:
    answers_df = pd.read_excel(xlsx_path, sheet_name="Answers")
    for _, row in answers_df.iterrows():
        pid = str(int(row["Page #"]))
        page = pages.get(pid)
        if page is None:
            continue
        rank_raw = row.get("Rank")
        rank = int(rank_raw) if pd.notna(rank_raw) else None
        year_raw = row.get("Year")
        key = str(int(year_raw)) if pd.notna(year_raw) else (f"#{rank}" if rank else "")
        item = PageItem(
            rank=rank,
            key=key,
            name=str(row.get("Name", "")).strip(),
            stat_value=str(row.get("Stat Value", "")).strip(),
            stat_label=str(row.get("Stat Label", "")).strip(),
        )
        page.items.append(item)
        page.item_count = len(page.items)
except Exception:
    pass  # Answers sheet absent — items stay empty, LLM fallback handles it
```

Also read `Clue Type` and `Stat Label` from the `Pages` sheet if present:

```python
clue_type = str(row.get("Clue Type", "")).strip().lower()
stat_label = str(row.get("Stat Label", "")).strip()
# Pass into Page(clue_type=clue_type, stat_label=stat_label, ...)
```

---

## Step 2 — New Module: `app/short_circuit.py`

This replaces the role of `mock_db.deterministic_match()` for intent-based queries.
`mock_db.py` can stay as-is for the hardcoded-fallback entries during transition, but
the new module drives the primary short-circuit path.

### Interface

```python
def short_circuit(user_message: str, page: Page) -> str | None:
    """Return a deterministic answer string, or None to fall through to the LLM."""
```

### Fuzzy Name Matching Helper

Use case-insensitive comparison with basic normalization — no external dependencies
needed for the PoC. `difflib.get_close_matches` is available in the stdlib for fuzzy
matching if exact match fails.

```python
import unicodedata, re as _re

def _normalize(s: str) -> str:
    """Lowercase, strip punctuation and diacritics for fuzzy comparison."""
    s = unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode()
    return _re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()

def _find_item_by_name(items: list[PageItem], name: str) -> list[PageItem]:
    """Return all items whose name fuzzy-matches `name` (case/punct insensitive)."""
    needle = _normalize(name)
    exact = [i for i in items if _normalize(i.name) == needle]
    if exact:
        return exact
    # Partial match: needle is a substring or superset
    partial = [i for i in items if needle in _normalize(i.name) or _normalize(i.name) in needle]
    return partial
```

### Intent → Response Mapping

#### RANK_LOOKUP — `"who is #3?"` / `"what is number 5?"`

```python
rank = int(params["rank"])
item = next((i for i in page.items if i.rank == rank), None)
if item:
    base = f"#{rank}: {item.name}"
    if item.stat_value and item.stat_label:
        base += f" ({item.stat_value} {item.stat_label})"
    return base
return f"There is no #{rank} on this list."  # out-of-range
```

#### REVERSE_RANK — `"what rank is Randy Moss?"`

```python
matches = _find_item_by_name(page.items, params["name"])
if not matches:
    return f"{params['name']} is not on this list."
item = matches[0]
base = f"{item.name} is #{item.rank} on this list."
if item.stat_value and item.stat_label:
    base += f" ({item.stat_value} {item.stat_label})"
return base
```

#### EXISTENCE — `"is Randy Moss on this list?"`

```python
matches = _find_item_by_name(page.items, params["name"])
if not matches:
    return f"No, {params['name']} is not on this list."
item = matches[0]
base = f"Yes, {item.name} is on this list"
if item.rank:
    base += f" (#{item.rank})"
if item.stat_value and item.stat_label:
    base += f" with {item.stat_value} {item.stat_label}"
return base + "."
```

#### CONFIRMATION — `"Jerry Rice?"` / `"is it Jerry Rice?"`

Same logic as EXISTENCE but response uses `"Correct!"` / `"No, that's not it."`:

```python
matches = _find_item_by_name(page.items, params["name"])
if not matches:
    return f"No, {params['name']} is not on this list."
item = matches[0]
resp = f"Yes! {item.name} is on this list"
if item.rank:
    resp += f" at #{item.rank}"
if item.stat_value and item.stat_label:
    resp += f" ({item.stat_value} {item.stat_label})"
return resp + "."
```

#### STAT_LOOKUP — `"how many TDs does Randy Moss have?"`

```python
matches = _find_item_by_name(page.items, params["name"])
if not matches:
    return f"{params['name']} is not on this list."
item = matches[0]
if item.stat_value and item.stat_label:
    return f"{item.name} has {item.stat_value} {item.stat_label}."
# stat columns present on page but not this item
if page.stat_label:
    return f"{item.name} is on this list but their {page.stat_label} is not available."
return None  # fall to LLM
```

#### YEAR_LOOKUP — `"who won in 2020?"`

Only applicable for `page.clue_type == "year"` pages:

```python
if page.clue_type != "year":
    return None  # fall to LLM
year = params["year"]
item = next((i for i in page.items if i.key == year), None)
if item:
    return f"The {year} answer is {item.name}."
return f"{year} is not on this list."
```

#### REVERSE_YEAR — `"what year did Mahomes win?"`

```python
if page.clue_type != "year":
    return None
matches = _find_item_by_name(page.items, params["name"])
if not matches:
    return f"{params['name']} is not on this list."
item = matches[0]
return f"{item.name} appears in {item.key}."
```

#### FREQUENCY — `"how many times does Brady appear?"`

```python
matches = _find_item_by_name(page.items, params["name"])
n = len(matches)
if n == 0:
    return f"{params['name']} does not appear on this list."
elif n == 1:
    return f"{matches[0].name} appears once on this list."
else:
    return f"{params['name']} appears {n} times on this list."
```

#### COUNT — `"how many items are on this list?"`

```python
count = page.item_count or len(page.items)
if count:
    return f"This list has {count} items."
return None  # no item data — fall to LLM
```

#### HINT — `"give me a hint"` / `"clue for #3?"`

For rank-specific hint, return the rank number itself as the clue (not the name —
that defeats the game):

```python
rank_str = params.get("rank")
if rank_str:
    rank = int(rank_str)
    item = next((i for i in page.items if i.rank == rank), None)
    if item and item.stat_value and item.stat_label:
        return f"Clue for #{rank}: {item.stat_value} {item.stat_label}."
    return f"The clue for #{rank} is... #{rank}! That's the hint for a rank-based list."
# General hint
desc = page.description or page.title
count = page.item_count or len(page.items)
hint = f"This list has {count} items." if count else ""
if desc:
    hint = f"{desc} {hint}".strip()
return hint or None
```

#### PAGE_META — `"what is this page about?"`

```python
parts = []
if page.title:
    parts.append(page.title)
if page.description:
    parts.append(page.description)
count = page.item_count or len(page.items)
if count:
    parts.append(f"There are {count} items to guess.")
return " ".join(parts) if parts else None
```

#### REVEAL — `"show me the answers"`

Always block regardless of page data:

```python
return "I can't give away the answers! Try guessing one at a time."
```

#### UNKNOWN — fall to LLM

```python
return None
```

### Empty Items Fallback

If `page.items` is empty and the intent is data-dependent (RANK_LOOKUP, REVERSE_RANK,
EXISTENCE, CONFIRMATION, STAT_LOOKUP, YEAR_LOOKUP, REVERSE_YEAR, FREQUENCY, COUNT),
return `None` so the LLM handles it. REVEAL still returns the block message regardless.

---

## Step 3 — Wire `short_circuit.py` into `main.py`

Replace the `mock_db.deterministic_match()` call in the `/api/v1/chat` endpoint with
the new module. Keep `mock_db` as a last-resort fallback during transition, or remove
it once the new layer is verified.

```python
# main.py (updated chat_endpoint)
from .short_circuit import short_circuit
from . import spreadsheet_store

@app.post("/api/v1/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    logger.info("Received request: %s", request)

    # 1. Look up the Page object (needed for short-circuit)
    page = spreadsheet_store.get_page(request.book_id, request.page_id)

    # 2. Attempt deterministic short-circuit
    if page is not None:
        det_answer = short_circuit(request.user_message, page)
        if det_answer is not None:
            response = ChatResponse(answer=det_answer, source="deterministic")
            logger.info("Returning response: %s", response.model_dump_json())
            return response

    # 3-4. LLM fallback (unchanged) ...
```

---

## Step 4 — Update Logging (from GitHub issue #1 requirement 4)

Add the source data answer to the log so monitoring can validate API response vs.
answer key:

```python
# When short-circuit fires:
logger.info(
    "Short-circuit: intent=%s page=%s/%s answer=%r",
    intent.value, request.book_id, request.page_id, det_answer
)

# When LLM fires:
logger.info(
    "LLM fallback: page=%s/%s message=%r",
    request.book_id, request.page_id, request.user_message
)
```

---

## Fallback Policy Summary

| Intent | Short-circuit when | Falls to LLM when |
|---|---|---|
| RANK_LOOKUP | `page.items` populated | items empty |
| REVERSE_RANK | `page.items` populated | items empty |
| EXISTENCE | `page.items` populated | items empty |
| CONFIRMATION | `page.items` populated | items empty |
| STAT_LOOKUP | item found with stat_value | item not found or no stat |
| YEAR_LOOKUP | `clue_type == "year"` + items | wrong clue_type or no items |
| REVERSE_YEAR | `clue_type == "year"` + items | wrong clue_type or no items |
| FREQUENCY | `page.items` populated | items empty |
| COUNT | `item_count > 0` or items present | no count data |
| HINT | always (best effort) | — |
| PAGE_META | always (uses title/description) | — |
| REVEAL | **always blocked** (never LLM) | — |
| UNKNOWN | never | always |

---

## Step 5 — Tests

### New test file: `tests/test_short_circuit.py`

Cover these cases per intent:

- Rank in range → correct name+stat
- Rank out of range → "no #N on this list"
- Name present → positive response with rank+stat
- Name absent → "not on this list"
- Items list empty → returns `None` (falls to LLM)
- REVEAL always blocks (even with no items)
- UNKNOWN always returns `None`
- Fuzzy match: "randy moss" matches "Randy Moss"
- Fuzzy match: missing item returns not-found, not a false positive

### Regression: existing tests

All existing `test_question_patterns.py` tests should continue to pass — no changes to
`question_patterns.py`. All existing `test_mock_db.py` tests should pass until `mock_db`
is removed.

---

## Files Changed

| File | Change |
|---|---|
| `app/spreadsheet_store.py` | Load `Answers` sheet; populate `Page.items`, `clue_type`, `stat_label` |
| `app/short_circuit.py` | **New** — intent→response dispatcher using `Page.items` |
| `app/main.py` | Replace `mock_db.deterministic_match` call with `short_circuit()` |
| `tests/test_short_circuit.py` | **New** — full coverage for all intents |
| `books/<book>/` | Add `Answers` sheet to spreadsheets (data work, not code) |

`app/mock_db.py` and `app/question_patterns.py` require **no changes**.

---

## Sequence Diagram

```
User message
    │
    ▼
classify_question(message)
    ├─► REVEAL ──────────────────────────────► "Can't give away answers!" (blocked)
    ├─► PAGE_META / COUNT / HINT ──────────► answer from Page metadata
    ├─► RANK/REVERSE/EXISTENCE/CONFIRM/STAT
    │       │
    │       ▼
    │   page.items populated?
    │       ├─ Yes ─► build answer from PageItem data ──► deterministic response
    │       └─ No  ─► None
    ├─► YEAR/REVERSE_YEAR
    │       ├─ clue_type==year & items ──► answer from PageItem data
    │       └─ otherwise ──────────────► None
    └─► UNKNOWN ───────────────────────────► None
            │
            ▼ (None → fall through)
        LLM (Ollama)
```
