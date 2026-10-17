from fastapi import APIRouter

from backend.controllers import AskController
from backend.schemas import AskRequest, AskResponse


def create_router(controller: AskController) -> APIRouter:
    router = APIRouter()

    @router.get("/health")
    async def health():
        return {"status": "ok", "readiness": controller.capabilities()}

    @router.get("/api/v1/capabilities")
    async def capabilities():
        return controller.capabilities()

    @router.post("/api/v1/ask", response_model=AskResponse)
    async def ask(request: AskRequest):
        return await controller.ask(request)

    return router
