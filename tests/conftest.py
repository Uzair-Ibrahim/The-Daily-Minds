import pytest

from backend.config import Settings


@pytest.fixture
def settings():
    return Settings(_env_file=None, search_provider="tavily", credit_search_confirmed_free=True, exa_api_key="", tavily_api_key="test-only-not-a-real-key", llm_api_key="", llm_provider="none")


@pytest.fixture
def payload():
    # MOCK DATA: automated tests only; never loaded by production paths.
    return {"results": [
        {"title": "Python documentation", "url": "https://docs.python.org/3/library/asyncio-task.html",
         "content": "asyncio.timeout bounds the time spent waiting.", "score": 0.9},
        {"title": "Other source", "url": "https://example.org/report?edition=1",
         "content": "A second source excerpt.", "score": 0.6, "published_date": "2026-10-16T09:00:00Z"}
    ]}
