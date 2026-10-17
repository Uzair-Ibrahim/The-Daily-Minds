import httpx
import pytest
from fastmcp import Client

from backend.mcp_server import create_server
from backend.providers.tavily import TavilyProvider
from backend.schemas import SearchResult


async def test_protocol_tool_and_structured_output(settings, payload):
    provider = TavilyProvider(settings, httpx.MockTransport(lambda _: httpx.Response(200, json=payload)))
    async with Client(create_server(provider)) as client:
        tools = await client.list_tools()
        assert {tool.name for tool in tools} == {"live_search", "discover_news"}
        assert tools[0].inputSchema["properties"]["max_results"]["maximum"] == 8
        result = await client.call_tool("live_search", {"query": "Python", "max_results": 2})
        assert SearchResult.model_validate(result.structured_content).status == "ok"


@pytest.mark.parametrize("args", [{"query": " "}, {"query": "x" * 2001}, {"query": "x", "max_results": 9}])
async def test_tool_validation(settings, args):
    def forbidden(_):
        raise AssertionError("Invalid input must not reach provider")
    server = create_server(TavilyProvider(settings, httpx.MockTransport(forbidden)))
    async with Client(server) as client:
        with pytest.raises(Exception):
            await client.call_tool("live_search", args)
