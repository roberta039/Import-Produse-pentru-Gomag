from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from typing import Optional

from playwright.async_api import async_playwright


def _ensure_playwright_chromium_installed() -> None:
    """Best-effort install of Playwright Chromium at runtime (Streamlit Cloud friendly).

    This is a fallback in case `postBuild` didn't run or browsers cache was cleared.
    It runs at most once per process using an env-flag.
    """
    if os.environ.get("PW_CHROMIUM_READY") == "1":
        return

    # Ensure browsers are installed in the project cache (not in a read-only path)
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "0")

    try:
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        os.environ["PW_CHROMIUM_READY"] = "1"
    except Exception:
        # Don't hard-fail; caller will get original error if launch still fails
        os.environ["PW_CHROMIUM_READY"] = "0"


async def render_html(url: str, wait_ms: int = 1500) -> str:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(wait_ms)
        html = await page.content()
        await browser.close()
        return html


def render_html_sync(url: str, wait_ms: int = 1500) -> str:
    """Sync wrapper with auto-install fallback when Chromium is missing."""
    try:
        return asyncio.run(render_html(url, wait_ms=wait_ms))
    except Exception as e:
        msg = str(e)
        # Most common Streamlit Cloud issue: browsers not downloaded
        if "Executable doesn't exist" in msg or "playwright install" in msg:
            _ensure_playwright_chromium_installed()
            # retry once
            return asyncio.run(render_html(url, wait_ms=wait_ms))
        raise
