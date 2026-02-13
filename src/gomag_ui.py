from __future__ import annotations
import asyncio
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import List, Optional
import yaml
import streamlit as st
from playwright.async_api import async_playwright

# --- Playwright runtime install + SSL/TLS workaround (Streamlit Cloud) ---

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
    """Launch chromium with SSL-ignore and return (browser, context, page)."""
    browser = await p.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
            "--ignore-certificate-errors",
        ],
    )
    context = await browser.new_context(ignore_https_errors=True)
    page = await context.new_page()
    return browser, context, page


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
    await page.goto(login_url, wait_until="domcontentloaded", timeout=60000)
    await page.fill(cfg["gomag"]["login"]["username_selector"], creds.username)
    await page.fill(cfg["gomag"]["login"]["password_selector"], creds.password)
    await page.click(cfg["gomag"]["login"]["submit_selector"])
    await page.wait_for_timeout(int(cfg["gomag"]["login"].get("post_login_wait", 2.0) * 1000))

async def fetch_categories_async(creds: GomagCreds) -> List[str]:
    cfg = _load_cfg()
    _ensure_playwright_chromium_installed()
    async with async_playwright() as p:
        browser, context, page = await _launch_ctx(p)
        await _login(page, creds, cfg)
        url = creds.base_url.rstrip("/") + cfg["gomag"]["categories"]["url_path"]
        try:

            await page.goto(url, wait_until="domcontentloaded", timeout=60000)

        except Exception:

            if url.startswith("https://"):

                await page.goto("http://" + url[len("https://"):], wait_until="domcontentloaded", timeout=60000)

            else:

                raise
        await page.wait_for_timeout(1000)
        items = await page.query_selector_all(cfg["gomag"]["categories"]["item_selector"])
        cats = []
        for it in items:
            try:
                txt = (await it.inner_text()).strip()
                if txt and txt not in cats:
                    cats.append(txt)
            except Exception:
                continue
        await context.close()
        await browser.close()
        # fallback: if none, return empty
        return cats

def fetch_categories(creds: GomagCreds) -> List[str]:
    return asyncio.run(fetch_categories_async(creds))

async def import_file_async(creds: GomagCreds, file_path: str) -> str:
    cfg = _load_cfg()
    _ensure_playwright_chromium_installed()
    async with async_playwright() as p:
        browser, context, page = await _launch_ctx(p)
        await _login(page, creds, cfg)

        url = creds.base_url.rstrip("/") + cfg["gomag"]["import"]["url_path"]
        try:

            await page.goto(url, wait_until="domcontentloaded", timeout=60000)

        except Exception:

            if url.startswith("https://"):

                await page.goto("http://" + url[len("https://"):], wait_until="domcontentloaded", timeout=60000)

            else:

                raise
        await page.wait_for_timeout(1000)

        # upload
        await page.set_input_files(cfg["gomag"]["import"]["file_input_selector"], file_path)

        # attempt start
        try:
            await page.click(cfg["gomag"]["import"]["start_import_selector"], timeout=5000)
        except Exception:
            # Gomag poate cere mapare coloane manual la prima importare
            await context.close()
        await browser.close()
            return "Am incarcat fisierul, dar nu am putut porni importul automat (probabil e nevoie de mapare coloane manual la prima rulare)."

        await page.wait_for_timeout(2000)
        await context.close()
        await browser.close()
        return "Import pornit (daca Gomag nu a cerut pasi suplimentari)."

def import_file(creds: GomagCreds, file_path: str) -> str:
    return asyncio.run(import_file_async(creds, file_path))
