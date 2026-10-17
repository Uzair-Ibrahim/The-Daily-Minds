import asyncio
from time import monotonic, time
from uuid import uuid4
from zoneinfo import ZoneInfo

from backend.news.discovery import NewsDiscovery
from backend.news.discovery import topic_matches
from backend.news.models import ProfileInput
from backend.news.ranking import interest_dna, rank_articles
from backend.news.store import Store
from backend.services.provenance import utc_now
from backend.news.memory import build_takeaways
from backend.news.story_graph import StoryGraph


class NoLiveNews(Exception):
    def __init__(self, warnings):
        self.warnings = warnings


class Newspaper:
    def __init__(self, settings, store=None, discovery=None):
        self.settings = settings
        if settings.database_backend == "postgres" and not settings.database_url.get_secret_value():
            raise ValueError("DATABASE_URL is required for Postgres; refusing temporary SQLite fallback.")
        self.store = store or Store(settings.database_path,
            database_url=settings.database_url.get_secret_value() if settings.database_backend == "postgres" else "",
            schema=settings.database_schema)
        self.discovery = discovery or NewsDiscovery(settings)
        self.stories = StoryGraph(self.store, settings)
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

    async def generate(self, profile_id, regenerate=False, targeted=False, now=None, trigger='on_demand'):
        async with self.locks.setdefault(profile_id, asyncio.Lock()):
            profile = self.profile(profile_id)
            now = now or utc_now()
            if now.tzinfo is None or now.utcoffset() is None:
                raise ValueError('Generation time must be timezone-aware')
            local_date = now.astimezone(ZoneInfo(profile["timezone"])).date().isoformat()
            previous = self.store.latest(profile_id, local_date)
            if previous and not regenerate:
                return previous
            owner = str(uuid4())
            wait_until = monotonic() + 65
            while True:
                state = self.store.claim_generation(profile_id, local_date, owner, time())
                if state == 'claimed':
                    break
                if state == 'cooldown' or monotonic() >= wait_until:
                    raise NoLiveNews(['Daily generation is busy or waiting to retry after a retrieval failure. Saved editions remain available.'])
                await asyncio.sleep(0.1)
                previous = self.store.latest(profile_id, local_date)
                if previous and not regenerate:
                    return previous
            try:
                # Recheck after the durable claim: another worker may have just completed.
                previous = self.store.latest(profile_id, local_date)
                if previous and not regenerate:
                    return previous
                async with asyncio.timeout(65):
                    return await self._build(profile_id, profile, local_date, regenerate, targeted, now, trigger)
            except asyncio.CancelledError:
                raise
            except Exception:
                self.store.finish_generation(profile_id, local_date, owner,
                                             time() + self.settings.daily_generation_retry_seconds)
                raise
            finally:
                self.store.finish_generation(profile_id, local_date, owner)

    async def _build(self, profile_id, profile, local_date, regenerate, targeted, now, trigger):
        query = " ".join(profile["keywords"][:3])
        try:
            async with asyncio.timeout(55):
                result = await self.discovery.retrieve(query, targeted)
        except (TimeoutError, OSError):
            result = {'articles': [], 'cached': False, 'warnings': ['RSS retrieval unavailable or timed out.']}
        offline = False
        if not result['articles'] and not regenerate:
            cached = self.store.cached_articles(now, self.settings.offline_news_max_age_days)
            if cached:
                offline = True
                result = {**result, 'articles': cached, 'cached': True,
                          'warnings': result['warnings'] + ['Offline fallback: previously retrieved RSS content, not fresh news. Original publication and retrieval times retained.']}
        if not result["articles"]:
            raise NoLiveNews(result["warnings"])
        self.store.articles(result["articles"])
        events = self.store.events(profile_id)
        cutoff = self.stories.cutoff(profile_id)
        story_ids = {}
        try:
            story_ids = await asyncio.to_thread(self.stories.ingest, profile_id, result["articles"])
        except Exception:
            result["warnings"].append("Story memory unavailable; standard newspaper ranking preserved.")
        ranked = rank_articles(result["articles"], profile, events, now,
                               story_ids, self.stories.followed(profile_id), self.stories.seen_articles(profile_id))
        selected = ranked[:profile["edition_length"]]
        if profile["depth"] == "brief":
            selected = [{**item, "description": item["description"][:180]} for item in selected]
        snapshot = {
            "title": "The Daily Mind", "profile_id": profile_id, "local_date": local_date,
            "timezone": profile["timezone"], "generated_at": now.isoformat(),
            "status": "offline_fallback" if offline else "cached_sources" if result["cached"] else "retrieved_live",
            "generation_trigger": trigger,
            "source_retrieved_from": min(item.retrieved_at for item in result['articles']).isoformat(),
            "source_retrieved_to": max(item.retrieved_at for item in result['articles']).isoformat(),
            "mode": "attributed_excerpts", "articles": selected, "article_count": len(selected),
            "source_count": len({article["source"] for article in selected}),
            "profile_snapshot": profile, "interest_dna": interest_dna(profile, events),
            "warnings": result["warnings"] + ["Attributed feed descriptions/excerpts, not LLM-written reporting. Retrieval time does not prove publication recency."],
            "takeaways": build_takeaways(selected), "takeaway_method": "extractive_sentences_v1",
        }
        try:
            snapshot["continuing_stories"] = self.stories.snapshot(profile_id, [story_ids[a["id"]] for a in selected if a["id"] in story_ids])
            snapshot["story_updates"] = self.stories.updates(profile_id, cutoff).model_dump(mode="json")
            snapshot["story_method"] = self.stories.embeddings.status
        except Exception:
            snapshot["warnings"].append("Story timeline unavailable for this edition.")
        return self.store.save_edition(profile_id, local_date, snapshot, regenerate)
