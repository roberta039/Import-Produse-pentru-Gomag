from __future__ import annotations

import asyncio
import os
import subprocess
import sys

from playwright.async_api import async_playwright


def _pw_writable_browsers_path() -> str:
    # Streamlit Cloud allows writing under /home/adminuser
    home = os.path.expanduser("~")
    return os.path.join(home, ".cache", "ms-playwright")


def _ensure_playwright_chromium_installed() -> None:
    """Install Chromium browser for Playwright at runtime (best-effort).

    We install into a **writable** cache path, not inside site-packages.
    Runs at most once per process.
    """
    if os.environ.get("PW_CHROMIUM_READY") == "1":
        return

    browsers_path = _pw_writable_browsers_path()
    os.makedirs(browsers_path, exist_ok=True)
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = browsers_path

    # Install chromium only (no apt deps here)
    proc = subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"playwright_install_failed (code={proc.returncode}):\n{proc.stdout}")

    os.environ["PW_CHROMIUM_READY"] = "1"


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
        if "Executable doesn't exist" in msg or "playwright install" in msg:
            # Try install into writable cache and retry once
            _ensure_playwright_chromium_installed()
            return asyncio.run(render_html(url, wait_ms=wait_ms))
        raise
