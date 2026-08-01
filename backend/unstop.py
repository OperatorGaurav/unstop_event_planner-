"""
Scraper for Unstop registered events using Playwright.
Visits each event page to get the actual event date.
"""

import os
import re
import logging
from playwright.async_api import async_playwright, Browser, Page

logger = logging.getLogger(__name__)

UNSTOP_BASE = "https://unstop.com"
LOGIN_URL = f"{UNSTOP_BASE}/login"


async def _get_event_date(page: Page, event_url: str) -> str | None:
    """Visit the event page and extract the actual event date."""
    try:
        await page.goto(event_url, wait_until="domcontentloaded", timeout=30_000)
        await page.wait_for_timeout(4000)

        # Try multiple date selectors used across Unstop event pages
        date_selectors = [
            "[class*='date']",
            "[class*='timing']",
            "[class*='schedule']",
            "[class*='start']",
            "[class*='event-date']",
            "un-icon + span",
            "[class*='dtls'] [class*='date']",
        ]

        for sel in date_selectors:
            els = await page.query_selector_all(sel)
            for el in els:
                text = (await el.inner_text()).strip()
                # Look for date patterns like "14 Aug 2025" or "Aug 14, 2025"
                if re.search(r'\d{1,2}\s+\w{3,9}\s+\d{4}', text) or \
                   re.search(r'\w{3,9}\s+\d{1,2},?\s+\d{4}', text):
                    logger.info("Found date '%s' on %s", text, event_url)
                    return text

        # Fallback: search all text on page for date patterns
        body_text = await page.inner_text("body")
        match = re.search(r'\d{1,2}\s+\w{3,9}\s+\d{4}', body_text)
        if match:
            return match.group(0)

        return None
    except Exception as exc:
        logger.warning("Could not get date from %s: %s", event_url, exc)
        return None


async def fetch_registered_events() -> list[dict]:
    async with async_playwright() as pw:
        browser: Browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800}
        )
        page = await context.new_page()

        try:
            email = os.environ["UNSTOP_EMAIL"]
            password = os.environ["UNSTOP_PASSWORD"]

            # ── Login ─────────────────────────────────────────────────
            logger.info("Logging in to Unstop...")
            await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60_000)
            await page.wait_for_timeout(4000)

            for sel in ['input[type="email"]', 'input[name="email"]', 'input[formcontrolname="email"]']:
                try:
                    el = await page.query_selector(sel)
                    if el:
                        await el.click()
                        await el.fill(email)
                        break
                except Exception:
                    continue

            await page.wait_for_timeout(1000)

            for sel in ['input[type="password"]', 'input[name="password"]', 'input[formcontrolname="password"]']:
                try:
                    el = await page.query_selector(sel)
                    if el:
                        await el.click()
                        await el.fill(password)
                        break
                except Exception:
                    continue

            await page.wait_for_timeout(1000)

            for sel in ['button[type="submit"]', 'button:has-text("Login")', 'button:has-text("Log In")']:
                try:
                    el = await page.query_selector(sel)
                    if el:
                        await el.click()
                        break
                except Exception:
                    continue

            await page.wait_for_timeout(8000)
            logger.info("Logged in, URL: %s", page.url)

            # ── Go to registrations page ──────────────────────────────
            await page.goto(
                f"{UNSTOP_BASE}/dashboard/registered",
                wait_until="networkidle",
                timeout=60_000
            )
            await page.wait_for_timeout(10000)

            try:
                await page.wait_for_selector("div.listing", timeout=15000)
            except Exception:
                logger.warning("Timed out waiting for div.listing")

            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(3000)

            # ── Parse listing cards ───────────────────────────────────
            cards = await page.query_selector_all("div.listing")
            logger.info("Found %d listing cards", len(cards))

            # Collect basic info first (title + URL) before navigating away
            basic_info = []
            for card in cards:
                try:
                    title_el = await card.query_selector("h2.double-wrap, h2, h3")
                    if not title_el:
                        continue
                    title = (await title_el.inner_text()).strip()
                    if not title:
                        continue

                    url_el = await card.query_selector("a.wrapper_left, a[href]")
                    relative_url = await url_el.get_attribute("href") if url_el else ""
                    event_url = (
                        f"{UNSTOP_BASE}{relative_url}"
                        if relative_url and relative_url.startswith("/")
                        else relative_url
                    )

                    unstop_id_match = re.search(r"-(\d+)/?$", event_url or "")
                    unstop_id = unstop_id_match.group(1) if unstop_id_match else title

                    basic_info.append({
                        "unstop_id": unstop_id,
                        "title": title,
                        "event_url": event_url,
                    })
                except Exception as exc:
                    logger.warning("Failed basic parse: %s", exc)
                    continue

            # ── Visit each event page to get real date ────────────────
            events = []
            for info in basic_info:
                event_date = None
                if info["event_url"]:
                    event_date = await _get_event_date(page, info["event_url"])

                events.append({
                    "unstop_id": info["unstop_id"],
                    "title": info["title"],
                    "date": event_date,
                    "time": None,
                    "deadline": None,
                    "event_url": info["event_url"],
                })
                logger.info("Event: %s | Date: %s", info["title"], event_date)

            logger.info("Total events parsed: %d", len(events))
            return events

        except Exception as exc:
            logger.error("Scraping error: %s", exc)
            raise
        finally:
            await browser.close()
