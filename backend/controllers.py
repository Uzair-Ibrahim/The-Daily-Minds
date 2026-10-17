from backend.config import Settings
from backend.orchestrator import Orchestrator
from backend.schemas import AskRequest, AskResponse


class AskController:
    def __init__(self, settings: Settings, orchestrator: Orchestrator):
        self.settings = settings
        self.orchestrator = orchestrator

    async def ask(self, request: AskRequest) -> AskResponse:
        return await self.orchestrator.ask(request)

    def capabilities(self) -> dict:
        return {"search_provider": self.settings.search_provider,
                "live_search_configured": self.settings.search_configured,
                "llm_enabled": False, "mode": "extractive",
                "cache_enabled": self.settings.live_cache_ttl_seconds > 0,
                "cache_ttl_seconds": self.settings.live_cache_ttl_seconds}
