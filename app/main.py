from contextlib import asynccontextmanager
from fastapi import FastAPI
from pydantic import BaseModel, Field
from .llm_service import generate_llm_answer
from .scraper import fetch_url_text
from . import mock_db
import logging

logger = logging.getLogger(__name__)

# In-memory cache: (book_id, page_id) -> fetched context text
_context_cache: dict[tuple[str, str], str] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Pre-load and cache all book/page context data on startup."""
    logger.info("Startup: pre-loading book/page context into cache...")
    for (book_id, page_id), url in mock_db.URL_DB.items():
        key = (book_id, page_id)
        logger.info(f"Fetching context for ({book_id}, {page_id}) from {url}")
        text = await fetch_url_text(url)
        if text.startswith("Error"):
            logger.warning(f"Failed to pre-load context for {key}: {text}")
        else:
            _context_cache[key] = text
            logger.info(f"Cached context for {key} ({len(text)} chars)")
    logger.info(f"Startup complete: {len(_context_cache)} page(s) cached.")
    yield
    _context_cache.clear()


app = FastAPI(title="Barbooks API PoC", lifespan=lifespan)

class ChatRequest(BaseModel):
    user_message: str = Field(..., max_length=150, description="The user's query")
    book_id: str = Field(..., description="ID of the book")
    page_id: str = Field(..., description="ID of the target page")

class ChatResponse(BaseModel):
    answer: str
    source: str

@app.post("/api/v1/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    logger.info(f"Received request: {request}")

    # 1. Attempt Deterministic Return
    det_answer = mock_db.deterministic_match(request.book_id, request.page_id, request.user_message)
    if det_answer:
        return ChatResponse(answer=det_answer, source="deterministic")

    # 2. Look up context from startup cache (avoids per-request URL fetching)
    key = (request.book_id, request.page_id)
    context = _context_cache.get(key)
    if context is None:
        # Cache miss: page not found or failed to load at startup
        target_url = mock_db.get_page_url(request.book_id, request.page_id)
        if not target_url:
            return ChatResponse(answer="I don't have any information for that book or page.", source="system")
        context = await fetch_url_text(target_url)
        if context.startswith("Error"):
            logger.error(f"Failed to fetch context on-demand: {context}")
            return ChatResponse(answer="I encountered an error trying to read the book's context.", source="system")
        _context_cache[key] = context

    # 3. Fallback to LLM
    llm_answer = await generate_llm_answer(context, request.user_message)
    return ChatResponse(answer=llm_answer, source="llm")
