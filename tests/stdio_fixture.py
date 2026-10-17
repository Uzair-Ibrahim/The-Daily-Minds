"""Test-only real STDIO server with isolated mocked search HTTP transport."""
import sys
import httpx

from backend.config import Settings
from backend.mcp_server import create_server
from backend.providers.search import create_provider


def handle(request):
    assert request.url.host in {"api.tavily.com", "api.exa.ai"}
    result = {"results": [
        {"title": "TEST FIXTURE ONLY", "url": "https://example.org/test-fixture",
         "content": "TEST FIXTURE ONLY: retrieved through real MCP STDIO and mocked HTTP.", "score": 0.8}
    ]}
    if request.url.host == "api.exa.ai":
        result["results"][0]["text"] = result["results"][0].pop("content")
    return httpx.Response(200, json=result)


if __name__ == "__main__":
    selected = sys.argv[1] if len(sys.argv) > 1 else "tavily"
    settings = Settings(_env_file=None, search_provider=selected, tavily_api_key="test-only-key", exa_api_key="test-only-key")
    provider = create_provider(settings)
    provider.transport = httpx.MockTransport(handle)
    create_server(provider).run(transport="stdio", show_banner=False)
