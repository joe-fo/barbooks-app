import logging

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


async def fetch_url_text(url: str) -> str:
    """
    Fetches the given URL and extracts the visible text content.
    Returns the plain text, or an error message if fetching fails.
    """
    try:
        # Some sites block requests without a standard User-Agent
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                " (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            )
        }
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, timeout=10.0)
            response.raise_for_status()

            # Parse HTML and extract text
            soup = BeautifulSoup(response.content, "html.parser")

            # Remove scripts and styles
            for script in soup(["script", "style"]):
                script.extract()

            # Extract text
            text = soup.get_text(separator=" ")

            # Clean up whitespace
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = "\n".join(chunk for chunk in chunks if chunk)

            return text

    except Exception as e:
        logger.error(f"Error fetching URL {url}: {str(e)}")
        return f"Error extracting context: {str(e)}"
