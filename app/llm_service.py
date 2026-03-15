"""LLM service layer using hexagonal architecture (port/adapter pattern)."""
import os
from abc import ABC, abstractmethod

import httpx

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")
DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")


class LLMPort(ABC):
    """Port (interface) for the LLM service. Decouples core logic from any specific model."""

    @abstractmethod
    async def generate_answer(self, context: str, user_message: str) -> str:
        """Generate an answer given page context and the user's question."""


class OllamaAdapter(LLMPort):
    """Adapter that calls a local Ollama instance via /api/chat."""

    def __init__(self, base_url: str = OLLAMA_URL, model: str = DEFAULT_MODEL) -> None:
        self._base_url = base_url
        self._model = model

    async def generate_answer(self, context: str, user_message: str) -> str:
        system_prompt = (
            "You are a terse trivia assistant. "
            "Answer using ONLY the information in the provided context. "
            "Your reply MUST be one of: 'Yes', 'No', or 'Correct!' followed by at most one short sentence. "
            "Do NOT explain. Do NOT add extra information. "
            "If the answer is not in the context, reply 'I don't know.'\n\n"
            f"Context:\n---\n{context}\n---"
        )

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "stream": False,
            "options": {
                "num_predict": 50,   # mechanically cap response length
                "temperature": 0.0,  # deterministic responses
            },
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(self._base_url, json=payload, timeout=30.0)
                response.raise_for_status()
                data = response.json()
                return data.get("message", {}).get("content", "").strip()
        except Exception as e:
            return f"Error connecting to local LLM: {e}"


# Module-level default adapter — main.py calls this convenience wrapper.
_default_adapter: LLMPort = OllamaAdapter()


async def generate_llm_answer(context: str, user_message: str) -> str:
    """Convenience wrapper used by the FastAPI endpoint."""
    return await _default_adapter.generate_answer(context, user_message)
