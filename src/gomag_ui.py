from __future__ import annotations

import asyncio
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import List, Optional, Tuple

import yaml
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright


# --- URL normalization (force https for Gomag where possible) ---
def _normalize_base_url(base_url: str) -> str:
    base = (base_url or "").strip()
    if base.startswith("http://"):
        return "https://" + base[len("http://"):].lstrip("/")
    return base


# ============================================================
# Playwright runtime install + SSL/TLS workaround (Streamlit Cloud)
# ============================================================

def _pw_writable_browsers_path() -> str:
    home = os.path.expanduser("~")
    return os.path.join(home, ".cache", "ms-playwright")


def _ensure_playwright_chromium_installed() -> None:
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
    url = (url or "").strip()
    if url.startswith("http://"):
        primary = "https://" + url[len("http://"):]
    else:
        primary = url
    fallback = "http://" + primary[len("https://"):] if primary.startswith("https://") else None

    last_err = None
    for target in [primary, fallback] if fallback else [primary]:
        if not target:
            continue
        try:
            resp = await page.goto(target, wait_until="domcontentloaded", timeout=120000)
            try:
                await page.wait_for_load_state("networkidle", timeout=45000)
            except Exception:
                pass
            if resp is not None and resp.status >= 400:
                raise RuntimeError(f"HTTP {resp.status} at {target}")
            html = await page.content()
            if html.strip().replace(" ", "") in ("<html><head></head><body></body></html>",):
                await page.wait_for_timeout(1500)
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
    try:
        await page.wait_for_load_state("networkidle", timeout=30000)
    except Exception:
        pass
    await page.wait_for_timeout(extra_ms)


# ============================================================
# Config + Login
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
    base = _normalize_base_url(creds.base_url).rstrip("/")
    login_url = base + (creds.dashboard_path or "/gomag/dashboard")

    await _goto_with_fallback(page, login_url)
    await _wait_render(page, 700)

    await page.fill(cfg["gomag"]["login"]["username_selector"], creds.username)
    await page.fill(cfg["gomag"]["login"]["password_selector"], creds.password)

    try:
        await page.click(cfg["gomag"]["login"]["submit_selector"], timeout=8000)
    except Exception:
        await page.keyboard.press("Enter")

    await _wait_render(page, int(cfg["gomag"]["login"].get("post_login_wait", 2.0) * 1000))


def _dedupe_keep_order(items: List[str]) -> List[str]:
    seen = set()
    out = []
    for x in items:
        x = re.sub(r"\s+", " ", (x or "").strip())
        if not x:
            continue
        k = x.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(x)
    return out


def _looks_like_login(html: str) -> bool:
    s = (html or "").lower()
    return ("type=\"password\"" in s) and ("login" in s or "autent" in s or "parol" in s)


# ============================================================
# Categories
# ============================================================

def _parse_categories_from_html(html: str) -> List[str]:
    soup = BeautifulSoup(html or "", "lxml")
    cats: List[str] = []

    rows = soup.select("table tbody tr")
    for tr in rows:
        tds = tr.find_all("td")
        if not tds:
            continue
        name = tds[0].get_text(" ", strip=True).replace("\u00a0", " ").strip()
        name = name.split("ID:")[0].strip()
        low = name.lower()
        if not name:
            continue
        if low in {"categorie", "categorii", "actiuni", "acțiuni", "nume", "name"}:
            continue
        if len(name) < 2 or len(name) > 80:
            continue
        cats.append(name)

    cats = _dedupe_keep_order(cats)
    if cats:
        return cats

    for a in soup.select('a[href*="/gomag/product/category"]'):
        txt = a.get_text(" ", strip=True)
        if not txt:
            continue
        low = txt.lower()
        if low in {"categorie", "categorii"}:
            continue
        if len(txt) < 2 or len(txt) > 80:
            continue
        cats.append(txt)

    return _dedupe_keep_order(cats)


async def fetch_categories_async(creds: GomagCreds) -> List[str]:
    cfg = _load_cfg()
    _ensure_playwright_chromium_installed()

    base = _normalize_base_url(creds.base_url).rstrip("/")
    url_path = cfg.get("gomag", {}).get("categories", {}).get("url_path") or "/gomag/product/category/list"
    url = base + url_path

    async with async_playwright() as p:
        browser, context, page = await _launch_ctx(p)
        try:
            await _login(page, creds, cfg)

            await _goto_with_fallback(page, url)
            await _wait_render(page, 1400)

            try:
                await page.wait_for_selector("table tbody tr, a[href*='/gomag/product/category']", timeout=20000)
            except Exception:
                pass

            await _wait_render(page, 800)
            html = await page.content()

            if _looks_like_login(html):
                raise RuntimeError("Login Gomag a esuat sau sesiunea nu s-a pastrat (am ajuns inapoi la pagina de login).")

            cats = _parse_categories_from_html(html)
            if not cats:
                raise RuntimeError("Nu am putut extrage categoriile (pagina s-a incarcat, dar nu am gasit tabelul/link-urile).")
            return cats
        finally:
            await context.close()
            await browser.close()


def fetch_categories(creds: GomagCreds) -> List[str]:
    return asyncio.run(fetch_categories_async(creds))


# ============================================================
# Import helpers
# ============================================================

