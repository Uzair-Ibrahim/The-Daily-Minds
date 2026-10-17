import asyncio
import io
from uuid import uuid4

import httpx
import pytest
from PIL import Image
from pypdf import PdfReader

from backend.main import create_app
from backend.news.discovery import NewsDiscovery
from backend.news.images import ImageDelivery, extract_image, image_url, prepare_image
from backend.news.models import Article
from backend.news.pdf import edition_html, render_pdf
from backend.news.service import Newspaper
from tests.test_newspaper import FixtureDiscovery, make_article, news_settings

URL = 'https://i.dawn.com/large/editorial.jpg'


def picture(width=640, height=360):
    output = io.BytesIO()
    # MOCK DATA: Plain test image; never represented as real news photography.
    Image.new('RGB', (width, height), '#365547').save(output, format='JPEG')
    return output.getvalue()


async def public(_):
    return True


def test_metadata_priority_and_larger_image_selection():
    entry = {'media_content': [{'url': URL + '?small', 'width': '200', 'height': '120'},
                               {'url': URL, 'width': '800', 'height': '480'}],
             'media_thumbnail': [{'url': 'https://i.dawn.com/thumb.jpg', 'width': '1000'}],
             'media_credit': [{'content': 'Photo: Test photographer'}]}
    result = extract_image(entry, 'https://www.dawn.com/story')
    assert result == {'image_url': URL, 'image_origin': 'media_content', 'image_credit': 'Photo: Test photographer'}


@pytest.mark.parametrize('entry,kind', [
    ({'media_content': [{'url': 'data:bad'}], 'media_thumbnail': [{'url': URL}]}, 'media_thumbnail'),
    ({'enclosures': [{'href': URL, 'type': 'image/jpeg'}]}, 'enclosure'),
    ({'summary': '<img src="data:bad"><img src="/large/editorial.jpg" width="800" height="480">'}, 'html_img'),
    ({'content': [{'value': '<img data-src="https://i.dawn.com/large/editorial.jpg">'}]}, 'html_img'),
    ({'image': {'href': URL}}, 'image'),
    ({'image': URL}, 'image'),
])
def test_extraction_fallbacks(entry, kind):
    result = extract_image(entry, 'https://i.dawn.com/story')
    assert result['image_url'] == URL and result['image_origin'] == kind


@pytest.mark.parametrize('url', ['data:image/png;base64,abc', 'javascript:alert(1)',
    'file:///photo.jpg', 'https://user:pass@i.dawn.com/a.jpg', 'http://localhost/a.jpg',
    'http://127.0.0.1/a.jpg', 'http://169.254.169.254/a.jpg', 'http://[::1]/a.jpg',
    'https://i.dawn.com/tracking.gif', 'https://i.dawn.com/sprite.png', 'https://i.dawn.com/a.svg',
    'https://i.dawn.com:8443/a.jpg', 'https://i.dawn.com/a.jpg?w=1&h=1'])
def test_invalid_urls_rejected_without_losing_article(url):
    assert image_url(url) is None
    values = make_article('science').model_dump()
    values['image_url'] = url
    assert Article.model_validate(values).image_url is None


def test_tiny_video_tracking_and_first_valid_html_image():
    result = extract_image({'media_content': [{'url': URL, 'width': '1', 'height': '1'},
                                             {'url': URL, 'medium': 'video'}],
                            'enclosures': [{'href': URL, 'type': 'audio/mpeg'}],
                            'summary': '<img src="/pixel.png" width="1"><img src="/large/editorial.jpg"><img src="/other.jpg">'},
                           'https://i.dawn.com/story')
    assert result['image_url'] == URL and result['image_origin'] == 'html_img'
    assert extract_image({}, 'https://example.org/story')['image_url'] is None


async def test_rss_extraction_persists_in_immutable_editions_and_legacy_works(news_settings):
    rss = b'''<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/"><channel><title>TEST RSS</title>
    <item><title>TEST science report</title><link>https://example.org/science</link>
    <media:content url="https://i.dawn.com/large/editorial.jpg" medium="image" width="800" height="480"/>
    <description>TEST ONLY article</description></item></channel></rss>'''
    discovery = NewsDiscovery(news_settings, httpx.MockTransport(lambda req: httpx.Response(200, content=rss)))
    paper = Newspaper(news_settings, discovery=discovery)
    reader = str(uuid4())
    edition = await paper.generate(reader)
    assert edition['articles'][0]['image_url'] == URL
    assert edition['articles'][0]['image_origin'] == 'media_content'
    restored = Newspaper(news_settings, discovery=FixtureDiscovery([]))
    assert restored.store.edition(reader, edition['id']) == edition
    for item in edition['articles']:
        item.pop('image_url', None)
        item.pop('image_origin', None)
        item.pop('image_credit', None)
    assert 'Publisher image unavailable' in edition_html(edition)


