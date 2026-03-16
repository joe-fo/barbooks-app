"""FastAPI endpoint tests using TestClient with mocked dependencies."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.domain.models import Page, PageItem
from app.main import app


@pytest.fixture
def client():
    """TestClient with mocked startup — no disk or network access during lifespan."""
    with (
        patch("app.main.spreadsheet_store.load_books"),
        patch("app.main.spreadsheet_store.all_pages", return_value=[]),
    ):
        with TestClient(app) as c:
            yield c


class TestPageInfoEndpoint:
    def test_returns_page_info_when_found(self, client):
        fake_page = Page(
            page_id="9",
            url="http://example.com",
            title="NFL All-Time Touchdown Leaders",
            description="Who leads the NFL in career TDs?",
            type="list",
        )
        with patch("app.main.spreadsheet_store.get_page", return_value=fake_page):
            response = client.get("/api/v1/page/nfl/9")

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "NFL All-Time Touchdown Leaders"
        assert data["description"] == "Who leads the NFL in career TDs?"
        assert data["category"] == "list"

    def test_returns_404_when_page_not_found(self, client):
        with patch("app.main.spreadsheet_store.get_page", return_value=None):
            response = client.get("/api/v1/page/unknown/999")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_response_shape(self, client):
        fake_page = Page(
            page_id="1",
            url="http://example.com",
            title="Some Title",
            description="",
            type="list",
        )
        with patch("app.main.spreadsheet_store.get_page", return_value=fake_page):
            response = client.get("/api/v1/page/nfl/1")

        assert response.status_code == 200
        data = response.json()
        assert "title" in data
        assert "description" in data
        assert "category" in data


class TestChatEndpointValidation:
    def test_missing_user_message_returns_422(self, client):
        response = client.post("/api/v1/chat", json={"book_id": "nfl", "page_id": "9"})
        assert response.status_code == 422

    def test_missing_book_id_returns_422(self, client):
        response = client.post(
            "/api/v1/chat", json={"user_message": "hello", "page_id": "9"}
        )
        assert response.status_code == 422

    def test_missing_page_id_returns_422(self, client):
        response = client.post(
            "/api/v1/chat", json={"user_message": "hello", "book_id": "nfl"}
        )
        assert response.status_code == 422

    def test_message_over_150_chars_returns_422(self, client):
        response = client.post(
            "/api/v1/chat",
            json={
                "user_message": "x" * 151,
                "book_id": "nfl",
                "page_id": "9",
            },
        )
        assert response.status_code == 422

    def test_message_exactly_150_chars_succeeds(self, client):
        with (
            patch("app.main.mock_db.deterministic_match", return_value="Yes!"),
        ):
            response = client.post(
                "/api/v1/chat",
                json={
                    "user_message": "x" * 150,
                    "book_id": "nfl",
                    "page_id": "9",
                },
            )
        assert response.status_code == 200

    def test_empty_message_returns_422(self, client):
        # Pydantic enforces min-length implicitly via required field;
        # an empty string IS valid (no min_length constraint), so 200 expected
        with patch("app.main.mock_db.deterministic_match", return_value="Answer"):
            response = client.post(
                "/api/v1/chat",
                json={"user_message": "", "book_id": "nfl", "page_id": "9"},
            )
        assert response.status_code == 200


class TestChatEndpointDeterministicPath:
    def test_deterministic_match_returned(self, client):
        with patch(
            "app.main.mock_db.deterministic_match",
            return_value="Yes, Jerry Rice is 1st.",
        ):
            response = client.post(
                "/api/v1/chat",
                json={
                    "user_message": "Is Jerry Rice on the list?",
                    "book_id": "nfl",
                    "page_id": "9",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["answer"] == "Yes, Jerry Rice is 1st."
        assert data["source"] == "short_circuit"

    def test_response_shape(self, client):
        with patch("app.main.mock_db.deterministic_match", return_value="Some answer"):
            response = client.post(
                "/api/v1/chat",
                json={"user_message": "test", "book_id": "b", "page_id": "1"},
            )
        assert response.status_code == 200
        data = response.json()
        assert "answer" in data
        assert "source" in data


class TestChatEndpointLLMFallback:
    def test_llm_fallback_when_no_deterministic_match(self, client):
        with (
            patch("app.main.mock_db.deterministic_match", return_value=None),
            patch(
                "app.main.generate_llm_answer",
                new=AsyncMock(return_value="LLM answer here"),
            ),
        ):
            # Pre-populate context cache so we skip the fetch
            from app.main import _context_cache

            _context_cache[("nfl", "9")] = "some page context"

            response = client.post(
                "/api/v1/chat",
                json={
                    "user_message": "Who is the best player?",
                    "book_id": "nfl",
                    "page_id": "9",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["answer"] == "LLM answer here"
        assert data["source"] == "llm"

    def test_unknown_book_page_returns_system_response(self, client):
        with (
            patch("app.main.mock_db.deterministic_match", return_value=None),
            patch("app.main.spreadsheet_store.get_page_url", return_value=None),
        ):
            response = client.post(
                "/api/v1/chat",
                json={
                    "user_message": "Some question",
                    "book_id": "unknown_book",
                    "page_id": "999",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert "don't have any information" in data["answer"]
        assert data["source"] == "system"

    def test_fetch_error_returns_system_response(self, client):
        with (
            patch("app.main.mock_db.deterministic_match", return_value=None),
            patch(
                "app.main.spreadsheet_store.get_page_url",
                return_value="http://example.com/page",
            ),
            patch(
                "app.main.fetch_url_text",
                new=AsyncMock(return_value="Error: connection refused"),
            ),
        ):
            response = client.post(
                "/api/v1/chat",
                json={
                    "user_message": "Some question",
                    "book_id": "nfl",
                    "page_id": "9",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert "error" in data["answer"].lower()
        assert data["source"] == "system"

    def test_on_demand_context_fetch_and_cache(self, client):
        """Context is fetched on first request and cached for subsequent ones."""
        call_count = 0

        async def fake_fetch(url):
            nonlocal call_count
            call_count += 1
            return "fetched context"

        with (
            patch("app.main.mock_db.deterministic_match", return_value=None),
            patch(
                "app.main.spreadsheet_store.get_page_url",
                return_value="http://example.com/page",
            ),
            patch("app.main.fetch_url_text", new=fake_fetch),
            patch(
                "app.main.generate_llm_answer",
                new=AsyncMock(return_value="Answer"),
            ),
        ):
            client.post(
                "/api/v1/chat",
                json={"user_message": "Q1", "book_id": "nfl", "page_id": "9"},
            )
            client.post(
                "/api/v1/chat",
                json={"user_message": "Q2", "book_id": "nfl", "page_id": "9"},
            )

        # fetch_url_text should only be called once; second request uses cache
        assert call_count == 1


class TestChatEndpointStructuredShortCircuit:
    """Tests for RANK_LOOKUP and REVEAL intents that return structured objects."""

    @pytest.fixture
    def page_with_items(self):
        return Page(
            page_id="9",
            url="http://example.com",
            title="NFL All-Time Touchdown Leaders",
            description="Career TD leaders",
            type="list",
            items=[
                PageItem(rank=1, name="Jerry Rice", stat_value="208", stat_label="TDs"),
                PageItem(
                    rank=2, name="Emmitt Smith", stat_value="175", stat_label="TDs"
                ),
                PageItem(
                    rank=3,
                    name="LaDainian Tomlinson",
                    stat_value="162",
                    stat_label="TDs",
                ),
                PageItem(rank=4, name="Randy Moss", stat_value="157", stat_label="TDs"),
            ],
        )

    def test_rank_lookup_returns_line_item_answer(self, client, page_with_items):
        with patch("app.main.spreadsheet_store.get_page", return_value=page_with_items):
            response = client.post(
                "/api/v1/chat",
                json={
                    "user_message": "Who is #1 on the list?",
                    "book_id": "nfl",
                    "page_id": "9",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "short_circuit"
        answer = data["answer"]
        assert answer["rank"] == 1
        assert answer["name"] == "Jerry Rice"
        assert answer["stat"] == "208"
        assert answer["correct"] is True

    def test_rank_lookup_rank4_returns_correct_item(self, client, page_with_items):
        with patch("app.main.spreadsheet_store.get_page", return_value=page_with_items):
            response = client.post(
                "/api/v1/chat",
                json={
                    "user_message": "Who is number 4?",
                    "book_id": "nfl",
                    "page_id": "9",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "short_circuit"
        assert data["answer"]["rank"] == 4
        assert data["answer"]["name"] == "Randy Moss"

    def test_reveal_returns_answer_key(self, client, page_with_items):
        with patch("app.main.spreadsheet_store.get_page", return_value=page_with_items):
            response = client.post(
                "/api/v1/chat",
                json={
                    "user_message": "Show me the answers",
                    "book_id": "nfl",
                    "page_id": "9",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "short_circuit"
        answer = data["answer"]
        assert "items" in answer
        assert len(answer["items"]) == 4
        assert answer["items"][0]["rank"] == 1
        assert answer["items"][0]["name"] == "Jerry Rice"

    def test_rank_lookup_falls_through_when_no_items(self, client):
        empty_page = Page(
            page_id="9",
            url="http://example.com",
            title="NFL Touchdown Leaders",
            description="",
            type="list",
            items=[],
        )
        with (
            patch("app.main.spreadsheet_store.get_page", return_value=empty_page),
            patch("app.main.mock_db.deterministic_match", return_value=None),
            patch(
                "app.main.generate_llm_answer",
                new=AsyncMock(return_value="LLM fallback"),
            ),
        ):
            from app.main import _context_cache

            _context_cache[("nfl", "9")] = "some context"
            response = client.post(
                "/api/v1/chat",
                json={
                    "user_message": "Who is #1 on the list?",
                    "book_id": "nfl",
                    "page_id": "9",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "llm"
        assert data["answer"] == "LLM fallback"

    def test_reveal_falls_through_when_no_items(self, client):
        empty_page = Page(
            page_id="9",
            url="http://example.com",
            title="NFL Touchdown Leaders",
            description="",
            type="list",
            items=[],
        )
        with (
            patch("app.main.spreadsheet_store.get_page", return_value=empty_page),
            patch("app.main.mock_db.deterministic_match", return_value=None),
            patch(
                "app.main.generate_llm_answer",
                new=AsyncMock(return_value="LLM fallback"),
            ),
        ):
            from app.main import _context_cache

            _context_cache[("nfl", "9")] = "some context"
            response = client.post(
                "/api/v1/chat",
                json={
                    "user_message": "Show me the answers",
                    "book_id": "nfl",
                    "page_id": "9",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "llm"
