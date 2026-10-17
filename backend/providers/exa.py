import asyncio
import random

import httpx
from exa_py import AsyncExa

from backend.config import Settings
from backend.schemas import SearchRequest, SearchResult
from backend.services.normalize import normalize_results
from backend.services.provenance import utc_now

SEARCH_URL = "https://api.exa.ai/search"


async def validate_sdk_response(response: httpx.Response) -> None:
    response.raise_for_status()
    await response.aread()
    if len(response.content) > 2_000_000:
        raise ValueError("Search response exceeded safe size")
    payload = response.json()
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise ValueError("Invalid search response")
    if any(not isinstance(row, dict) for row in payload["results"]):
        raise ValueError("Invalid search record")


def normalize_exa_rows(rows: list) -> list:
    normalized = []
    for row in rows[:40]:
        if not isinstance(row, dict):
            normalized.append(row)
            continue
        text = row.get("text")
        if not isinstance(text, str) or not text.strip():
            highlights = row.get("highlights")
            text = "\n".join(item[:3000] for item in highlights[:10] if isinstance(item, str)) if isinstance(highlights, list) else ""
        normalized.append({"url": row.get("url"), "title": row.get("title"),
                           "content": text, "published_date": row.get("publishedDate")})
    return normalized


class ExaProvider:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self.transport = transport

    async def search(self, request: SearchRequest) -> SearchResult:
        queried = utc_now()

        def failure(code: str, message: str) -> SearchResult:
            return SearchResult(status="provider_unavailable", queried_at_utc=queried,
                                error_code=code, limitations=[message])

        if not self.settings.exa_api_key.get_secret_value().strip():
            return failure("missing_key", "Set EXA_API_KEY in .env or the environment to use Exa live search.")
        try:
            async with asyncio.timeout(self.settings.live_request_timeout_seconds):
                timeout = httpx.Timeout(self.settings.live_request_timeout_seconds, connect=5)
                async with httpx.AsyncClient(timeout=timeout, transport=self.transport, follow_redirects=False,
                                            event_hooks={"response": [validate_sdk_response]}) as client:
                    sdk = AsyncExa(api_key=self.settings.exa_api_key.get_secret_value())
                    # exa-py 2.25.0 has no public HTTP-client/timeout injection API.
                    sdk._client = client
                    for attempt in range(2):
                        try:
                            result = await sdk.search(request.query, type="auto", num_results=request.max_results,
                                                      contents={"highlights": True})
                        except httpx.HTTPStatusError as error:
                            code = error.response.status_code
                            if code in {401, 403}:
                                return failure("unauthorized", "Exa rejected the credentials. Check EXA_API_KEY locally.")
                            if code == 402:
                                return failure("quota_exhausted", "Exa credits are unavailable. Check the account quota locally.")
                            if code == 429 or 500 <= code <= 599:
                                if attempt == 0:
                                    await asyncio.sleep(0.15 + random.uniform(0, 0.1))
                                    continue
                                return failure("rate_limited" if code == 429 else "upstream_error",
                                               "Exa search service temporarily busy. Try again shortly.")
                            return failure("http_error", "Exa rejected the search request.")
                        except httpx.RequestError:
                            if attempt == 0:
                                await asyncio.sleep(0.15 + random.uniform(0, 0.1))
                                continue
                            raise
                        retrieved = utc_now()
                        rows = [{"url": item.url, "title": item.title, "text": item.text,
                                 "highlights": item.highlights, "publishedDate": item.published_date}
                                for item in result.results]
                        records, dropped = normalize_results(normalize_exa_rows(rows), retrieved, request.max_results)
                        warnings = ["Exa may return indexed content; retrieval time does not establish page freshness."]
                        if dropped:
                            warnings.append("Some Exa results lacked usable extracted text or contained malformed fields and were discarded.")
                        return SearchResult(status=("partial" if dropped else "ok") if records else "no_evidence",
                            evidence=records, queried_at_utc=queried, retrieved_at_utc=retrieved, limitations=warnings)
        except (TimeoutError, httpx.TimeoutException):
            return failure("timeout", "Exa search timed out. Try again shortly.")
        except httpx.RequestError:
            return failure("network_error", "Exa search is unreachable. Check connectivity.")
        except (ValueError, TypeError, AttributeError, KeyError):
            return failure("invalid_response", "Exa returned invalid JSON or evidence.")
