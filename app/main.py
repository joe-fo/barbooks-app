import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import mock_db, spreadsheet_store
from .admin import router as admin_router
from .domain import ChatRequest, ChatResponse
from .llm_service import generate_llm_answer
from .scraper import fetch_url_text

logger = logging.getLogger(__name__)

BOOKS_DIR = os.getenv("BOOKS_DIR", "books")

# In-memory cache: (book_id, page_id) -> fetched context text
_context_cache: dict[tuple[str, str], str] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load spreadsheet data and pre-fetch all page contexts on startup."""
    logger.info(
        "Startup: loading book/page data from spreadsheets in '%s'...", BOOKS_DIR
    )
    spreadsheet_store.load_books(BOOKS_DIR)

    pages = spreadsheet_store.all_pages()
    logger.info("Loaded %d page(s) from spreadsheets.", len(pages))

    for book_id, page_id, url in pages:
        key = (book_id, page_id)
        logger.info("Fetching context for (%s, %s) from %s", book_id, page_id, url)
        text = await fetch_url_text(url)
        if text.startswith("Error"):
            logger.warning("Failed to pre-load context for %s: %s", key, text)
        else:
            _context_cache[key] = text
            logger.info("Cached context for %s (%d chars)", key, len(text))

    logger.info("Startup complete: %d page context(s) cached.", len(_context_cache))
    yield
    _context_cache.clear()


app = FastAPI(title="Barbooks API PoC", lifespan=lifespan)
app.include_router(admin_router)


@app.post("/api/v1/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    logger.info("Received request: %s", request)

    # 1. Attempt deterministic short-circuit before hitting the LLM
    det_answer = mock_db.deterministic_match(
        request.book_id, request.page_id, request.user_message
    )
    if det_answer:
        return ChatResponse(answer=det_answer, source="deterministic")

    # 2. Look up context from startup cache
    key = (request.book_id, request.page_id)
    context = _context_cache.get(key)
    if context is None:
        target_url = spreadsheet_store.get_page_url(request.book_id, request.page_id)
        if not target_url:
            return ChatResponse(
                answer="I don't have any information for that book or page.",
                source="system",
            )
        context = await fetch_url_text(target_url)
        if context.startswith("Error"):
            logger.error("Failed to fetch context on-demand: %s", context)
            return ChatResponse(
                answer="I encountered an error trying to read the book's context.",
                source="system",
            )
        _context_cache[key] = context

    # 3. Fallback to LLM
    llm_answer = await generate_llm_answer(context, request.user_message)
    return ChatResponse(answer=llm_answer, source="llm")
