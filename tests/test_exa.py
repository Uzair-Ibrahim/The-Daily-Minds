import asyncio
import json

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from backend.config import Settings
from backend.providers.exa import ExaProvider, SEARCH_URL
from backend.providers.search import create_provider
from backend.providers.tavily import TavilyProvider
from backend.schemas import SearchRequest, AskRequest
from backend.orchestrator import Orchestrator
from backend.main import create_app
from backend.mcp_server import create_server
from backend.mcp_client import MCPSearchClient

REQUEST = SearchRequest(query="Python asyncio", max_results=3)


@pytest.fixture
def exa_settings():
    return Settings(_env_file=None, search_provider="exa", exa_api_key="exa-test-only-secret", tavily_api_key="",
                    llm_api_key="", llm_provider="none")


@pytest.fixture
def exa_payload():
    return {"results": [
        {"title": "TEST source", "url": "https://example.org/doc?q=1#section", "text": "Extracted page text.",
         "publishedDate": "2026-10-16T09:00:00Z"},
        {"title": "TEST highlights", "url": "https://example.org/other", "highlights": ["An excerpt.", "Another excerpt."]},
    ]}


async def test_official_request_normalized_extraction(exa_settings, exa_payload):
    def handle(request):
        assert str(request.url) == SEARCH_URL and request.method == "POST"
        assert request.headers["x-api-key"] == "exa-test-only-secret"
        assert "authorization" not in request.headers
        body = json.loads(request.content)
        assert body == {"query": REQUEST.query, "numResults": 3, "type": "auto",
                        "contents": {"highlights": True}}
        assert "exa-test-only-secret" not in request.content.decode() + str(request.url)
        return httpx.Response(200, json=exa_payload)
    result = await ExaProvider(exa_settings, httpx.MockTransport(handle)).search(REQUEST)
    assert result.status == "ok" and len(result.evidence) == 2
    assert result.evidence[0].snippet == "Extracted page text."
    assert str(result.evidence[0].url) == exa_payload["results"][0]["url"]
    assert result.evidence[0].published_at_utc.isoformat() == "2026-10-16T09:00:00+00:00"
    assert result.evidence[1].published_at_utc is None
    assert result.evidence[1].snippet == "An excerpt.\nAnother excerpt."
    assert all(item.relevance_score is None and item.is_official_source is None for item in result.evidence)
    assert result.queried_at_utc <= result.retrieved_at_utc
    assert result.evidence[0].retrieved_at_utc == result.retrieved_at_utc


@pytest.mark.parametrize("code,expected,calls", [
    (401, "unauthorized", 1), (403, "unauthorized", 1), (402, "quota_exhausted", 1),
    (429, "rate_limited", 2), (500, "upstream_error", 2), (503, "upstream_error", 2),
    (400, "http_error", 1), (302, "http_error", 1),
])
async def test_exa_http_failures_are_redacted(exa_settings, code, expected, calls):
    requests = []
    def handle(request):
        requests.append(request)
        return httpx.Response(code, text="exa-test-only-secret: upstream private diagnostic")
    result = await ExaProvider(exa_settings, httpx.MockTransport(handle)).search(REQUEST)
    assert result.status == "provider_unavailable" and result.error_code == expected
    assert len(requests) == calls
    assert not result.evidence and result.retrieved_at_utc is None
    assert "exa-test-only-secret" not in result.model_dump_json()


@pytest.mark.parametrize("body", [b"broken", b"[]", b"{}", b'{"results":null}', b'x' * 2_000_001],
                         ids=["bad-json", "array", "missing-results", "null-results", "oversized"])
async def test_exa_bad_response(exa_settings, body):
    result = await ExaProvider(exa_settings, httpx.MockTransport(lambda _: httpx.Response(200, content=body))).search(REQUEST)
    assert result.error_code == "invalid_response"


@pytest.mark.parametrize("error,code", [(httpx.ReadTimeout("private"), "timeout"), (httpx.ConnectError("private"), "network_error")])
async def test_exa_network_errors(exa_settings, error, code):
    def handle(_):
        raise error
    result = await ExaProvider(exa_settings, httpx.MockTransport(handle)).search(REQUEST)
    assert result.error_code == code and "private" not in result.model_dump_json()


async def test_exa_deadline(exa_settings):
    exa_settings.live_request_timeout_seconds = 1
    async def handle(_):
        await asyncio.sleep(3)
        return httpx.Response(200, json={"results": []})
    result = await ExaProvider(exa_settings, httpx.MockTransport(handle)).search(REQUEST)
    assert result.error_code == "timeout"


