from __future__ import annotations

import asyncio
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import List, Tuple

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


async def _wait_render(page, extra_ms: int = 800):
    # Networkidle is often best for dashboards with XHR
    try:
        await page.wait_for_load_state("networkidle", timeout=30000)
    except Exception:
        pass
    await page.wait_for_timeout(extra_ms)


# ========= Gomag helpers =========

@dataclass
class GomagCreds:
    base_url: str
    username: str
    password: str


def _dashboard_url(base: str) -> str:
    return base.rstrip("/") + "/gomag/dashboard"


def _categories_url(base: str) -> str:
    # user confirmed
    return base.rstrip("/") + "/gomag/product/category/list"


def _looks_like_login(html: str) -> bool:
    s = html.lower()
    return ("type=\"password\"" in s) and ("login" in s or "autent" in s)


async def _login(page, creds: GomagCreds):
    await _goto_with_fallback(page, _dashboard_url(creds.base_url))
    await _wait_render(page, 600)

    # Fill login form (generic selectors)
    await page.fill(
        'input[type="email"], input[name*="email" i], input[id*="email" i], input[name*="user" i], input[placeholder*="email" i], input[placeholder*="user" i]',
        creds.username,
    )
    await page.fill(
        'input[type="password"], input[name*="pass" i], input[id*="pass" i], input[placeholder*="parol" i], input[placeholder*="pass" i]',
        creds.password,
    )

    # Submit
    try:
        await page.click(
            'button[type="submit"], input[type="submit"], button:has-text("Login"), button:has-text("Autentificare")',
            timeout=8000,
        )
    except Exception:
        await page.keyboard.press("Enter")

    await _wait_render(page, 1400)


def _dedupe_keep_order(items: List[str]) -> List[str]:
    seen = set()
    out = []
    for x in items:
        x = re.sub(r"\s+", " ", x).strip()
        if not x:
            continue
        if x.lower() in seen:
            continue
        seen.add(x.lower())
        out.append(x)
    return out


def _parse_categories_from_html(html: str) -> Tuple[List[str], str]:
    soup = BeautifulSoup(html, "lxml")

    cats: List[str] = []

    # 1) Preferred: table first column
    rows = soup.select("table tbody tr")
    for tr in rows:
        tds = tr.find_all("td")
        if not tds:
            continue
        name = tds[0].get_text(" ", strip=True).replace("\u00a0", " ").strip()
        name = name.split("ID:")[0].strip()
        if name:
            cats.append(name)

    if cats:
        return _dedupe_keep_order(cats), "table"

    # 2) Fallback: links that look like category edit/view inside gomag
    for a in soup.select('a[href*="/gomag/product/category"]'):
        txt = a.get_text(" ", strip=True)
        if txt and len(txt) < 80:
            cats.append(txt)

    if cats:
        return _dedupe_keep_order(cats), "links"

    # 3) Fallback: any strong/bold in list
    for el in soup.select("strong, b"):
        txt = el.get_text(" ", strip=True)
        if txt and len(txt) < 80:
            cats.append(txt)

    return _dedupe_keep_order(cats), "fallback"


async def fetch_categories_async(creds: GomagCreds) -> List[str]:
    _ensure_playwright_chromium_installed()

    async with async_playwright() as p:
        browser, context, page = await _launch_ctx(p)
        try:
            await _login(page, creds)

            url = _categories_url(creds.base_url)
            await _goto_with_fallback(page, url)
            await _wait_render(page, 1200)

            # Try to wait for either table rows or something that indicates list loaded
            try:
                await page.wait_for_selector("table tbody tr, a[href*='/gomag/product/category']", timeout=20000)
            except Exception:
                pass

            await _wait_render(page, 800)
            html = await page.content()

            # Detect login redirect (common reason for 0 cats)
            if _looks_like_login(html):
                raise RuntimeError("Login Gomag a esuat sau sesiunea nu s-a pastrat (am ajuns inapoi la pagina de login).")

            cats, method = _parse_categories_from_html(html)
            if not cats:
                # write debug artifact to help if still needed
                dbg = os.path.join("/tmp", "gomag_categories_debug.html")
                try:
                    with open(dbg, "w", encoding="utf-8") as f:
                        f.write(html)
                except Exception:
                    pass
                raise RuntimeError("Nu am putut extrage categoriile (pagina s-a incarcat, dar nu am gasit tabelul/link-urile).")

            return cats
        finally:
            await context.close()
            await browser.close()


def fetch_categories(creds: GomagCreds) -> List[str]:
    return asyncio.run(fetch_categories_async(creds))


# import_file should remain in your repo; app.py imports it from here.
# If your existing repo already has import_file/import_file_async implemented in this module,
# keep them below unchanged. This patch only modifies category loading robustness.
