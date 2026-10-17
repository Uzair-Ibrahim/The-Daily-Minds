import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from backend.news.discovery import NewsDiscovery
from backend.news.discovery import topic_matches
from backend.news.models import ProfileInput
from backend.news.ranking import interest_dna, rank_articles
from backend.news.store import Store
from backend.services.provenance import utc_now
from backend.news.memory import build_takeaways


class NoLiveNews(Exception):
    def __init__(self, warnings):
        self.warnings = warnings


class Newspaper:
    def __init__(self, settings, store=None, discovery=None):
        self.settings = settings
        self.store = store or Store(settings.database_path)
        self.discovery = discovery or NewsDiscovery(settings)
        self.locks = {}

    def profile(self, profile_id):
        return self.store.profile(profile_id)

    def dna(self, profile_id):
        return interest_dna(self.profile(profile_id), self.store.events(profile_id))

    async def discover(self, query, limit=12):
        result = await self.discovery.retrieve(query)
        self.store.articles(result["articles"])
        profile = ProfileInput(topics={topic: 1 for topic in topic_matches(query)}, keywords=[query[:60]] if query else []).model_dump()
        ranked = rank_articles(result["articles"], profile, [])[:limit]
        return {"status": result["status"], "articles": ranked, "warnings": result["warnings"], "cached": result["cached"]}

    async def generate(self, profile_id, regenerate=False, targeted=False, now=None):
        async with self.locks.setdefault(profile_id, asyncio.Lock()):
            profile = self.profile(profile_id)
            now = now or utc_now()
            local_date = now.astimezone(ZoneInfo(profile["timezone"])).date().isoformat()
            previous = self.store.latest(profile_id, local_date)
            if previous and not regenerate:
                return previous
            query = " ".join(profile["keywords"][:3])
            result = await self.discovery.retrieve(query, targeted)
            if not result["articles"]:
                raise NoLiveNews(result["warnings"])
            self.store.articles(result["articles"])
            events = self.store.events(profile_id)
            ranked = rank_articles(result["articles"], profile, events, now)
            selected = ranked[:profile["edition_length"]]
            if profile["depth"] == "brief":
                selected = [{**item, "description": item["description"][:180]} for item in selected]
            snapshot = {
                "title": "The Daily Mind", "profile_id": profile_id, "local_date": local_date,
                "timezone": profile["timezone"], "generated_at": now.isoformat(),
                "status": "cached_sources" if result["cached"] else "retrieved_live",
                "mode": "attributed_excerpts", "articles": selected, "article_count": len(selected),
                "source_count": len({article["source"] for article in selected}),
                "profile_snapshot": profile, "interest_dna": interest_dna(profile, events),
                "warnings": result["warnings"] + ["Attributed feed descriptions/excerpts, not LLM-written reporting. Retrieval time does not prove publication recency."],
                "takeaways": build_takeaways(selected), "takeaway_method": "extractive_sentences_v1",
            }
            return self.store.save_edition(profile_id, local_date, snapshot, regenerate)
