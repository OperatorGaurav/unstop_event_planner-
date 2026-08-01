"""
Scraper for Unstop registered events using Playwright.
"""

import os
import re
import logging
from playwright.async_api import async_playwright, Browser

logger = logging.getLogger(__name__)

UNSTOP_BASE = "https://unstop.com"
LOGIN_URL = f"{UNSTOP_BASE}/login"


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

            # ── Step 1: Login ─────────────────────────────────────────
            logger.info("Navigating to login page...")
            await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60_000)
            await page.wait_for_timeout(4000)

            for sel in ['input[type="email"]', 'input[name="email"]', 'input[formcontrolname="email"]']:
                try:
                    el = await page.query_selector(sel)
                    if el:
                        await el.click()
                        await el.fill(email)
                        logger.info("Filled email with: %s", sel)
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
                        logger.info("Filled password with: %s", sel)
                        break
                except Exception:
                    continue

            await page.wait_for_timeout(1000)

            for sel in ['button[type="submit"]', 'button:has-text("Login")', 'button:has-text("Log In")', 'button:has-text("Sign in")']:
                try:
                    el = await page.query_selector(sel)
                    if el:
                        await el.click()
                        logger.info("Clicked submit: %s", sel)
                        break
                except Exception:
                    continue

            # Wait for login to complete
            await page.wait_for_timeout(8000)
            logger.info("URL after login: %s", page.url)

            # ── Step 2: Go to registrations page ─────────────────────
            await page.goto(
                f"{UNSTOP_BASE}/dashboard/registered",
                wait_until="networkidle",
                timeout=60_000
            )
            await page.wait_for_timeout(10000)
            logger.info("URL on registrations page: %s", page.url)

            # ── Step 3: Wait for listings to appear ───────────────────
            try:
                await page.wait_for_selector("div.listing", timeout=15000)
            except Exception:
                logger.warning("Timed out waiting for div.listing")

            # ── Step 4: Scroll to load all events ─────────────────────
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(3000)

            # ── Step 5: Parse listings ────────────────────────────────
            cards = await page.query_selector_all("div.listing")
            logger.info("Found %d listing cards", len(cards))

            events = []
            for card in cards:
                try:
                    # Title
                    title_el = await card.query_selector("h2.double-wrap, h2, h3")
                    if not title_el:
                        continue
                    title = (await title_el.inner_text()).strip()
                    if not title:
                        continue

                    # URL
                    url_el = await card.query_selector("a.wrapper_left, a[href]")
                    relative_url = await url_el.get_attribute("href") if url_el else ""
                    event_url = (
                        f"{UNSTOP_BASE}{relative_url}"
                        if relative_url and relative_url.startswith("/")
                        else relative_url
                    )

                    # ID from URL
                    unstop_id_match = re.search(r"-(\d+)/?$", event_url or "")
                    unstop_id = unstop_id_match.group(1) if unstop_id_match else title

                    # Date — "Registered on: 31 Jul 26, 11:20 AM IST"
                    date_text = None
                    date_els = await card.query_selector_all("div.item, div.dtls, div.m_dtls div")
                    for el in date_els:
                        text = (await el.inner_text()).strip()
                        if "registered on" in text.lower() or re.search(r'\d{1,2}\s\w{3}\s\d{2}', text):
                            # Extract just the date part after the colon
                            if ":" in text:
                                date_text = text.split(":", 1)[1].strip()
                            else:
                                date_text = text
                            break

                    # Deadline — look for any date-like text mentioning deadline/ends
                    deadline_text = None
                    all_text_els = await card.query_selector_all("div, span, p")
                    for el in all_text_els:
                        text = (await el.inner_text()).strip()
                        if any(word in text.lower() for word in ["deadline", "ends", "last date", "apply by"]):
                            deadline_text = text
                            break

                    events.append({
                        "unstop_id": unstop_id,
                        "title": title,
                        "date": date_text,
                        "time": None,
                        "deadline": deadline_text,
                        "event_url": event_url or None,
                    })
                    logger.info("Parsed event: %s", title)

                except Exception as exc:
                    logger.warning("Failed to parse card: %s", exc)
                    continue

            logger.info("Total events parsed: %d", len(events))
            return events

        except Exception as exc:
            logger.error("Scraping error: %s", exc)
            raise
        finally:
            await browser.close()
