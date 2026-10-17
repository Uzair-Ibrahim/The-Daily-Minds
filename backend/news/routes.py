import asyncio
import sqlite3
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, Response

from backend.news.models import ProfileInput, GenerateInput, InteractionInput, TOPICS, reader_id
from backend.news.pdf import render_pdf, edition_html
from backend.news.service import NoLiveNews
from backend.news.images import ImageDelivery
from backend.news.image_resolver import ArticleImageResolver
from backend.news.editorial import primary_topic
from backend.news.story_graph import StoryDetail, StoryUpdates, FollowInput


def create_news_router(paper):
    router = APIRouter(prefix="/api")
    pdf_lock = asyncio.Semaphore(1)
    images = ImageDelivery()
    images.cache_dir = Path(paper.store.path).parent / 'publisher-images'
    images.cache_dir.mkdir(parents=True, exist_ok=True)
    resolver = ArticleImageResolver(paper.store, images)
    paper.image_delivery, paper.image_resolver = images, resolver

    def identify(value):
        try:
            return reader_id(value or "")
        except ValueError:
            raise HTTPException(400, "Provide your anonymous reader ID in X-Reader-ID.")

    @router.get("/topics")
    async def topics():
        return [{"id": key, "label": info["label"]} for key, info in TOPICS.items()]

    @router.get("/stories/updates", response_model=StoryUpdates)
    async def story_updates(x_reader_id: str | None = Header(default=None)):
        reader = identify(x_reader_id)
        return paper.stories.updates(reader, paper.stories.cutoff(reader))

    @router.get("/stories/{story_id}", response_model=StoryDetail)
    async def story_detail(story_id: str, x_reader_id: str | None = Header(default=None)):
        try:
            return paper.stories.detail(identify(x_reader_id), reader_id(story_id))
        except (KeyError, ValueError):
            raise HTTPException(404, "Story not found for this reader.")

    @router.put("/stories/{story_id}/follow", response_model=StoryDetail)
    async def follow_story(story_id: str, body: FollowInput, x_reader_id: str | None = Header(default=None)):
        try:
            return paper.stories.follow(identify(x_reader_id), reader_id(story_id), body.followed)
        except (KeyError, ValueError):
            raise HTTPException(404, "Story not found for this reader.")

    @router.get("/profile")
    async def profile(x_reader_id: str | None = Header(default=None)):
        return paper.profile(identify(x_reader_id))

    @router.put("/profile")
    async def update_profile(body: ProfileInput, x_reader_id: str | None = Header(default=None)):
        return paper.store.save_profile(identify(x_reader_id), body)

    @router.get("/profile/interests")
    async def interests(x_reader_id: str | None = Header(default=None)):
        return {"weights": paper.dna(identify(x_reader_id)), "method": "Explicit interests + bounded feedback. Heuristic ranking, not a confidence estimate."}

    @router.post("/profile/reset-feedback")
    async def reset(x_reader_id: str | None = Header(default=None)):
        profile_id = identify(x_reader_id)
        paper.store.reset_feedback(profile_id)
        return {"weights": paper.dna(profile_id), "message": "Feedback reset. Saved editions remain unchanged."}

    @router.post("/editions/generate")
    async def generate(body: GenerateInput, x_reader_id: str | None = Header(default=None)):
        try:
            async with asyncio.timeout(75):
                return await paper.generate(identify(x_reader_id), body.regenerate, body.targeted_search)
        except NoLiveNews as error:
            raise HTTPException(503, {"code": "no_live_data", "message": "No live news is available. Try again or open a saved edition.", "warnings": error.warnings})
        except TimeoutError:
            raise HTTPException(503, "News retrieval timed out. Saved editions are still available.")
        except sqlite3.Error:
            raise HTTPException(503, "Local storage is temporarily busy. Try again shortly.")

    @router.get("/editions")
    async def archive(x_reader_id: str | None = Header(default=None)):
        return paper.store.archive(identify(x_reader_id))

    @router.get('/reading-list')
    async def reading_list(x_reader_id: str | None = Header(default=None)):
        return paper.store.reading_list(identify(x_reader_id))

    def get_edition(edition_id, header):
        try:
            return paper.store.edition(identify(header), edition_id)
        except KeyError:
            raise HTTPException(404, "Saved edition not found for this reader.")

    @router.get("/editions/{edition_id}")
    async def edition(edition_id: str, x_reader_id: str | None = Header(default=None)):
        value = get_edition(edition_id, x_reader_id)
        actions = paper.store.events(identify(x_reader_id))
        return {**value, 'article_sections': {item['id']: primary_topic(item) for item in value['articles']},
                'article_engagement': {item['id']: paper.store.engagement(identify(x_reader_id), item['id']) for item in value['articles']},
                "reader_actions": [{"article_id": event["article_id"], "action": event["action"]} for event in actions]}

    @router.get("/editions/{edition_id}/print")
    async def print_view(edition_id: str, x_reader_id: str | None = Header(default=None)):
        return Response(edition_html(get_edition(edition_id, x_reader_id)), media_type="text/html")

    @router.get("/editions/{edition_id}/pdf")
    async def pdf(edition_id: str, x_reader_id: str | None = Header(default=None)):
        value = get_edition(edition_id, x_reader_id)
        try:
            async with pdf_lock:
                if value['articles']:
                    lead = value['articles'][0]
                    metadata = await resolver.resolve(lead)
                    value = {**value, 'articles': [{**lead, **metadata}, *value['articles'][1:]]}
                content = await render_pdf(value, image_loader=images)
            return Response(content, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="daily-mind-{value["local_date"]}-v{value["version"]}.pdf"'})
        except Exception:
            raise HTTPException(503, "PDF renderer unavailable. Run python -m playwright install chromium locally, then retry.")

    @router.get('/editions/{edition_id}/articles/{article_id}/image')
    async def article_image(edition_id: str, article_id: str, x_reader_id: str | None = Header(default=None)):
        value = get_edition(edition_id, x_reader_id)
        article = next((item for item in value['articles'] if item['id'] == article_id), None)
        if not article:
            raise HTTPException(404, 'Article not found in this edition.')
        metadata = await resolver.resolve(article)
        content = resolver.ready_images.get(metadata.get('image_url')) or await images.get(metadata.get('image_url'))
        if not content:
            return Response(status_code=204, headers={'Cache-Control': 'private, max-age=60', 'Vary': 'X-Reader-ID'})
        return Response(content, media_type='image/jpeg', headers={
            'Cache-Control': 'private, max-age=86400', 'Vary': 'X-Reader-ID', 'X-Content-Type-Options': 'nosniff'})

    @router.get('/editions/{edition_id}/articles/{article_id}/image/metadata')
    async def image_metadata(edition_id: str, article_id: str, x_reader_id: str | None = Header(default=None)):
        value = get_edition(edition_id, x_reader_id)
        article = next((item for item in value['articles'] if item['id'] == article_id), None)
        if not article:
            raise HTTPException(404, 'Article not found in this edition.')
        return await resolver.resolve(article)

    @router.post("/articles/{article_id}/interactions")
    async def interact(article_id: str, body: InteractionInput, x_reader_id: str | None = Header(default=None)):
        profile_id = identify(x_reader_id)
        try:
            changed = paper.store.interact(profile_id, article_id, body.action, body.active)
        except KeyError:
            raise HTTPException(404, "Article not found in your saved editions.")
        except ValueError:
            raise HTTPException(422, 'Only likes and saves can be removed.')
        return {"recorded": changed, "weights": paper.dna(profile_id),
                'engagement': paper.store.engagement(profile_id, article_id),
                'active': body.active}

    return router