async def test_delivery_coalesces_reencodes_and_caches():
    calls = []
    async def handle(request):
        calls.append(request)
        await asyncio.sleep(0.01)
        assert 'authorization' not in request.headers and 'cookie' not in request.headers
        return httpx.Response(200, content=picture(), headers={'content-type': 'image/jpeg'})
    delivery = ImageDelivery(httpx.MockTransport(handle), public)
    a, b = await asyncio.gather(delivery.get(URL), delivery.get(URL))
    assert a and a == b and len(calls) == 1
    assert await delivery.get(URL) == a and len(calls) == 1
    assert Image.open(io.BytesIO(a)).size == (640, 360)


@pytest.mark.parametrize('code,content,kind', [
    (503, b'busy', 'text/plain'), (200, b'<script>bad</script>', 'image/jpeg'),
    (200, b'html', 'text/html'), (302, b'', 'image/jpeg'),
    (200, b'x' * 3_000_001, 'image/jpeg'), (200, picture(1, 1), 'image/jpeg'),
], ids=['unavailable', 'invalid-bytes', 'html', 'redirect', 'oversize', 'tiny'])
async def test_delivery_failures_are_cached_and_graceful(code, content, kind):
    calls = []
    def handle(request):
        calls.append(request)
        return httpx.Response(code, content=content, headers={'content-type': kind, 'location': 'http://127.0.0.1/private'})
    delivery = ImageDelivery(httpx.MockTransport(handle), public)
    assert await delivery.get(URL) is None
    assert await delivery.get(URL) is None
    assert len(calls) == 1


async def test_proxy_rejects_unknown_hosts_and_private_dns_without_requests():
    calls = []
    def handle(request):
        calls.append(request)
        return httpx.Response(200)
    async def private(_):
        return False
    delivery = ImageDelivery(httpx.MockTransport(handle), private)
    for url in [URL, 'https://i.dawn.com.evil.org/a.jpg', 'http://127.0.0.1/a.jpg', 'https://unknown.example/a.jpg']:
        assert await delivery.get(url) is None
    assert calls == []


async def test_network_timeout_is_negative_cached_without_exception():
    calls = []
    def handle(request):
        calls.append(request)
        raise httpx.ReadTimeout('TEST ONLY upstream timeout')
    delivery = ImageDelivery(httpx.MockTransport(handle), public)
    assert await delivery.get(URL) is None
    assert await delivery.get(URL) is None and len(calls) == 1


async def test_image_endpoint_scopes_snapshot_and_returns_clean_fallback(news_settings, monkeypatch):
    import backend.news.routes as routes
    calls = []
    class Loader:
        async def get(self, url):
            calls.append(url)
            return picture() if url else None
    monkeypatch.setattr(routes, 'ImageDelivery', Loader)
    paper = Newspaper(news_settings, discovery=FixtureDiscovery([make_article('science').model_copy(update={'image_url': URL})]))
    reader = str(uuid4())
    edition = await paper.generate(reader)
    path = f"/api/editions/{edition['id']}/articles/{edition['articles'][0]['id']}/image"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(create_app(news_settings, newspaper=paper)), base_url='http://test') as client:
        assert (await client.get(path)).status_code == 400
        assert (await client.get(path, headers={'X-Reader-ID': str(uuid4())})).status_code == 404
        response = await client.get(path, headers={'X-Reader-ID': reader})
        assert response.status_code == 200 and response.headers['content-type'] == 'image/jpeg'
        assert set(response.headers['vary'].split(', ')) == {'X-Reader-ID', 'Authorization'}
        assert calls == [URL]
        missing = path.replace(edition['articles'][0]['id'], 'not-in-edition')
        assert (await client.get(missing, headers={'X-Reader-ID': reader})).status_code == 404


@pytest.mark.pdf
async def test_actual_pdf_embeds_only_lead_photo_and_keeps_snapshot_text(news_settings):
    article = make_article('science').model_copy(update={'image_url': URL, 'image_credit': 'TEST photographer'})
    paper = Newspaper(news_settings, discovery=FixtureDiscovery([article]))
    edition = await paper.generate(str(uuid4()))
    delivery = ImageDelivery(httpx.MockTransport(lambda req: httpx.Response(200, content=picture(), headers={'content-type': 'image/jpeg'})), public)
    content = await render_pdf(edition, image_loader=delivery)
    pdf = PdfReader(io.BytesIO(content))
    assert sum(len(page.images) for page in pdf.pages) == 1
    text = ' '.join(page.extract_text() for page in pdf.pages)
    assert article.title in text and edition['id'] in text and 'TEST photographer' in text
    assert edition['articles'][0]['image_url'] == URL
    class Broken:
        async def get(self, url):
            raise TimeoutError()
    fallback = PdfReader(io.BytesIO(await render_pdf(edition, image_loader=Broken())))
    assert sum(len(page.images) for page in fallback.pages) == 0
    assert 'Publisher image unavailable' in ' '.join(page.extract_text() for page in fallback.pages)
