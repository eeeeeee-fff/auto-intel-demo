from __future__ import annotations

from fastapi import FastAPI

from app.api import router
from app.config import get_settings
from app.db import SessionLocal, init_db
from app.scheduler import start_scheduler, stop_scheduler
from app.services.ingestion import bootstrap_sources


settings = get_settings()
app = FastAPI(title=settings.app_name)
app.include_router(router)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    with SessionLocal() as session:
        bootstrap_sources(session)
    start_scheduler()


@app.on_event("shutdown")
def on_shutdown() -> None:
    stop_scheduler()
