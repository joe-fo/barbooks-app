# ingest/

Data pipeline tooling for Barbooks AI. This directory contains the CLI and
helpers for fetching, validating, and writing trivia page data to the
spreadsheet store.

## Usage

```bash
# Preview (dry run — shows parsed data, no writes)
python -m ingest --url <url> --book nfl --page 10

# Also print suggested short-circuit regex patterns
python -m ingest --url <url> --book nfl --page 10 --patterns

# Write to spreadsheet (prompts for confirmation)
python -m ingest --url <url> --book nfl --page 10 --write

# Via Taskfile
task ingest -- --url <url> --book nfl --page 10
```

Run `python -m ingest --help` for the full option list.

## Structure

| File | Purpose |
|------|---------|
| `cli.py` | All fetch, parse, display, and write logic |
| `__init__.py` | Re-exports the public API for import by other modules |
| `__main__.py` | Entry point for `python -m ingest` |

## Notes

The ingest process is intentionally manual — a human reviews the parsed preview
before committing a row to the spreadsheet. The admin web form at
`/admin` provides the same functionality without a terminal. This pipeline
will be improved over time as data sources and parsing requirements evolve.
