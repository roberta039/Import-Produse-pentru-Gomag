import asyncio
from dataclasses import dataclass
from urllib.parse import urlparse

from .fetcher import fetch_html_requests, fetch_html_playwright, looks_blocked_or_empty
from .extract_generic import extract_generic
from .extract_by_rules import extract_by_rules
from .supplier_registry import normalize_domain, domain_from_url
from .models import ExtractedProduct
from .pricing import compute_final_price_ron
from .translate import translate_to_ro
from .gomag_payload import build_product_payload

@dataclass
class ImportSettings:
    category_id: int | None
    eur_ron: float
    gbp_ron: float
    markup_percent: float
    stock_default: int = 1
    missing_price_fallback_ron: float = 1.0
    publish_immediately: bool = True
    force_playwright: bool = False

def _merge(primary: dict, secondary: dict) -> dict:
    # take primary values if present else secondary
    out = dict(secondary)
    for k, v in primary.items():
        if v is not None and v != "" and v != [] and v != {}:
            out[k] = v
    return out

async def _fetch_html(url: str, force_playwright: bool) -> str:
    if force_playwright:
        return await fetch_html_playwright(url)

    html = fetch_html_requests(url)
    if looks_blocked_or_empty(html):
        html = await fetch_html_playwright(url)
    return html

async def process_one_url(url: str, settings: ImportSettings, gomag, secrets: dict) -> dict:
    domain = normalize_domain(domain_from_url(url))

    html = await _fetch_html(url, settings.force_playwright)

    # extraction: domain rules first (if exist), then generic, then merge
    by_rules = extract_by_rules(domain, url, html)
    generic = extract_generic(url, html)
    data = _merge(by_rules, generic)

    # build model
    name = data.get("title") or data.get("sku") or "Produs"
    sku = (data.get("sku") or "").strip() or "IMP-UNKNOWN"
    desc = data.get("description") or ""
    imgs = data.get("images") or []
    specs = data.get("specs") or {}

    # Translate (plugin-based)
    name_ro = translate_to_ro(name, secrets)
    desc_ro = translate_to_ro(desc, secrets)
    specs_ro = {}
    for k, v in specs.items():
        kk = translate_to_ro(str(k), secrets)
        vv = translate_to_ro(str(v), secrets)
        specs_ro[kk] = vv

    # Price compute
    price_ron = compute_final_price_ron(
        data.get("price_val"),
        data.get("price_cur"),
        eur_ron=settings.eur_ron,
        gbp_ron=settings.gbp_ron,
        markup_percent=settings.markup_percent,
        missing_price_fallback_ron=settings.missing_price_fallback_ron
    )

    prod = ExtractedProduct(
        url=url,
        name=name_ro,
        sku=sku,
        description_html=desc_ro,
        specs=specs_ro,
        images=imgs,
        source_price_value=data.get("price_val"),
        source_price_currency=data.get("price_cur"),
        price_ron=price_ron,
        stock=settings.stock_default,
        category_id=settings.category_id,
        publish_immediately=settings.publish_immediately
    )

    payload = build_product_payload(prod)

    # Write to Gomag
    resp = gomag.product_write(payload)

    return {
        "sku": prod.sku,
        "name": prod.name,
        "price_ron": prod.price_ron,
        "category_id": prod.category_id,
        "images": len(prod.images),
        "gomag_response": resp,
    }
