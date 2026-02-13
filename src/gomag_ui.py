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
    login_url = creds.base_url.rstrip("/") + (creds.dashboard_path or "/gomag/dashboard")
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

    # Prefer: table first column
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

    # Fallback: category links
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

    url_path = cfg.get("gomag", {}).get("categories", {}).get("url_path") or "/gomag/product/category/list"
    url = creds.base_url.rstrip("/") + url_path

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
# Import: upload file even if DOM has no <input type=file>
# ============================================================

async def _set_input_files_anywhere(page, file_path: str, timeout_ms: int = 60000) -> str:
    candidates = [
        'input[type="file"]',
        'input[type="file"][name]',
        'input[type="file"][accept]',
        'input[accept*="csv" i]',
        'input[accept*="xls" i]',
        'input[accept*="xlsx" i]',
    ]

    # Main page
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
            return f"main:{sel}"
        except Exception:
            continue

    # Iframes
    for fr in page.frames:
        if fr == page.main_frame:
            continue
        for sel in candidates:
            try:
                loc = fr.locator(sel).first
                await loc.wait_for(state="attached", timeout=timeout_ms // 3)
                try:
                    await fr.evaluate(
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
                return f"frame:{sel}"
            except Exception:
                continue

    raise RuntimeError("Nu am gasit niciun <input type=file> pe pagina (nici in iframe-uri).")


async def _try_expect_filechooser_click(page, locator, file_path: str, timeout_ms: int = 8000) -> bool:
    try:
        async with page.expect_file_chooser(timeout=timeout_ms) as fc_info:
            await locator.click(timeout=timeout_ms)
        fc = await fc_info.value
        await fc.set_files(file_path)
        return True
    except Exception:
        return False


async def _upload_via_filechooser_sweep(page, file_path: str) -> str:
    try:
        await page.wait_for_load_state("networkidle", timeout=20000)
    except Exception:
        pass
    await page.wait_for_timeout(800)

    # 1) by visible texts
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
            ok = await _try_expect_filechooser_click(page, loc, file_path, timeout_ms=7000)
            if ok:
                return f"filechooser:text:{t}"

    # 2) common uploader/dropzone elements (limit clicks)
    selectors = [
        ".dropzone", ".dz-clickable", ".dz-message",
        ".qq-upload-button", ".fine-uploader", ".qq-upload-drop-area",
        "[class*='upload' i]", "[id*='upload' i]",
        "[class*='import' i]", "[id*='import' i]",
        "[class*='file' i]", "[id*='file' i]",
        "button", "a", "label",
    ]
    for sel in selectors:
        try:
            locs = page.locator(sel)
            n = await locs.count()
            for i in range(min(n, 25)):
                loc = locs.nth(i)
                try:
                    if not await loc.is_visible():
                        continue
                except Exception:
                    continue
                ok = await _try_expect_filechooser_click(page, loc, file_path, timeout_ms=4000)
                if ok:
                    return f"filechooser:sel:{sel}[{i}]"
        except Exception:
            continue

    # Inline debug + artifacts in writable folder
    try:
        current_url = page.url
    except Exception:
        current_url = "unknown"
    try:
        current_title = await page.title()
    except Exception:
        current_title = "unknown"
    try:
        inputs_cnt = await page.locator('input[type="file"]').count()
    except Exception:
        inputs_cnt = -1
    try:
        btn_texts = await page.locator("button, a, label").all_inner_texts()
        btn_texts = [t.strip() for t in btn_texts if t and t.strip()]
        btn_texts = btn_texts[:40]
    except Exception:
        btn_texts = []

    html = ""
    try:
        os.makedirs("debug_artifacts", exist_ok=True)
        await page.screenshot(path="debug_artifacts/gomag_import_debug.png", full_page=True)
        html = await page.content()
        with open("debug_artifacts/gomag_import_debug.html", "w", encoding="utf-8") as f:
            f.write(html)
    except Exception:
        pass

    html_snip = (html or "")[:2000]
    raise RuntimeError(
        "Nu am reusit upload: nu exista <input type=file> si niciun buton/dropzone nu a deschis FileChooser.\n"
        f"URL: {current_url}\n"
        f"TITLE: {current_title}\n"
        f"input[type=file] count: {inputs_cnt}\n"
        f"Butoane/Link-uri detectate (max 40): {btn_texts}\n"
        "Am salvat debug_artifacts/gomag_import_debug.png si debug_artifacts/gomag_import_debug.html (daca platforma permite).\n"
        f"HTML snippet (primele 2000 caractere):\n{html_snip}"
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

            # 1) try config file input selector
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

            # 2) try generic input search
            if not note:
                try:
                    note = await _set_input_files_anywhere(page, file_path, timeout_ms=60000)
                except Exception:
                    note = ""

            # 3) file chooser sweep fallback
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
