from __future__ import annotations
import requests
import cloudscraper

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
    "Accept-Language": "ro-RO,ro;q=0.9,en-US;q=0.8,en;q=0.7",
}

def fetch_html(url: str, timeout: int = 30) -> tuple[str, str]:
    """Return (html, method). Method in {'requests','cloudscraper'}"""
    try:
        r = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout)
        if r.status_code == 200 and len(r.text) > 2000:
            return r.text, "requests"
    except Exception:
        pass

    scraper = cloudscraper.create_scraper(
        browser={"browser": "chrome", "platform": "linux", "desktop": True}
    )
    r = scraper.get(url, headers=DEFAULT_HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.text, "cloudscraper"
