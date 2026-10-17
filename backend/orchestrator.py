from time import perf_counter

from backend.config import Settings
from backend.mcp_client import MCPSearchClient
from backend.schemas import AskRequest, AskResponse, SearchRequest, SearchResult
from backend.services.evidence import evidence_limitations
from backend.services.provenance import utc_now
from backend.services.synthesize import extractive_answer
from backend.services.cache import EvidenceCache


class Orchestrator:
    def __init__(self, settings: Settings, search=None):
        self.settings = settings
        self.search = search or MCPSearchClient(settings)
        self.cache = EvidenceCache(settings.live_cache_ttl_seconds)

    async def ask(self, request: AskRequest) -> AskResponse:
        start = perf_counter()
        cache_key = (self.settings.search_provider, request.question, request.max_sources)
        result = self.cache.get(cache_key) if request.use_cache else None
        cache_hit = result is not None
        if cache_hit:
            result.queried_at_utc = utc_now()
            result.limitations.append("Reused cached evidence within TTL; original retrieval timestamps are preserved.")
        elif request.live:
            try:
                result = await self.search.search(SearchRequest(query=request.question, max_results=request.max_sources))
                self.cache.put(cache_key, result)
            except Exception:
                result = SearchResult(status="error", queried_at_utc=utc_now(), error_code="workflow_error",
                                      limitations=["Evidence service temporarily unavailable. Try again shortly."])
        else:
            result = SearchResult(status="no_evidence", queried_at_utc=utc_now(),
                                  limitations=["Live retrieval disabled. No offline evidence is configured."])
        warnings = list(result.limitations)
        if result.evidence:
            warnings.extend(evidence_limitations(result.evidence))
        if self.settings.llm_provider != "none" or self.settings.llm_api_key.get_secret_value():
            warnings.append("LLM adapter is not enabled in this baseline; output remains extractive.")
        freshness = "not_retrieved"
        if cache_hit:
            freshness = "cached_within_ttl"
        elif result.retrieved_at_utc:
            freshness = "retrieved_now_publication_date_unknown" if any(
                item.published_at_utc is None for item in result.evidence) else "retrieved_now"
        return AskResponse(answer=extractive_answer(result.evidence), status=result.status,
            citations=[item.id for item in result.evidence], evidence=result.evidence,
            queried_at_utc=result.queried_at_utc, retrieved_at_utc=result.retrieved_at_utc,
            freshness=freshness, limitations=warnings, elapsed_ms=int((perf_counter() - start) * 1000))
