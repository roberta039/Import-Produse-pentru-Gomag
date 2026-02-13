from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import List

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright


# ========= Playwright runtime install + SSL/TLS workaround (Streamlit Cloud) =========

def _pw_writable_browsers_path() -> str:
    home = os.path.expanduser("~")
    return os.path.join(home, ".cache", "ms-playwright")


def _ensure_playwright_chromium_installed() -> None:
    """Ensure Playwright Chromium exists. Safe for Streamlit Cloud."""
    if os.environ.get("PW_CHROMIUM_READY") == "1":
        return

    browsers_path = _pw_writable_browsers_path()
    os.makedirs(browsers_path, exist_ok=True)
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = browsers_path

    proc = subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"playwright_install_failed (code={proc.returncode}):\n{proc.stdout}")

    os.environ["PW_CHROMIUM_READY"] = "1"


async def _launch_ctx(p):
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
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1366, "height": 768},
        locale="ro-RO",
        extra_http_headers={"Accept-Language": "ro-RO,ro;q=0.9,en-US;q=0.8,en;q=0.7"},
    )
    page = await context.new_page()
    await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
    return browser, context, page


async def _goto_with_fallback(page, url: str):
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
    except Exception:
        if url.startswith("https://"):
            await page.goto("http://" + url[len("https://"):], wait_until="domcontentloaded", timeout=60000)
        else:
            raise


# ========= Gomag helpers =========

@dataclass
class GomagCreds:
    base_url: str
    username: str
    password: str


def _dashboard_url(base: str) -> str:
    return base.rstrip("/") + "/gomag/dashboard"


def _categories_url(base: str) -> str:
    return base.rstrip("/") + "/gomag/dashboard/categories"


async def _login(page, creds: GomagCreds):
    await _goto_with_fallback(page, _dashboard_url(creds.base_url))
    await page.wait_for_timeout(800)

    await page.fill(
        'input[type="email"], input[name*="email" i], input[id*="email" i], input[name*="user" i], input[placeholder*="email" i], input[placeholder*="user" i]',
        creds.username,
    )
    await page.fill(
        'input[type="password"], input[name*="pass" i], input[id*="pass" i], input[placeholder*="parol" i], input[placeholder*="pass" i]',
        creds.password,
    )

    try:
        await page.click(
            'button[type="submit"], input[type="submit"], button:has-text("Login"), button:has-text("Autentificare")',
            timeout=8000,
        )
    except Exception:
        await page.keyboard.press("Enter")

    await page.wait_for_timeout(1500)


def _parse_categories_from_html(html: str) -> List[str]:
    soup = BeautifulSoup(html, "lxml")
    rows = soup.select("table tbody tr")
    cats: List[str] = []
    for tr in rows:
        tds = tr.find_all("td")
        if not tds:
            continue
        name = tds[0].get_text(" ", strip=True).replace("\u00a0", " ").strip()
        if not name:
            continue
        name = name.split("ID:")[0].strip()
        if name and name not in cats:
            cats.append(name)
    return cats


async def fetch_categories_async(creds: GomagCreds) -> List[str]:
    _ensure_playwright_chromium_installed()

    async with async_playwright() as p:
        browser, context, page = await _launch_ctx(p)
        try:
            await _login(page, creds)
            await _goto_with_fallback(page, _categories_url(creds.base_url))

            try:
                await page.wait_for_selector("table tbody tr", timeout=20000)
            except Exception:
                await page.wait_for_timeout(3000)

            await page.wait_for_timeout(800)
            html = await page.content()
            return _parse_categories_from_html(html)
        finally:
            await context.close()
            await browser.close()


def fetch_categories(creds: GomagCreds) -> List[str]:
    return asyncio.run(fetch_categories_async(creds))


# IMPORTANT:
# This patch focuses on categories loading.
# Keep your existing import_file/import_file_async functions in your repo.
