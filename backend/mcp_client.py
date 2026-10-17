import asyncio
import sys

from fastmcp import Client
from fastmcp.client.transports import StdioTransport

from backend.config import ROOT, Settings
from backend.schemas import SearchRequest, SearchResult
from backend.services.provenance import utc_now


class MCPSearchClient:
    def __init__(self, settings: Settings, transport=None):
        self.settings = settings
        self.transport = transport

    def make_transport(self):
        return StdioTransport(command=sys.executable, args=["-m", "backend.mcp_server"], cwd=str(ROOT),
            env={"SEARCH_PROVIDER": self.settings.search_provider,
                 "EXA_API_KEY": self.settings.exa_api_key.get_secret_value(),
                 "TAVILY_API_KEY": self.settings.tavily_api_key.get_secret_value(),
                 "LIVE_REQUEST_TIMEOUT_SECONDS": str(self.settings.live_request_timeout_seconds),
                 "CREDIT_SEARCH_CONFIRMED_FREE": str(self.settings.credit_search_confirmed_free).lower(),
                 "DATABASE_PATH": self.settings.database_path,
                 "FASTMCP_CHECK_FOR_UPDATES": "off"}, keep_alive=False)

    async def search(self, request: SearchRequest) -> SearchResult:
        try:
            async with asyncio.timeout(self.settings.live_request_timeout_seconds + 20):
                async with Client(self.transport or self.make_transport()) as client:
                    result = await client.call_tool("live_search", request.model_dump())
                    return SearchResult.model_validate(result.structured_content)
        except Exception:
            return SearchResult(status="provider_unavailable", queried_at_utc=utc_now(),
                                error_code="mcp_unavailable", limitations=["MCP search connection failed or timed out."])

    async def list_tools(self) -> list[str]:
        async with asyncio.timeout(self.settings.live_request_timeout_seconds + 20):
            async with Client(self.transport or self.make_transport()) as client:
                return [tool.name for tool in await client.list_tools()]

    async def discover_news(self, query: str, max_results: int = 12):
        from backend.news.models import NewsSearchResult
        try:
            async with asyncio.timeout(60):
                async with Client(self.transport or self.make_transport()) as client:
                    result = await client.call_tool("discover_news", {"query": query, "max_results": max_results})
                    return NewsSearchResult.model_validate(result.structured_content)
        except Exception:
            return NewsSearchResult(status="error", warnings=["MCP news discovery is temporarily unavailable."])
