import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from . import mock_db, spreadsheet_store
from .admin import router as admin_router
from .domain import AnswerKey, ChatRequest, ChatResponse, LineItemAnswer
from .llm_service import generate_llm_answer
from .question_patterns import QuestionIntent, classify_question
from .scraper import fetch_url_content, fetch_url_text

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
        text, items = await fetch_url_content(url)
        if text.startswith("Error"):
            logger.warning("Failed to pre-load context for %s: %s", key, text)
        else:
            _context_cache[key] = text
            logger.info("Cached context for %s (%d chars)", key, len(text))
            if items:
                spreadsheet_store.update_page_items(book_id, page_id, items)
                logger.info("Cached %d items for %s", len(items), key)

    logger.info("Startup complete: %d page context(s) cached.", len(_context_cache))
    yield
    _context_cache.clear()


app = FastAPI(title="Barbooks API PoC", lifespan=lifespan)
app.include_router(admin_router)


class PageInfoResponse(BaseModel):
    """Page metadata returned to the Streamlit UI for display."""

    title: str
    description: str
    category: str


@app.get("/api/v1/page/{book_id}/{page_id}", response_model=PageInfoResponse)
async def page_info(book_id: str, page_id: str):
    """Return display metadata for a given (book_id, page_id)."""
    page = spreadsheet_store.get_page(book_id, page_id)
    if page is None:
        raise HTTPException(status_code=404, detail="Page not found")
    return PageInfoResponse(
        title=page.title,
        description=page.description,
        category=page.type,
    )


@app.post("/api/v1/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    logger.info("Received request: %s", request)

    # Fetch page items for source data logging.
    # TODO: Remove this temporary instrumentation once proper observability is in place
    # (e.g. Logfire/pydantic-ai tracing evaluated in ba-18x).
    page = spreadsheet_store.get_page(request.book_id, request.page_id)
    page_items = page.items if page else []

    # 1. Classify question intent for structured short-circuits
    intent, params = classify_question(request.user_message)

    # 1a. RANK_LOOKUP — "who is #N?" → return LineItemAnswer if page data available
    if intent == QuestionIntent.RANK_LOOKUP:
        if page and page.items:
            rank = int(params.get("rank", 0))
            item = next((i for i in page.items if i.rank == rank), None)
            if item:
                line_item = LineItemAnswer(
                    rank=item.rank,
                    name=item.name,
                    stat=item.stat_value,
                    correct=True,
                )
                response = ChatResponse(answer=line_item, source="short_circuit")
                logger.info("Returning response: %s", response.model_dump_json())
                return response

    # 1b. REVEAL — "show me the answers" → return AnswerKey if page data available
    if intent == QuestionIntent.REVEAL:
        if page and page.items:
            answer_key = AnswerKey(
                items=[
                    LineItemAnswer(
                        rank=i.rank if i.rank is not None else 0,
                        name=i.name,
                        stat=i.stat_value,
                        correct=True,
                    )
                    for i in page.items
                ]
            )
            response = ChatResponse(answer=answer_key, source="short_circuit")
            logger.info("Returning response: %s", response.model_dump_json())
            return response

    # 2. Legacy regex-based short-circuit (hardcoded rules for known pages)
    det_answer = mock_db.deterministic_match(
        request.book_id, request.page_id, request.user_message
    )
    if det_answer:
        response = ChatResponse(answer=det_answer, source="short_circuit")
        logger.info("Returning response: %s", response.model_dump_json())
        return response

    # 3. Look up context from startup cache
    key = (request.book_id, request.page_id)
    context = _context_cache.get(key)
    if context is None:
        target_url = spreadsheet_store.get_page_url(request.book_id, request.page_id)
        if not target_url:
            response = ChatResponse(
                answer="I don't have any information for that book or page.",
                source="system",
            )
            logger.info("source_data=%s response=%s", page_items, response.answer)
            logger.info("Returning response: %s", response.model_dump_json())
            return response
        context = await fetch_url_text(target_url)
        if context.startswith("Error"):
            logger.error("Failed to fetch context on-demand: %s", context)
            response = ChatResponse(
                answer="I encountered an error trying to read the book's context.",
                source="system",
            )
            logger.info("source_data=%s response=%s", page_items, response.answer)
            logger.info("Returning response: %s", response.model_dump_json())
            return response
        _context_cache[key] = context

    # 4. Fallback to LLM — pass page metadata and items for enriched system prompt
    llm_answer = await generate_llm_answer(context, request.user_message, page=page)
    response = ChatResponse(answer=llm_answer, source="llm")
    logger.info("source_data=%s response=%s", page_items, response.answer)
    logger.info("Returning response: %s", response.model_dump_json())
    return response
