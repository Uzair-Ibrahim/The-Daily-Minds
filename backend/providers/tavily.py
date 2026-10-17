import asyncio
import random

import httpx

from backend.config import Settings
from backend.schemas import SearchRequest, SearchResult
from backend.services.normalize import normalize_results
from backend.services.provenance import utc_now

SEARCH_URL = "https://api.tavily.com/search"


class TavilyProvider:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self.transport = transport

    async def search(self, request: SearchRequest) -> SearchResult:
        queried = utc_now()

        def failure(code: str, message: str) -> SearchResult:
            return SearchResult(status="provider_unavailable", queried_at_utc=queried,
                                error_code=code, limitations=[message])

        if not self.settings.tavily_api_key.get_secret_value().strip():
            return failure("missing_key", "Set TAVILY_API_KEY in .env or the environment to use live search.")
        try:
            async with asyncio.timeout(self.settings.live_request_timeout_seconds):
                timeout = httpx.Timeout(self.settings.live_request_timeout_seconds, connect=5)
                async with httpx.AsyncClient(timeout=timeout, transport=self.transport, follow_redirects=False) as client:
                    for attempt in range(2):
                        response = await client.post(SEARCH_URL,
                            headers={"Authorization": f"Bearer {self.settings.tavily_api_key.get_secret_value()}"},
                            json={"query": request.query, "max_results": request.max_results,
                                  "include_answer": False, "include_raw_content": False, "search_depth": "basic"})
                        if response.status_code in {401, 403}:
                            return failure("unauthorized", "Tavily rejected the credentials. Check TAVILY_API_KEY locally.")
                        if response.status_code == 429 or 500 <= response.status_code <= 599:
                            if attempt == 0:
                                await asyncio.sleep(0.15 + random.uniform(0, 0.1))
                                continue
                            return failure("rate_limited" if response.status_code == 429 else "upstream_error",
                                           "Search service temporarily busy. Try again shortly.")
                        if not response.is_success:
                            return failure("http_error", "Search provider rejected the request.")
                        if len(response.content) > 2_000_000:
                            return failure("invalid_response", "Search response exceeded the safe size limit.")
                        payload = response.json()
                        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
                            return failure("invalid_response", "Search provider returned an invalid response.")
                        retrieved = utc_now()
                        records, dropped = normalize_results(payload["results"], retrieved, request.max_results)
                        warnings = ["Some malformed search records were discarded."] if dropped else []
                        return SearchResult(status=("partial" if dropped else "ok") if records else "no_evidence",
                                            evidence=records, queried_at_utc=queried, retrieved_at_utc=retrieved,
                                            limitations=warnings)
        except (TimeoutError, httpx.TimeoutException):
            return failure("timeout", "Search service timed out. Try again shortly.")
        except httpx.RequestError:
            return failure("network_error", "Search service is unreachable. Check connectivity.")
        except (ValueError, TypeError):
            return failure("invalid_response", "Search provider returned invalid JSON or evidence.")
