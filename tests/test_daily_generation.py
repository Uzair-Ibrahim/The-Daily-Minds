import asyncio
from datetime import datetime, timedelta
from uuid import uuid4

import httpx
import pytest

from backend.main import create_app
from backend.news.discovery import FEEDS, NewsDiscovery
from backend.news.models import ProfileInput
from backend.news.pdf import edition_html
from backend.news.scheduler import DailyScheduler
from backend.news.service import Newspaper, NoLiveNews
from tests.test_newspaper import FixtureDiscovery, RSS, make_article, news_settings


async def test_scheduler_and_on_demand_share_one_stable_edition(news_settings):
    reader = str(uuid4())
    discovery = FixtureDiscovery()
    paper = Newspaper(news_settings, discovery=discovery)
    paper.store.save_profile(reader, ProfileInput())
    scheduler = DailyScheduler(paper)
    await asyncio.gather(scheduler.tick(), paper.generate(reader), scheduler.tick())
    assert len(paper.store.archive(reader)) == 1
    assert discovery.calls == 1


async def test_separate_workers_claim_before_retrieval(news_settings):
    class SlowDiscovery(FixtureDiscovery):
        async def retrieve(self, *args):
            await asyncio.sleep(0.15)
            return await super().retrieve(*args)
    discovery = SlowDiscovery()
    first = Newspaper(news_settings, discovery=discovery)
    second = Newspaper(news_settings, discovery=discovery)
    reader = str(uuid4())
    a, b = await asyncio.gather(first.generate(reader), second.generate(reader))
    assert a['id'] == b['id'] and discovery.calls == 1


async def test_restart_catches_up_only_today_and_keeps_old_snapshot(news_settings):
    reader = str(uuid4())
    paper = Newspaper(news_settings, discovery=FixtureDiscovery())
    paper.store.save_profile(reader, ProfileInput(timezone='Asia/Karachi'))
    past = datetime.fromisoformat('2026-10-13T20:00:00+00:00')
    old = await paper.generate(reader, now=past)
    restarted = Newspaper(news_settings, discovery=FixtureDiscovery())
    now = datetime.fromisoformat('2026-10-17T20:00:00+00:00')
    await DailyScheduler(restarted).tick(now)
    archive = restarted.store.archive(reader)
    assert [row['local_date'] for row in archive] == ['2026-10-18', '2026-10-14']
    assert restarted.store.edition(reader, old['id']) == old
    await DailyScheduler(restarted).tick(now)
    assert restarted.discovery.calls == 1


@pytest.mark.parametrize('first,second,expected', [
    ('2026-11-01T05:30:00+00:00', '2026-11-01T06:30:00+00:00', '2026-11-01'),
    ('2026-03-08T06:30:00+00:00', '2026-03-08T07:30:00+00:00', '2026-03-08'),
])
async def test_dst_repeated_and_missing_hours_do_not_duplicate(news_settings, first, second, expected):
    paper = Newspaper(news_settings, discovery=FixtureDiscovery())
    reader = str(uuid4())
    paper.store.save_profile(reader, ProfileInput(timezone='America/New_York'))
    a = await paper.generate(reader, now=datetime.fromisoformat(first))
    b = await paper.generate(reader, now=datetime.fromisoformat(second))
    assert a['id'] == b['id'] and a['local_date'] == expected
    assert paper.discovery.calls == 1


async def test_offline_fallback_retains_dates_and_never_relabels_old_edition(news_settings):
    now = datetime.now().astimezone()
    article = make_article('technology').model_copy(update={'retrieved_at': now - timedelta(days=2)})
    paper = Newspaper(news_settings, discovery=FixtureDiscovery([article]))
    reader = str(uuid4())
    old = await paper.generate(reader, now=now - timedelta(days=1))
    restarted = Newspaper(news_settings, discovery=FixtureDiscovery([]))
    current = await restarted.generate(reader, now=now, trigger='automatic')
    assert current['status'] == 'offline_fallback'
    assert current['id'] != old['id'] and current['local_date'] != old['local_date']
    assert current['articles'][0]['retrieved_at'] == article.model_dump(mode='json')['retrieved_at']
    assert 'previously retrieved content, not fresh news' in edition_html(current)
    assert restarted.store.edition(reader, old['id']) == old
    assert (await restarted.generate(reader, now=now)) == current
    assert restarted.discovery.calls == 1


