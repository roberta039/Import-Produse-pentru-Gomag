from __future__ import annotations

import os
from typing import List, Dict

import pandas as pd

from .models import ProductDraft


_TEMPLATE_COLUMNS_FALLBACK = [
    "Cod Produs (SKU)",
    "Denumire Produs",
    "Descriere Produs",
    "Descriere Scurta a Produsului",
    "URL Poza de Produs",
    "Pret",
    "Moneda",
    "Stoc Cantitativ",
    "Stare Stoc",
    "Activ in Magazin",
    "Categorie / Categorii",
]


def _load_template_columns() -> List[str]:
    """Load Gomag import template columns from assets/modelImport.xlsx if present."""
    here = os.path.dirname(__file__)
    cand = os.path.abspath(os.path.join(here, "..", "assets", "modelImport.xlsx"))
    if os.path.exists(cand):
        try:
            # nrows=0 reads only headers
            df0 = pd.read_excel(cand, nrows=0)
            cols = [str(c).strip() for c in df0.columns.tolist() if str(c).strip()]
            if cols:
                return cols
        except Exception:
            pass
    return _TEMPLATE_COLUMNS_FALLBACK


def to_gomag_dataframe(products: List[ProductDraft], category_map: Dict[str, str] | None = None) -> pd.DataFrame:
    """Return a DataFrame compatible with Gomag 'Model import' XLSX."""
    category_map = category_map or {}
    columns = _load_template_columns()

    rows = []
    for p in products:
        cat = category_map.get(p.source_url, "")

        row = {c: "" for c in columns}

        # Core fields
        row["Cod Produs (SKU)"] = p.sku
        row["Denumire Produs"] = p.title
        row["Descriere Produs"] = p.description_html or ""
        row["Descriere Scurta a Produsului"] = p.short_description or ""
        row["URL Poza de Produs"] = "|".join(p.images or [])
        row["Pret"] = round(float(p.price_final()), 2)
        row["Moneda"] = "RON"
        row["Stoc Cantitativ"] = 1
        row["Stare Stoc"] = "instock"
        row["Activ in Magazin"] = "DA"
        row["Categorie / Categorii"] = cat

        rows.append(row)

    df = pd.DataFrame(rows)

    # Ensure exact column order as template
    for c in columns:
        if c not in df.columns:
            df[c] = ""
    df = df[columns]
    return df


def save_xlsx(df: pd.DataFrame, path: str) -> None:
    df.to_excel(path, index=False)
