from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import List

import streamlit as st
import yaml
from playwright.async_api import async_playwright


@dataclass
class GomagCreds:
    base_url: str
    dashboard_path: str
    username: str
    password: str


def _load_cfg():
    with open("config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _pw_writable_browsers_path() -> str:
    # Streamlit Cloud: /home/appuser or /home/adminuser is writable
    home = os.path.expanduser("~")
    return os.path.join(home, ".cache", "ms-playwright")


def _ensure_playwright_chromium_installed() -> None:
    """Ensure Playwright Chromium executable exists (Streamlit Cloud friendly)."""
    if os.environ.get("PW_CHROMIUM_READY") == "1":
        return

    browsers_path = _pw_writable_browsers_path()
    os.makedirs(browsers_path, exist_ok=True)
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = browsers_path

    # Install chromium if missing (safe to re-run; it will be quick if already installed)
    proc = subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if proc.returncode != 0:
        # show output in Streamlit logs for debugging
        raise RuntimeError(f"playwright_install_failed (code={proc.returncode}):\n{proc.stdout}")

    os.environ["PW_CHROMIUM_READY"] = "1"


async def _launch_ctx(p):
    """Launch Chromium with SSL-ignore and return (browser, context, page)."""
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
    )
    page = await context.new_page()
    await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
    return browser, context, page


async def _safe_goto(page, url: str):
    """Goto with HTTPS->HTTP fallback for SSL handshake errors."""
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
    except Exception:
        if url.startswith("https://"):
            http_url = "http://" + url[len("https://") :]
            await page.goto(http_url, wait_until="domcontentloaded", timeout=60000)
        else:
            raise


async def _login(page, creds: GomagCreds, cfg):
    login_url = creds.base_url.rstrip("/") + creds.dashboard_path
    await _safe_goto(page, login_url)
    await page.fill(cfg["gomag"]["login"]["username_selector"], creds.username)
    await page.fill(cfg["gomag"]["login"]["password_selector"], creds.password)
    await page.click(cfg["gomag"]["login"]["submit_selector"])
    await page.wait_for_timeout(int(cfg["gomag"]["login"].get("post_login_wait", 2.0) * 1000))


async def fetch_categories_async(creds: GomagCreds) -> List[str]:
    cfg = _load_cfg()
    _ensure_playwright_chromium_installed()

    async with async_playwright() as p:
        browser, context, page = await _launch_ctx(p)
        try:
            await _login(page, creds, cfg)
            url = creds.base_url.rstrip("/") + cfg["gomag"]["categories"]["url_path"]
            await _safe_goto(page, url)
            await page.wait_for_timeout(1000)

            items = await page.query_selector_all(cfg["gomag"]["categories"]["item_selector"])
            cats: List[str] = []
            for it in items:
                try:
                    t = (await it.inner_text()).strip()
                    if t and t not in cats:
                        cats.append(t)
                except Exception:
                    continue
            return cats
        finally:
            try:
                await context.close()
            except Exception:
                pass
            try:
                await browser.close()
            except Exception:
                pass


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
            await _safe_goto(page, url)
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
            try:
                await browser.close()
            except Exception:
                pass


def import_file(creds: GomagCreds, file_path: str) -> str:
    return asyncio.run(import_file_async(creds, file_path))
