import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.config import Settings
from backend.orchestrator import Orchestrator
from backend.schemas import AskRequest


async def main() -> int:
    settings = Settings()
    if not settings.search_configured:
        print("LIVE_SMOKE_TEST: NOT RUN (missing key)")
        return 2
    if not settings.credit_search_confirmed_free:
        print("LIVE_SMOKE_TEST: NOT RUN (no-payment free credits unconfirmed; use python -m backend.cli paper for RSS)")
        return 2
    result = await Orchestrator(settings).ask(AskRequest(
        question="What does the official Python documentation say about asyncio timeouts?", live=True))
    print(json.dumps(result.model_dump(mode="json"), ensure_ascii=True, indent=2))
    passed = result.status in {"ok", "partial"} and bool(result.evidence) and bool(result.citations)
    print("LIVE_SMOKE_TEST: " + ("PASS" if passed else "FAIL"))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
