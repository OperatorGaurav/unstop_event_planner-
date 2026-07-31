"""
Google Calendar API helper.

Authentication uses OAuth 2.0 with a long-lived refresh token so the app
can run unattended.

Environment variables required:
  GOOGLE_CLIENT_ID
  GOOGLE_CLIENT_SECRET
  GOOGLE_REFRESH_TOKEN

Optional:
  GOOGLE_CALENDAR_ID   – defaults to "primary"
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Optional

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "primary")
SCOPES = ["https://www.googleapis.com/auth/calendar"]

# Reminder minutes before event
REMINDERS = [
    {"method": "popup", "minutes": 24 * 60},  # 1 day
    {"method": "popup", "minutes": 2 * 60},   # 2 hours
    {"method": "popup", "minutes": 30},        # 30 minutes
]


def _get_credentials() -> Credentials:
    """Build Google credentials from environment variables."""
    creds = Credentials(
        token=None,
        refresh_token=os.environ["GOOGLE_REFRESH_TOKEN"],
        client_id=os.environ["GOOGLE_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=SCOPES,
    )
    # Refresh to get a valid access token
    creds.refresh(Request())
    return creds


def _get_service():
    """Return an authenticated Google Calendar service object."""
    creds = _get_credentials()
    return build("calendar", "v3", credentials=creds)


def _build_event_body(event_data: dict) -> dict:
    """
    Convert an Unstop event dict into a Google Calendar event body.

    If we have a proper date, create a timed event; otherwise an all-day event.
    """
    title = event_data["title"]
    url = event_data.get("event_url", "")
    deadline = event_data.get("deadline", "")
    date_str = event_data.get("date", "")
    time_str = event_data.get("time", "")

    description_parts = [f"Unstop Event: {url}"]
    if deadline:
        description_parts.append(f"Registration Deadline: {deadline}")

    description = "\n".join(description_parts)

    # Try to parse as a datetime if time is available
    start: dict
    end: dict
    try:
        if date_str and time_str:
            dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %I:%M %p")
            start = {"dateTime": dt.isoformat(), "timeZone": "Asia/Kolkata"}
            end = {"dateTime": (dt + timedelta(hours=2)).isoformat(), "timeZone": "Asia/Kolkata"}
        elif date_str:
            # Parse flexible date strings like "14 Sep 2025"
            try:
                dt = datetime.strptime(date_str, "%d %b %Y")
                date_iso = dt.strftime("%Y-%m-%d")
            except ValueError:
                date_iso = date_str  # assume already ISO

            start = {"date": date_iso}
            end = {"date": date_iso}
        else:
            raise ValueError("No date available")
    except Exception:
        # Fallback: schedule for tomorrow if date is unparseable
        tomorrow = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d")
        start = {"date": tomorrow}
        end = {"date": tomorrow}

    return {
        "summary": title,
        "description": description,
        "start": start,
        "end": end,
        "source": {
            "title": "Unstop Calendar Sync",
            "url": url,
        },
        "reminders": {
            "useDefault": False,
            "overrides": REMINDERS,
        },
    }


def create_event(event_data: dict) -> Optional[str]:
    """
    Create a new Google Calendar event.

    Returns the Google Calendar event ID on success, or None on failure.
    """
    try:
        service = _get_service()
        body = _build_event_body(event_data)
        result = service.events().insert(calendarId=CALENDAR_ID, body=body).execute()
        cal_id = result.get("id")
        logger.info("Created Google Calendar event '%s' (%s)", event_data["title"], cal_id)
        return cal_id
    except HttpError as exc:
        logger.error("Failed to create calendar event: %s", exc)
        return None


def update_event(calendar_event_id: str, event_data: dict) -> bool:
    """
    Update an existing Google Calendar event.

    Returns True on success, False on failure.
    """
    try:
        service = _get_service()
        body = _build_event_body(event_data)
        service.events().update(
            calendarId=CALENDAR_ID,
            eventId=calendar_event_id,
            body=body,
        ).execute()
        logger.info("Updated Google Calendar event '%s'", event_data["title"])
        return True
    except HttpError as exc:
        logger.error("Failed to update calendar event %s: %s", calendar_event_id, exc)
        return False


def delete_event(calendar_event_id: str) -> bool:
    """
    Delete a Google Calendar event.

    Returns True on success, False on failure.
    """
    try:
        service = _get_service()
        service.events().delete(
            calendarId=CALENDAR_ID,
            eventId=calendar_event_id,
        ).execute()
        logger.info("Deleted Google Calendar event %s", calendar_event_id)
        return True
    except HttpError as exc:
        logger.error("Failed to delete calendar event %s: %s", calendar_event_id, exc)
        return False
