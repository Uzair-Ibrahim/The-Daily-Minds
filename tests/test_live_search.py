import os

import pytest

from backend.config import Settings
from backend.orchestrator import Orchestrator
from backend.schemas import AskRequest


@pytest.mark.live
@pytest.mark.skipif(os.getenv("RUN_LIVE_SEARCH_TESTS") != "1", reason="Opt in with RUN_LIVE_SEARCH_TESTS=1; uses real API credits")
async def test_exa_live_through_real_mcp():
    settings = Settings(search_provider="exa")
    if not settings.credit_search_confirmed_free:
        pytest.skip("No-payment free credits have not been confirmed; zero-spend policy")
    if not settings.search_configured:
        pytest.skip("EXA_API_KEY is missing")
    result = await Orchestrator(settings).ask(AskRequest(question="Python official asyncio timeout documentation", live=True))
    assert result.status in {"ok", "partial"}, result.limitations
    assert result.evidence and result.citations and result.retrieved_at_utc is not None
    assert set(result.citations) == {item.id for item in result.evidence}
