from __future__ import annotations
import pandas as pd
from typing import List, Dict
from .models import ProductDraft
from .utils import clean_text

def to_gomag_dataframe(products: List[ProductDraft], category_map: Dict[str, str] | None = None) -> pd.DataFrame:
    rows = []
    category_map = category_map or {}
    for p in products:
        cat = category_map.get(p.source_url, "")

        rows.append({
            "Cod Produs (SKU)": p.sku,
            "Denumire Produs": p.title,
            "Descriere Produs": p.description_html or "",
            "Descriere Scurta Produs": p.short_description or "",
            "URL Poza de Produs": "|".join(p.images or []),
            "Pret": round(p.price_final(), 2),
            "Stoc Cantitativ": 1,
            "Stare Stoc": "instock",
            "Activ in Magazin": "DA",
            "Categorie": cat,
            "Sursa URL": p.source_url,
            "Note": p.notes,
            "Needs translation": "DA" if p.needs_translation else "NU",
        })
    return pd.DataFrame(rows)

def save_xlsx(df: pd.DataFrame, path: str) -> None:
    df.to_excel(path, index=False)
