from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import List

import yaml
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


# ========= Original public API (compat with app.py) =========

@dataclass
class GomagCreds:
    base_url: str
    dashboard_path: str
    username: str
    password: str


def _load_cfg():
    with open("config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


async def _login(page, creds: GomagCreds, cfg):
    login_url = creds.base_url.rstrip("/") + creds.dashboard_path
    await _goto_with_fallback(page, login_url)

    await page.fill(cfg["gomag"]["login"]["username_selector"], creds.username)
    await page.fill(cfg["gomag"]["login"]["password_selector"], creds.password)
    await page.click(cfg["gomag"]["login"]["submit_selector"])
    await page.wait_for_timeout(int(cfg["gomag"]["login"].get("post_login_wait", 2.5) * 1000))


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
    cfg = _load_cfg()
    _ensure_playwright_chromium_installed()

    async with async_playwright() as p:
        browser, context, page = await _launch_ctx(p)
        try:
            await _login(page, creds, cfg)

            # URL corect confirmat de user:
            url = creds.base_url.rstrip("/") + "/gomag/product/category/list"
            await _goto_with_fallback(page, url)

            # asteapta randurile din tabel
            try:
                await page.wait_for_selector("table tbody tr", timeout=20000)
            except Exception:
                await page.wait_for_timeout(2500)

            html = await page.content()
            cats = _parse_categories_from_html(html)
            return cats
        finally:
            await context.close()
            await browser.close()


def fetch_categories(creds: GomagCreds) -> List[str]:
    return asyncio.run(fetch_categories_async(creds))


async def import_file_async(creds: GomagCreds, file_path: str) -> str:
    cfg = _load_cfg()
    _ensure_playwright_chromium_installed()

    async with async_playwright() as p:
        browser, context, page = await _launch_ctx(p)
        try:
            await _login(page, creds, cfg)

            url = creds.base_url.rstrip("/") + cfg["gomag"]["import"]["url_path"]
            await _goto_with_fallback(page, url)
            await page.wait_for_timeout(1000)

            await page.set_input_files(cfg["gomag"]["import"]["file_input_selector"], file_path)

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
            await context.close()
            await browser.close()


def import_file(creds: GomagCreds, file_path: str) -> str:
    return asyncio.run(import_file_async(creds, file_path))
