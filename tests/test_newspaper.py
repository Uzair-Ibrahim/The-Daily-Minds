import asyncio
import io
from datetime import timedelta, datetime
from uuid import uuid4

import httpx
import pytest
from fastmcp import Client
from pypdf import PdfReader

from backend.config import Settings
from backend.main import create_app
from backend.mcp_server import create_server
from backend.news.discovery import NewsDiscovery, canonical_url, dedupe, topic_matches
from backend.news.models import Article, ProfileInput
from backend.news.pdf import edition_html, render_pdf
from backend.news.ranking import rank_articles, interest_dna
from backend.news.service import Newspaper, NoLiveNews
from backend.news.store import Store
from backend.services.provenance import utc_now

RSS = b'''<?xml version="1.0"?><rss version="2.0"><channel><title>TEST ONLY RSS</title>
<item><title>Artificial intelligence research advances</title><link>https://example.org/ai?utm_source=feed</link><description>&lt;b&gt;TEST ONLY:&lt;/b&gt; artificial intelligence research.</description><pubDate>Sat, 17 Oct 2026 07:00:00 GMT</pubDate></item>
<item><title>Cricket match report</title><link>https://example.org/cricket</link><description>TEST ONLY cricket tournament.</description></item>
</channel></rss>'''


@pytest.fixture
def news_settings(tmp_path):
    return Settings(_env_file=None, database_path=str(tmp_path / "paper.sqlite3"), search_provider="exa",
                    credit_search_confirmed_free=False, exa_api_key="", tavily_api_key="", llm_api_key="")


def make_article(topic, index=0, source=None):
    now = utc_now()
    return Article(id=f"article-{topic}-{index}", url=f"https://example.org/{topic}/{index}", title=f"TEST {topic} story {index}",
                   source=source or f"TEST source {index}", origin="test-fixture", description=f"TEST ONLY {topic} excerpt.",
                   published_at=now - timedelta(hours=1), retrieved_at=now, topics=[topic])


class FixtureDiscovery:
    def __init__(self, articles=None):
        self.items = articles if articles is not None else [make_article(topic, i) for i, topic in enumerate(["technology", "sports", "science", "culture", "world", "business"])]
        self.calls = 0

    async def retrieve(self, query="", targeted=False):
        self.calls += 1
        return {"status": "ok" if self.items else "no_live_data", "articles": self.items, "cached": False, "warnings": ["TEST FIXTURE ONLY"]}


@pytest.fixture
def paper(news_settings):
    return Newspaper(news_settings, discovery=FixtureDiscovery())


async def test_rss_normalization_dedupe_cache_and_no_credit_call(news_settings):
    requests = []
    def handle(request):
        requests.append(request)
        assert request.url.host not in {"api.exa.ai", "api.tavily.com"}
        return httpx.Response(200, content=RSS)
    discovery = NewsDiscovery(news_settings, httpx.MockTransport(handle))
    result = await discovery.retrieve(targeted=True)
    assert result["status"] == "ok" and len(result["articles"]) == 2
    assert str(result["articles"][0].url) == "https://example.org/ai"
    assert "<b>" not in result["articles"][0].description
    assert result["articles"][0].published_at.tzinfo is not None
    assert result["articles"][1].published_at is None
    assert any("disabled" in warning for warning in result["warnings"])
    count = len(requests)
    cached = await discovery.retrieve()
    assert len(requests) == count and cached["cached"]
    assert cached["articles"][0].retrieved_at == result["articles"][0].retrieved_at


async def test_feed_failures_are_honest(news_settings):
    discovery = NewsDiscovery(news_settings, httpx.MockTransport(lambda _: httpx.Response(503)))
    result = await discovery.retrieve()
    assert result["status"] == "no_live_data" and not result["articles"] and result["warnings"]


async def test_exa_quota_failure_retains_rss(news_settings, monkeypatch):
    from backend.mcp_client import MCPSearchClient
    from backend.schemas import SearchResult
    from pydantic import SecretStr
    news_settings.credit_search_confirmed_free = True
    news_settings.exa_api_key = SecretStr("TEST ONLY key")
    async def quota(self, request):
        return SearchResult(status="provider_unavailable", queried_at_utc=utc_now(), error_code="quota_exhausted",
                            limitations=["TEST ONLY exhausted free credits"])
    monkeypatch.setattr(MCPSearchClient, "search", quota)
    result = await NewsDiscovery(news_settings, httpx.MockTransport(lambda _: httpx.Response(200, content=RSS))).retrieve("AI", True)
    assert result["articles"] and any("retained RSS" in warning for warning in result["warnings"])


