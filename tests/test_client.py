"""
tests/test_client.py — Unit tests for ApiClient using respx mock transport.
"""
from __future__ import annotations

import json

import httpx
import pytest
import respx

from qa_pipeline.extractor.client import ApiClient


@pytest.fixture
def client() -> ApiClient:
    return ApiClient(
        base_url="https://jira.example.com",
        auth_token="Bearer test-token",
        retry_max=2,
        backoff_base_ms=10,
    )


class TestGet:
    @respx.mock
    def test_simple_get(self, client):
        respx.get("https://jira.example.com/rest/api/3/issue/QA-1").mock(
            return_value=httpx.Response(200, json={"key": "QA-1"})
        )
        result = client.get("/rest/api/3/issue/QA-1")
        assert result["key"] == "QA-1"

    @respx.mock
    def test_get_with_params(self, client):
        route = respx.get("https://jira.example.com/rest/api/3/search").mock(
            return_value=httpx.Response(200, json={"issues": [], "total": 0})
        )
        result = client.get("/rest/api/3/search", jql="project=QA", maxResults=10)
        assert result["total"] == 0
        assert route.called

    @respx.mock
    def test_retries_on_429(self, client):
        call_count = 0

        def side_effect(request):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                return httpx.Response(429, json={"error": "rate limited"})
            return httpx.Response(200, json={"ok": True})

        respx.get("https://jira.example.com/api/test").mock(side_effect=side_effect)
        result = client.get("/api/test")
        assert result["ok"] is True
        assert call_count == 2

    @respx.mock
    def test_raises_after_max_retries(self, client):
        respx.get("https://jira.example.com/api/test").mock(
            return_value=httpx.Response(500, json={"error": "server error"})
        )
        with pytest.raises(httpx.HTTPStatusError):
            client.get("/api/test")

    @respx.mock
    def test_non_retryable_4xx_raises_immediately(self, client):
        respx.get("https://jira.example.com/api/test").mock(
            return_value=httpx.Response(404, json={"error": "not found"})
        )
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            client.get("/api/test")
        assert exc_info.value.response.status_code == 404


class TestPaginateJira:
    @respx.mock
    def test_single_page(self, client):
        respx.get("https://jira.example.com/rest/api/3/search").mock(
            return_value=httpx.Response(200, json={
                "issues": [{"key": "QA-1"}, {"key": "QA-2"}],
                "total": 2,
                "startAt": 0,
                "maxResults": 50,
            })
        )
        pages = list(client.paginate_jira("/rest/api/3/search", page_size=50))
        assert len(pages) == 1
        assert len(pages[0]) == 2

    @respx.mock
    def test_multi_page(self, client):
        call_count = 0

        def side_effect(request):
            nonlocal call_count
            call_count += 1
            start = int(request.url.params.get("startAt", 0))
            if start == 0:
                return httpx.Response(200, json={
                    "issues": [{"key": f"QA-{i}"} for i in range(2)],
                    "total": 4, "startAt": 0, "maxResults": 2,
                })
            else:
                return httpx.Response(200, json={
                    "issues": [{"key": f"QA-{i}"} for i in range(2, 4)],
                    "total": 4, "startAt": 2, "maxResults": 2,
                })

        respx.get("https://jira.example.com/rest/api/3/search").mock(side_effect=side_effect)
        pages = list(client.paginate_jira("/rest/api/3/search", page_size=2))
        assert len(pages) == 2
        assert call_count == 2

    @respx.mock
    def test_empty_result(self, client):
        respx.get("https://jira.example.com/rest/api/3/search").mock(
            return_value=httpx.Response(200, json={
                "issues": [], "total": 0, "startAt": 0, "maxResults": 50,
            })
        )
        pages = list(client.paginate_jira("/rest/api/3/search"))
        assert pages == []


class TestAuthHeader:
    @respx.mock
    def test_bearer_prefix_preserved(self):
        c = ApiClient("https://example.com", "Bearer my-token")
        respx.get("https://example.com/test").mock(return_value=httpx.Response(200, json={}))
        c.get("/test")
        req = respx.calls.last.request
        assert req.headers["Authorization"] == "Bearer my-token"
        c.close()

    @respx.mock
    def test_token_without_prefix_gets_basic(self):
        c = ApiClient("https://example.com", "raw-token-value")
        respx.get("https://example.com/test").mock(return_value=httpx.Response(200, json={}))
        c.get("/test")
        req = respx.calls.last.request
        assert req.headers["Authorization"] == "Basic raw-token-value"
        c.close()
