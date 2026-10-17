"""Publisher metadata extraction and bounded delivery from known feed image CDNs."""
import asyncio
from collections import OrderedDict
from html.parser import HTMLParser
import io
import ipaddress
import re
import socket
import hashlib
import json
from pathlib import Path
from time import time
from uuid import uuid4
from time import monotonic
from urllib.parse import parse_qs, urljoin, urlsplit

import httpx
from backend.news.safe_network import PublicTransport
from PIL import Image, ImageOps, UnidentifiedImageError

IMAGE_HOSTS = {'ichef.bbci.co.uk', 'i.dawn.com', 'i.guim.co.uk'}


def image_url(value, base=''):
    try:
        value = str(value or '').strip()
        if not value or len(value) > 4096:
            return None
        value = urljoin(base, value)
        parts = urlsplit(value)
        if (parts.scheme not in {'http', 'https'} or not parts.hostname
            or parts.username or parts.password or parts.port not in {None, 80, 443}
            or parts.hostname.lower() in {'localhost', 'localhost.localdomain'}):
            return None
        try:
            if not ipaddress.ip_address(parts.hostname).is_global:
                return None
        except ValueError:
            pass
        if re.search(r'(?i)(?:tracking|tracker|pixel|spacer|sprite|favicon|logo|1x1|beacon|placeholder|no[-_]?image|social[-_]?badge)(?:[._/\-?=]|$)|\.(?:svg|gif|ico)(?:\?|$)', parts.path + '?' + parts.query):
            return None
        query = parse_qs(parts.query)
        for key, minimum in [('width', 160), ('w', 160), ('height', 90), ('h', 90)]:
            size = dimension(query.get(key, [''])[0])
            if size and size < minimum:
                return None
        return value
    except (ValueError, TypeError):
        return None


def dimension(value):
    try:
        return int(float(str(value).removesuffix('px')))
    except (ValueError, TypeError, OverflowError):
        return 0


def best(candidates, base):
    valid = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        if item.get('medium') and item['medium'] != 'image':
            continue
        if item.get('type') and not item['type'].startswith('image/'):
            continue
        url = image_url(item.get('url') or item.get('href') or item.get('src'), base)
        width, height = dimension(item.get('width')), dimension(item.get('height'))
        if not url or width and width < 160 or height and height < 90:
            continue
        valid.append((width * (height or width), url))
    return max(valid, key=lambda item: item[0])[1] if valid else None


