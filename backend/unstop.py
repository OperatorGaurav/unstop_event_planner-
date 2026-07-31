"""
Scraper for Unstop registered events.

Strategy:
  1. Launch a headless Chromium browser via Playwright.
  2. Log in with credentials from environment variables.
  3. Navigate to the "My Registrations" page.
  4. Parse all event cards and return a list of dicts.

Environment variables required:
  UNSTOP_EMAIL    – your Unstop account email
  UNSTOP_PASSWORD – your Unstop account password
"""

import os
import re
import logging
from typing import Optional
from playwright.async_api import async_playwright, Page, Browser

logger = logging.getLogger(__name__)

UNSTOP_BASE = "https://unstop.com"
LOGIN_URL = f"{UNSTOP_BASE}/login"
REGISTRATIONS_URL = f"{UNSTOP_BASE}/api/v2/users/my-registrations"


async def _login(page: Page) -> None:
    """Fill the login form and wait for redirect."""
    email = os.environ["UNSTOP_EMAIL"]
    password = os.environ["UNSTOP_PASSWORD"]

    await page.goto(LOGIN_URL, wait_until="networkidle")
    await page.fill('input[type="email"]', email)
    await page.fill('input[type="password"]', password)
    await page.click('button[type="submit"]')
    # Wait for navigation away from login page
    await page.wait_for_url(lambda url: "login" not in url, timeout=15_000)
    logger.info("Logged in to Unstop successfully.")


async def _parse_event_card(card) -> Optional[dict]:
    """Extract event data from a single registration card element."""
    try:
        title_el = await card.query_selector(".competition-name, h3, .title")
        title = (await title_el.inner_text()).strip() if title_el else "Untitled"

        url_el = await card.query_selector("a[href]")
        relative_url = await url_el.get_attribute("href") if url_el else ""
        event_url = f"{UNSTOP_BASE}{relative_url}" if relative_url.startswith("/") else relative_url

        # unstop_id from URL: /competitions/<slug>/<id>
        unstop_id_match = re.search(r"/(\d+)/?$", event_url)
        unstop_id = unstop_id_match.group(1) if unstop_id_match else event_url

        # Date / time — Unstop uses various selectors; try multiple
        date_text = ""
        for sel in [".date", ".event-date", '[class*="date"]']:
            date_el = await card.query_selector(sel)
            if date_el:
                date_text = (await date_el.inner_text()).strip()
                break

        # Deadline
        deadline_text = ""
        for sel in [".deadline", ".reg-deadline", '[class*="deadline"]']:
            dl_el = await card.query_selector(sel)
            if dl_el:
                deadline_text = (await dl_el.inner_text()).strip()
                break

        return {
            "unstop_id": unstop_id,
            "title": title,
            "date": date_text or None,
            "time": None,           # Unstop rarely shows time on card; enrich if needed
            "deadline": deadline_text or None,
            "event_url": event_url,
        }
    except Exception as exc:
        logger.warning("Failed to parse event card: %s", exc)
        return None


async def fetch_registered_events() -> list[dict]:
    """
    Log in to Unstop and return a list of registered events.

    Each event dict has keys:
      unstop_id, title, date, time, deadline, event_url
    """
    async with async_playwright() as pw:
        browser: Browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        )
        page = await context.new_page()

        try:
            await _login(page)

            # Navigate to registrations page
            await page.goto(
                f"{UNSTOP_BASE}/dashboard/registered",
                wait_until="networkidle",
                timeout=20_000,
            )

            # Wait for event cards to appear
            await page.wait_for_selector(
                ".competition-card, .registered-card, [class*='competition']",
                timeout=10_000,
            )

            cards = await page.query_selector_all(
                ".competition-card, .registered-card, [class*='competition-card']"
            )
            logger.info("Found %d event cards.", len(cards))

            events = []
            for card in cards:
                event = await _parse_event_card(card)
                if event:
                    events.append(event)

            return events

        except Exception as exc:
            logger.error("Error scraping Unstop: %s", exc)
            raise
        finally:
            await browser.close()
