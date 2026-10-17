import asyncio
import sqlite3

from fastapi import APIRouter, Header, HTTPException, Response

from backend.news.models import ProfileInput, GenerateInput, InteractionInput, TOPICS, reader_id
from backend.news.pdf import render_pdf, edition_html
from backend.news.service import NoLiveNews


def create_news_router(paper):
    router = APIRouter(prefix="/api")
    pdf_lock = asyncio.Semaphore(1)

    def identify(value):
        try:
            return reader_id(value or "")
        except ValueError:
            raise HTTPException(400, "Provide your anonymous reader ID in X-Reader-ID.")

    @router.get("/topics")
    async def topics():
        return [{"id": key, "label": info["label"]} for key, info in TOPICS.items()]

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

    def get_edition(edition_id, header):
        try:
            return paper.store.edition(identify(header), edition_id)
        except KeyError:
            raise HTTPException(404, "Saved edition not found for this reader.")

    @router.get("/editions/{edition_id}")
    async def edition(edition_id: str, x_reader_id: str | None = Header(default=None)):
        value = get_edition(edition_id, x_reader_id)
        actions = paper.store.events(identify(x_reader_id))
        return {**value, "reader_actions": [{"article_id": event["article_id"], "action": event["action"]} for event in actions]}

    @router.get("/editions/{edition_id}/print")
    async def print_view(edition_id: str, x_reader_id: str | None = Header(default=None)):
        return Response(edition_html(get_edition(edition_id, x_reader_id)), media_type="text/html")

    @router.get("/editions/{edition_id}/pdf")
    async def pdf(edition_id: str, x_reader_id: str | None = Header(default=None)):
        value = get_edition(edition_id, x_reader_id)
        try:
            async with pdf_lock:
                content = await render_pdf(value)
            return Response(content, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="daily-mind-{value["local_date"]}-v{value["version"]}.pdf"'})
        except Exception:
            raise HTTPException(503, "PDF renderer unavailable. Run python -m playwright install chromium locally, then retry.")

    @router.post("/articles/{article_id}/interactions")
    async def interact(article_id: str, body: InteractionInput, x_reader_id: str | None = Header(default=None)):
        profile_id = identify(x_reader_id)
        try:
            changed = paper.store.interact(profile_id, article_id, body.action)
        except KeyError:
            raise HTTPException(404, "Article not found in your saved editions.")
        return {"recorded": changed, "weights": paper.dna(profile_id)}

    return router
