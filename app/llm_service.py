import httpx
from typing import Optional

import os

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
DEFAULT_MODEL = "llama3.2" # You can configure this to the specific model you have installed

async def generate_llm_answer(context: str, user_message: str) -> str:
    """
    Calls the local Ollama LLM to generate an answer based on the provided context.
    Enforces strict prompting length constraints.
    """
    
    system_prompt = f"""You are a helpful but extremely terse trivia assistant.
You are given the following context from a book:
---
{context}
---
Answer the user's question using ONLY the provided answers.
Your response MUST be no more than 2 sentences. DO NOT explain yourself.
The user is trying to answer a trivia question. Format your response accordingly.
"""

    payload = {
        "model": DEFAULT_MODEL,
        "prompt": f"{system_prompt}\n\nUser Question: {user_message}\nAnswer:",
        "stream": False,
        "options": {
            "num_predict": 50, # mechanically restrict response length
            "temperature": 0.0 # deterministic responses
        }
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(OLLAMA_URL, json=payload, timeout=30.0)
            response.raise_for_status()
            data = response.json()
            return data.get("response", "").strip()
    except Exception as e:
        return f"Error connecting to local LLM: {str(e)}"
