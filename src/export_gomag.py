from __future__ import annotations

import hashlib
import os
import re
from typing import Dict, List

import pandas as pd

from .models import ProductDraft

TEMPLATE_PATH = os.path.join("assets", "modelImport.xlsx")


def _load_template_headers() -> List[str]:
    """Loads headers from Gomag 'Model import' template.
    If template is missing, falls back to a minimal safe set.
    """
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
    """Gomag limita SKU = 30. Pastreaza determinist si unic."""
    sku = (sku or "").strip()
    if len(sku) <= max_len:
        return sku
    h = hashlib.sha1(sku.encode("utf-8")).hexdigest()[:8]
    prefix_len = max_len - 1 - len(h)
    prefix = sku[:prefix_len]
    return f"{prefix}-{h}"


def _clean_tsv_cell(val: str) -> str:
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

        # Keep TSV stable: only first image URL
        imgs = [i for i in (p.images or []) if i]
        row["URL Poza de Produs"] = imgs[0] if imgs else ""

        row["Pret"] = round(p.price_final(), 2)
        row["Moneda"] = "RON"
        row["Stoc Cantitativ"] = 1
        row["Activ in Magazin"] = "DA"
        row["Categorie / Categorii"] = cat

        # sanitize strings for TSV/XLSX safety
        for k, v in list(row.items()):
            if isinstance(v, str):
                row[k] = _clean_tsv_cell(v)

        rows.append(row)

    return pd.DataFrame(rows, columns=headers)


def save_tsv(df: pd.DataFrame, path: str) -> None:
    """TSV (TAB) UTF-8 – recommended for Gomag import."""
    df.to_csv(path, sep="\t", index=False, encoding="utf-8")


def save_xlsx(df: pd.DataFrame, path: str) -> None:
    """Backward-compat for app.py that still imports save_xlsx.
    If path ends with .tsv, it will write TSV; otherwise XLSX.
    """
    if str(path).lower().endswith(".tsv"):
        return save_tsv(df, path)
    df.to_excel(path, index=False)