async def test_exa_retry_recovers(exa_settings, exa_payload):
    responses = iter([httpx.Response(503), httpx.Response(200, json=exa_payload)])
    provider = ExaProvider(exa_settings, httpx.MockTransport(lambda _: next(responses)))
    assert (await provider.search(REQUEST)).status == "ok"


async def test_sdk_search_is_used_and_client_closed(exa_settings, exa_payload, monkeypatch):
    from exa_py import AsyncExa
    original = AsyncExa.search
    calls = []
    async def spy(self, *args, **kwargs):
        calls.append(self)
        return await original(self, *args, **kwargs)
    monkeypatch.setattr(AsyncExa, "search", spy)
    provider = ExaProvider(exa_settings, httpx.MockTransport(lambda _: httpx.Response(200, json=exa_payload)))
    assert (await provider.search(REQUEST)).status == "ok"
    assert len(calls) == 1 and calls[0].client.is_closed


async def test_exa_connection_retry_recovers(exa_settings, exa_payload):
    calls = []
    def handle(request):
        calls.append(request)
        if len(calls) == 1:
            raise httpx.ConnectError("private diagnostic")
        return httpx.Response(200, json=exa_payload)
    result = await ExaProvider(exa_settings, httpx.MockTransport(handle)).search(REQUEST)
    assert result.status == "ok" and len(calls) == 2


async def test_exa_missing_key_does_not_fallback(exa_settings):
    exa_settings.exa_api_key = SecretStr("")
    exa_settings.tavily_api_key = SecretStr("configured-but-not-selected")
    assert not exa_settings.search_configured
    def forbidden(_):
        raise AssertionError("No network or fallback permitted")
    result = await ExaProvider(exa_settings, httpx.MockTransport(forbidden)).search(REQUEST)
    assert result.error_code == "missing_key" and "EXA_API_KEY" in result.limitations[0]


async def test_exa_empty_extraction_and_malformed_sources(exa_settings):
    for rows in ([], [{"url": "https://example.org", "title": "No extracted content"}]):
        result = await ExaProvider(exa_settings, httpx.MockTransport(lambda _: httpx.Response(200, json={"results": rows}))).search(REQUEST)
        assert result.status == "no_evidence" and not result.evidence


async def test_exa_malformed_sdk_records(exa_settings):
    provider = ExaProvider(exa_settings, httpx.MockTransport(lambda _: httpx.Response(200, json={"results": [None, "invalid"]})))
    assert (await provider.search(REQUEST)).error_code == "invalid_response"


async def test_exa_dedupe_bounds_and_partial(exa_settings, exa_payload):
    rows = exa_payload["results"]
    rows[0]["text"] = "x" * 5000
    rows.append(dict(rows[0], url="https://example.org/doc?q=1#duplicate"))
    rows.append({"url": "javascript:bad", "text": "unsafe link"})
    provider = ExaProvider(exa_settings, httpx.MockTransport(lambda _: httpx.Response(200, json={"results": rows})))
    result = await provider.search(REQUEST)
    assert result.status == "partial" and len(result.evidence) == 2
    assert len(result.evidence[0].snippet) == 3000


def test_provider_selection_and_secret_configuration(exa_settings, settings):
    assert isinstance(create_provider(exa_settings), ExaProvider)
    assert isinstance(create_provider(settings), TavilyProvider)
    assert exa_settings.search_configured and settings.search_configured
    assert "exa-test-only-secret" not in repr(exa_settings)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, search_provider="untrusted-url")
    transport = MCPSearchClient(exa_settings).make_transport()
    assert transport.env["SEARCH_PROVIDER"] == "exa"
    assert transport.env["EXA_API_KEY"] == "exa-test-only-secret"


async def test_exa_api_via_mcp_protocol(exa_settings, exa_payload):
    provider = ExaProvider(exa_settings, httpx.MockTransport(lambda _: httpx.Response(200, json=exa_payload)))
    search = MCPSearchClient(exa_settings, create_server(provider))
    app = create_app(exa_settings, Orchestrator(exa_settings, search))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        capabilities = (await client.get("/api/v1/capabilities")).json()
        assert capabilities["search_provider"] == "exa" and capabilities["live_search_configured"]
        response = await client.post("/api/v1/ask", json={"question": "Python", "live": True})
    result = response.json()
    assert response.status_code == 200 and result["status"] == "ok"
    assert result["mode"] == "extractive" and result["citations"] == ["src_1", "src_2"]
    assert "indexed content" in " ".join(result["limitations"])
