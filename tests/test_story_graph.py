"""Synthetic examples are test-only; never served as real news."""
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from backend.config import Settings
from backend.news.models import Article, ProfileInput
from backend.news.pdf import edition_html
from backend.news.ranking import rank_articles
from backend.news.routes import create_news_router
from backend.news.service import Newspaper
from backend.news.store import Store
from backend.news.story_graph import StoryGraph, match, text

NOW = datetime(2026, 10, 17, 8, tzinfo=timezone.utc)


def article(title='Aurora satellite mission enters lunar orbit', id='a', day=0, **changes):
    return Article(**{'id': id, 'url': f'https://example.org/{id}', 'title': title,
                     'source': 'TEST publisher', 'origin': 'synthetic-test', 'description': 'TEST ONLY attributed excerpt.',
                     'retrieved_at': NOW + timedelta(days=day), 'published_at': NOW + timedelta(days=day),
                     'topics': ['science'], **changes})


@pytest.fixture
def setup(tmp_path):
    settings = Settings(_env_file=None, database_path=str(tmp_path/'isolated.sqlite3'),
                        story_semantic_enabled=False, daily_generation_enabled=False)
    store = Store(settings.database_path)
    reader = str(uuid4())
    store.save_profile(reader, ProfileInput(topics={'science': 1}))
    return settings, store, reader, StoryGraph(store, settings)


def test_matching_rejects_broad_topics_dates_entities_and_sparse_text():
    pairs = [
        (article('OpenAI launches GPT-5 language model'), article('Google launches Gemini language model', 'b')),
        (article('Karachi factory fire on 12 October'), article('Karachi factory fire on 15 October', 'b')),
        (article(), article(id='b', day=30)),
        (article('Science news'), article('Science news', 'b')),
        (article('Aurora satellite mission enters lunar orbit'), article('Borealis satellite mission enters Mars orbit', 'b')),
    ]
    for a, b in pairs:
        assert not match(a.model_dump(mode='json'), b.model_dump(mode='json'))[0]


def test_shared_url_and_conservative_positive():
    a, b = article(), article('Aurora satellite mission reaches lunar orbit', 'b', day=1)
    assert match(a.model_dump(mode='json'), b.model_dump(mode='json'))[0]
    b = article('Changed publisher headline', 'b', url=str(a.url))
    assert match(a.model_dump(mode='json'), b.model_dump(mode='json'))[0]


def test_semantics_alone_cannot_merge_unrelated_events():
    a, b = article(), article('Borealis satellite reaches Mars', 'b')
    av, bv = a.model_dump(mode='json'), b.model_dump(mode='json')
    assert not match(av, bv, {text(av): [1., 0.], text(bv): [1., 0.]})[0]


def test_persistence_idempotence_changed_versions_and_late_old_article(setup):
    settings, store, reader, graph = setup
    first = article()
    sid = graph.ingest(reader, [first])['a']
    graph.ingest(reader, [first, first])
    assert len(graph.detail(reader, sid).timeline) == 1
    revised = article(description='A changed source excerpt supplied by the publisher.')
    graph.ingest(reader, [revised])
    late = article('Aurora satellite mission reaches lunar orbit', 'b', day=2,
                   published_at=NOW-timedelta(days=2), source='TEST second publisher')
    assert graph.ingest(reader, [late])['b'] == sid
    restarted = StoryGraph(Store(settings.database_path), settings)
    detail = restarted.detail(reader, sid)
    assert len(detail.timeline) == 3
    assert detail.timeline[-1].published_at < detail.timeline[-1].observed_at
    assert 'New source' in detail.timeline[-1].change
    assert all('Not enough source evidence' in e.change for e in detail.timeline)
    with store.connect() as db:
        assert not db.execute('PRAGMA foreign_key_check').fetchall()


def test_reader_isolation_follow_restart_and_updates(setup):
    settings, store, reader, graph = setup
    sid = graph.ingest(reader, [article()])['a']
    other = str(uuid4())
    store.save_profile(other, ProfileInput())
    with pytest.raises(KeyError):
        graph.follow(other, sid, True)
    with pytest.raises(KeyError):
        graph.detail(other, sid)
    graph.follow(reader, sid, True)
    graph.follow(reader, sid, True)
    assert StoryGraph(store, settings).followed(reader) == {sid}
    assert graph.followed(other) == set()
    assert not graph.updates(reader, (NOW+timedelta(hours=1)).isoformat()).stories
    graph.ingest(reader, [article('Aurora satellite mission reaches lunar orbit', 'b', day=1)])
    assert len(graph.updates(reader, (NOW+timedelta(hours=1)).isoformat()).stories[0].timeline) == 1
    graph.follow(reader, sid, False)
    assert not graph.followed(reader)


def test_follow_bonus_bounded_and_seen_articles_not_boosted():
    items = [article(id=str(i)) for i in range(8)]
    profile = ProfileInput(topics={'science': 1}, edition_length=4).model_dump()
    ids = {a.id: 'story' for a in items}
    ranked = rank_articles(items, profile, [], NOW, ids, {'story'})
    assert sum(bool(a['breakdown'].get('followed_story')) for a in ranked) == 2
    seen = rank_articles(items, profile, [], NOW, ids, {'story'}, {a.id for a in items})
    assert all('followed_story' not in a['breakdown'] for a in seen)


