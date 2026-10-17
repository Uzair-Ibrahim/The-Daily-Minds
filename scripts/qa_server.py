"""Isolated localhost QA server; shutdown route exists only in this harness."""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uvicorn
from fastapi import BackgroundTasks
from backend.main import create_app

app = create_app()
config = uvicorn.Config(app, host="127.0.0.1", port=int(os.environ["QA_PORT"]), log_level="warning")
server = uvicorn.Server(config)


@app.get("/__qa/status")
async def status():
    return {"run_id": os.environ["QA_RUN_ID"]}


@app.post("/__qa/stop")
async def stop(background: BackgroundTasks):
    background.add_task(setattr, server, "should_exit", True)
    return {"stopping": True}


if __name__ == "__main__":
    qa_routes = [route for route in app.router.routes if getattr(route, "path", "").startswith("/__qa/")]
    for route in qa_routes:
        app.router.routes.remove(route)
        app.router.routes.insert(0, route)
    server.run(sockets=[config.bind_socket()])