async def _set_input_files_anywhere(page, file_path: str, timeout_ms: int = 60000) -> str:
    candidates = [
        'input[type="file"]',
        'input[type="file"][name]',
        'input[type="file"][accept]',
        'input[accept*="csv" i]',
        'input[accept*="xls" i]',
        'input[accept*="xlsx" i]',
        'input',  # last resort (your current working message was Upload=input:input)
    ]

    for sel in candidates:
        try:
            loc = page.locator(sel).first
            await loc.wait_for(state="attached", timeout=timeout_ms // 3)
            try:
                await page.evaluate(
                    """(sel) => {
                        const el = document.querySelector(sel);
                        if (!el) return;
                        el.style.display = 'block';
                        el.style.visibility = 'visible';
                        el.style.opacity = 1;
                        el.removeAttribute('hidden');
                    }""", sel
                )
            except Exception:
                pass
            await loc.set_input_files(file_path, timeout=timeout_ms // 3)
            return f"input:{sel}"
        except Exception:
            continue

    raise RuntimeError("Nu am gasit input pentru upload (nici macar generic).")


async def _try_click_start_import(page) -> Tuple[bool, Optional[str]]:
    start_selectors = [
        'button:has-text("Start Import")',
        'a:has-text("Start Import")',
        '[role="button"]:has-text("Start Import")',
        'text=Start Import',
    ]
    last_err = None
    for sel in start_selectors:
        try:
            loc = page.locator(sel).first
            if await loc.count() == 0:
                continue
            await loc.scroll_into_view_if_needed(timeout=5000)
            await loc.wait_for(state="visible", timeout=15000)
            try:
                await loc.click(timeout=8000, force=True)
            except Exception:
                await page.evaluate("(el) => el.click()", await loc.element_handle())
            return True, None
        except Exception as e:
            last_err = str(e)
            continue
    return False, last_err


def _parse_import_list_counts(html: str) -> Tuple[Optional[int], Optional[int], Optional[str]]:
    """Best-effort parse: returns (imported_products, errors, status_text)."""
    soup = BeautifulSoup(html or "", "lxml")
    # Try first table row in list page
    row = soup.select_one("table tbody tr")
    if not row:
        return None, None, None
    tds = [td.get_text(" ", strip=True) for td in row.find_all("td")]
    txt = " | ".join(tds)
    # extract first two ints seen (often products / errors)
    nums = [int(x) for x in re.findall(r"\b(\d+)\b", txt)]
    imported = nums[0] if len(nums) > 0 else None
    errors = nums[1] if len(nums) > 1 else None
    status = tds[0] if tds else None
    return imported, errors, txt[:200]


async def _check_latest_import_result(page, base: str) -> str:
    # Common list URL; if it 404s, we just return "unknown"
    candidates = [
        "/gomag/product/import/list",
        "/gomag/product/import",
        "/gomag/product/imports",
    ]
    last = None
    for path in candidates:
        try:
            await _goto_with_fallback(page, base + path)
            await _wait_render(page, 1200)
            html = await page.content()
            imported, errors, status = _parse_import_list_counts(html)
            if imported is not None or errors is not None:
                return f"Rezultat import (estimare): produse={imported}, erori={errors}, raw='{status}'"
            last = path
        except Exception:
            continue
    return f"Nu am putut verifica rezultatul (nu am gasit pagina list). Ultimul incercat: {last}"


# ============================================================
# Import in Gomag
# ============================================================

async def import_file_async(creds: GomagCreds, file_path: str) -> str:
    cfg = _load_cfg()
    _ensure_playwright_chromium_installed()

    base = _normalize_base_url(creds.base_url).rstrip("/")
    url_path = cfg.get("gomag", {}).get("import", {}).get("url_path") or "/gomag/product/import/add"
    url = base + url_path

    async with async_playwright() as p:
        browser, context, page = await _launch_ctx(p)
        try:
            await _login(page, creds, cfg)

            await _goto_with_fallback(page, url)
            await _wait_render(page, 1400)

            # Upload
            note = await _set_input_files_anywhere(page, file_path, timeout_ms=60000)
            await _wait_render(page, 1400)

            # Wait mapping section (best-effort)
            try:
                await page.wait_for_selector('text="Alege Semnificatia", text="Alege Semnificația", text="Start Import"', timeout=45000)
            except Exception:
                pass

            # Scroll top and click Start Import
            try:
                await page.evaluate("window.scrollTo(0, 0)")
                await page.wait_for_timeout(400)
            except Exception:
                pass

            ok, last_err = await _try_click_start_import(page)
            if not ok:
                # Save debug
                try:
                    os.makedirs("debug_artifacts", exist_ok=True)
                    await page.screenshot(path="debug_artifacts/gomag_after_upload.png", full_page=True)
                    html = await page.content()
                    with open("debug_artifacts/gomag_after_upload.html", "w", encoding="utf-8") as f:
                        f.write(html)
                except Exception:
                    pass
                return (
                    "Am incarcat fisierul, dar nu am putut apasa 'Start Import'. "
                    f"Upload={note}. Ultima eroare click: {last_err}."
                )

            # After clicking, wait a bit and try to detect any confirmation / progress
            await _wait_render(page, 2500)

            # Verify result by checking import list page
            result = await _check_latest_import_result(page, base)

            # If likely 0 imported, warn about file format (Gomag accepts XLS/TSV; XLSX may parse preview but import 0)
            return f"Import pornit (Start Import apasat). Upload={note}. {result}"

        finally:
            await context.close()
            await browser.close()


def import_file(creds: GomagCreds, file_path: str) -> str:
    return asyncio.run(import_file_async(creds, file_path))
