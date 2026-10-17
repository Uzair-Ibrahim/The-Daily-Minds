"""Local startup catch-up and daily generation; no external scheduler or paid API."""
import asyncio
import logging

from backend.news.service import NoLiveNews

logger = logging.getLogger(__name__)


class DailyScheduler:
    def __init__(self, newspaper):
        self.paper = newspaper

    async def tick(self, now=None):
        counts = {'ready': 0, 'unavailable': 0}
        for reader in self.paper.store.onboarded_readers():
            try:
                await self.paper.generate(reader, now=now, trigger='automatic')
                counts['ready'] += 1
            except (NoLiveNews, TimeoutError):
                counts['unavailable'] += 1
            except Exception:
                # Do not log reader IDs, source payloads or secret-bearing exceptions.
                logger.warning('Daily generation failed for a reader; retrying on a later tick.')
                counts['unavailable'] += 1
        return counts

    async def run(self):
        while True:
            try:
                await self.tick()
            except Exception:
                logger.warning('Daily scheduler storage unavailable; retrying on a later tick.')
            await asyncio.sleep(self.paper.settings.daily_generation_interval_seconds)
