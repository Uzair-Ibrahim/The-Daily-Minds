"""Bounded, publisher-associated image enrichment without rewriting edition snapshots."""
import asyncio
from collections import OrderedDict
from html.parser import HTMLParser
import json
import re
from time import time
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import feedparser
import httpx

from backend.news.images import extract_image, image_url
from backend.news.safe_network import PublicTransport

PUBLISHER_FEEDS = {
    'www.dawn.com': 'https://www.dawn.com/feeds/home',
    'www.bbc.co.uk': 'https://feeds.bbci.co.uk/news/world/rss.xml',
    'www.bbc.com': 'https://feeds.bbci.co.uk/news/world/rss.xml',
    'www.theguardian.com': 'https://www.theguardian.com/world/rss',
}
PAGE_HOSTS = set(PUBLISHER_FEEDS)
SAFE_HOSTS = PAGE_HOSTS | {'feeds.bbci.co.uk'}


def text(value, limit=300):
    return re.sub(r'\s+', ' ', re.sub('<[^>]+>', '', str(value or ''))).strip()[:limit]


def fields(entry, url):
    metadata = extract_image(entry, url)
    description = entry.get('media_description') or []
    alt = next((text(item.get('content')) for item in description if isinstance(item, dict) and item.get('content')), None)
    return {**metadata, 'image_source': metadata['image_origin'],
            'image_alt': alt, 'image_status': 'candidate' if metadata['image_url'] else 'unavailable'}


