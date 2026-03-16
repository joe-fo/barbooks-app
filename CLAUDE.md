# Barbooks AI — Agent Guide

## Project Purpose

A trivia chatbot that answers questions about ranked lists and stats. Users scan QR codes on physical book pages to reach a Streamlit chat interface. The Streamlit frontend calls a FastAPI backend, which uses a deterministic short-circuit layer and an Ollama-backed LLM to answer questions about the specific page the user scanned.

## Architecture Principles

### Hexagonal Architecture (Ports & Adapters)

Core domain logic must not depend on infrastructure. The boundary is enforced by ports (abstract interfaces) defined in `app/domain/ports.py`. Adapters implement those ports and live outside the domain.

- **Ports**: `AnswerSource` (abstract base class) — anything that can answer a `ChatRequest` given a `Page` and context string.
- **Adapters**: Ollama LLM client, regex/deterministic short-circuit, spreadsheet data loader.
- **Rule**: Never import infrastructure modules (`llm_service`, `spreadsheet_store`, `scraper`) from domain code. Domain code imports only from `app/domain/`.

### Domain-Driven Design

The domain is modeled explicitly in `app/domain/models.py`. Business logic lives in the domain layer, not in FastAPI route handlers or Streamlit callbacks.

**First-class domain objects:**

| Object | Purpose |
|--------|---------|
| `Book` | A collection of pages loaded from a spreadsheet |
| `Page` | A single trivia question page, identified by QR-scanned `page_id` |
| `PageItem` | One row in a page's answer list (rank, name, stat) |
| `ChatRequest` | Incoming user message with `book_id` and `page_id` context |
| `ChatResponse` | Validated answer returned to user, with source attribution |
| `LineItemAnswer` | Structured answer for a rank-based lookup |
| `AnswerKey` | Full ordered answer key for a page |
| `QRCodeRef` | The `(book_id, page_id)` pair encoded in a QR code |
| `AnswerSource` | Port interface: answers a `ChatRequest` or returns `None` |

## Key Conventions

- **Tests mock at the adapter boundary**, never inside the domain. Use fakes/stubs for `AnswerSource` implementations; never patch Ollama internals.
- **New LLM backends = new adapter, zero domain changes.** Implement `AnswerSource` in a new file under `app/`, wire it in `main.py`.
- **All new trivia data goes through the `ingest/` pipeline**, not manual spreadsheet edits. The ingest CLI normalizes and validates data before it reaches `books/`.
- **Short-circuit first**: the deterministic regex/lookup layer (`question_patterns.py`) runs before the LLM. If it returns an answer, the LLM is never called.
- **Input validation at the boundary**: `ChatRequest.user_message` is capped at 150 characters via Pydantic. Don't add extra validation inside domain logic.

## Directory Structure

```
barbooks_app/
├── app/                    # Application code
│   ├── domain/             # Domain layer — pure Python, no infrastructure imports
│   │   ├── models.py       # All first-class domain objects (Pydantic models)
│   │   └── ports.py        # Abstract interfaces (AnswerSource)
│   ├── main.py             # FastAPI app, lifespan startup, route wiring
│   ├── llm_service.py      # Adapter: Ollama LLM backend (implements AnswerSource)
│   ├── spreadsheet_store.py # Adapter: loads Book/Page data from spreadsheets
│   ├── scraper.py          # Adapter: fetches and caches page content from URLs
│   ├── question_patterns.py # Adapter: deterministic regex short-circuit
│   ├── app.py              # Streamlit UI frontend
│   └── admin.py            # Admin/debug endpoints (optional)
├── ingest/                 # Data pipeline: normalize and validate trivia data
│   ├── cli.py              # CLI entrypoint for ingest pipeline
│   └── README.md           # Ingest pipeline documentation
├── books/                  # Spreadsheet data files (input to the system)
├── tests/                  # Test suite
│   ├── conftest.py         # Shared fixtures
│   ├── integration/        # Integration tests (hit real adapters)
│   ├── test_domain_models.py
│   ├── test_endpoints.py
│   ├── test_llm_service.py
│   ├── test_question_patterns.py
│   └── test_spreadsheet_store.py
└── docs/                   # Additional documentation (architecture, plans)
```

## Running the Project

```bash
poetry install      # Install dependencies
task dev            # Run API (port 8000) + Streamlit UI together
task api            # FastAPI backend only
task ui             # Streamlit frontend only
```

Requires Python 3.10+ and [Ollama](https://ollama.com) running locally.
