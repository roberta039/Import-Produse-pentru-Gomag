from __future__ import annotations

import hashlib
import os
import re
from typing import Dict, List

import pandas as pd

from .models import ProductDraft

TEMPLATE_PATH = os.path.join("assets", "modelImport.xlsx")


def _load_template_headers() -> List[str]:
    """Loads headers from Gomag's template. If template missing, uses minimal safe set."""
    try:
        import openpyxl  # type: ignore
        wb = openpyxl.load_workbook(TEMPLATE_PATH)
        ws = wb.active
        headers = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
        headers = [h for h in headers if h]
        if headers:
            return headers
    except Exception:
        pass

    return [
        "Cod Produs (SKU)",
        "Denumire Produs",
        "Descriere Produs",
        "Descriere Scurta a Produsului",
        "URL Poza de Produs",
        "Pret",
        "Moneda",
        "Stoc Cantitativ",
        "Activ in Magazin",
        "Categorie / Categorii",
    ]


def _shorten_sku(sku: str, max_len: int = 30) -> str:
    sku = (sku or "").strip()
    if len(sku) <= max_len:
        return sku
    h = hashlib.sha1(sku.encode("utf-8")).hexdigest()[:8]
    prefix_len = max_len - 1 - len(h)
    prefix = sku[:prefix_len]
    return f"{prefix}-{h}"


def _clean_tsv_cell(val: str) -> str:
    """TSV-safe: remove tabs/newlines, keep single spaces."""
    s = (val or "")
    s = re.sub(r"[\t\r\n]+", " ", s)
    s = re.sub(r"\s{2,}", " ", s).strip()
    return s


def to_gomag_dataframe(products: List[ProductDraft], category_map: Dict[str, str] | None = None) -> pd.DataFrame:
    headers = _load_template_headers()
    category_map = category_map or {}
    rows: List[dict] = []

    for p in products:
        cat = category_map.get(p.source_url, "") or ""
        row = {h: "" for h in headers}

        row["Cod Produs (SKU)"] = _shorten_sku(p.sku)
        row["Denumire Produs"] = p.title or ""
        row["Descriere Produs"] = p.description_html or ""
        row["Descriere Scurta a Produsului"] = p.short_description or ""

        # For TSV stability, use ONLY first image URL
        imgs = [i for i in (p.images or []) if i]
        row["URL Poza de Produs"] = imgs[0] if imgs else ""

        row["Pret"] = round(p.price_final(), 2)
        row["Moneda"] = "RON"
        row["Stoc Cantitativ"] = 1
        row["Activ in Magazin"] = "DA"
        row["Categorie / Categorii"] = cat

        # Clean TSV cells
        for k, v in list(row.items()):
            if isinstance(v, str):
                row[k] = _clean_tsv_cell(v)

        rows.append(row)

    return pd.DataFrame(rows, columns=headers)


def save_tsv(df: pd.DataFrame, path: str) -> None:
    # Gomag: TSV (TAB). UTF-8.
    df.to_csv(path, sep="\t", index=False, encoding="utf-8")