class PageMetadata(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta, self.scripts, self.canonical = {}, [], None
        self.script = None

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == 'meta':
            self.meta[values.get('property', values.get('name', '')).lower()] = values.get('content', '')
        if tag == 'link' and values.get('rel') == 'canonical':
            self.canonical = values.get('href')
        if tag == 'script' and values.get('type', '').lower() == 'application/ld+json':
            self.script = ''

    def handle_data(self, data):
        if self.script is not None:
            self.script += data[:200_000]

    def handle_endtag(self, tag):
        if tag == 'script' and self.script is not None:
            self.scripts.append(self.script)
            self.script = None


def page_images(html, article_url):
    parser = PageMetadata()
    parser.feed(html)
    if parser.canonical and urljoin(article_url, parser.canonical).split('?')[0].rstrip('/') != article_url.split('?')[0].rstrip('/'):
        return []
    candidates = []
    for key in ['og:image', 'og:image:url', 'twitter:image', 'twitter:image:src']:
        url = image_url(parser.meta.get(key), article_url)
        if url:
            candidates.append({'image_url': url, 'image_source': key, 'image_origin': key,
                               'image_alt': text(parser.meta.get('og:image:alt') or parser.meta.get('twitter:image:alt')) or None,
                               'image_credit': None})
    def visit(value, depth=0):
        if depth > 8:
            return
        if isinstance(value, list):
            for child in value[:30]:
                visit(child, depth+1)
        elif isinstance(value, dict):
            kind = value.get('@type', '')
            if 'NewsArticle' in (kind if isinstance(kind, list) else [kind]):
                photos = value.get('image') or []
                for item in (photos if isinstance(photos, list) else [photos])[:10]:
                    item = {'url': item} if isinstance(item, str) else item
                    if isinstance(item, dict):
                        url = image_url(item.get('url') or item.get('contentUrl'), article_url)
                        if url:
                            candidates.append({'image_url': url, 'image_source': 'NewsArticle.image',
                                'image_origin': 'NewsArticle.image', 'image_alt': text(item.get('caption')) or None,
                                'image_credit': text(item.get('creditText')) or None,
                                'image_license': item.get('license') if isinstance(item.get('license'), str) else None})
            visit(value.get('@graph', []), depth+1)
    for script in parser.scripts[:10]:
        try:
            visit(json.loads(script))
        except (ValueError, TypeError):
            continue
    return candidates


class ArticleImageResolver:
    def __init__(self, store, delivery, transport=None):
        self.store, self.delivery, self.transport = store, delivery, transport
        self.feeds, self.robots, self.inflight = {}, {}, {}
        self.feed_lock = asyncio.Lock()
        self.pages = asyncio.Semaphore(2)
        self.last_page = {}
        self.host_locks = {}
        self.requests = 0
        self.ready_images = OrderedDict()

    def remember(self, url, content):
        self.ready_images[url] = content
        self.ready_images.move_to_end(url)
        while len(self.ready_images) > 32:
            self.ready_images.popitem(last=False)

    async def fetch(self, url, cap=1_500_000):
        for _ in range(3):
            parts = urlsplit(url)
            if parts.scheme != 'https' or parts.hostname not in SAFE_HOSTS or parts.username or parts.password or parts.port not in {None, 443}:
                return None, 'blocked_destination'
            self.requests += 1
            async with httpx.AsyncClient(transport=self.transport or PublicTransport(), trust_env=False,
                timeout=httpx.Timeout(4, connect=2), follow_redirects=False) as client:
                async with client.stream('GET', url, headers={'User-Agent': 'TheDailyMind/1.0'}) as response:
                    if response.is_redirect:
                        url = urljoin(url, response.headers.get('location', ''))
                        continue
                    if response.status_code != 200:
                        return None, 'http_' + str(response.status_code)
                    content = bytearray()
                    async for chunk in response.aiter_bytes():
                        content.extend(chunk)
                        if len(content) > cap:
                            return None, 'oversize'
                    return bytes(content), 'ok'
        return None, 'redirect_limit'

    async def resolve(self, article):
        cached = self.store.image_enrichment(article['id'], article['url'], time())
        if cached:
            return cached
        key = (article['id'], article['url'])
        task = self.inflight.get(key)
        if task is None:
            if len(self.inflight) >= 8:
                return {'image_url': None, 'image_status': 'busy'}
            task = asyncio.create_task(self._resolve(article))
            self.inflight[key] = task
            task.add_done_callback(lambda done: self.inflight.pop(key, None))
        return await asyncio.shield(task)

    async def _resolve(self, article):
        metadata = {'image_url': None, 'image_status': 'unavailable', 'image_alt': None, 'image_credit': None}
        reason = 'no_publisher_metadata'
        try:
            async with asyncio.timeout(16):
                candidates = []
                if article.get('image_url'):
                    candidates.append({key: article.get(key) for key in ['image_url', 'image_source', 'image_origin', 'image_credit', 'image_alt']})
                host = urlsplit(article['url']).hostname
                feed_url = PUBLISHER_FEEDS.get(host)
                if not candidates and feed_url:
                    async with self.feed_lock:
                        saved = self.feeds.get(feed_url)
                        if not saved or saved[0] < time():
                            body, reason = await self.fetch(feed_url)
                            entries = (await asyncio.to_thread(feedparser.parse, body)).entries if body else []
                            self.feeds[feed_url] = (time() + 180, entries)
                        for entry in self.feeds[feed_url][1]:
                            if entry.get('link', '').split('?')[0].rstrip('/') == article['url'].split('?')[0].rstrip('/'):
                                candidate = fields(entry, article['url'])
                                if candidate['image_url']:
                                    candidates.append(candidate)
                                break
                for candidate in candidates:
                    content = await self.delivery.get(candidate['image_url'])
                    if content:
                        self.remember(candidate['image_url'], content)
                        metadata = {**candidate, 'image_status': 'ready', 'image_association': 'same_article_publisher_metadata'}
                        break
                else:
                    if host in PAGE_HOSTS:
                        async with self.pages, self.host_locks.setdefault(host, asyncio.Lock()):
                            robots_url = 'https://' + host + '/robots.txt'
                            cached = self.robots.get(host)
                            if not cached or cached[0] < time():
                                body, reason = await self.fetch(robots_url, 100_000)
                                parser = RobotFileParser()
                                parser.parse(body.decode(errors='replace').splitlines() if body else ['User-agent: *', 'Disallow: /'])
                                self.robots[host] = (time() + 3600, parser)
                            if self.robots[host][1].can_fetch('TheDailyMind', article['url']):
                                interval = max(2, self.robots[host][1].crawl_delay('TheDailyMind') or 0)
                                delay = max(0, self.last_page.get(host, 0) + interval - time())
                                await asyncio.sleep(delay)
                                self.last_page[host] = time()
                                body, reason = await self.fetch(article['url'])
                                if body:
                                    for candidate in page_images(body.decode(errors='replace'), article['url']):
                                        content = await self.delivery.get(candidate['image_url'])
                                        if content:
                                            self.remember(candidate['image_url'], content)
                                            metadata = {**candidate, 'image_status': 'ready', 'image_association': 'same_article_publisher_metadata'}
                                            break
                            else:
                                reason = 'robots_disallowed'
        except Exception:
            reason = 'unavailable_or_timeout'
        metadata = {**metadata, 'image_resolution_reason': 'validated' if metadata['image_url'] else reason,
                    'image_resolved_at': time(), 'image_permission': 'publisher_reference; reuse_license_not_independently_verified'}
        self.store.save_image_enrichment(article, metadata, time() + (86400 if metadata['image_url'] else 300))
        return metadata
