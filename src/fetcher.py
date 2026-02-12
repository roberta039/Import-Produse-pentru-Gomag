import requests

def fetch_html_requests(url: str, timeout: int = 45) -> str:
    r = requests.get(url, timeout=timeout, headers={
        "User-Agent": "Mozilla/5.0 (Importer; +https://github.com/your-repo)"
    })
    r.raise_for_status()
    return r.text

async def fetch_html_playwright(url: str) -> str:
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, wait_until="networkidle", timeout=60000)
        html = await page.content()
        await browser.close()
        return html

def looks_blocked_or_empty(html: str) -> bool:
    h = (html or "").lower()
    return (
        len(h) < 2500
        or "cf-browser-verification" in h
        or "cloudflare" in h and "attention required" in h
        or "<title>just a moment" in h
    )
