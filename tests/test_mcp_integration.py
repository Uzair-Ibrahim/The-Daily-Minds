import argparse
import json
import sys

import httpx
import pytest
from fastmcp.client.transports import StdioTransport

from backend.cli import execute
from backend.config import ROOT
from backend.main import create_app
from backend.mcp_client import MCPSearchClient
from backend.orchestrator import Orchestrator
from backend.schemas import AskRequest, SearchRequest


def fixture_transport(provider="tavily"):
    return StdioTransport(command=sys.executable, args=["-m", "tests.stdio_fixture", provider],
                          cwd=str(ROOT), env={"FASTMCP_CHECK_FOR_UPDATES": "off"}, keep_alive=False)


@pytest.mark.integration
@pytest.mark.parametrize("provider", ["exa", "tavily"])
async def test_real_stdio_protocol(settings, provider):
    client = MCPSearchClient(settings, fixture_transport(provider))
    assert set(await client.list_tools()) == {"live_search", "discover_news"}
    result = await client.search(SearchRequest(query="test fixture"))
    assert result.status == "ok"
    assert "TEST FIXTURE ONLY" in result.evidence[0].snippet


@pytest.mark.integration
@pytest.mark.parametrize("provider", ["exa", "tavily"])
async def test_cli_api_same_real_mcp_path(settings, monkeypatch, capfd, provider):
    monkeypatch.setattr(MCPSearchClient, "make_transport", lambda _: fixture_transport(provider))
    args = argparse.Namespace(command="ask", question="test fixture", live=True, json=True, max_sources=5)
    assert await execute(args) == 0
    cli = json.loads(capfd.readouterr().out)
    app = create_app(settings)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.post("/api/v1/ask", json={"question": "test fixture", "live": True})
    assert response.status_code == 200
    api = response.json()
    for field in ("answer", "mode", "status", "citations", "freshness", "limitations"):
        assert cli[field] == api[field]
    assert cli["evidence"][0]["url"] == api["evidence"][0]["url"]


async def test_mcp_failure_is_typed(settings):
    transport = StdioTransport(command=sys.executable, args=["-c", "raise SystemExit(1)"], keep_alive=False)
    result = await MCPSearchClient(settings, transport).search(SearchRequest(query="test"))
    assert result.error_code == "mcp_unavailable"
