import asyncio
import calendar
import hashlib
import html
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from time import monotonic
from itertools import zip_longest
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl

import feedparser
import httpx

from backend.config import Settings
from backend.news.models import Article, TOPICS
from backend.news.images import extract_image
from backend.news.image_resolver import fields as image_fields
from backend.news.editorial import primary_topic
from backend.services.provenance import utc_now

FEEDS = [
    ("BBC", "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("Dawn", "https://www.dawn.com/feeds/home"),
    ("The Guardian", "https://www.theguardian.com/world/rss"),
    ("BBC Technology", "https://feeds.bbci.co.uk/news/technology/rss.xml"),
    ("BBC Science", "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml"),
    ("BBC Sport", "https://feeds.bbci.co.uk/sport/rss.xml"),
]


def plain(value, limit=450):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", str(value or "")))).strip()[:limit]


def canonical_url(value):
    parts = urlsplit(str(value))
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
        raise ValueError("Invalid public article URL")
    if len(str(value)) > 8192:
        raise ValueError("Article URL too long")
    query = [(key, item) for key, item in parse_qsl(parts.query, keep_blank_values=True)
             if not key.lower().startswith("utm_") and key.lower() not in {"fbclid", "gclid", "mc_cid", "mc_eid"}]
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or "/", urlencode(query), ""))


def topic_matches(text):
    lowered = text.casefold()
    return [topic for topic, info in TOPICS.items() if any(re.search(r"\b" + re.escape(term) + r"(?:s|es)?\b", lowered) for term in info["terms"])] or ["world"]


def dedupe(articles):
    result, seen, titles = [], set(), []
    for article in articles:
        title = re.sub(r"[^\w\s]", "", article.title.casefold())
        if str(article.url) in seen or any(SequenceMatcher(None, title, old).ratio() > 0.9 for old in titles):
            continue
        seen.add(str(article.url))
        titles.append(title)
        result.append(article)
    return result


