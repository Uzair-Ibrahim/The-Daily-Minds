from backend.orchestrator import Orchestrator
from backend.schemas import AskRequest, EvidenceRecord, SearchResult
from backend.services.cache import EvidenceCache
from backend.services.provenance import utc_now


def sample_result():
    now = utc_now()
    return SearchResult(status="ok", queried_at_utc=now, retrieved_at_utc=now,
        evidence=[EvidenceRecord(id="src_1", title="TEST source", url="https://example.org/test",
                                 snippet="TEST ONLY evidence", retrieved_at_utc=now)])


def test_cache_expiry_and_copy_isolation():
    clock = [0]
    cache = EvidenceCache(10, clock=lambda: clock[0])
    result = sample_result()
    cache.put(("exa", "question", 1), result)
    result.evidence[0].snippet = "mutated"
    cached = cache.get(("exa", "question", 1))
    assert cached.evidence[0].snippet == "TEST ONLY evidence"
    cached.limitations.append("mutation")
    assert not cache.get(("exa", "question", 1)).limitations
    clock[0] = 10
    assert cache.get(("exa", "question", 1)) is None


def test_cache_capacity_and_no_failures():
    cache = EvidenceCache(10, max_entries=2)
    cache.put((1,), sample_result())
    cache.put((2,), sample_result())
    cache.get((1,))
    cache.put((3,), sample_result())
    assert cache.get((2,)) is None and cache.get((1,)) is not None
    cache.put((4,), SearchResult(status="provider_unavailable", queried_at_utc=utc_now()))
    assert cache.get((4,)) is None


def test_cache_disabled():
    cache = EvidenceCache(0)
    cache.put((1,), sample_result())
    assert cache.get((1,)) is None


async def test_cache_opt_in_and_fresh_live_bypass(settings):
    class Search:
        calls = 0
        async def search(self, request):
            self.calls += 1
            return sample_result()
    search = Search()
    workflow = Orchestrator(settings, search)
    fresh = await workflow.ask(AskRequest(question="test", live=True))
    cached = await workflow.ask(AskRequest(question="test", live=True, use_cache=True))
    assert search.calls == 1
    assert cached.freshness == "cached_within_ttl"
    assert cached.retrieved_at_utc == fresh.retrieved_at_utc
    assert cached.evidence == fresh.evidence and cached.citations == fresh.citations
    assert any("cached evidence" in warning for warning in cached.limitations)
    await workflow.ask(AskRequest(question="test", live=True))
    assert search.calls == 2
    await workflow.ask(AskRequest(question="different question", live=True, use_cache=True))
    await workflow.ask(AskRequest(question="test", max_sources=2, live=True, use_cache=True))
    assert search.calls == 4


async def test_expired_cache_offline_does_not_fetch(settings):
    class Search:
        async def search(self, request):
            raise AssertionError("Offline cache miss must not fetch")
    workflow = Orchestrator(settings, Search())
    clock = [0]
    workflow.cache = EvidenceCache(10, clock=lambda: clock[0])
    workflow.cache.put((settings.search_provider, "test", 5), sample_result())
    hit = await workflow.ask(AskRequest(question="test", live=False, use_cache=True))
    assert hit.freshness == "cached_within_ttl"
    clock[0] = 11
    miss = await workflow.ask(AskRequest(question="test", live=False, use_cache=True))
    assert miss.status == "no_evidence" and not miss.evidence
