import asyncio
import json

import httpx
import pytest

from backend.providers.tavily import TavilyProvider, SEARCH_URL
from backend.schemas import SearchRequest

REQUEST = SearchRequest(query="Python asyncio")


async def test_success_auth_and_limits(settings, payload):
    def handle(request):
        assert str(request.url) == SEARCH_URL
        assert request.headers["authorization"] == "Bearer test-only-not-a-real-key"
        assert json.loads(request.content)["include_answer"] is False
        assert "api_key" not in str(request.url)
        return httpx.Response(200, json=payload)
    result = await TavilyProvider(settings, httpx.MockTransport(handle)).search(REQUEST)
    assert result.status == "ok"
    assert len(result.evidence) == 2
    assert result.evidence[0].published_at_utc is None
    assert result.queried_at_utc <= result.retrieved_at_utc


@pytest.mark.parametrize("code,expected,calls", [
    (401, "unauthorized", 1), (403, "unauthorized", 1), (429, "rate_limited", 2),
    (500, "upstream_error", 2), (503, "upstream_error", 2), (400, "http_error", 1),
])
async def test_http_failures(settings, code, expected, calls):
    requests = []
    def handle(request):
        requests.append(request)
        return httpx.Response(code, text="private upstream diagnostic test-only-not-a-real-key")
    result = await TavilyProvider(settings, httpx.MockTransport(handle)).search(REQUEST)
    assert result.error_code == expected
    assert len(requests) == calls
    assert "test-only-not-a-real-key" not in result.model_dump_json()


@pytest.mark.parametrize("body", [b"not-json", b'[]', b'{"results": {}}', b'{}'])
async def test_bad_json(settings, body):
    result = await TavilyProvider(settings, httpx.MockTransport(lambda _: httpx.Response(200, content=body))).search(REQUEST)
    assert result.error_code == "invalid_response"


@pytest.mark.parametrize("exception,code", [
    (httpx.ReadTimeout("sensitive diagnostic"), "timeout"),
    (httpx.ConnectError("sensitive diagnostic"), "network_error")])
async def test_network_failure(settings, exception, code):
    def handle(_):
        raise exception
    result = await TavilyProvider(settings, httpx.MockTransport(handle)).search(REQUEST)
    assert result.error_code == code
    assert "sensitive" not in result.model_dump_json()


async def test_overall_timeout(settings):
    settings.live_request_timeout_seconds = 1
    async def handle(_):
        await asyncio.sleep(2)
        return httpx.Response(200, json={"results": []})
    result = await TavilyProvider(settings, httpx.MockTransport(handle)).search(REQUEST)
    assert result.error_code == "timeout"


async def test_retry_recovers(settings, payload):
    calls = 0
    def handle(_):
        nonlocal calls
        calls += 1
        return httpx.Response(503) if calls == 1 else httpx.Response(200, json=payload)
    assert (await TavilyProvider(settings, httpx.MockTransport(handle)).search(REQUEST)).status == "ok"
    assert calls == 2


async def test_missing_key_no_network(settings):
    from pydantic import SecretStr
    settings.tavily_api_key = SecretStr("")
    def forbidden(_):
        raise AssertionError("Network must not be called")
    result = await TavilyProvider(settings, httpx.MockTransport(forbidden)).search(REQUEST)
    assert result.error_code == "missing_key"


async def test_empty_and_malformed_records(settings):
    for rows in ([], [None, {"url": "javascript:alert(1)", "content": "bad"}]):
        result = await TavilyProvider(settings, httpx.MockTransport(lambda _: httpx.Response(200, json={"results": rows}))).search(REQUEST)
        assert result.status == "no_evidence"
        assert result.evidence == []