async def test_atom_and_unsafe_links(news_settings):
    atom = b'''<feed xmlns="http://www.w3.org/2005/Atom"><title>TEST</title><entry><title>Science discovery</title><link href="https://example.org/atom"/><summary>TEST ONLY summary</summary><updated>2026-10-16T12:00:00Z</updated></entry><entry><title>Unsafe</title><link href="javascript:alert(1)"/></entry></feed>'''
    result = await NewsDiscovery(news_settings, httpx.MockTransport(lambda _: httpx.Response(200, content=atom))).retrieve()
    assert len(result["articles"]) == 1 and result["articles"][0].published_at is None


def test_topic_boundaries_and_canonicalization():
    assert "culture" not in topic_matches("Artificial intelligence research")
    assert "technology" not in topic_matches("Air quality in cities")
    assert "culture" in topic_matches("Art and music")
    assert canonical_url("https://EXAMPLE.org/a?utm_campaign=x&keep=1#anchor") == "https://example.org/a?keep=1"
    with pytest.raises(ValueError):
        canonical_url("javascript:bad")
    first = make_article("technology")
    second = first.model_copy(update={"id": "other", "url": "https://example.org/other"})
    assert len(dedupe([first, second])) == 1


def test_two_profiles_rank_differently_and_unknown_dates_have_no_bonus():
    items = [make_article("technology"), make_article("sports")]
    technology = ProfileInput(topics={"technology": 2}).model_dump()
    sports = ProfileInput(topics={"sports": 2}).model_dump()
    assert rank_articles(items, technology, [])[0]["topics"] == ["technology"]
    assert rank_articles(items, sports, [])[0]["topics"] == ["sports"]
    items[0].published_at = None
    assert rank_articles(items, technology, [])[0]["breakdown"]["recency"] == 0
    items[0].published_at = utc_now() + timedelta(days=3)
    ranked = rank_articles(items, technology, [])
    assert ranked[0]["breakdown"]["recency"] == 0
    assert any("future" in reason for reason in ranked[0]["reasons"])


async def test_feedback_changes_ranking_and_snapshots_stay_immutable(paper):
    reader = str(uuid4())
    paper.store.save_profile(reader, ProfileInput(topics={"technology": 1, "sports": 1}, edition_length=4))
    first = await paper.generate(reader)
    before = [item for item in first["articles"] if item["topics"] == ["technology"]][0]
    paper.store.interact(reader, before["id"], "liked")
    assert not paper.store.interact(reader, before["id"], "liked")
    after = await paper.generate(reader, regenerate=True)
    current = next(item for item in after["articles"] if item["id"] == before["id"])
    assert current["breakdown"]["feedback"] > before["breakdown"]["feedback"]
    assert after["articles"][0]["topics"] == ["technology"]
    assert paper.store.edition(reader, first["id"])["articles"] == first["articles"]
    assert after["version"] == 2 and after["id"] != first["id"]
    with pytest.raises(KeyError):
        paper.store.interact(str(uuid4()), before["id"], "liked")


async def test_idempotence_concurrency_timezone_and_restart(paper, news_settings):
    reader = str(uuid4())
    paper.store.save_profile(reader, ProfileInput(timezone="Asia/Karachi"))
    a, b = await asyncio.gather(paper.generate(reader), paper.generate(reader))
    assert a["id"] == b["id"] and paper.discovery.calls == 1
    tomorrow = utc_now() + timedelta(days=1)
    c = await paper.generate(reader, now=tomorrow)
    assert c["local_date"] != a["local_date"] and c["version"] == 1
    paper.store.interact(reader, a["articles"][0]["id"], "saved")
    restored = Newspaper(news_settings, discovery=FixtureDiscovery([]))
    assert restored.store.edition(reader, a["id"])["articles"] == a["articles"]
    assert len(restored.store.archive(reader)) == 2
    assert restored.store.events(reader)[0]["action"] == "saved"


async def test_empty_news_never_saves_a_fake_paper(news_settings):
    paper = Newspaper(news_settings, discovery=FixtureDiscovery([]))
    reader = str(uuid4())
    with pytest.raises(NoLiveNews):
        await paper.generate(reader)
    assert paper.store.archive(reader) == []


