from fastapi import FastAPI

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


def create_app(settings: Settings | None = None, orchestrator: Orchestrator | None = None, newspaper=None) -> FastAPI:
    settings = settings or Settings()
    application = FastAPI(title="The Daily Mind", version="1.0.0")
    application.include_router(create_router(AskController(settings, orchestrator or Orchestrator(settings))))
    application.include_router(create_news_router(newspaper or Newspaper(settings)))
    @application.exception_handler(sqlite3.Error)
    async def storage_error(request, error):
        return JSONResponse(status_code=503, content={"detail": "Local storage is temporarily unavailable. Please retry."})
    if (ROOT / "frontend" / "dist").is_dir():
        application.mount("/", StaticFiles(directory=ROOT / "frontend" / "dist", html=True), name="reader")
    return application


app = create_app()
