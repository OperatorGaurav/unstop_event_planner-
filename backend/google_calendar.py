"""
Google Calendar API helper.
Sets a reminder at exactly 6:00 PM the day before each event.
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Optional
import re

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "primary")
SCOPES = ["https://www.googleapis.com/auth/calendar"]
IST_OFFSET = timedelta(hours=5, minutes=30)


def _get_credentials() -> Credentials:
    creds = Credentials(
        token=None,
        refresh_token=os.environ["GOOGLE_REFRESH_TOKEN"],
        client_id=os.environ["GOOGLE_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=SCOPES,
    )
    creds.refresh(Request())
    return creds


def _get_service():
    return build("calendar", "v3", credentials=_get_credentials())


def _parse_date(date_str: str) -> Optional[datetime]:
    """Try to parse various date formats from Unstop."""
    if not date_str:
        return None

    # Clean up the string
    date_str = re.sub(r'\s+', ' ', date_str).strip()

    formats = [
        "%d %b %Y",        # 14 Aug 2025
        "%d %B %Y",        # 14 August 2025
        "%b %d, %Y",       # Aug 14, 2025
        "%B %d, %Y",       # August 14, 2025
        "%d %b %Y %I:%M %p",  # 14 Aug 2025 10:00 AM
        "%Y-%m-%d",        # 2025-08-14
        "%d/%m/%Y",        # 14/08/2025
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str[:len(fmt)+5], fmt)
        except ValueError:
            continue

    # Try extracting just a date pattern
    match = re.search(r'(\d{1,2})\s+(\w{3,9})\s+(\d{4})', date_str)
    if match:
        try:
            return datetime.strptime(f"{match.group(1)} {match.group(2)} {match.group(3)}", "%d %b %Y")
        except ValueError:
            try:
                return datetime.strptime(f"{match.group(1)} {match.group(2)} {match.group(3)}", "%d %B %Y")
            except ValueError:
                pass

    return None


def _build_event_body(event_data: dict) -> dict:
    title = event_data["title"]
    url = event_data.get("event_url", "")
    date_str = event_data.get("date", "")

    description = f"Unstop Event: {url}\n\nReminder: You will be notified at 6:00 PM the day before this event."

    # Try to parse the event date
    event_dt = _parse_date(date_str) if date_str else None

    if event_dt:
        # Create an all-day event on the actual event date
        event_date_iso = event_dt.strftime("%Y-%m-%d")
        start = {"date": event_date_iso}
        end = {"date": event_date_iso}

        # Calculate 6 PM the day before in minutes before midnight of event day
        # Event starts at midnight (all-day), day before 6 PM = 6 hours before midnight = 360 min
        # But Google counts from start of all-day event (midnight)
        # So 6 PM day before = 6 hours before midnight = 360 minutes before start
        reminder_minutes = 6 * 60  # 6 hours before midnight of event day = 6 PM day before

        logger.info("Event '%s' on %s — reminder at 6 PM the day before", title, event_date_iso)
    else:
        # No date found — create as all-day event tomorrow as placeholder
        tomorrow = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d")
        start = {"date": tomorrow}
        end = {"date": tomorrow}
        reminder_minutes = 6 * 60
        logger.warning("No date found for '%s', using tomorrow as placeholder", title)

    return {
        "summary": f"🏆 {title}",
        "description": description,
        "start": start,
        "end": end,
        "source": {
            "title": "Unstop Calendar Sync",
            "url": url,
        },
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "popup", "minutes": reminder_minutes},
                {"method": "email", "minutes": reminder_minutes},
            ],
        },
    }


def create_event(event_data: dict) -> Optional[str]:
    try:
        service = _get_service()
        body = _build_event_body(event_data)
        result = service.events().insert(calendarId=CALENDAR_ID, body=body).execute()
        cal_id = result.get("id")
        logger.info("Created calendar event '%s' (%s)", event_data["title"], cal_id)
        return cal_id
    except HttpError as exc:
        logger.error("Failed to create event: %s", exc)
        return None


def update_event(calendar_event_id: str, event_data: dict) -> bool:
    try:
        service = _get_service()
        body = _build_event_body(event_data)
        service.events().update(
            calendarId=CALENDAR_ID,
            eventId=calendar_event_id,
            body=body,
        ).execute()
        logger.info("Updated calendar event '%s'", event_data["title"])
        return True
    except HttpError as exc:
        logger.error("Failed to update event: %s", exc)
        return False


def delete_event(calendar_event_id: str) -> bool:
    try:
        service = _get_service()
        service.events().delete(
            calendarId=CALENDAR_ID,
            eventId=calendar_event_id,
        ).execute()
        logger.info("Deleted calendar event %s", calendar_event_id)
        return True
    except HttpError as exc:
        logger.error("Failed to delete event: %s", exc)
        return False


def event_exists(calendar_event_id: str) -> bool:
    """Check if a Google Calendar event still exists."""
    try:
        service = _get_service()
        service.events().get(
            calendarId=CALENDAR_ID,
            eventId=calendar_event_id,
        ).execute()
        return True
    except HttpError as exc:
        if exc.resp.status == 404:
            return False
        logger.error("Error checking event %s: %s", calendar_event_id, exc)
        return False