async def test_timezone_date_boundary(paper):
    karachi, utc = str(uuid4()), str(uuid4())
    paper.store.save_profile(karachi, ProfileInput(timezone="Asia/Karachi"))
    paper.store.save_profile(utc, ProfileInput(timezone="UTC"))
    instant = datetime.fromisoformat("2026-10-16T20:00:00+00:00")
    assert (await paper.generate(karachi, now=instant))["local_date"] == "2026-10-17"
    assert (await paper.generate(utc, now=instant))["local_date"] == "2026-10-16"


async def test_api_archive_after_restart_without_live_sources(paper, news_settings):
    reader = str(uuid4())
    edition = await paper.generate(reader)
    offline = Newspaper(news_settings, discovery=FixtureDiscovery([]))
    app = create_app(news_settings, newspaper=offline)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test", headers={"X-Reader-ID": reader}) as client:
        assert (await client.get("/api/editions")).json()[0]["id"] == edition["id"]
        restored = (await client.get('/api/editions/' + edition["id"])).json()
        assert restored["articles"] == edition["articles"]
        failed = await client.post("/api/editions/generate", json={"regenerate": True})
        assert failed.status_code == 503 and failed.json()["detail"]["code"] == "no_live_data"
        assert len((await client.get("/api/editions")).json()) == 1


def test_feedback_caps_and_profiles_are_separate():
    profile = ProfileInput(topics={"technology": 1}).model_dump()
    events = [{"topics": ["technology"], "action": "liked"} for _ in range(100)]
    dna = interest_dna(profile, events)
    assert next(row for row in dna if row["topic"] == "technology")["feedback"] == 1
    assert next(row for row in interest_dna(profile, []) if row["topic"] == "technology")["feedback"] == 0


async def test_api_profile_archive_interactions_and_validation(paper, news_settings):
    app = create_app(news_settings, newspaper=paper)
    headers = {"X-Reader-ID": str(uuid4())}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test", headers=headers) as client:
        assert len((await client.get("/api/topics")).json()) == 7
        assert (await client.get("/api/profile")).json()["onboarded"] is False
        assert (await client.put("/api/profile", json={"topics": {"sports": 2}})).status_code == 200
        assert (await client.put("/api/profile", json={"topics": {"unknown": 1}})).status_code == 422
        first = (await client.post("/api/editions/generate", json={})).json()
        assert first["id"]
        assert (await client.post("/api/editions/generate", json={})).json()["id"] == first["id"]
        assert len((await client.get("/api/editions")).json()) == 1
        saved = await client.post(f'/api/articles/{first["articles"][0]["id"]}/interactions', json={"action": "saved"})
        assert saved.json()["recorded"]
        assert (await client.get("/api/profile/interests")).json()["weights"]
        assert (await client.get(f'/api/editions/{first["id"]}', headers={"X-Reader-ID": str(uuid4())})).status_code == 404
        assert (await client.get("/api/profile", headers={"X-Reader-ID": "invalid"})).status_code == 400
        assert (await client.post("/api/profile/reset-feedback")).status_code == 200


async def test_mcp_news_tool(paper):
    async with Client(create_server(newspaper=paper)) as client:
        result = await client.call_tool("discover_news", {"query": "technology", "max_results": 4})
    assert result.structured_content["status"] == "ok"
    assert len(result.structured_content["articles"]) == 4
    assert result.structured_content["articles"][0]["reasons"]


async def test_no_payment_gate_preserves_rss_option(monkeypatch, news_settings):
    from pydantic import SecretStr
    import backend.mcp_server as module
    news_settings.exa_api_key = SecretStr("TEST ONLY secret")
    monkeypatch.setattr(module, "Settings", lambda: news_settings)
    async with Client(module.create_server()) as client:
        result = await client.call_tool("live_search", {"query": "test"})
    assert result.structured_content["error_code"] == "free_credits_unconfirmed"
    assert not result.structured_content["evidence"]


@pytest.mark.pdf
async def test_real_pdf_has_saved_snapshot_text_and_links(paper):
    reader = str(uuid4())
    edition = await paper.generate(reader)
    content = await render_pdf(edition)
    assert content.startswith(b"%PDF") and len(content) > 5000
    pdf = PdfReader(io.BytesIO(content))
    text = " ".join(page.extract_text() for page in pdf.pages)
    assert "The Daily Mind" in text and edition["local_date"] in text
    for article in edition["articles"]:
        assert article["title"] in text
        assert article["title"] in edition_html(edition)
    assert any(page.get("/Annots") for page in pdf.pages)
