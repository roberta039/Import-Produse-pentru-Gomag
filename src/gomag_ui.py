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


async def import_file_async(creds: GomagCreds, file_path: str) -> str:
    cfg = _load_cfg()
    _ensure_playwright_chromium_installed()

    base = creds.base_url.rstrip("/")
    add_url = base + cfg["gomag"]["import"]["url_path"]
    list_url = base + "/gomag/product/import/list"

    def _extract_first_row(html: str):
        soup = BeautifulSoup(html or "", "lxml")
        row = soup.select_one("table tbody tr")
        if not row:
            return "", "", ""
        tds = [td.get_text(" ", strip=True) for td in row.find_all("td")]
        first_text = " | ".join([t for t in tds if t])
        status_txt = tds[-1] if tds else ""
        a = row.select_one("td a")
        href = a.get("href") if a else ""
        return first_text.strip(), status_txt.strip(), (href or "").strip()

    async def _goto_and_get_html(url: str):
        await _goto_with_fallback(page, url)
        await _wait_render(page, 1500)
        html = await page.content()
        if html.strip().replace(" ", "") == "<html><head></head><body></body></html>":
            await page.wait_for_timeout(1200)
            try:
                await page.reload(wait_until="domcontentloaded", timeout=120000)
            except Exception:
                pass
            await _wait_render(page, 1500)
            html = await page.content()
        return html

    async def _upload_file_robust():
        # Best-effort show hidden file inputs
        try:
            await page.evaluate("""() => {
                document.querySelectorAll('input[type=file]').forEach(el => {
                    el.style.display='block';
                    el.style.visibility='visible';
                    el.style.opacity='1';
                    el.removeAttribute('hidden');
                });
            }""")
        except Exception:
            pass

        async def _try_locator(loc):
            try:
                cnt = await loc.count()
                if cnt == 0:
                    return False
                for i in range(cnt):
                    try:
                        await loc.nth(i).set_input_files(file_path, timeout=60000)
                        return True
                    except Exception:
                        continue
                return False
            except Exception:
                return False

        # 1) main page
        if await _try_locator(page.locator('input[type="file"]')):
            return True

        # 2) configured selector (if any)
        sel = cfg["gomag"]["import"].get("file_input_selector")
        if sel and sel != 'input[type="file"]':
            if await _try_locator(page.locator(sel)):
                return True

        # 3) frames
        for fr in page.frames:
            if fr == page.main_frame:
                continue
            if await _try_locator(fr.locator('input[type="file"]')):
                return True

        return False

    async with async_playwright() as p:
        browser, context, page = await _launch_ctx(p)
        try:
            await _login(page, creds, cfg)

            # Snapshot first row before
            before_html = ""
            try:
                before_html = await _goto_and_get_html(list_url)
            except Exception:
                before_html = ""
            before_first, _, _ = _extract_first_row(before_html)

            # Go to import/add
            await _goto_and_get_html(add_url)

            # Upload
            ok = await _upload_file_robust()
            if not ok:
                try:
                    os.makedirs("debug_artifacts", exist_ok=True)
                    await page.screenshot(path="debug_artifacts/gomag_upload_no_file_input.png", full_page=True)
                    with open("debug_artifacts/gomag_upload_no_file_input.html", "w", encoding="utf-8") as f:
                        f.write(await page.content())
                except Exception:
                    pass
                raise RuntimeError("Upload esuat: nu am gasit input[type=file] utilizabil pe pagina (nici in iframe).")

            await _wait_render(page, 1200)

            # Click Start Import
            btn = page.locator('button:has-text("Start Import"), a:has-text("Start Import"), [role="button"]:has-text("Start Import")').first
            if await btn.count() == 0:
                raise RuntimeError("Nu gasesc butonul 'Start Import'.")
            await btn.click(timeout=15000, force=True)
            await page.wait_for_timeout(2500)

            # Read list
            after_html = await _goto_and_get_html(list_url)
            first_text, status_txt, href = _extract_first_row(after_html)

            if before_first and first_text and first_text == before_first:
                return "Start Import apasat, dar nu a aparut un import nou in lista."

            if not first_text:
                try:
                    os.makedirs("debug_artifacts", exist_ok=True)
                    await page.screenshot(path="debug_artifacts/gomag_import_list_empty.png", full_page=True)
                    with open("debug_artifacts/gomag_import_list_empty.html", "w", encoding="utf-8") as f:
                        f.write(after_html)
                except Exception:
                    pass
                return "Import nou detectat, dar nu am putut extrage randul din lista (tabel lipsa/HTML gol). Am salvat debug_artifacts/gomag_import_list_empty.*"

            # If errors, try open details and extract
            if "erori" in (status_txt or "").lower() or "erori" in first_text.lower():
                if href:
                    if href.startswith("/"):
                        det_url = base + href
                    elif href.startswith("http"):
                        det_url = href
                    else:
                        det_url = base + "/" + href.lstrip("/")
                    det_html = await _goto_and_get_html(det_url)
                    soup = BeautifulSoup(det_html or "", "lxml")
                    if "Erori Import" in soup.get_text(" ", strip=True):
                        errs = []
                        for tr in soup.select("table tbody tr")[:10]:
                            tds = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
                            if tds:
                                errs.append(" | ".join(tds))
                        if errs:
                            return "Finalizat cu erori. Primele erori:\n- " + "\n- ".join(errs)

                return f"Finalizat cu erori. Status='{status_txt}'. Primul rand: {first_text[:200]}"

            return f"OK: import nou detectat. Status='{status_txt}'. Primul rand: {first_text[:200]}"

        finally:
            await context.close()
            await browser.close()

def import_file(creds: GomagCreds, file_path: str) -> str:
    return asyncio.run(import_file_async(creds, file_path))
