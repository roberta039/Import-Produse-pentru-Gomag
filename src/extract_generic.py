import json, re, hashlib
from bs4 import BeautifulSoup
from urllib.parse import urlparse

def _hash_sku(url: str) -> str:
    h = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10].upper()
    return f"IMP-{h}"

def extract_jsonld(soup: BeautifulSoup) -> list[dict]:
    out = []
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(tag.get_text(strip=True))
            if isinstance(data, list):
                out.extend([d for d in data if isinstance(d, dict)])
            elif isinstance(data, dict):
                out.append(data)
        except Exception:
            pass
    return out

def find_product_ld(ld_list: list[dict]) -> dict | None:
    for obj in ld_list:
        t = obj.get("@type")
        if t == "Product" or (isinstance(t, list) and "Product" in t):
            return obj
    for obj in ld_list:
        g = obj.get("@graph")
        if isinstance(g, list):
            for x in g:
                t = x.get("@type")
                if t == "Product" or (isinstance(t, list) and "Product" in t):
                    return x
    return None

def parse_price_from_text(text: str):
    t = text.upper()
    currency = None
    if "€" in text or "EUR" in t:
        currency = "EUR"
    elif "RON" in t or "LEI" in t:
        currency = "RON"
    elif "£" in text or "GBP" in t:
        currency = "GBP"

    m = re.search(r"(\d{1,3}([.,]\d{3})*[.,]\d{2}|\d+[.,]\d{2}|\d+)", text)
    if not m or not currency:
        return None, None

    raw = m.group(1)
    if raw.count(",") and raw.count("."):
        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    else:
        raw = raw.replace(",", ".")
    try:
        return float(raw), currency
    except Exception:
        return None, None

def extract_sku_fallback(html_text: str, url: str) -> str:
    patterns = [
        r"\bSKU\s*[:#]?\s*([A-Z0-9\.\-_/]{3,})\b",
        r"\b(Product code|Item code|Cod produs)\s*[:#]?\s*([A-Z0-9\.\-_/]{3,})\b",
    ]
    for p in patterns:
        m = re.search(p, html_text, re.IGNORECASE)
        if m:
            return m.groups()[-1].strip().upper()

    path = urlparse(url).path
    m = re.search(r"(AP\d{6,}-\d+|MO\d{3,5}|KI\d{4}|P\d{3}\.\d{2}|DM\d{5,}|PC\d{4,})", path, re.IGNORECASE)
    if m:
        return m.group(1).upper()

    return _hash_sku(url)

def extract_generic(url: str, html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    ld = extract_jsonld(soup)
    p = find_product_ld(ld)

    title = None
    sku = None
    images = []
    description = None
    price_val, price_cur = None, None
    specs = {}

    if p:
        title = p.get("name") or title
        sku = p.get("sku") or sku
        description = p.get("description") or description
        img = p.get("image")
        if isinstance(img, str):
            images = [img]
        elif isinstance(img, list):
            images = [x for x in img if isinstance(x, str)]

        offers = p.get("offers")
        if isinstance(offers, dict):
            price = offers.get("price")
            cur = offers.get("priceCurrency")
            try:
                if price is not None and cur:
                    price_val = float(str(price).replace(",", "."))
                    price_cur = str(cur).upper()
            except Exception:
                pass

    if not title:
        og = soup.find("meta", property="og:title")
        if og and og.get("content"):
            title = og["content"].strip()
    if not title and soup.title:
        title = soup.title.get_text(strip=True)

    if not description:
        ogd = soup.find("meta", property="og:description")
        if ogd and ogd.get("content"):
            description = ogd["content"].strip()

    if not images:
        for prop in ["og:image", "og:image:url"]:
            m = soup.find("meta", property=prop)
            if m and m.get("content"):
                images.append(m["content"].strip())

    if price_val is None:
        # heuristic: search for obvious price snippets in visible text
        text = soup.get_text(" ", strip=True)
        pv, pc = parse_price_from_text(text)
        price_val, price_cur = pv, pc

    if not sku:
        sku = extract_sku_fallback(html, url)

    # Dedup images
    dedup = []
    seen = set()
    for im in images:
        if im and im not in seen:
            seen.add(im)
            dedup.append(im)

    return {
        "title": title or sku,
        "sku": sku,
        "description": description or "",
        "images": dedup,
        "price_val": price_val,
        "price_cur": price_cur,
        "specs": specs
    }
