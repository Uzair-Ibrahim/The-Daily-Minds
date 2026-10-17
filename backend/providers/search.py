from typing import Protocol

from backend.config import Settings
from backend.schemas import SearchRequest, SearchResult
from backend.providers.exa import ExaProvider
from backend.providers.tavily import TavilyProvider


class SearchProvider(Protocol):
    async def search(self, request: SearchRequest) -> SearchResult: ...


def create_provider(settings: Settings) -> SearchProvider:
    if settings.search_provider == "exa":
        return ExaProvider(settings)
    return TavilyProvider(settings)
