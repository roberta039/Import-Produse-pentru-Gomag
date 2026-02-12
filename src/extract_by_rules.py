import yaml
from bs4 import BeautifulSoup
from pathlib import Path
from .extract_generic import parse_price_from_text

def load_rules(domain: str) -> dict | None:
    p = Path("suppliers") / f"{domain}.yaml"
    if p.exists():
        return yaml.safe_load(p.read_text(encoding="utf-8"))

    # try stripping www.
    if domain.startswith("www."):
        p2 = Path("suppliers") / f"{domain[4:]}.yaml"
        if p2.exists():
            return yaml.safe_load(p2.read_text(encoding="utf-8"))

    pdef = Path("suppliers") / "default.yaml"
    if pdef.exists():
        return yaml.safe_load(pdef.read_text(encoding="utf-8"))
    return None

def css_text(soup: BeautifulSoup, selector: str) -> str | None:
    if not selector:
        return None
    el = soup.select_one(selector)
    return el.get_text(" ", strip=True) if el else None

def css_attr_list(soup: BeautifulSoup, selector: str, attr: str) -> list[str]:
    if not selector or not attr:
        return []
    out = []
    for el in soup.select(selector):
        v = el.get(attr)
        if v:
            out.append(v.strip())
    # dedup
    res = []
    seen = set()
    for x in out:
        if x not in seen:
            seen.add(x)
            res.append(x)
    return res

def extract_by_rules(domain: str, url: str, html: str) -> dict:
    rules = load_rules(domain) or {}
    soup = BeautifulSoup(html, "lxml")

    title = css_text(soup, rules.get("title_css", ""))
    desc = css_text(soup, rules.get("description_css", ""))
    sku = css_text(soup, rules.get("sku_css", ""))

    price_val, price_cur = None, None
    price_text = css_text(soup, rules.get("price_css", ""))
    if price_text:
        price_val, price_cur = parse_price_from_text(price_text)

    images = []
    if rules.get("image_css") and rules.get("image_attr"):
        images = css_attr_list(soup, rules["image_css"], rules["image_attr"])

    return {
        "title": title,
        "sku": sku,
        "description": desc,
        "images": images,
        "price_val": price_val,
        "price_cur": price_cur,
        "specs": {}
    }
