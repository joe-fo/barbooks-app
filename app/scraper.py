import logging
import re

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


def _parse_items_from_soup(soup: BeautifulSoup) -> list:
    """Parse rank-ordered items from a BeautifulSoup document.

    Tries tables first (rank, name, stat columns), then falls back to <ol> lists.
    Returns a list of PageItem objects; empty list if nothing useful is found.
    """
    from .domain.models import PageItem

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 4:
            continue

        header_cells = [c.get_text(strip=True) for c in rows[0].find_all(["th", "td"])]
        if not header_cells:
            continue

        rank_col = name_col = stat_col = None
        for i, h in enumerate(header_cells):
            low = h.lower()
            if rank_col is None and any(k in low for k in ["rank", "no.", "pos", " #"]):
                rank_col = i
            elif name_col is None and any(
                k in low for k in ["name", "player", "team", "athlete"]
            ):
                name_col = i
            elif stat_col is None and any(
                k in low
                for k in [
                    "yards",
                    "yds",
                    "td",
                    "touchdown",
                    "points",
                    "pts",
                    "receptions",
                    "rec",
                    "sack",
                    "tackles",
                    "interceptions",
                ]
            ):
                stat_col = i

        if rank_col is None:
            rank_col = 0
        if name_col is None and len(header_cells) >= 2:
            name_col = 1
        if stat_col is None and len(header_cells) >= 3:
            stat_col = 2

        stat_label = (
            header_cells[stat_col]
            if stat_col is not None and stat_col < len(header_cells)
            else ""
        )

        items: list = []
        for row_idx, row in enumerate(rows[1:], start=1):
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            if len(cells) < 2:
                continue

            rank_val: int
            if rank_col is not None and rank_col < len(cells):
                raw = re.sub(r"[^\d]", "", cells[rank_col])
                rank_val = int(raw) if raw else row_idx
            else:
                rank_val = row_idx

            nc, sc = name_col, stat_col
            name_val = cells[nc] if nc is not None and nc < len(cells) else ""
            stat_val = cells[sc] if sc is not None and sc < len(cells) else ""

            if not name_val:
                continue

            items.append(
                PageItem(
                    rank=rank_val,
                    key=f"#{rank_val}",
                    name=name_val,
                    stat_value=stat_val,
                    stat_label=stat_label,
                )
            )

        if len(items) >= 3:
            return items

    for ol in soup.find_all("ol"):
        items = []
        for i, li in enumerate(ol.find_all("li"), start=1):
            text = li.get_text(strip=True)
            if text:
                from .domain.models import PageItem as _PI

                items.append(_PI(rank=i, key=f"#{i}", name=text))
        if len(items) >= 3:
            return items

    return []


async def fetch_url_content(url: str) -> tuple[str, list]:
    """Fetch URL once; return ``(text_context, parsed_items)``.

    Parses rank-ordered items from tables/lists before stripping HTML, so both
    structured data and plain text are derived from a single network request.
    Returns ``("Error ...", [])`` on failure.
    """
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                " (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            )
        }
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(url, headers=headers, timeout=10.0)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, "html.parser")

            items = _parse_items_from_soup(soup)

            for script in soup(["script", "style"]):
                script.extract()

            text = soup.get_text(separator=" ")
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = "\n".join(chunk for chunk in chunks if chunk)

            return text, items

    except Exception as e:
        logger.error(f"Error fetching URL {url}: {e}")
        return f"Error extracting context: {e}", []


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
        async with httpx.AsyncClient(follow_redirects=True) as client:
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
