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
    """
    Fix pentru ERR_SSL_PROTOCOL_ERROR:
    - încearcă https
    - dacă pică handshake-ul, încearcă http
    """
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        return
    except Exception:
        if url.startswith("https://"):
            await page.goto("http://" + url[len("https://"):], wait_until="domcontentloaded", timeout=60000)
            return
        raise


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
    login_url = creds.base_url.rstrip("/") + (creds.dashboard_path or "/gomag/dashboard")
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
    url = creds.base_url.rstrip("/") + url_path

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


async def _try_expect_filechooser_click(locator, file_path: str, timeout_ms: int = 8000) -> bool:
    """Click locator and, if it opens a file chooser, set file and return True."""
    try:
        async with locator.page.expect_file_chooser(timeout=timeout_ms) as fc_info:
            await locator.click(timeout=timeout_ms)
        fc = await fc_info.value
        await fc.set_files(file_path)
        return True
    except Exception:
        return False


async def _upload_via_filechooser_sweep(page, file_path: str) -> str:
    """Fallback când NU există <input type=file> în DOM.
    În Gomag uneori uploaderul e un buton/dropzone care deschide dialog nativ.
    Facem un 'sweep' pe texte + clase uzuale + elemente clickabile.
    """
    # Ensure UI is rendered
    try:
        await page.wait_for_load_state("networkidle", timeout=20000)
    except Exception:
        pass
    await page.wait_for_timeout(800)

    # 1) Try by visible texts (Romanian/English)
    texts = [
        "Alege fisier", "Alege fișier",
        "Selecteaza fisier", "Selectează fișier",
        "Incarca fisier", "Încarcă fișier", "Incarca", "Încarcă",
        "Upload", "Choose file", "Browse",
        "Import", "Importa", "Importă",
        "Fisiere", "Fișiere",
    ]
    for t in texts:
        loc = page.get_by_text(t, exact=False).first
        if await loc.count() > 0:
            ok = await _try_expect_filechooser_click(loc, file_path, timeout_ms=7000)
            if ok:
                return f"filechooser:text:{t}"

    # 2) Try common uploader/dropzone classes & buttons
    selectors = [
        "button", "a", "label",
        ".btn", ".button", ".upload", ".uploader", ".import",
        ".dropzone", ".dz-clickable", ".dz-message",
        ".qq-upload-button", ".fine-uploader", ".qq-upload-drop-area",
        "[class*='upload' i]", "[id*='upload' i]",
        "[class*='import' i]", "[id*='import' i]",
        "[class*='file' i]", "[id*='file' i]",
    ]
    for sel in selectors:
        try:
            # only a handful (avoid clicking whole page)
            locs = page.locator(sel)
            n = await locs.count()
            for i in range(min(n, 20)):
                loc = locs.nth(i)
                # skip invisible
                try:
                    if not await loc.is_visible():
                        continue
                except Exception:
                    continue
                ok = await _try_expect_filechooser_click(loc, file_path, timeout_ms=4000)
                if ok:
                    return f"filechooser:sel:{sel}[{i}]"
        except Exception:
            continue

    # 3) Last resort: click center of the largest visible "dropzone-like" div
    try:
        # find candidates in DOM with keywords in class/id
        handle = await page.evaluate_handle("""() => {
            const els = Array.from(document.querySelectorAll('div,section,main'));
            const cand = els
              .filter(e => {
                const s = ((e.id||'') + ' ' + (e.className||'')).toLowerCase();
                return s.includes('drop') || s.includes('upload') || s.includes('import') || s.includes('file');
              })
              .filter(e => e.offsetWidth > 200 && e.offsetHeight > 80)
              .sort((a,b) => (b.offsetWidth*b.offsetHeight) - (a.offsetWidth*a.offsetHeight))[0];
            return cand || null;
        }""")
        if handle:
            loc = page.locator(":is(div,section,main)").filter(has=page.locator("text=Upload")).first  # harmless
            # click the element via JS to trigger file chooser if bound
            try:
                async with page.expect_file_chooser(timeout=8000) as fc_info:
                    await page.evaluate("""(el) => el.click()""", handle)
                fc = await fc_info.value
                await fc.set_files(file_path)
                return "filechooser:js_click:dropzone"
            except Exception:
                pass
    except Exception:
        pass

    # Debug artifacts (help in Streamlit Cloud logs)
    try:
        await page.screenshot(path="/tmp/gomag_import_debug.png", full_page=True)
        html = await page.content()
        with open("/tmp/gomag_import_debug.html", "w", encoding="utf-8") as f:
            f.write(html)
    except Exception:
        pass

    raise RuntimeError(
        "Nu am reusit upload: nu exista <input type=file> si niciun buton/dropzone nu a deschis FileChooser. "
        "Am salvat /tmp/gomag_import_debug.png si /tmp/gomag_import_debug.html (daca platforma permite)."
    )


async def import_file_async(creds: GomagCreds, file_path: str) -> str:
    cfg = _load_cfg()
    _ensure_playwright_chromium_installed()

    url = creds.base_url.rstrip("/") + cfg["gomag"]["import"]["url_path"]

    async with async_playwright() as p:
        browser, context, page = await _launch_ctx(p)
        try:
            await _login(page, creds, cfg)

            await _goto_with_fallback(page, url)
            await _wait_render(page, 1600)

            # 1) try config file input (if any)
            note = ""
            file_sel = cfg.get("gomag", {}).get("import", {}).get("file_input_selector")
            if file_sel:
                try:
                    loc = page.locator(file_sel).first
                    await loc.wait_for(state="attached", timeout=15000)
                    await loc.set_input_files(file_path, timeout=30000)
                    note = f"cfg:{file_sel}"
                except Exception:
                    note = ""

            # 2) try generic input search (main + iframes) - if helper exists in your file, keep it;
            # if not, we fall back to FileChooser sweep directly.
            if not note and "async def _set_input_files_anywhere" in globals():
                try:
                    note = await _set_input_files_anywhere(page, file_path, timeout_ms=60000)  # type: ignore[name-defined]
                except Exception:
                    note = ""

            # 3) FileChooser sweep (no <input type=file>)
            if not note:
                note = await _upload_via_filechooser_sweep(page, file_path)

            await _wait_render(page, 1200)

            # Start import (if exists)
            try:
                await page.click(cfg["gomag"]["import"]["start_import_selector"], timeout=7000)
                await page.wait_for_timeout(1500)
                return f"Fisier incarcat ({note}). Import pornit (daca Gomag nu a cerut pasi suplimentari)."
            except Exception:
                return (
                    f"Fisier incarcat ({note}). Nu am putut porni importul automat "
                    "(probabil e nevoie de mapare coloane/manual la prima rulare)."
                )
        finally:
            await context.close()
            await browser.close()

def import_file(creds: GomagCreds, file_path: str) -> str:
    return asyncio.run(import_file_async(creds, file_path))
