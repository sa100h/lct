from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException, Query, Request

from app.event_store import EventArchiveStore
from app.models import EventPage, FeedStatus
from app.settings import Settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    store = EventArchiveStore(Settings.from_environment())
    await asyncio.to_thread(store.prepare)
    app.state.event_store = store
    yield


app = FastAPI(
    title="LCT test event feeder",
    description="Replays the organizer's event journal against the current wall clock.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/status", response_model=FeedStatus)
def status(request: Request) -> FeedStatus:
    return _store(request).get_status()


@app.get("/api/v1/events", response_model=EventPage)
def events(
    request: Request,
    from_at: datetime = Query(alias="from"),
    to_at: datetime = Query(alias="to"),
    limit: int = Query(default=1000, ge=1, le=5000),
    cursor: str | None = Query(default=None),
) -> EventPage:
    try:
        return _store(request).get_events(from_at, to_at, limit, cursor)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _store(request: Request) -> EventArchiveStore:
    return request.app.state.event_store