async def test_expired_future_and_non_rss_content_is_not_offline_fallback(news_settings):
    now = datetime.now().astimezone()
    paper = Newspaper(news_settings, discovery=FixtureDiscovery([]))
    paper.store.articles([
        make_article('technology').model_copy(update={'retrieved_at': now - timedelta(days=8)}),
        make_article('science').model_copy(update={'retrieved_at': now + timedelta(days=1)}),
        make_article('sports').model_copy(update={'provenance': 'exa_excerpt'}),
    ])
    reader = str(uuid4())
    with pytest.raises(NoLiveNews):
        await paper.generate(reader, now=now)
    assert not paper.store.archive(reader)


async def test_failed_generation_cooldown_and_expired_lease_recovery(news_settings):
    paper = Newspaper(news_settings, discovery=FixtureDiscovery([]))
    reader = str(uuid4())
    with pytest.raises(NoLiveNews):
        await paper.generate(reader)
    with pytest.raises(NoLiveNews):
        await paper.generate(reader)
    assert paper.discovery.calls == 1
    with paper.store.connect() as db:
        db.execute('UPDATE generation_leases SET expires_at=0')
    paper.discovery.items = [make_article('science')]
    assert (await paper.generate(reader))['article_count'] == 1


async def test_query_and_common_feeds_are_cached_without_changing_retrieval_times(news_settings):
    calls = []
    def handle(request):
        calls.append(str(request.url))
        return httpx.Response(200, content=RSS)
    discovery = NewsDiscovery(news_settings, httpx.MockTransport(handle))
    first = await discovery.retrieve('AI')
    second = await discovery.retrieve('climate')
    third = await discovery.retrieve('AI')
    assert len(calls) == len(FEEDS) + 2
    assert second['cached'] and third['cached']
    assert third['articles'][0].retrieved_at == first['articles'][0].retrieved_at


async def test_scheduler_skips_not_onboarded_and_isolates_failure(news_settings):
    paper = Newspaper(news_settings, discovery=FixtureDiscovery([]))
    paper.store.save_profile(str(uuid4()), ProfileInput(onboarded=False))
    paper.store.save_profile(str(uuid4()), ProfileInput())
    paper.store.save_profile(str(uuid4()), ProfileInput())
    result = await DailyScheduler(paper).tick()
    assert result == {'ready': 0, 'unavailable': 2}
    assert paper.discovery.calls == 2


async def test_fastapi_lifespan_automatically_generates_and_stops(news_settings):
    news_settings.daily_generation_interval_seconds = 1
    paper = Newspaper(news_settings, discovery=FixtureDiscovery())
    reader = str(uuid4())
    paper.store.save_profile(reader, ProfileInput())
    app = create_app(news_settings, newspaper=paper)
    async with app.router.lifespan_context(app):
        for _ in range(50):
            if paper.store.archive(reader):
                break
            await asyncio.sleep(0.01)
        edition = paper.store.archive(reader)[0]
        assert paper.store.edition(reader, edition['id'])['generation_trigger'] == 'automatic'
    assert paper.discovery.calls == 1


async def test_disabled_scheduler_does_not_retrieve(news_settings):
    news_settings.daily_generation_enabled = False
    paper = Newspaper(news_settings, discovery=FixtureDiscovery())
    reader = str(uuid4())
    paper.store.save_profile(reader, ProfileInput())
    app = create_app(news_settings, newspaper=paper)
    async with app.router.lifespan_context(app):
        await asyncio.sleep(0.01)
    assert paper.discovery.calls == 0


async def test_naive_generation_clock_rejected(news_settings):
    paper = Newspaper(news_settings, discovery=FixtureDiscovery())
    with pytest.raises(ValueError, match='timezone-aware'):
        await paper.generate(str(uuid4()), now=datetime(2026, 10, 17))


async def test_shutdown_cancellation_releases_claim_for_restart(news_settings):
    started = asyncio.Event()
    class SlowDiscovery:
        async def retrieve(self, *args):
            started.set()
            await asyncio.Future()
    paper = Newspaper(news_settings, discovery=SlowDiscovery())
    reader = str(uuid4())
    task = asyncio.create_task(paper.generate(reader))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    restored = Newspaper(news_settings, discovery=FixtureDiscovery())
    assert (await restored.generate(reader))['version'] == 1


async def test_retrieval_timeout_uses_real_persisted_rss_schema(news_settings):
    class TimeoutDiscovery:
        async def retrieve(self, *args):
            raise TimeoutError()
    paper = Newspaper(news_settings, discovery=TimeoutDiscovery())
    paper.store.articles([make_article('science')])
    edition = await paper.generate(str(uuid4()))
    assert edition['status'] == 'offline_fallback'
    assert any('timed out' in warning for warning in edition['warnings'])
