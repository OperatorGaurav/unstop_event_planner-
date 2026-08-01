"""
Scraper for Unstop registered events using Playwright.
"""

import os
import re
import logging
from typing import Optional
from playwright.async_api import async_playwright, Page, Browser

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

            # ── Step 1: Go to login page ──────────────────────────────
            logger.info("Navigating to login page...")
            await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60_000)
            await page.wait_for_timeout(8000)

            logger.info("Current URL after goto: %s", page.url)

            # ── Step 2: Fill email ────────────────────────────────────
            email_selectors = [
                'input[type="email"]',
                'input[name="email"]',
                'input[formcontrolname="email"]',
                'input[placeholder*="mail" i]',
                'input[placeholder*="Email" i]',
            ]

            for sel in email_selectors:
                try:
                    el = await page.query_selector(sel)
                    if el:
                        await el.click()
                        await el.fill(email)
                        logger.info("Filled email with: %s", sel)
                        break
                except Exception as e:
                    logger.debug("Email selector %s failed: %s", sel, e)
                    continue

            await page.wait_for_timeout(1000)

            # ── Step 3: Fill password ─────────────────────────────────
            password_selectors = [
                'input[type="password"]',
                'input[name="password"]',
                'input[formcontrolname="password"]',
                'input[placeholder*="assword" i]',
            ]

            for sel in password_selectors:
                try:
                    el = await page.query_selector(sel)
                    if el:
                        await el.click()
                        await el.fill(password)
                        logger.info("Filled password with: %s", sel)
                        break
                except Exception as e:
                    logger.debug("Password selector %s failed: %s", sel, e)
                    continue

            await page.wait_for_timeout(1000)

            # ── Step 4: Click submit ──────────────────────────────────
            submit_selectors = [
                'button[type="submit"]',
                'button:has-text("Login")',
                'button:has-text("Log In")',
                'button:has-text("Sign in")',
                'button:has-text("Continue")',
            ]

            for sel in submit_selectors:
                try:
                    el = await page.query_selector(sel)
                    if el:
                        await el.click()
                        logger.info("Clicked submit: %s", sel)
                        break
                except Exception as e:
                    logger.debug("Submit selector %s failed: %s", sel, e)
                    continue

            # ── Step 5: Wait for login to complete ────────────────────
            await page.wait_for_timeout(6000)
            logger.info("URL after login attempt: %s", page.url)

            # ── Step 6: Go to registered events ──────────────────────
            await page.goto(
            f"{UNSTOP_BASE}/dashboard/registered",
            wait_until="networkidle",
            timeout=60_000
            )
            await page.wait_for_timeout(10000)
            logger.info("URL on registrations page: %s", page.url)

            # ── Step 7: Get page HTML for debugging ───────────────────
            html = await page.content()
            logger.info("Page HTML length: %d", len(html))
            logger.info("Page HTML snippet: %s", html[:2000])

            # ── Step 8: Try to find event cards ──────────────────────
            card_selectors = [
                ".competition-card",
                ".registered-card",
                "[class*='competition-card']",
                "[class*='opportunity']",
                "[class*='card']",
                "app-competition-card",
                ".list-item",
                "li",
            ]

            cards = []
            for sel in card_selectors:
                try:
                    found = await page.query_selector_all(sel)
                    if found and len(found) > 0:
                        cards = found
                        logger.info("Found %d cards with: %s", len(cards), sel)
                        break
                except Exception as e:
                    logger.debug("Card selector %s failed: %s", sel, e)
                    continue

            if not cards:
                logger.warning("No event cards found. Returning empty list.")
                return []

            # ── Step 9: Parse cards ───────────────────────────────────
            events = []
            for card in cards:
                try:
                    title_el = await card.query_selector(
                        ".competition-name, h3, h2, .title, [class*='title'], [class*='name']"
                    )
                    title = (await title_el.inner_text()).strip() if title_el else None
                    if not title:
                        continue

                    url_el = await card.query_selector("a[href]")
                    relative_url = await url_el.get_attribute("href") if url_el else ""
                    event_url = (
                        f"{UNSTOP_BASE}{relative_url}"
                        if relative_url and relative_url.startswith("/")
                        else relative_url
                    )

                    unstop_id_match = re.search(r"/(\d+)/?$", event_url or "")
                    unstop_id = unstop_id_match.group(1) if unstop_id_match else event_url

                    date_text = ""
                    for sel in [".date", ".event-date", '[class*="date"]']:
                        date_el = await card.query_selector(sel)
                        if date_el:
                            date_text = (await date_el.inner_text()).strip()
                            break

                    deadline_text = ""
                    for sel in [".deadline", ".reg-deadline", '[class*="deadline"]']:
                        dl_el = await card.query_selector(sel)
                        if dl_el:
                            deadline_text = (await dl_el.inner_text()).strip()
                            break

                    events.append({
                        "unstop_id": unstop_id or title,
                        "title": title,
                        "date": date_text or None,
                        "time": None,
                        "deadline": deadline_text or None,
                        "event_url": event_url or None,
                    })
                except Exception as exc:
                    logger.warning("Failed to parse card: %s", exc)
                    continue

            logger.info("Parsed %d events total", len(events))
            return events

        except Exception as exc:
            logger.error("Scraping error: %s", exc)
            raise
        finally:
            await browser.close()