class NewsDiscovery:
    def __init__(self, settings: Settings, transport=None):
        self.settings = settings
        self.transport = transport
        self.cache = None
        self.cache_expires = 0
        self.lock = asyncio.Lock()
        self.feed_cache = {}
        self.last_fetch_cached = False

    async def retrieve(self, query="", targeted=False):
        async with self.lock:
            now = monotonic()
            cached = self.cache is not None and now < self.cache_expires and not query
            if cached:
                articles, warnings = self.cache
                articles, warnings = list(articles), list(warnings) + ["RSS responses reused from the short-lived cache; original retrieval times retained."]
            else:
                articles, warnings = await self.fetch_feeds(query)
                cached = self.last_fetch_cached
                if not query and articles and self.settings.live_cache_ttl_seconds:
                    self.cache = (list(articles), list(warnings))
                    self.cache_expires = monotonic() + self.settings.live_cache_ttl_seconds
        if targeted:
            if not self.settings.credit_search_confirmed_free:
                warnings.append("Credit-based search disabled: existing no-payment free credits have not been confirmed. RSS only.")
            elif self.settings.search_configured:
                from backend.mcp_client import MCPSearchClient
                from backend.schemas import SearchRequest
                result = await MCPSearchClient(self.settings).search(SearchRequest(query=query or "latest world news", max_results=5))
                if result.evidence:
                    for source in result.evidence:
                        try:
                            url = canonical_url(source.url)
                            articles.append(Article(id=hashlib.sha256(url.encode()).hexdigest()[:24], url=url,
                                title=plain(source.title, 300), description=plain(source.snippet, 450),
                                source=urlsplit(url).hostname, origin=self.settings.search_provider,
                                published_at=source.published_at_utc, retrieved_at=source.retrieved_at_utc,
                                topics=topic_matches(source.title + " " + source.snippet),
                                provenance=self.settings.search_provider + "_excerpt"))
                        except ValueError:
                            continue
                else:
                    warnings.append("Targeted search unavailable; retained RSS results without inventing replacements.")
                    warnings.extend(result.limitations)
            else:
                warnings.append("Targeted provider key missing; using RSS only.")
        return {"articles": dedupe(articles)[:150], "warnings": warnings, "cached": cached,
                "status": "ok" if articles else "no_live_data"}

    async def fetch_feeds(self, query):
        feeds = list(FEEDS)
        if query:
            feeds.insert(0, ("Google News RSS", "https://news.google.com/rss/search?" + urlencode({"q": query, "hl": "en", "gl": "PK", "ceid": "PK:en"})))
        semaphore = asyncio.Semaphore(3)
        reused = []

        async def fetch(source, url, client):
            saved = self.feed_cache.get(url)
            if saved and monotonic() < saved[0]:
                reused.append(True)
                return list(saved[1]), saved[2]
            reused.append(False)
            async with semaphore:
                for attempt in range(2):
                    try:
                        async with asyncio.timeout(10):
                            async with client.stream("GET", url) as response:
                                response.raise_for_status()
                                content = bytearray()
                                async for chunk in response.aiter_bytes():
                                    content.extend(chunk)
                                    if len(content) > 1_500_000:
                                        raise ValueError("Feed exceeds size limit")
                            feed = await asyncio.to_thread(feedparser.parse, bytes(content))
                            retrieved = utc_now()
                            result = []
                            for entry in feed.entries[:30]:
                                try:
                                    link = canonical_url(entry.get("link", ""))
                                    title = plain(entry.get("title"), 300)
                                    if not title:
                                        continue
                                    date = entry.get("published_parsed")
                                    published = datetime.fromtimestamp(calendar.timegm(date), timezone.utc) if date else None
                                    description = plain(entry.get("summary", ""), 320)
                                    publisher = plain(entry.get("source", {}).get("title", "")) or source
                                    if publisher.startswith("BBC"):
                                        publisher = "BBC"
                                    result.append(Article(id=hashlib.sha256(link.encode()).hexdigest()[:24], url=link,
                                        title=title, source=publisher, origin=url, description=description,
                                        published_at=published, retrieved_at=retrieved, topics=topic_matches(title + " " + description),
                                        primary_topic=primary_topic({'title': title, 'topics': topic_matches(title + ' ' + description)}),
                                        **image_fields(entry, link)))
                                except (ValueError, TypeError, OverflowError):
                                    continue
                            warning = None if result else f"{source}: no usable feed entries."
                            if self.settings.live_cache_ttl_seconds:
                                self.feed_cache[url] = (monotonic() + self.settings.live_cache_ttl_seconds, list(result), warning)
                                while len(self.feed_cache) > 32:
                                    del self.feed_cache[next(iter(self.feed_cache))]
                            return result, warning
                    except (httpx.RequestError, httpx.HTTPStatusError, TimeoutError, ValueError):
                        if attempt == 0:
                            await asyncio.sleep(0.2)
                            continue
                        warning = f"{source}: feed unavailable; other feeds retained."
                        if self.settings.live_cache_ttl_seconds:
                            self.feed_cache[url] = (monotonic() + min(30, self.settings.live_cache_ttl_seconds), [], warning)
                            while len(self.feed_cache) > 32:
                                del self.feed_cache[next(iter(self.feed_cache))]
                        return [], warning

        async with httpx.AsyncClient(timeout=httpx.Timeout(8, connect=4), follow_redirects=True,
                                     max_redirects=3, transport=self.transport,
                                     headers={"User-Agent": "TheDailyMind/1.0 (local RSS reader)"}) as client:
            results = await asyncio.gather(*(fetch(name, url, client) for name, url in feeds))
        articles = [article for batch in zip_longest(*(rows for rows, _ in results)) for article in batch if article is not None]
        self.last_fetch_cached = any(reused)
        warnings = [warning for _, warning in results if warning]
        if self.last_fetch_cached:
            warnings.append('Some RSS responses reused from the short-lived feed cache; original retrieval times retained.')
        return articles, warnings
