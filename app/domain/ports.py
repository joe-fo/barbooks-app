"""Domain ports (abstract interfaces) for the hexagonal architecture."""
from abc import ABC, abstractmethod
from typing import Optional

from .models import ChatRequest, Page


class AnswerSource(ABC):
    """Port: anything that can answer a ChatRequest given a Page and its scraped context.

    Implementations include the deterministic short-circuit (regex/lookup) and the
    LLM adapter (Ollama). Returning None means this source cannot answer the request.
    """

    @abstractmethod
    async def answer(self, request: ChatRequest, page: Page, context: str) -> Optional[str]:
        """Return an answer string, or None if this source declines to answer."""
