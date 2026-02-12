from __future__ import annotations

import json
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base import Scraper
from ..browser import render_html_sync
from ..fetch import fetch_html
from ..models import ProductDraft
from ..utils import clean_text, domain_of, ensure_sku


def _extract_images_basic(soup: BeautifulSoup, base_url: str) -> list[str]:
    imgs: list[str] = []
    for img in soup.select("img"):
        src = img.get("src") or img.get("data-src") or img.get("data-original")
        if not src:
            continue
        src = urljoin(base_url, src)
        if src.lower().startswith("data:"):
            continue
        if any(x in src.lower() for x in ["logo", "icon", "sprite"]):
            continue
        imgs.append(src)

    # dedupe keep order
    seen = set()
    out: list[str] = []
    for u in imgs:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out[:12]


def _extract_title_basic(soup: BeautifulSoup) -> str:
    h1 = soup.select_one("h1")
    if h1 and clean_text(h1.get_text()):
        return clean_text(h1.get_text())
    if soup.title and clean_text(soup.title.get_text()):
        return clean_text(soup.title.get_text())
    return "Produs"


def _extract_price_basic(soup: BeautifulSoup) -> float | None:
    # heuristic: find first price-like pattern
    text = soup.get_text(" ", strip=True)
    m = re.search(r"(\d+[\.,]?\d*)\s*(lei|ron|eur|€)", text, re.IGNORECASE)
    if not m:
        return None
    val = m.group(1).replace(".", "").replace(",", ".")
    try:
        return float(val)
    except Exception:
        return None


def _extract_desc_basic(soup: BeautifulSoup) -> str:
    for sel in [
        '[itemprop="description"]',
        ".product-description",
        ".description",
        "#description",
        ".tab-content",
        ".product-tabs",
        ".product__description",
    ]:
        el = soup.select_one(sel)
        if el and len(el.get_text(strip=True)) > 50:
            return str(el)

    # fallback: largest paragraph-like block
    ps = soup.find_all(["p", "div"])
    best = ""
    for p in ps:
        t = p.get_text(" ", strip=True)
        if len(t) > len(best) and len(t) > 80:
            best = t
    return f"<p>{best}</p>" if best else ""


def _iter_jsonld_objects(soup: BeautifulSoup):
    for sc in soup.select('script[type="application/ld+json"]'):
        raw = sc.string or sc.get_text() or ""
        raw = raw.strip()
        if not raw:
            continue
        # Some sites put multiple JSON objects without a list; try best-effort parsing.
        try:
            data = json.loads(raw)
        except Exception:
            # attempt to fix trailing garbage
            continue

        # normalize to list of objects
        if isinstance(data, dict):
            yield data
        elif isinstance(data, list):
            for obj in data:
                if isinstance(obj, dict):
                    yield obj


def _find_product_jsonld(soup: BeautifulSoup) -> dict | None:
    # Return the first JSON-LD node describing a Product
    for obj in _iter_jsonld_objects(soup):
        # direct Product
        t = obj.get("@type") or obj.get("type")
        if isinstance(t, list):
            if "Product" in t:
                return obj
        if t == "Product":
            return obj

        # graph
        graph = obj.get("@graph")
        if isinstance(graph, list):
            for node in graph:
                if not isinstance(node, dict):
                    continue
                nt = node.get("@type")
                if isinstance(nt, list):
                    if "Product" in nt:
                        return node
                if nt == "Product":
                    return node
    return None


def _jsonld_get_images(prod: dict) -> list[str]:
    imgs = prod.get("image")
    out: list[str] = []
    if isinstance(imgs, str):
        out = [imgs]
    elif isinstance(imgs, list):
        out = [x for x in imgs if isinstance(x, str)]
    # dedupe
    seen = set()
    res = []
    for u in out:
        if u not in seen:
            seen.add(u)
            res.append(u)
    return res


def _jsonld_get_price(prod: dict) -> float | None:
    offers = prod.get("offers")
    if isinstance(offers, dict):
        p = offers.get("price")
        if p is None:
            return None
        try:
            return float(str(p).replace(",", "."))
        except Exception:
            return None
    if isinstance(offers, list) and offers:
        for o in offers:
            if isinstance(o, dict) and o.get("price") is not None:
                try:
                    return float(str(o.get("price")).replace(",", "."))
                except Exception:
                    continue
    return None


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
            "for full functionality of this site",
        ]

        # Force Playwright when blocked or HTML too small
        if len(html) < 1500 or any(mark in html.lower() for mark in blocked_markers):
            try:
                html = render_html_sync(url, wait_ms=2500)
                method = "playwright"
            except Exception:
                pass

        soup = BeautifulSoup(html, "lxml")

        # Prefer JSON-LD Product data if available (fixes many sites with complex layouts)
        prod = _find_product_jsonld(soup)
        title = None
        desc_html = None
        images = None
        sku = None
        price = None

        if prod:
            title = clean_text(str(prod.get("name") or "")) or None
            sku = clean_text(str(prod.get("sku") or "")) or None

            # description in JSON-LD is plain text; wrap in <p>
            d = prod.get("description")
            if isinstance(d, str) and clean_text(d):
                desc_html = f"<p>{clean_text(d)}</p>"
            images = _jsonld_get_images(prod) or None
            price = _jsonld_get_price(prod)

        # Fallbacks
        if not title:
            title = _extract_title_basic(soup)
        if not desc_html:
            desc_html = _extract_desc_basic(soup)
        if images is None:
            images = _extract_images_basic(soup, url)
        if price is None:
            price = _extract_price_basic(soup)

        # Fallback SKU extraction from DOM
        if not sku:
            for sel in ['[itemprop="sku"]', ".sku", ".product-sku", "#sku"]:
                el = soup.select_one(sel)
                if el and clean_text(el.get_text()):
                    sku = clean_text(el.get_text())
                    break

        return ProductDraft(
            source_url=url,
            domain=domain,
            sku=ensure_sku(url, sku),
            title=title,
            description_html=desc_html or "",
            short_description=clean_text(BeautifulSoup(desc_html or "", "lxml").get_text())[:200],
            images=images or [],
            price=price,
            currency="RON",
            needs_translation=False,
            notes=f"parsed_with={method}",
        )
