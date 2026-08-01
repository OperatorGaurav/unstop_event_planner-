"""
Unstop API client — fetches registered events directly via Unstop's internal API.
No browser/Playwright needed. Uses the Bearer token from your logged-in session.

Environment variables required:
  UNSTOP_TOKEN  – Bearer token from browser Network tab (see README)
"""

import os
import logging
import httpx
from datetime import datetime

logger = logging.getLogger(__name__)

API_BASE = "https://api.unstop.com/api/user/registered-opportunities"
UNSTOP_BASE = "https://unstop.com"


async def fetch_registered_events() -> list[dict]:
    """
    Fetch all registered events from Unstop's API.
    Handles pagination automatically (fetches all pages).
    """
    token = os.environ.get("UNSTOP_TOKEN", "")
    if not token:
        raise ValueError("UNSTOP_TOKEN environment variable is not set.")

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Origin": "https://unstop.com",
        "Referer": "https://unstop.com/",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
    }

    all_events = []
    page = 1

    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            url = f"{API_BASE}?page={page}&per_page=10&filterBy=type,status&filterValue=all,all"
            logger.info("Fetching page %d from Unstop API...", page)

            response = await client.get(url, headers=headers)

            if response.status_code == 401:
                raise ValueError(
                    "UNSTOP_TOKEN is expired or invalid. "
                    "Please get a new token from your browser Network tab and update Render."
                )

            response.raise_for_status()
            data = response.json()

            items = data.get("data", {}).get("data", [])
            last_page = data.get("data", {}).get("last_page", 1)

            logger.info("Page %d: got %d events (last page: %d)", page, len(items), last_page)

            for item in items:
                try:
                    title = item.get("title", "").strip()
                    if not title:
                        continue

                    unstop_id = str(item.get("id", ""))
                    seo_url = item.get("seo_url", "")
                    end_date_raw = item.get("end_date", "")
                    end_regn_dt = item.get("end_regn_dt", "")
                    status = item.get("status", "")

                    # Parse end_date into a clean date string
                    event_date = None
                    if end_date_raw:
                        try:
                            dt = datetime.fromisoformat(end_date_raw)
                            event_date = dt.strftime("%Y-%m-%d")
                        except Exception:
                            event_date = end_date_raw[:10]

                    # Parse registration deadline
                    deadline = None
                    if end_regn_dt:
                        try:
                            dt = datetime.fromisoformat(end_regn_dt.replace(" ", "T"))
                            deadline = dt.strftime("%d %b %Y, %I:%M %p")
                        except Exception:
                            deadline = end_regn_dt

                    all_events.append({
                        "unstop_id": unstop_id,
                        "title": title,
                        "date": event_date,
                        "time": None,
                        "deadline": deadline,
                        "event_url": seo_url,
                        "status": status,
                    })
                    logger.info("Parsed: %s | Date: %s | Status: %s", title, event_date, status)

                except Exception as exc:
                    logger.warning("Failed to parse item: %s", exc)
                    continue

            if page >= last_page:
                break
            page += 1

    logger.info("Total events fetched: %d", len(all_events))
    return all_events
