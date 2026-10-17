import asyncio
import json
import subprocess
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from backend.main import create_app
from backend.news.editorial import primary_topic
from backend.news.image_resolver import ArticleImageResolver, page_images
from backend.news.images import ImageDelivery
from backend.news.images import extract_image
from backend.news.ranking import rank_articles
from backend.news.safe_network import PublicNetworkBackend
from backend.news.service import Newspaper
from tests.test_images import URL, picture, public
from tests.test_newspaper import FixtureDiscovery, make_article, news_settings


async def test_like_save_desired_states_reverse_independently_and_persist(news_settings):
    paper = Newspaper(news_settings, discovery=FixtureDiscovery([make_article('technology')]))
    reader = str(uuid4())
    edition = await paper.generate(reader)
    article = edition['articles'][0]
    baseline = paper.dna(reader)
    for active in [True, True, False, False, True]:
        paper.store.interact(reader, article['id'], 'liked', active)
        assert paper.store.engagement(reader, article['id'])['like_count'] == int(active)
    paper.store.interact(reader, article['id'], 'saved', True)
    paper.store.interact(reader, article['id'], 'liked', False)
    state = paper.store.engagement(reader, article['id'])
    assert not state['liked'] and state['saved'] and state['like_count'] == 0
    dna = next(item for item in paper.dna(reader) if item['topic'] == 'technology')
    assert dna['feedback'] == 0.25
    paper.store.interact(reader, article['id'], 'saved', False)
    assert paper.dna(reader) == baseline
    restored = Newspaper(news_settings, discovery=FixtureDiscovery([]))
    assert restored.store.events(reader) == []
    assert restored.store.edition(reader, edition['id']) == edition


async def test_api_like_save_counts_reading_list_cross_edition_and_isolation(news_settings):
    paper = Newspaper(news_settings, discovery=FixtureDiscovery([make_article('science')]))
    reader = str(uuid4())
    first = await paper.generate(reader)
    await paper.generate(reader, regenerate=True)
    app = create_app(news_settings, newspaper=paper)
    article_id = first['articles'][0]['id']
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test', headers={'X-Reader-ID':reader}) as client:
        async def desired(action, active):
            response = await client.post(f'/api/articles/{article_id}/interactions', json={'action':action,'active':active})
            assert response.status_code == 200
            return response.json()
        results = await asyncio.gather(*(desired('liked',True) for _ in range(6)))
        assert sum(result['recorded'] for result in results) == 1
        assert all(result['engagement']['like_count'] == 1 for result in results)
        for active in [False,True,False]:
            result = await desired('liked',active)
            assert result['engagement']['liked'] is active
        for active in [True,False,True]:
            result = await desired('saved',active)
            assert result['engagement']['saved'] is active
        reading = (await client.get('/api/reading-list')).json()
        assert len(reading) == 1 and reading[0]['article']['id'] == article_id
        restored = (await client.get('/api/editions/'+first['id'])).json()
        assert restored['articles'] == first['articles']
        assert restored['article_engagement'][article_id]['saved']
        assert (await client.get('/api/reading-list', headers={'X-Reader-ID':str(uuid4())})).json() == []
        denied = await client.post(f'/api/articles/{article_id}/interactions', headers={'X-Reader-ID':str(uuid4())},json={'action':'liked'})
        assert denied.status_code == 404


async def test_dna_and_rank_match_after_like_and_save_reversals(news_settings):
    item = make_article('technology')
    paper = Newspaper(news_settings, discovery=FixtureDiscovery([item]))
    reader = str(uuid4())
    await paper.generate(reader)
    for action, active in [('liked', True),('saved',True),('liked',False),('saved',False),('liked',True)]:
        paper.store.interact(reader, item.id, action, active)
        dna = next(row for row in paper.dna(reader) if row['topic']=='technology')
        score = rank_articles([item],paper.profile(reader),paper.store.events(reader))[0]
        assert score['breakdown']['interests']+score['breakdown']['feedback'] == pytest.approx(dna['weight']*3)


@pytest.mark.parametrize('title,expected', [
    ('Millions may be forced to move as climate change hits South Asia: UN','science'),
    ('New AI software powers digital computers','technology'),
    ('World election and diplomacy talks','world'),
    ('Climate scientists publish new study','science'),
    ('Stock market trade lifts economy','business'),
])
def test_primary_category_uses_headline_not_preferred_interest(title,expected):
    assert primary_topic({'title':title,'topics':['technology','world','science','business']}) == expected


def test_page_og_twitter_structured_metadata_and_association():
    html = '''<link rel="canonical" href="https://www.dawn.com/news/test"><meta property="og:image" content="https://i.dawn.com/a.jpg">
    <meta property="og:image:alt" content="Source caption"><meta name="twitter:image" content="https://i.dawn.com/b.jpg">
    <script type="application/ld+json">{"@graph":[{"@type":"NewsArticle","image":{"url":"https://i.dawn.com/c.jpg","caption":"Actual caption","creditText":"Photographer","license":"https://example.org/license"}}]}</script>'''
    result = page_images(html,'https://www.dawn.com/news/test')
    assert [item['image_source'] for item in result] == ['og:image','twitter:image','NewsArticle.image']
    assert result[2]['image_credit']=='Photographer'
    assert page_images(html,'https://www.dawn.com/news/unrelated') == []


