from __future__ import annotations

import asyncio
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import List

import yaml
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

# --- URL normalization (force https for Gomag where possible) ---
def _normalize_base_url(base_url: str) -> str:
    base = (base_url or '').strip()
    if base.startswith('http://'):
        # Gomag admin usually works best over HTTPS; we ignore TLS errors in Playwright anyway.
        return 'https://' + base[len('http://'):].lstrip('/')
    return base


# ============================================================
# Playwright runtime install + SSL/TLS workaround (Streamlit Cloud)
# ============================================================

def _pw_writable_browsers_path() -> str:
    home = os.path.expanduser("~")
    return os.path.join(home, ".cache", "ms-playwright")


def _ensure_playwright_chromium_installed() -> None:
    """
    Ensure Playwright Chromium exists. Safe for Streamlit Cloud.
    Installs into a writable path: ~/.cache/ms-playwright
    """
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
    """Robust navigation for Streamlit Cloud + Gomag:
    - forces https first (even if url is http)
    - ignores TLS errors (handled in context)
    - captures response status for debugging
    - retries once if HTML shell is empty
    """
    url = (url or "").strip()
    if url.startswith("http://"):
        primary = "https://" + url[len("http://"):]
    else:
        primary = url
    fallback = None
    if primary.startswith("https://"):
        fallback = "http://" + primary[len("https://"):]

    last_err = None
    for attempt, target in enumerate([primary, fallback] if fallback else [primary], start=1):
        if not target:
            continue
        try:
            resp = await page.goto(target, wait_until="domcontentloaded", timeout=120000)
            # wait for SPA shell / scripts
            try:
                await page.wait_for_load_state("networkidle", timeout=45000)
            except Exception:
                pass

            # If response exists, check status
            if resp is not None:
                status = resp.status
                if status >= 400:
                    raise RuntimeError(f"HTTP {status} at {target}")
            # Sometimes we get an empty shell; retry once after a short delay
            html = await page.content()
            if html.strip() in ("<html><head></head><body></body></html>", "<html><head></head><body></body></html>\n"):
                if attempt == 1:
                    await page.wait_for_timeout(2000)
                    await page.reload(wait_until="domcontentloaded", timeout=120000)
                    try:
                        await page.wait_for_load_state("networkidle", timeout=45000)
                    except Exception:
                        pass
            return
        except Exception as e:
            last_err = e
            continue

    raise RuntimeError(f"Navigation failed. primary={primary} fallback={fallback} last={last_err}")
async def _wait_render(page, extra_ms: int = 800):
    # Pentru pagini cu XHR: networkidle e mai robust
    try:
        await page.wait_for_load_state("networkidle", timeout=30000)
    except Exception:
        pass
    await page.wait_for_timeout(extra_ms)


def _looks_like_login(html: str) -> bool:
    s = (html or "").lower()
    return ("type=\"password\"" in s) and ("login" in s or "autent" in s or "parol" in s)


def _dedupe_keep_order(items: List[str]) -> List[str]:
    seen = set()
    out = []
    for x in items:
        x = re.sub(r"\s+", " ", (x or "").strip())
        if not x:
            continue
        key = x.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(x)
    return out


def _parse_categories_from_html(html: str) -> List[str]:
    soup = BeautifulSoup(html or "", "lxml")

    cats: List[str] = []

    # 1) tabel - prima coloana
    rows = soup.select("table tbody tr")
    for tr in rows:
        tds = tr.find_all("td")
        if not tds:
            continue
        name = tds[0].get_text(" ", strip=True).replace("\u00a0", " ").strip()
        name = name.split("ID:")[0].strip()
        if name:
            cats.append(name)

    cats = _dedupe_keep_order(cats)
    if cats:
        return cats

    # 2) fallback: link-uri care par a fi categorii
    for a in soup.select('a[href*="/gomag/product/category"]'):
        txt = a.get_text(" ", strip=True)
        if txt and len(txt) < 80:
            cats.append(txt)

    return _dedupe_keep_order(cats)


# ============================================================
# Gomag UI API (folosit de app.py)
# ============================================================

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
    login_url = _normalize_base_url(creds.base_url).rstrip("/") + (creds.dashboard_path or "/gomag/dashboard")
    await _goto_with_fallback(page, login_url)
    await _wait_render(page, 600)

    # selectori din config.yaml (compatibil cu versiunea ta)
    await page.fill(cfg["gomag"]["login"]["username_selector"], creds.username)
    await page.fill(cfg["gomag"]["login"]["password_selector"], creds.password)
    await page.click(cfg["gomag"]["login"]["submit_selector"])

    await _wait_render(page, int(cfg["gomag"]["login"].get("post_login_wait", 2.0) * 1000))


async def fetch_categories_async(creds: GomagCreds) -> List[str]:
    cfg = _load_cfg()
    _ensure_playwright_chromium_installed()

    # IMPORTANT: user a confirmat URL-ul corect:
    # /gomag/product/category/list
    url_path = cfg.get("gomag", {}).get("categories", {}).get("url_path") or "/gomag/product/category/list"
    url = _normalize_base_url(creds.base_url).rstrip("/") + url_path

    async with async_playwright() as p:
        browser, context, page = await _launch_ctx(p)
        try:
            await _login(page, creds, cfg)

            await _goto_with_fallback(page, url)
            await _wait_render(page, 1200)

            # 1) încearcă selectorul din config (dacă există)
            cats: List[str] = []
            item_selector = cfg.get("gomag", {}).get("categories", {}).get("item_selector")
            if item_selector:
                try:
                    await page.wait_for_selector(item_selector, timeout=15000)
                except Exception:
                    pass
                try:
                    items = await page.query_selector_all(item_selector)
                    for it in items:
                        try:
                            txt = (await it.inner_text()).strip()
                            if txt:
                                cats.append(txt)
                        except Exception:
                            continue
                    cats = _dedupe_keep_order(cats)
                except Exception:
                    cats = []

            # 2) dacă selectorul nu a produs nimic, parsează HTML (tabel/link-uri)
            if not cats:
                # așteaptă orice indicator de listă: tabel sau link-uri de categorie
                try:
                    await page.wait_for_selector("table tbody tr, a[href*='/gomag/product/category']", timeout=20000)
                except Exception:
                    pass
                await _wait_render(page, 800)
                html = await page.content()

                if _looks_like_login(html):
                    raise RuntimeError(
                        "Login Gomag a esuat sau sesiunea nu s-a pastrat (am ajuns inapoi la pagina de login)."
                    )

                cats = _parse_categories_from_html(html)

            if not cats:
                raise RuntimeError(
                    "Nu am putut extrage categoriile (pagina s-a incarcat, dar nu am gasit tabelul/link-urile)."
                )

            return cats
        finally:
            await context.close()
            await browser.close()


def fetch_categories(creds: GomagCreds) -> List[str]:
    return asyncio.run(fetch_categories_async(creds))


async def import_file_async(creds: GomagCreds, file_path: str) -> str:
    cfg = _load_cfg()
    _ensure_playwright_chromium_installed()

    url = _normalize_base_url(creds.base_url).rstrip("/") + cfg["gomag"]["import"]["url_path"]

    async with async_playwright() as p:
        browser, context, page = await _launch_ctx(p)
        try:
            await _login(page, creds, cfg)

            await _goto_with_fallback(page, url)
            await _wait_render(page, 1000)

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
            await context.close()
            await browser.close()


def import_file(creds: GomagCreds, file_path: str) -> str:
    return asyncio.run(import_file_async(creds, file_path))
