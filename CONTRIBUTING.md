# Contributing Trivia Pages

This guide explains how to add a new trivia page to Barbooks **without editing
spreadsheets or running CLI tools directly**. You only need a web browser.

---

## Prerequisites

- The Barbooks API must be running (see [README](README.md)).
- You need the **Admin Password** (ask the project owner; leave blank in local dev).

---

## Adding a New Trivia Page

### Step 1 — Open the Admin Form

Navigate to:

```
http://localhost:8000/admin
```

You will see the **Add Trivia Page** form.

### Step 2 — Fill in the Fields

| Field | Description | Example |
|-------|-------------|---------|
| **Book ID** | The short identifier for the book | `nfl` |
| **Page #** | The page number that maps to this question | `10` |
| **Source URL** | The public web page that contains the answer list | `https://www.espn.com/nfl/history/leaders/_/stat/touchdown` |
| **Admin Password** | Leave blank if not set; ask the project owner otherwise | |

### Step 3 — Preview

Click **Preview**. The app will:

1. Fetch the source URL.
2. Parse ranked lists or stats tables from the page.
3. Display a summary of what it found (title, item count, first 10 items).

Review the preview carefully. If the data looks wrong (wrong list, missing
items, etc.) check that the URL points directly to the list page.

### Step 4 — Save

If the preview looks correct, click **Save to Spreadsheet**.

The page row is written to the book's spreadsheet (`books/<book_id>/*.xlsx`).
The API will pick up the new page on next restart (or if hot-reload is enabled,
within a few seconds).

---

## What Happens Behind the Scenes

```
Browser → POST /api/v1/admin/preview
        ← Page preview (title, items, …)

Browser → POST /api/v1/admin/add-page
        ← Confirmation { message, book_id, page_id }
        → Spreadsheet row written to books/<book_id>/*.xlsx  Pages sheet
```

The admin endpoints reuse the same scraping and parsing logic as the
`ingest.py` CLI tool, so the data is validated the same way.

---

## Securing the Admin Form

In production, set the `ADMIN_PASSWORD` environment variable before starting
the API:

```bash
export ADMIN_PASSWORD="your-secret-password"
task api
```

Contributors will be prompted for this password in the form. Requests with a
wrong password receive a `401 Unauthorized` response.

For local development you can leave `ADMIN_PASSWORD` unset — the form will
accept any (including blank) password.

---

## Troubleshooting

| Problem | Likely cause | Fix |
|---------|-------------|-----|
| Preview shows "no items parsed" | The URL doesn't contain a recognized ranked list or stats table | Try the ESPN or Wikipedia URL that lists the data in a table |
| "Failed to fetch URL" error | The source site blocked the request | Try a different source URL or run the CLI tool (`python ingest.py`) |
| "No spreadsheet found for book" | The `books/<book_id>/` directory is missing or has no `.xlsx` file | Create the directory and add a spreadsheet, or check the Book ID |
| 401 Unauthorized | Wrong admin password | Ask the project owner for the password |

---

## Alternative: CLI Tool

If you're comfortable with a terminal, the `ingest.py` CLI offers the same
validation with more detail:

```bash
# Preview (dry run)
python ingest.py --url <url> --book nfl --page 10 --patterns

# Write to spreadsheet (interactive confirmation)
python ingest.py --url <url> --book nfl --page 10 --write
```

See `python ingest.py --help` for all options.
