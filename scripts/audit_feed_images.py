"""Read current public feeds and record observed image metadata, without paid APIs."""
import asyncio
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import feedparser
import httpx
from backend.news.discovery import FEEDS
from backend.services.provenance import utc_now


async def audit_feeds():
    feeds = FEEDS + [('Google News RSS', 'https://news.google.com/rss/search?q=AI&hl=en&gl=PK&ceid=PK:en')]
    slots = asyncio.Semaphore(3)
    async with httpx.AsyncClient(timeout=15, follow_redirects=True, max_redirects=3) as client:
        async def inspect(name, url):
            row = {'feed': name, 'url': url, 'audited_at_utc': utc_now().isoformat()}
            try:
                async with slots, asyncio.timeout(20):
                    content = bytearray()
                    async with client.stream('GET', url) as response:
                        response.raise_for_status()
                        async for chunk in response.aiter_bytes():
                            content.extend(chunk)
                            if len(content) > 1_500_000:
                                raise ValueError('Oversize feed')
                    feed = await asyncio.to_thread(feedparser.parse, bytes(content))
                counts = {key: 0 for key in ['media_content', 'media_thumbnail', 'enclosures', 'image', 'html_img']}
                for entry in feed.entries:
                    for key in list(counts)[:-1]:
                        if entry.get(key):
                            counts[key] += 1
                    html = entry.get('summary', '') + ' '.join(item.get('value', '') for item in entry.get('content', []))
                    if '<img' in html.lower():
                        counts['html_img'] += 1
                row.update(entries=len(feed.entries), fields=counts, samples=[
                    {key: entry.get(key) for key in ['link', 'media_content', 'media_thumbnail', 'enclosures',
                                                    'image', 'media_credit', 'summary', 'content']}
                    for entry in feed.entries[:2]])
            except (httpx.HTTPError, TimeoutError, OSError, ValueError) as error:
                row['error'] = type(error).__name__
            return row
        rows = await asyncio.gather(*(inspect(name, url) for name, url in feeds))
    (ROOT / 'artifacts').mkdir(exist_ok=True)
    (ROOT / 'artifacts' / 'image-feed-audit.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')
    return rows


async def main():
    rows = await audit_feeds()
    print(json.dumps([{key: value for key, value in row.items() if key != 'samples'} for row in rows], indent=2))


if __name__ == '__main__':
    asyncio.run(main())
