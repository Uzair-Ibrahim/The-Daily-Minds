import httpx
import pytest

from backend.main import create_app
from backend.orchestrator import Orchestrator
from backend.schemas import SearchResult, AskRequest
from backend.services.provenance import utc_now


class FakeSearch:
    async def search(self, request):
        return SearchResult(status="provider_unavailable", queried_at_utc=utc_now(),
                            error_code="timeout", limitations=["Search service timed out."])


async def test_health_capabilities_validation_and_failure(settings):
    app = create_app(settings, Orchestrator(settings, FakeSearch()))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        health = await client.get("/health")
        assert health.status_code == 200
        assert "test-only-not-a-real-key" not in health.text
        assert (await client.get("/api/v1/capabilities")).json()["llm_enabled"] is False
        for payload in ({"question": ""}, {"question": "x", "max_sources": 99}):
            assert (await client.post("/api/v1/ask", json=payload)).status_code == 422
        result = (await client.post("/api/v1/ask", json={"question": "test"})).json()
        assert result["status"] == "provider_unavailable"
        assert not result["citations"]
        assert result["retrieved_at_utc"] is None


async def test_disabled_live_has_no_fabricated_data(settings):
    class ForbiddenSearch:
        async def search(self, request):
            raise AssertionError("No retrieval permitted")
    result = await Orchestrator(settings, ForbiddenSearch()).ask(AskRequest(question="test", live=False))
    assert result.status == "no_evidence"
    assert result.freshness == "not_retrieved"
    assert not result.evidence


async def test_unexpected_workflow_failure_is_safe(settings):
    class BrokenSearch:
        async def search(self, request):
            raise RuntimeError("secret-bearing exception must not reach user")
    app = create_app(settings, Orchestrator(settings, BrokenSearch()))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.post("/api/v1/ask", json={"question": "test"})
    assert response.status_code == 200
    assert response.json()["status"] == "error"
    assert "secret-bearing" not in response.text
