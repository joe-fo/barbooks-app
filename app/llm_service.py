"""LLM service layer using hexagonal architecture (port/adapter pattern)."""

import logging
import os
from typing import Optional

import httpx

from .domain import AnswerSource, ChatRequest, Page

logger = logging.getLogger(__name__)

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")
DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "phi3:mini")


def _build_system_prompt(context: str, page: Optional[Page]) -> str:
    """Build a system prompt enriched with page metadata and ranked list."""
    if page and page.items:
        title_line = page.title or "a trivia list"
        desc_line = f"\n{page.description}" if page.description else ""

        items = page.items
        if page.answer_count > 0:
            items = [
                i for i in items if i.rank is not None and i.rank <= page.answer_count
            ]

        list_lines = []
        for item in items:
            stat_part = (
                f" ({item.stat_value} {item.stat_label})" if item.stat_value else ""
            )
            list_lines.append(f"  {item.key}: {item.name}{stat_part}")
        ranked_list = "\n".join(list_lines)

        boundary_note = ""
        if page.answer_count > 0:
            boundary_note = (
                f"The trivia question covers only the top {page.answer_count} players. "
                f"Items beyond rank {page.answer_count} are out of scope. "
                "NEVER confirm a player as 'on the list' if their rank exceeds "
                f"{page.answer_count}.\n\n"
            )

        return (
            "You are a terse trivia assistant for this page: "
            f"{title_line}.{desc_line}\n\n"
            f"{boundary_note}"
            "Answer using ONLY the ranked list below. "
            "NEVER invent or assume facts not in the list. "
            "If the answer is not in the list, reply exactly: 'I don't know.'\n\n"
            "Determine the type of request and respond accordingly:\n"
            "- GUESS (user proposes a name, e.g. 'Is it Dak Prescott?', or types "
            "only a bare name like 'Patrick Mahomes'): "
            "Reply 'Yes' or 'No' followed by one short confirming sentence.\n"
            "- QUESTION (user asks for information, e.g. 'Who is #1?'): "
            "Return the player at that rank from the list. "
            "For a list request, enumerate each item on its own line.\n"
            "When asked who is #N, return the player at that rank from the list. "
            "Do not reference ranks not in the list. "
            "Do NOT use the word 'Correct!' — that is reserved for another layer.\n\n"
            f"Ranked List:\n---\n{ranked_list}\n---"
        )

    return (
        "You are a terse trivia assistant. "
        "Answer using ONLY the information in the provided context. "
        "NEVER invent or assume facts not stated in the context. "
        "If the answer is not in the context, reply exactly: 'I don't know.'\n\n"
        "Determine the type of request and respond accordingly:\n"
        "- GUESS (user proposes a specific answer, e.g. 'Is it Dak Prescott?', "
        "'Randy Moss?', or a bare name like 'Patrick Mahomes'): Reply 'Yes' or "
        "'No' followed by one short confirming sentence from the context.\n"
        "- QUESTION (user asks for information, e.g. 'Who is #1?', 'Show me the "
        "list'): For a list request, enumerate each item on its own line. For a "
        "simple factual question, answer in one short sentence.\n"
        "Do NOT use the word 'Correct!' — that is reserved for another layer.\n\n"
        f"Context:\n---\n{context}\n---"
    )


class OllamaAdapter(AnswerSource):
    """AnswerSource adapter that calls a local Ollama instance via /api/chat."""

    def __init__(self, base_url: str = OLLAMA_URL, model: str = DEFAULT_MODEL) -> None:
        self._base_url = base_url
        self._model = model

    async def answer(
        self, request: ChatRequest, page: Page, context: str
    ) -> Optional[str]:
        system_prompt = _build_system_prompt(context, page)

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": request.user_message},
            ],
            "stream": False,
            "options": {
                # Generous cap for list responses; yes/no answers use far fewer tokens.
                "num_predict": 150,
                "temperature": 0.0,  # deterministic responses
            },
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(self._base_url, json=payload, timeout=30.0)
                response.raise_for_status()
                data = response.json()
                return data.get("message", {}).get("content", "").strip() or None
        except Exception as e:
            detail = str(e) or repr(e)
            logger.error(
                "LLM request failed [%s]: %r (url=%s model=%s)",
                type(e).__name__,
                e,
                self._base_url,
                self._model,
            )
            return f"Error connecting to local LLM: {type(e).__name__}: {detail}"


# Module-level default adapter — main.py uses this convenience wrapper.
_default_adapter: AnswerSource = OllamaAdapter()


async def generate_llm_answer(
    context: str,
    user_message: str,
    page: Optional[Page] = None,
) -> str:
    """Convenience wrapper used by the FastAPI endpoint."""
    from .domain.models import ChatRequest as _ChatRequest
    from .domain.models import Page as _Page

    req = _ChatRequest(user_message=user_message, book_id="", page_id="")
    effective_page = page if page is not None else _Page(page_id="", url="")
    result = await _default_adapter.answer(req, effective_page, context)
    return result or ""
