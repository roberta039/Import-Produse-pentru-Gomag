from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Tuple
from urllib.parse import urlparse

import re
import json
import time

import cloudscraper
from bs4 import BeautifulSoup

from ..models import ProductDraft
from .base import Scraper
from ..utils import domain_of
from .playwright_fetch import fetch_html_playwright


def _clean_text(x: str) -> str:
    return re.sub(r"\s+", " ", (x or "").strip())


def _extract_title(soup: BeautifulSoup) -> str:
    # OG title first
    og = soup.find("meta", attrs={"property": "og:title"})
    if og and og.get("content"):
        return _clean_text(og["content"])
    # then <title>
    if soup.title and soup.title.string:
        return _clean_text(soup.title.string)
    # then h1
    h1 = soup.find("h1")
    if h1:
        return _clean_text(h1.get_text(" ", strip=True))
    return ""


def _extract_description(soup: BeautifulSoup) -> str:
    # OG description first
    og = soup.find("meta", attrs={"property": "og:description"})
    if og and og.get("content"):
        return _clean_text(og["content"])
    # meta description
    md = soup.find("meta", attrs={"name": "description"})
    if md and md.get("content"):
        return _clean_text(md["content"])
    return ""


def _extract_images(soup: BeautifulSoup) -> List[str]:
    urls: List[str] = []
    # og:image(s)
    for m in soup.find_all("meta", attrs={"property": "og:image"}):
        u = (m.get("content") or "").strip()
        if u and u not in urls:
            urls.append(u)
    # fallback: first few <img>
    if len(urls) < 1:
        for img in soup.find_all("img"):
            src = (img.get("src") or "").strip()
            if not src:
                continue
            if src.startswith("data:"):
                continue
            if src not in urls:
                urls.append(src)
            if len(urls) >= 8:
                break
    return urls


def _jsonld_blocks(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for s in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = (s.string or s.get_text() or "").strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except Exception:
            # sometimes it's multiple json objects; try to salvage by stripping
            continue
        if isinstance(data, dict):
            out.append(data)
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    out.append(item)
    return out


def _jsonld_find_product(blocks: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    # Search for a dict that looks like Product
    for b in blocks:
        t = b.get("@type")
        if isinstance(t, str) and t.lower() == "product":
            return b
        if isinstance(t, list) and any(isinstance(x, str) and x.lower() == "product" for x in t):
            return b
    # Sometimes in @graph
    for b in blocks:
        g = b.get("@graph")
        if isinstance(g, list):
            for item in g:
                if isinstance(item, dict):
                    t = item.get("@type")
                    if isinstance(t, str) and t.lower() == "product":
                        return item
                    if isinstance(t, list) and any(isinstance(x, str) and x.lower() == "product" for x in t):
                        return item
    return None


def _jsonld_get_sku(prod: Dict[str, Any]) -> str:
    sku = prod.get("sku") or prod.get("mpn") or ""
    return _clean_text(str(sku))


def _jsonld_get_price(prod: Dict[str, Any]) -> Optional[float]:
    offers = prod.get("offers")
    if isinstance(offers, dict):
        price = offers.get("price") or offers.get("lowPrice") or offers.get("highPrice")
        try:
            if price is None:
                return None
            return float(str(price).replace(",", "."))
        except Exception:
            return None
    if isinstance(offers, list) and offers:
        for o in offers:
            if isinstance(o, dict):
                p = o.get("price")
                try:
                    if p is None:
                        continue
                    return float(str(p).replace(",", "."))
                except Exception:
                    continue
    return None


def _maybe_blocked(html: str) -> bool:
    h = (html or "").lower()
    markers = [
        "enable javascript",
        "attention required",
        "access denied",
        "captcha",
        "cloudflare",
        "please enable",
        "for full functionality of this site",
    ]
    return any(m in h for m in markers)


def fetch_html(url: str) -> Tuple[str, str]:
    """Return (html, method) where method is http or playwright."""
    scraper = cloudscraper.create_scraper()
    try:
        r = scraper.get(url, timeout=30)
        html = r.text or ""
        if r.status_code >= 400 or _maybe_blocked(html):
            raise RuntimeError(f"blocked_or_http_{r.status_code}")
        return html, "http"
    except Exception:
        html = fetch_html_playwright(url)
        return html, "playwright"


class GenericScraper(Scraper):
    def can_handle(self, url: str) -> bool:
        return True

    def parse(self, url: str) -> ProductDraft:
        dom = domain_of(url)
        html, method = fetch_html(url)
        soup = BeautifulSoup(html, "lxml")

        title = _extract_title(soup)
        description = _extract_description(soup)
        images = _extract_images(soup)

        # JSON-LD if available (for sku/price, sometimes title/desc too)
        blocks = _jsonld_blocks(soup)
        prod = _jsonld_find_product(blocks)
        sku = ""
        price: Optional[float] = None

        if prod:
            if not title:
                title = _clean_text(str(prod.get("name") or ""))
            if not description:
                description = _clean_text(str(prod.get("description") or ""))
            sku = _jsonld_get_sku(prod)
            price = _jsonld_get_price(prod)

            # images in jsonld
            img = prod.get("image")
            if isinstance(img, str) and img and img not in images:
                images.insert(0, img)
            elif isinstance(img, list):
                for u in img:
                    if isinstance(u, str) and u and u not in images:
                        images.append(u)

        # Hard defaults per your rules (handled later in pipeline/export)
        if not title:
            title = f"Produs {dom}"
        if not description:
            description = ""

        draft = ProductDraft(
            source_url=url,
            source_domain=dom,
            title=title,
            description=description,
            images=images,
            variants=[],
            sku=sku,
            price=price,
            stock=1,
            notes=f"generic=v5-meta+jsonld; parsed_with={method}"
        )
        return draft
