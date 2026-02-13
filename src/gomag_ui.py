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
    """Uploads file, clicks Start Import, then reads the newest import row status.
    If status indicates errors, opens the import details page and extracts first errors.
    """
    cfg = _load_cfg()
    _ensure_playwright_chromium_installed()

    base = creds.base_url.rstrip("/")
    add_url = base + cfg["gomag"]["import"]["url_path"]
    list_url = base + "/gomag/product/import/list"

    async with async_playwright() as p:
        browser, context, page = await _launch_ctx(p)
        try:
            await _login(page, creds, cfg)

            # Snapshot first row before
            before_first = ""
            try:
                await _goto_with_fallback(page, list_url)
                await _wait_render(page, 1200)
                before_first = (await page.locator("table tbody tr").first.inner_text(timeout=6000)).strip()
            except Exception:
                before_first = ""

            # Add page
            await _goto_with_fallback(page, add_url)
            await _wait_render(page, 1400)

            # Make file inputs visible
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

            file_inputs = page.locator('input[type="file"]')
            n = await file_inputs.count()
            if n == 0:
                raise RuntimeError("Nu exista input[type=file] pe pagina /import/add (uploader custom / iframe).")

            uploaded = False
            for i in range(n):
                try:
                    await file_inputs.nth(i).set_input_files(file_path, timeout=60000)
                    uploaded = True
                    break
                except Exception:
                    continue
            if not uploaded:
                raise RuntimeError("Nu am putut incarca fisierul pe niciun input[type=file].")

            await _wait_render(page, 1400)

            # Confirm attachment
            fname = os.path.basename(file_path)
            attached = False
            try:
                if await page.locator(f'text="{fname}"').count() > 0:
                    attached = True
            except Exception:
                pass
            if not attached:
                try:
                    attached = bool(await page.evaluate("""() => {
                        const el = document.querySelector('input[type=file]');
                        return !!(el && el.files && el.files.length);
                    }"""))
                except Exception:
                    attached = False
            if not attached:
                try:
                    os.makedirs("debug_artifacts", exist_ok=True)
                    await page.screenshot(path="debug_artifacts/gomag_upload_not_attached.png", full_page=True)
                    with open("debug_artifacts/gomag_upload_not_attached.html", "w", encoding="utf-8") as f:
                        f.write(await page.content())
                except Exception:
                    pass
                raise RuntimeError("Fisierul nu pare atasat (nu apare numele fisierului / input.files e gol).")

            # Unmap TVA fields
            try:
                await page.evaluate("""() => {
                    const targets = ['Pretul Include TVA', 'Prețul Include TVA', 'Cota TVA'];
                    const norm = (s) => (s||'').toLowerCase().replace(/\s+/g,' ').trim();
                    const tnorm = targets.map(norm);
                    const nodes = Array.from(document.querySelectorAll('th, td, label, div, span'));
                    for (const el of nodes) {
                        const txt = norm(el.textContent);
                        if (!txt) continue;
                        if (!tnorm.some(t => txt.includes(t))) continue;
                        let root = el.closest('th') || el.closest('td') || el.closest('label') || el.parentElement;
                        if (!root) continue;
                        const cb = root.querySelector('input[type="checkbox"]');
                        if (cb && cb.checked) cb.click();
                    }
                }""")
            except Exception:
                pass

            # Click Start Import
            try:
                await page.evaluate("window.scrollTo(0, 0)")
                await page.wait_for_timeout(300)
            except Exception:
                pass

            btn = page.locator('button:has-text("Start Import"), a:has-text("Start Import"), [role="button"]:has-text("Start Import")').first
            if await btn.count() == 0:
                raise RuntimeError("Nu gasesc butonul 'Start Import'.")
            await btn.click(timeout=10000, force=True)

            # Wait a bit so Gomag registers import
            await page.wait_for_timeout(2500)

            # Go to list and find newest row (first row) - must differ from before
            await _goto_with_fallback(page, list_url)
            await _wait_render(page, 1400)

            row = page.locator("table tbody tr").first
            try:
                await row.wait_for(state="visible", timeout=15000)
            except Exception:
                pass

            first_text = ""
            try:
                first_text = (await row.inner_text(timeout=8000)).strip()
            except Exception:
                first_text = ""

            if before_first and first_text and first_text == before_first:
                return "Start Import apasat, dar nu a aparut un import nou in lista."

            # Extract status cell if possible (often last td)
            status_txt = ""
            try:
                tds = row.locator("td")
                td_count = await tds.count()
                if td_count > 0:
                    status_txt = (await tds.nth(td_count - 1).inner_text()).strip()
            except Exception:
                status_txt = ""

            # If errors, open details by clicking file name link in first cell
            if ("erori" in (status_txt or "").lower()) or ("erori" in (first_text or "").lower()):
                try:
                    link = row.locator("td a").first
                    if await link.count() > 0:
                        await link.click(timeout=10000)
                        await _wait_render(page, 1400)

                        # Find error table and return first few rows
                        if await page.locator("text=Erori Import").count() > 0:
                            errs = []
                            erows = page.locator("table tbody tr")
                            nerr = await erows.count()
                            for i in range(min(nerr, 10)):
                                t = await erows.nth(i).inner_text()
                                errs.append(re.sub(r"\s+", " ", t).strip())
                            return "Finalizat cu erori. Primele erori:\n- " + "\n- ".join(errs)
                except Exception:
                    pass

                # Could not open details; save artifacts
                try:
                    os.makedirs("debug_artifacts", exist_ok=True)
                    await page.screenshot(path="debug_artifacts/gomag_import_errors_list.png", full_page=True)
                    with open("debug_artifacts/gomag_import_errors_list.html", "w", encoding="utf-8") as f:
                        f.write(await page.content())
                except Exception:
                    pass
                return f"Finalizat cu erori, dar nu am putut extrage lista. Status='{status_txt}'. Primul rand='{first_text[:180]}'"

            return f"OK: import nou detectat. Status='{status_txt}'. Primul rand: {first_text[:180]}"

        finally:
            await context.close()
            await browser.close()

def import_file(creds: GomagCreds, file_path: str) -> str:
    return asyncio.run(import_file_async(creds, file_path))
