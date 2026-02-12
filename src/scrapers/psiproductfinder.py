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


def _meta(soup: BeautifulSoup, key: str) -> str:
    el = soup.select_one(f'meta[property="{key}"]') or soup.select_one(f'meta[name="{key}"]')
    if el and el.get("content"):
        return clean_text(el.get("content"))
    return ""


def _iter_jsonld(soup: BeautifulSoup):
    for sc in soup.select('script[type="application/ld+json"]'):
        raw = (sc.string or sc.get_text() or "").strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue
        if isinstance(data, dict):
            yield data
        elif isinstance(data, list):
            for obj in data:
                if isinstance(obj, dict):
                    yield obj


def _find_product(soup: BeautifulSoup) -> dict | None:
    for obj in _iter_jsonld(soup):
        t = obj.get("@type")
        if t == "Product" or (isinstance(t, list) and "Product" in t):
            return obj
        g = obj.get("@graph")
        if isinstance(g, list):
            for node in g:
                if isinstance(node, dict):
                    nt = node.get("@type")
                    if nt == "Product" or (isinstance(nt, list) and "Product" in nt):
                        return node
    return None


def _jsonld_images(prod: dict) -> list[str]:
    imgs = prod.get("image")
    if isinstance(imgs, str):
        return [imgs]
    if isinstance(imgs, list):
        return [x for x in imgs if isinstance(x, str)]
    return []


def _jsonld_price(prod: dict) -> float | None:
    offers = prod.get("offers")

    def _to_float(x):
        try:
            return float(str(x).replace(",", "."))
        except Exception:
            return None

    if isinstance(offers, dict):
        return _to_float(offers.get("price"))
    if isinstance(offers, list):
        for o in offers:
            if isinstance(o, dict) and o.get("price") is not None:
                v = _to_float(o.get("price"))
                if v is not None:
                    return v
    return None


def _extract_images(soup: BeautifulSoup, base_url: str) -> list[str]:
    urls: list[str] = []

    og = _meta(soup, "og:image")
    if og:
        urls.append(urljoin(base_url, og))

    for m in soup.select('meta[property="og:image"], meta[property="og:image:secure_url"], meta[name="twitter:image"]'):
        c = m.get("content")
        if c:
            urls.append(urljoin(base_url, c))

    for img in soup.select("img"):
        src = img.get("src") or img.get("data-src") or img.get("data-original") or img.get("data-lazy")
        if not src:
            srcset = img.get("srcset") or img.get("data-srcset")
            if srcset:
                src = srcset.split(",")[-1].strip().split(" ")[0]
        if not src:
            continue
        src = urljoin(base_url, src)
        if src.lower().startswith("data:"):
            continue
        if any(x in src.lower() for x in ["logo", "icon", "sprite"]):
            continue
        urls.append(src)

    for el in soup.select("[style]"):
        st = el.get("style") or ""
        m = re.findall(r"url\(['\"]?(.*?)['\"]?\)", st, flags=re.I)
        for u in m:
            if not u:
                continue
            u = urljoin(base_url, u)
            if u.lower().startswith("data:"):
                continue
            urls.append(u)

    seen = set()
    out = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out[:12]


def _extract_desc(soup: BeautifulSoup) -> str:
    d = _meta(soup, "og:description") or _meta(soup, "description") or _meta(soup, "twitter:description")
    if d and len(d) > 40:
        return f"<p>{d}</p>"

    for sel in [
        "[itemprop=description]",
        ".product-description",
        ".description",
        "#description",
        ".tabs-content",
        ".product__description",
    ]:
        el = soup.select_one(sel)
        if el and len(el.get_text(strip=True)) > 50:
            return str(el)

    return ""


class PSIProductFinderScraper(Scraper):
    def can_handle(self, url: str) -> bool:
        return domain_of(url).endswith("psiproductfinder.de")

    def parse(self, url: str) -> ProductDraft:
        domain = domain_of(url)
        html, method = fetch_html(url)

        # PSI content is often JS-driven; use Playwright when HTML looks thin
        if len(html) < 2500:
            try:
                html = render_html_sync(url, wait_ms=2500)
                method = "playwright"
            except Exception:
                pass

        soup = BeautifulSoup(html, "lxml")
        prod = _find_product(soup)

        title = None
        sku = None
        price = None
        images: list[str] = []

        if prod:
            title = clean_text(str(prod.get("name") or "")) or None
            sku = clean_text(str(prod.get("sku") or "")) or None
            price = _jsonld_price(prod)
            images = _jsonld_images(prod)

        if not title:
            title = _meta(soup, "og:title") or _meta(soup, "twitter:title") or "Produs"

        desc_html = _extract_desc(soup)
        if not desc_html and prod and isinstance(prod.get("description"), str):
            dd = clean_text(prod.get("description"))
            if dd:
                desc_html = f"<p>{dd}</p>"

        if not images:
            images = _extract_images(soup, url)

        return ProductDraft(
            source_url=url,
            domain=domain,
            sku=ensure_sku(url, sku),
            title=title,
            description_html=desc_html or "",
            short_description=clean_text(BeautifulSoup(desc_html or "", "lxml").get_text())[:200],
            images=images,
            price=price,
            currency="RON",
            needs_translation=False,
            notes=f"psi_scraper=v2 | parsed_with={method}",
        )
