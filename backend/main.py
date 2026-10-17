from fastapi import FastAPI

from backend.auth import ReaderAuth
from backend.auth_routes import create_auth_router
from backend.config import Settings
from backend.controllers import AskController
from backend.orchestrator import Orchestrator
from backend.routes import create_router
from backend.news.routes import create_news_router
from backend.news.service import Newspaper
from fastapi.staticfiles import StaticFiles
from backend.config import ROOT
import sqlite3
from fastapi.responses import JSONResponse
import asyncio
from contextlib import asynccontextmanager, suppress
from backend.news.scheduler import DailyScheduler


def create_app(settings: Settings | None = None, orchestrator: Orchestrator | None = None, newspaper=None, auth_service=None) -> FastAPI:
    settings = settings or Settings()
    paper = newspaper or Newspaper(settings)

    @asynccontextmanager
    async def lifespan(app):
        task = asyncio.create_task(DailyScheduler(paper).run()) if settings.daily_generation_enabled else None
        try:
            yield
        finally:
            if task:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

    application = FastAPI(title="The Daily Mind", version="1.0.0", lifespan=lifespan)
    application.state.newspaper = paper
    auth = auth_service or ReaderAuth(settings, paper.store)
    application.state.reader_auth = auth
    application.include_router(create_auth_router(auth))

    @application.middleware("http")
    async def private_responses(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
            response.headers["Vary"] = "Authorization, X-Reader-ID"
        return response

    application.include_router(create_router(AskController(settings, orchestrator or Orchestrator(settings))))
    application.include_router(create_news_router(paper, auth))
    @application.exception_handler(sqlite3.Error)
    async def storage_error(request, error):
        return JSONResponse(status_code=503, content={"detail": "Local storage is temporarily unavailable. Please retry."})
    if (ROOT / "frontend" / "dist").is_dir():
        application.mount("/", StaticFiles(directory=ROOT / "frontend" / "dist", html=True), name="reader")
    return application


app = create_app()
