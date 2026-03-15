from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from .llm_service import generate_llm_answer
from .scraper import fetch_url_text
from . import mock_db
import logging

app = FastAPI(title="Barbooks API PoC")
logger = logging.getLogger(__name__)

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

    # 2. Get the target URL for the requested page
    target_url = mock_db.get_page_url(request.book_id, request.page_id)
    if not target_url:
        return ChatResponse(answer="I don't have any information for that book or page.", source="system")

    # 3. Fetch context from URL
    context = await fetch_url_text(target_url)
    if context.startswith("Error"):
        logger.error(f"Failed to fetch context: {context}")
        return ChatResponse(answer="I encountered an error trying to read the book's context.", source="system")

    # 4. Fallback to LLM
    llm_answer = await generate_llm_answer(context, request.user_message)
    return ChatResponse(answer=llm_answer, source="llm")
