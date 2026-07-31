"""
Background sync scheduler.

Runs a sync job every 30 minutes using APScheduler.
The sync job:
  1. Fetches registered Unstop events via Playwright.
  2. Compares with events stored in SQLite.
  3. Creates / updates / marks removed events on Google Calendar.
  4. Logs every sync run to the sync_logs table.
"""

import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session

from database import SessionLocal
from models import Event, SyncLog
from unstop import fetch_registered_events
from google_calendar import create_event, update_event, delete_event

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()


def _events_differ(db_event: Event, scraped: dict) -> bool:
    """Return True if any meaningful field has changed."""
    return (
        db_event.title != scraped.get("title")
        or db_event.date != scraped.get("date")
        or db_event.time != scraped.get("time")
        or db_event.deadline != scraped.get("deadline")
        or db_event.event_url != scraped.get("event_url")
    )


async def run_sync() -> dict:
    """
    Core sync logic.  Returns a summary dict.
    """
    db: Session = SessionLocal()
    added = updated = removed = 0
    error_msg = None

    try:
        logger.info("Starting Unstop sync…")
        scraped_events: list[dict] = await fetch_registered_events()
        scraped_ids = {e["unstop_id"] for e in scraped_events}

        # ── New & updated events ────────────────────────────────────────────
        for scraped in scraped_events:
            uid = scraped["unstop_id"]
            existing: Event | None = (
                db.query(Event).filter(Event.unstop_id == uid).first()
            )

            if existing is None:
                # Brand-new event → create in DB and Google Calendar
                cal_id = create_event(scraped)
                db.add(
                    Event(
                        unstop_id=uid,
                        title=scraped.get("title"),
                        date=scraped.get("date"),
                        time=scraped.get("time"),
                        deadline=scraped.get("deadline"),
                        event_url=scraped.get("event_url"),
                        calendar_event_id=cal_id,
                        is_active=True,
                    )
                )
                added += 1
                logger.debug("Added new event: %s", scraped["title"])

            elif _events_differ(existing, scraped):
                # Details changed → update Google Calendar
                if existing.calendar_event_id:
                    update_event(existing.calendar_event_id, scraped)

                existing.title = scraped.get("title")
                existing.date = scraped.get("date")
                existing.time = scraped.get("time")
                existing.deadline = scraped.get("deadline")
                existing.event_url = scraped.get("event_url")
                existing.updated_at = datetime.utcnow()
                updated += 1
                logger.debug("Updated event: %s", scraped["title"])

            else:
                # Re-activate if it was previously marked inactive
                if not existing.is_active:
                    existing.is_active = True

        # ── Removed events ──────────────────────────────────────────────────
        all_active: list[Event] = db.query(Event).filter(Event.is_active == True).all()
        for ev in all_active:
            if ev.unstop_id not in scraped_ids:
                ev.is_active = False
                ev.updated_at = datetime.utcnow()
                if ev.calendar_event_id:
                    delete_event(ev.calendar_event_id)
                removed += 1
                logger.debug("Removed event: %s", ev.title)

        # ── Persist sync log ─────────────────────────────────────────────────
        db.add(
            SyncLog(
                events_added=added,
                events_updated=updated,
                events_removed=removed,
                status="success",
            )
        )
        db.commit()

        summary = {
            "added": added,
            "updated": updated,
            "removed": removed,
            "status": "success",
            "synced_at": datetime.utcnow().isoformat(),
        }
        logger.info("Sync complete — added %d, updated %d, removed %d", added, updated, removed)
        return summary

    except Exception as exc:
        error_msg = str(exc)
        db.rollback()
        db.add(SyncLog(status="error", error_message=error_msg))
        db.commit()
        logger.exception("Sync failed: %s", error_msg)
        return {"status": "error", "error": error_msg}
    finally:
        db.close()


def start_scheduler() -> None:
    """Register and start the background scheduler."""
    scheduler.add_job(
        run_sync,
        trigger=IntervalTrigger(minutes=30),
        id="unstop_sync",
        name="Unstop → Google Calendar sync",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler started — syncing every 30 minutes.")


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler stopped.")
