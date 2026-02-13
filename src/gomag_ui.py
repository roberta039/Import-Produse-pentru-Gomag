from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import List, Optional
import yaml
import streamlit as st
from playwright.async_api import async_playwright, Page


@dataclass
class GomagCreds:
    base_url: str
    dashboard_path: str
    username: str
    password: str


def _load_cfg():
    with open("config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


async def _launch_ctx(p):
    """Launch Chromium in a Streamlit-Cloud friendly way (SSL/TLS tolerant)."""
    browser = await p.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
            "--ignore-certificate-errors",
        ],
    )
    context = await browser.new_context(
        ignore_https_errors=True,
        viewport={"width": 1366, "height": 768},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
    )
    page = await context.new_page()
    await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
    return browser, context, page


async def _goto_safe(page: Page, url: str, timeout: int = 60000):
    """Goto with https->http fallback for broken SSL handshakes."""
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
    except Exception:
        if url.startswith("https://"):
            url2 = "http://" + url[len("https://") :]
            await page.goto(url2, wait_until="domcontentloaded", timeout=timeout)
        else:
            raise


async def _login(page: Page, creds: GomagCreds, cfg):
    login_url = creds.base_url.rstrip("/") + creds.dashboard_path
    await _goto_safe(page, login_url, timeout=60000)
    await page.fill(cfg["gomag"]["login"]["username_selector"], creds.username)
    await page.fill(cfg["gomag"]["login"]["password_selector"], creds.password)
    await page.click(cfg["gomag"]["login"]["submit_selector"])
    await page.wait_for_timeout(int(cfg["gomag"]["login"].get("post_login_wait", 2.0) * 1000))


async def fetch_categories_async(creds: GomagCreds) -> List[str]:
    cfg = _load_cfg()
    async with async_playwright() as p:
        browser, context, page = await _launch_ctx(p)
        try:
            await _login(page, creds, cfg)
            url = creds.base_url.rstrip("/") + cfg["gomag"]["categories"]["url_path"]
            await _goto_safe(page, url, timeout=60000)
            await page.wait_for_timeout(1000)

            items = await page.query_selector_all(cfg["gomag"]["categories"]["item_selector"])
            cats: List[str] = []
            for it in items:
                try:
                    txt = (await it.inner_text()).strip()
                    if txt and txt not in cats:
                        cats.append(txt)
                except Exception:
                    continue

            return cats
        finally:
            try:
                await context.close()
            except Exception:
                pass
            await browser.close()


def fetch_categories(creds: GomagCreds) -> List[str]:
    return asyncio.run(fetch_categories_async(creds))


async def import_file_async(creds: GomagCreds, file_path: str) -> str:
    cfg = _load_cfg()
    async with async_playwright() as p:
        browser, context, page = await _launch_ctx(p)
        try:
            await _login(page, creds, cfg)
            url = creds.base_url.rstrip("/") + cfg["gomag"]["import"]["url_path"]
            await _goto_safe(page, url, timeout=60000)
            await page.wait_for_timeout(1000)

            # upload
            await page.set_input_files(cfg["gomag"]["import"]["file_input_selector"], file_path)

            # attempt start
            try:
                await page.click(cfg["gomag"]["import"]["start_import_selector"], timeout=5000)
            except Exception:
                return (
                    "Am incarcat fisierul, dar nu am putut porni importul automat "
                    "(probabil e nevoie de mapare coloane manual la prima rulare)."
                )

            await page.wait_for_timeout(2000)
            return "Import pornit (daca Gomag nu a cerut pasi suplimentari)."
        finally:
            try:
                await context.close()
            except Exception:
                pass
            await browser.close()


def import_file(creds: GomagCreds, file_path: str) -> str:
    return asyncio.run(import_file_async(creds, file_path))
