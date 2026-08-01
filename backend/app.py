"""
Unstop Calendar Sync — FastAPI backend.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from database import init_db, get_db
from models import Event, SyncLog
from scheduler import run_sync, start_scheduler, stop_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="Unstop Calendar Sync", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/status")
def get_status(db: Session = Depends(get_db)):
    last_log = db.query(SyncLog).order_by(SyncLog.synced_at.desc()).first()
    active_count = db.query(Event).filter(Event.is_active == True).count()
    return {
        "active_events": active_count,
        "last_sync": {
            "synced_at": last_log.synced_at.isoformat() if last_log else None,
            "status": last_log.status if last_log else None,
            "added": last_log.events_added if last_log else 0,
            "updated": last_log.events_updated if last_log else 0,
            "removed": last_log.events_removed if last_log else 0,
        },
    }


@app.get("/api/events")
def list_events(db: Session = Depends(get_db)):
    events = db.query(Event).filter(Event.is_active == True).order_by(Event.date.asc()).all()
    return [e.to_dict() for e in events]


@app.get("/api/events/{event_id}")
def get_event(event_id: int, db: Session = Depends(get_db)):
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event.to_dict()


@app.post("/api/sync")
async def trigger_sync():
    logger.info("Manual sync triggered.")
    result = await run_sync()
    return result


@app.get("/api/logs")
def get_logs(limit: int = 20, db: Session = Depends(get_db)):
    logs = db.query(SyncLog).order_by(SyncLog.synced_at.desc()).limit(limit).all()
    return [
        {
            "id": log.id,
            "synced_at": log.synced_at.isoformat(),
            "status": log.status,
            "added": log.events_added,
            "updated": log.events_updated,
            "removed": log.events_removed,
            "error_message": log.error_message,
        }
        for log in logs
    ]


@app.get("/health")
def health():
    return {"status": "ok"}