async def test_service_snapshot_follow_ranking_and_archive_immutable(setup):
    settings, store, reader, graph = setup
    class Discovery:
        items = [article()]
        async def retrieve(self, *args):
            return {'articles': self.items, 'warnings': [], 'cached': False}
    discovery = Discovery()
    paper = Newspaper(settings, store, discovery)
    first = await paper.generate(reader, now=NOW)
    frozen = json.dumps(first, sort_keys=True)
    sid = first['articles'][0]['story_id']
    graph.follow(reader, sid, True)
    discovery.items = [article('Aurora satellite mission reaches lunar orbit', 'b', day=1)]
    second = await paper.generate(reader, now=NOW+timedelta(days=1))
    assert second['articles'][0]['breakdown']['followed_story'] == 1.5
    assert len(second['continuing_stories'][0]['timeline']) == 2
    assert len(second['story_updates']['stories'][0]['timeline']) == 1
    assert json.dumps(store.edition(reader, first['id']), sort_keys=True) == frozen
    html = edition_html(second)
    assert 'THE CONTINUING STORIES' in html and 'Since your last edition' in html
    assert 'https://example.org/b' in html and 'Published:' in html and 'Observed:' in html


async def test_story_routes_validate_readers_and_ids(setup):
    settings, store, reader, graph = setup
    sid = graph.ingest(reader, [article()])['a']
    app = FastAPI()
    app.include_router(create_news_router(Newspaper(settings, store)))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        headers = {'X-Reader-ID': reader}
        assert (await client.get('/api/stories/'+sid)).status_code == 400
        assert (await client.get('/api/stories/bad', headers=headers)).status_code == 404
        assert (await client.get('/api/stories/'+sid, headers={'X-Reader-ID':str(uuid4())})).status_code == 404
        result = await client.put('/api/stories/'+sid+'/follow', headers=headers, json={'followed':True})
        assert result.status_code == 200 and result.json()['followed']
        assert (await client.get('/api/stories/updates', headers=headers)).json()['stories']


def test_missing_model_falls_back_without_network(setup, tmp_path):
    settings, store, reader, graph = setup
    settings.story_semantic_enabled = True
    settings.story_model_cache = str(tmp_path/'missing-model-cache')
    assert graph.ingest(reader, [article()])
    assert graph.embeddings.status == 'model_unavailable'


def test_embedding_cache_uses_one_batch_and_no_repeated_inference(setup, monkeypatch, tmp_path):
    from backend.news import embeddings
    settings, store, reader, graph = setup
    settings.story_semantic_enabled = True
    settings.story_model_cache = str(tmp_path)
    calls = []
    class Vectors(list):
        def tolist(self): return list(self)
    class Model:
        def encode(self, texts, **kwargs):
            calls.append(texts)
            assert kwargs['normalize_embeddings']
            return Vectors([[1., 0.] for _ in texts])
    monkeypatch.setattr(embeddings, 'load_model', lambda *args: Model())
    engine = embeddings.Embeddings(settings, store)
    assert engine.encode(['one', 'two', 'one']) == {'one':[1.,0.], 'two':[1.,0.]}
    engine.encode(['one', 'two'])
    assert calls == [['one', 'two']]


async def test_story_failure_preserves_standard_edition(setup, monkeypatch):
    settings, store, reader, graph = setup
    class Discovery:
        async def retrieve(self, *args):
            return {'articles':[article()], 'warnings':[], 'cached':False}
    paper = Newspaper(settings, store, Discovery())
    def unavailable(*args):
        raise OSError('TEST ONLY unavailable story processing')
    monkeypatch.setattr(paper.stories, 'ingest', unavailable)
    result = await paper.generate(reader, now=NOW)
    assert result['article_count'] == 1
    assert 'story_id' not in result['articles'][0]
    assert any('standard newspaper ranking preserved' in w for w in result['warnings'])


def test_additive_migration_preserves_legacy_snapshot_and_source_escaping(tmp_path):
    from backend.news.pdf import story_html
    settings = Settings(_env_file=None,database_path=str(tmp_path/'legacy.sqlite3'),story_semantic_enabled=False)
    store = Store(settings.database_path)
    reader = str(uuid4())
    store.save_profile(reader, ProfileInput())
    legacy = {'articles':[], 'generated_at':NOW.isoformat(), 'legacy_field':'preserved'}
    saved = store.save_edition(reader,'2026-10-17',legacy,False)
    graph = StoryGraph(store,settings)
    assert store.edition(reader,saved['id']) == saved
    sid = graph.ingest(reader,[article(title='<script>alert(1)</script>')])['a']
    detail = graph.detail(reader,sid).model_dump(mode='json')
    html = story_html({'continuing_stories':[detail]})
    assert '<script>' not in html and '&lt;script&gt;' in html


def test_semantic_candidate_requires_shared_specific_terms():
    a = article('Aurora lunar mission prepares touchdown').model_dump(mode='json')
    b = article('Aurora lunar probe begins landing', 'b').model_dump(mode='json')
    assert not match(a,b)[0]
    assert match(a,b,{text(a):[1.,0.],text(b):[.9,.435889894]})[0]
