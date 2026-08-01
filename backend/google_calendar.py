"""
Google Calendar API helper.
Sets a reminder at exactly 6:00 PM the day before each event.
Includes duplicate prevention by searching before creating.
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
    if not date_str:
        return None
    date_str = re.sub(r'\s+', ' ', date_str).strip()
    formats = ["%Y-%m-%d", "%d %b %Y", "%d %B %Y", "%b %d, %Y", "%B %d, %Y"]
    for fmt in formats:
        try:
            return datetime.strptime(date_str[:20], fmt)
        except ValueError:
            continue
    match = re.search(r'(\d{1,2})\s+(\w{3,9})\s+(\d{4})', date_str)
    if match:
        for fmt in ["%d %b %Y", "%d %B %Y"]:
            try:
                return datetime.strptime(
                    f"{match.group(1)} {match.group(2)} {match.group(3)}", fmt
                )
            except ValueError:
                continue
    return None


def _build_event_body(event_data: dict) -> dict:
    title = event_data["title"]
    url = event_data.get("event_url", "")
    date_str = event_data.get("date", "")

    description = f"Unstop Event: {url}\n\nReminder: 6:00 PM the day before this event."
    event_dt = _parse_date(date_str) if date_str else None

    if event_dt:
        event_date_iso = event_dt.strftime("%Y-%m-%d")
        start = {"date": event_date_iso}
        end = {"date": event_date_iso}
        reminder_minutes = 6 * 60
    else:
        tomorrow = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d")
        start = {"date": tomorrow}
        end = {"date": tomorrow}
        reminder_minutes = 6 * 60

    return {
        "summary": f"🏆 {title}",
        "description": description,
        "start": start,
        "end": end,
        "source": {"title": "Unstop Calendar Sync", "url": url},
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "popup", "minutes": reminder_minutes},
                {"method": "email", "minutes": reminder_minutes},
            ],
        },
    }


def find_existing_event(title: str) -> Optional[str]:
    """
    Search Google Calendar for an event with this exact title.
    Returns the calendar event ID if found, None otherwise.
    This prevents duplicates even when SQLite resets.
    """
    try:
        service = _get_service()
        search_title = f"🏆 {title}"
        results = service.events().list(
            calendarId=CALENDAR_ID,
            q=search_title,
            singleEvents=True,
            maxResults=5,
        ).execute()

        events = results.get("items", [])
        for event in events:
            if event.get("summary", "").strip() == search_title:
                logger.info("Found existing calendar event for '%s': %s", title, event["id"])
                return event["id"]
        return None
    except HttpError as exc:
        logger.error("Error searching for event '%s': %s", title, exc)
        return None


def event_exists(calendar_event_id: str) -> bool:
    """Check if a Google Calendar event still exists by ID."""
    try:
        service = _get_service()
        service.events().get(calendarId=CALENDAR_ID, eventId=calendar_event_id).execute()
        return True
    except HttpError as exc:
        if exc.resp.status == 404:
            return False
        return False


def create_event(event_data: dict) -> Optional[str]:
    """
    Create a Google Calendar event.
    First checks if an event with the same title already exists to prevent duplicates.
    """
    try:
        # Check if already exists in Google Calendar
        existing_id = find_existing_event(event_data["title"])
        if existing_id:
            logger.info("Skipping '%s' — already exists in Google Calendar", event_data["title"])
            return existing_id

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
        service.events().delete(calendarId=CALENDAR_ID, eventId=calendar_event_id).execute()
        logger.info("Deleted calendar event %s", calendar_event_id)
        return True
    except HttpError as exc:
        logger.error("Failed to delete event: %s", exc)
        return False