async def test_dns_pins_validated_address_and_blocks_rebinding():
    calls = []
    class Backend:
        async def connect_tcp(self,host,port,**kwargs):
            calls.append(host)
            return 'TEST STREAM'
    async def lookup(host,port,**kwargs):
        return [(None,None,None,None,('93.184.216.34',443))]
    backend = PublicNetworkBackend(Backend(),lookup)
    assert await backend.connect_tcp('publisher.example',443)=='TEST STREAM'
    assert calls == ['93.184.216.34']
    async def private(host,port,**kwargs):
        return [(None,None,None,None,('127.0.0.1',443))]
    with pytest.raises(OSError):
        await PublicNetworkBackend(Backend(),private).connect_tcp('publisher.example',443)
    assert calls == ['93.184.216.34']


def test_rss_image_extension_precedes_description_html():
    result = extract_image({'image':{'href':URL},'summary':'<img src="https://i.dawn.com/other.jpg">'}, 'https://www.dawn.com/news/test')
    assert result['image_url']==URL and result['image_origin']=='image'


async def test_redirect_to_private_and_unknown_hosts_is_not_requested(news_settings):
    paper=Newspaper(news_settings,discovery=FixtureDiscovery([]))
    calls=[]
    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(302,headers={'location':'http://127.0.0.1/private'})
    resolver=ArticleImageResolver(paper.store,ImageDelivery(),httpx.MockTransport(handler))
    body,status=await resolver.fetch('https://www.dawn.com/news/test')
    assert body is None and status=='blocked_destination' and len(calls)==1


async def test_legacy_rss_enrichment_persists_without_snapshot_mutation(news_settings):
    article=make_article('science').model_dump(mode='json')
    article['url']='https://www.dawn.com/news/test'
    paper=Newspaper(news_settings,discovery=FixtureDiscovery([]))
    calls=[]
    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200,content=b'<rss xmlns:media="http://search.yahoo.com/mrss/"><channel><item><title>TEST</title><link>https://www.dawn.com/news/test</link><media:content medium="image" url="https://i.dawn.com/large/editorial.jpg"/></item></channel></rss>')
    delivery=ImageDelivery(httpx.MockTransport(lambda r:httpx.Response(200,content=picture(),headers={'content-type':'image/jpeg'})),public)
    resolver=ArticleImageResolver(paper.store,delivery,httpx.MockTransport(handler))
    old=dict(article)
    found=await resolver.resolve(article)
    assert found['image_status']=='ready' and found['image_url']==URL and article==old
    restored=ArticleImageResolver(paper.store,delivery,httpx.MockTransport(lambda r:pytest.fail('Unexpected repeat metadata request')))
    assert await restored.resolve(article)==found
    assert len(calls)==1


async def test_robots_denial_and_page_403_are_honored_and_negative_cached(news_settings):
    paper=Newspaper(news_settings,discovery=FixtureDiscovery([]))
    article=make_article('science').model_dump(mode='json');article['url']='https://www.dawn.com/news/test'
    for allow in [False,True]:
        article['id']=str(uuid4())
        calls=[]
        def handle(request):
            calls.append(request.url.path)
            if request.url.path=='/feeds/home':return httpx.Response(200,content=b'<rss><channel/></rss>')
            if request.url.path=='/robots.txt':return httpx.Response(200,text='User-agent: *\nDisallow: '+('' if allow else '/'))
            return httpx.Response(403)
        resolver=ArticleImageResolver(paper.store,ImageDelivery(),httpx.MockTransport(handle))
        result=await resolver.resolve(article)
        assert not result['image_url']
        assert ('/news/test' in calls) is allow
        count=len(calls)
        assert await resolver.resolve(article)==result and len(calls)==count


async def test_disk_image_cache_survives_restart_and_failure_is_cached(tmp_path):
    calls=[]
    def handle(request):
        calls.append(request)
        return httpx.Response(200,content=picture(),headers={'content-type':'image/jpeg'})
    first=ImageDelivery(httpx.MockTransport(handle),public,cache_dir=tmp_path)
    content=await first.get(URL)
    second=ImageDelivery(httpx.MockTransport(lambda r:pytest.fail('Unexpected redownload')),public,cache_dir=tmp_path)
    assert await second.get(URL)==content and len(calls)==1


def test_share_links_encode_public_original_only():
    module=(Path(__file__).resolve().parents[1]/'frontend/src/components/share-links.js').as_uri()
    script='import {shareLinks} from '+json.dumps(module)+';console.log(JSON.stringify([shareLinks({title:"Climate & health?",url:"https://example.org/news?a=1&b=2"}),shareLinks({title:"Private",url:"http://localhost:8000/private"})]));'
    result=subprocess.run(['node','--input-type=module','-e',script],capture_output=True,text=True,check=True)
    links,private=json.loads(result.stdout)
    assert private is None and set(links)=={'WhatsApp','X','LinkedIn'}
    from urllib.parse import urlsplit,parse_qs
    assert parse_qs(urlsplit(links['WhatsApp']).query)['text']==['Climate & health?\nhttps://example.org/news?a=1&b=2']
    assert parse_qs(urlsplit(links['LinkedIn']).query)['url']==['https://example.org/news?a=1&b=2']
