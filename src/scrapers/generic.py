from __future__ import annotations
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
import re

from .base import Scraper
from ..models import ProductDraft
from ..fetch import fetch_html
from ..browser import render_html_sync
from ..utils import domain_of, ensure_sku, clean_text

def _extract_images(soup: BeautifulSoup, base_url: str) -> list[str]:
    imgs = []
    for img in soup.select('img'):
        src = img.get("src") or img.get("data-src") or img.get("data-original")
        if not src:
            continue
        src = urljoin(base_url, src)
        if src.lower().startswith("data:"):
            continue
        if any(x in src.lower() for x in ["logo", "icon", "sprite"]):
            continue
        imgs.append(src)
    # dedupe while keeping order
    seen = set()
    out = []
    for u in imgs:
        if u not in seen:
            seen.add(u); out.append(u)
    return out[:12]

def _extract_title(soup: BeautifulSoup) -> str:
    h1 = soup.select_one("h1")
    if h1 and clean_text(h1.get_text()):
        return clean_text(h1.get_text())
    if soup.title and clean_text(soup.title.get_text()):
        return clean_text(soup.title.get_text())
    return "Produs"

def _extract_price(soup: BeautifulSoup) -> float | None:
    # heuristic: look for currency patterns
    text = soup.get_text(" ", strip=True)
    m = re.search(r"(\d+[\.,]?\d*)\s*(lei|ron|eur|€)", text, re.IGNORECASE)
    if not m:
        return None
    val = m.group(1).replace(".", "").replace(",", ".")
    try:
        return float(val)
    except Exception:
        return None

def _extract_desc(soup: BeautifulSoup) -> str:
    # prefer common product description containers
    for sel in [
        '[itemprop="description"]',
        '.product-description', '.description', '#description',
        '.tab-content', '.product-tabs', '.product__description'
    ]:
        el = soup.select_one(sel)
        if el and len(el.get_text(strip=True)) > 50:
            return str(el)
    # fallback: first substantial paragraph block
    ps = soup.find_all(["p", "div"])
    best = ""
    for p in ps:
        t = p.get_text(" ", strip=True)
        if len(t) > len(best) and len(t) > 80:
            best = t
    return f"<p>{best}</p>" if best else ""

class GenericScraper(Scraper):
    def can_handle(self, url: str) -> bool:
        return True

    def parse(self, url: str) -> ProductDraft:
        domain = domain_of(url)
        html, method = fetch_html(url)

blocked_markers = [
    "enable javascript",
    "attention required",
    "access denied",
    "captcha",
    "cloudflare",
    "cookie",
    "cookies",
    "consent",
    "please enable",
]

# Forteaza Playwright daca pare blocat (mesaje de JS/captcha/consent) sau daca HTML e prea mic
if len(html) < 1500 or any(mark in html.lower() for mark in blocked_markers):
    try:
        html = render_html_sync(url, wait_ms=2500)
        method = "playwright"
    except Exception:
        pass

soup = BeautifulSoup(html, "lxml")

        title = _extract_title(soup)
        price = _extract_price(soup)
        desc_html = _extract_desc(soup)
        images = _extract_images(soup, url)

        sku = None
        # try common sku markers
        for sel in ['[itemprop="sku"]', '.sku', '.product-sku', '#sku']:
            el = soup.select_one(sel)
            if el and clean_text(el.get_text()):
                sku = clean_text(el.get_text())
                break

        draft = ProductDraft(
            source_url=url,
            domain=domain,
            sku=ensure_sku(url, sku),
            title=title,
            description_html=desc_html,
            short_description=clean_text(BeautifulSoup(desc_html, "lxml").get_text())[:200],
            images=images,
            price=price,
            currency="RON",
            needs_translation=False,
            notes=f"parsed_with={method}"
        )
        return draft