class ImageTags(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.items = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == 'img' and len(self.items) < 30:
            item = dict(attrs)
            item['src'] = item.get('data-src') or item.get('src')
            self.items.append(item)


def extract_image(entry, base):
    credits = entry.get('media_credit') or []
    credit = next((re.sub(r'<[^>]+>', '', str(item.get('content', '')))[:160]
                   for item in credits if isinstance(item, dict) and item.get('content')), None)
    groups = [('media_content', entry.get('media_content') or []),
              ('media_thumbnail', entry.get('media_thumbnail') or []),
              ('enclosure', [item for item in entry.get('enclosures', [])
                             if isinstance(item, dict) and item.get('type', '').startswith('image/')])]
    for kind, candidates in groups:
        url = best(candidates, base)
        if url:
            return {'image_url': url, 'image_origin': kind, 'image_credit': credit}
    fallback = entry.get('image')
    url = best([fallback], base) if isinstance(fallback, dict) else image_url(fallback, base) if isinstance(fallback, str) else None
    if url:
        return {'image_url': url, 'image_origin': 'image', 'image_credit': credit}
    parser = ImageTags()
    try:
        parser.feed(str(entry.get('summary', ''))[:100_000])
        for item in entry.get('content', [])[:5]:
            parser.feed(str(item.get('value', ''))[:100_000])
    except (ValueError, TypeError):
        pass
    for item in parser.items:
        url = best([item], base)
        if url:
            return {'image_url': url, 'image_origin': 'html_img', 'image_credit': credit}
    return {'image_url': None, 'image_origin': None, 'image_credit': None}


def prepare_image(content):
    try:
        with Image.open(io.BytesIO(content)) as source:
            width, height = source.size
            if (source.format not in {'JPEG', 'PNG', 'WEBP'} or width < 160 or height < 90
                or width * height > 20_000_000 or not 0.4 <= width / height <= 4):
                return None
            source.verify()
        with Image.open(io.BytesIO(content)) as source:
            picture = ImageOps.exif_transpose(source).convert('RGB')
            picture.thumbnail((1280, 1000))
            output = io.BytesIO()
            picture.save(output, format='JPEG', quality=82)
            result = output.getvalue()
            return result if len(result) <= 1_500_000 else None
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        return None


async def public_host(host):
    addresses = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    return bool(addresses) and all(ipaddress.ip_address(row[4][0]).is_global for row in addresses)


class ImageDelivery:
    def __init__(self, transport=None, resolver=public_host, cache_dir=None):
        self.transport, self.resolver = transport, resolver
        self.cache, self.inflight = OrderedDict(), {}
        self.slots = asyncio.Semaphore(3)
        self.cache_dir = Path(cache_dir) if cache_dir else None
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.requests = 0

    async def get(self, url):
        url = image_url(url)
        if not url or urlsplit(url).hostname not in IMAGE_HOSTS:
            return None
        if self.cache_dir and url not in self.cache:
            try:
                key = hashlib.sha256(url.encode()).hexdigest()
                record = json.loads((self.cache_dir / (key + '.json')).read_text())
                if record['expires_at'] > time():
                    content = (self.cache_dir / (key + '.jpg')).read_bytes() if record['available'] else None
                    if content is None or len(content) <= 1_500_000:
                        self.cache[url] = (monotonic() + record['expires_at'] - time(), content)
            except (OSError, ValueError, KeyError):
                pass
        cached = self.cache.get(url)
        if cached and cached[0] > monotonic():
            self.cache.move_to_end(url)
            return cached[1]
        task = self.inflight.get(url)
        if task is None:
            if len(self.inflight) >= 16:
                return None
            task = asyncio.create_task(self._fetch(url))
            self.inflight[url] = task
            task.add_done_callback(lambda done: self.inflight.pop(url, None))
        return await asyncio.shield(task)

    async def _fetch(self, url):
        result = None
        try:
            async with asyncio.timeout(6):
                async with self.slots:
                    if not await self.resolver(urlsplit(url).hostname):
                        return None
                    async with httpx.AsyncClient(timeout=httpx.Timeout(4, connect=2), transport=self.transport or PublicTransport(),
                                                 follow_redirects=False, trust_env=False) as client:
                        self.requests += 1
                        async with client.stream('GET', url, headers={'User-Agent': 'TheDailyMind/1.0 (RSS image reader)',
                                                                      'Accept': 'image/jpeg,image/png,image/webp'}) as response:
                            response.raise_for_status()
                            if response.headers.get('content-type', '').split(';')[0] not in {'image/jpeg', 'image/png', 'image/webp'}:
                                return None
                            content = bytearray()
                            async for chunk in response.aiter_bytes():
                                content.extend(chunk)
                                if len(content) > 3_000_000:
                                    return None
                        result = await asyncio.to_thread(prepare_image, bytes(content))
        except Exception:
            # Images are optional; no upstream diagnostics are exposed or logged.
            pass
        finally:
            self.cache[url] = (monotonic() + (86400 if result else 300), result)
            self.cache.move_to_end(url)
            while len(self.cache) > 32:
                self.cache.popitem(last=False)
            if self.cache_dir:
                try:
                    key = hashlib.sha256(url.encode()).hexdigest()
                    record_path = self.cache_dir / (key + '.json')
                    if record_path.exists() or len(list(self.cache_dir.glob('*.json'))) < 64:
                        if result:
                            temp = self.cache_dir / (uuid4().hex + '.tmp')
                            temp.write_bytes(result)
                            temp.replace(self.cache_dir / (key + '.jpg'))
                        temp = self.cache_dir / (uuid4().hex + '.tmp')
                        temp.write_text(json.dumps({'expires_at': time() + (86400 if result else 300), 'available': bool(result)}))
                        temp.replace(record_path)
                except OSError:
                    pass
        return result
