from __future__ import annotations

import hashlib
import os
import re
from typing import Any, Dict, List, Optional, Union

import pandas as pd

try:
    from .models import ProductDraft  # type: ignore
except Exception:
    ProductDraft = Any  # fallback for type checkers

TEMPLATE_PATH = os.path.join("assets", "modelImport.xlsx")


def _load_template_headers() -> List[str]:
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


def _clean_cell(val: Any) -> Any:
    if val is None:
        return ""
    if isinstance(val, (int, float)):
        return val
    s = str(val)
    s = re.sub(r"[\t\r\n]+", " ", s)
    s = re.sub(r"\s{2,}", " ", s).strip()
    return s


def _pick_first_image(images_val: Any) -> str:
    # Accept list[str] or comma-separated string
    if images_val is None:
        return ""
    if isinstance(images_val, list):
        return str(images_val[0]) if images_val else ""
    s = str(images_val).strip()
    if not s:
        return ""
    # split by comma/space if multiple
    parts = [p.strip() for p in re.split(r"[\s,]+", s) if p.strip()]
    return parts[0] if parts else s


def to_gomag_dataframe(
    products_or_df: Union[List[ProductDraft], pd.DataFrame],
    categories: Optional[List[Any]] = None,
    category_map: Optional[Dict[str, str]] = None,
) -> pd.DataFrame:
    """Compatibility wrapper.

    - Old flow: to_gomag_dataframe(list[ProductDraft], category_map=...)
    - New app.py flow (current in repo): to_gomag_dataframe(df_final, categories=[...])
    """
    headers = _load_template_headers()
    categories = categories or []
    category_map = category_map or {}

    # Case 1: DataFrame already (intermediate table in Streamlit)
    if isinstance(products_or_df, pd.DataFrame):
        df = products_or_df.copy()

        # Detect category column in df
        cat_col = None
        for c in df.columns:
            cl = str(c).strip().lower()
            if "categorie" in cl or "category" in cl:
                cat_col = c
                break

        def ensure(col: str, default: Any = ""):
            if col not in df.columns:
                df[col] = default

        # Map common intermediate columns -> Gomag template columns
        ensure("Cod Produs (SKU)")
        ensure("Denumire Produs")
        ensure("Descriere Produs")
        ensure("Descriere Scurta a Produsului")
        ensure("URL Poza de Produs")
        ensure("Pret", 1)
        ensure("Moneda", "RON")
        ensure("Stoc Cantitativ", 1)
        ensure("Activ in Magazin", "DA")
        ensure("Categorie / Categorii", "")

        # Try to fill missing from alternative names if present
        alt_map = {
            "sku": "Cod Produs (SKU)",
            "cod produs": "Cod Produs (SKU)",
            "title": "Denumire Produs",
            "nume": "Denumire Produs",
            "name": "Denumire Produs",
            "descriere": "Descriere Produs",
            "description": "Descriere Produs",
            "short_description": "Descriere Scurta a Produsului",
            "descriere scurta": "Descriere Scurta a Produsului",
            "image": "URL Poza de Produs",
            "images": "URL Poza de Produs",
            "price": "Pret",
            "pret": "Pret",
        }

        lower_cols = {str(c).strip().lower(): c for c in df.columns}
        for k, target in alt_map.items():
            if target in df.columns and df[target].isna().all():
                # try fill from alt if exists
                if k in lower_cols:
                    df[target] = df[lower_cols[k]]

        # SKU shorten
        df["Cod Produs (SKU)"] = df["Cod Produs (SKU)"].apply(lambda x: _shorten_sku(str(x)) if str(x).strip() else "")

        # Images keep only first
        df["URL Poza de Produs"] = df["URL Poza de Produs"].apply(_pick_first_image)

        # Category from cat_col if provided
        if cat_col and (df["Categorie / Categorii"].astype(str).str.strip() == "").all():
            df["Categorie / Categorii"] = df[cat_col].astype(str)

        # Clean strings
        for c in df.columns:
            df[c] = df[c].apply(_clean_cell)

        # Keep only template headers (but also keep extras if header missing? We'll output only headers)
        out = pd.DataFrame({h: df[h] if h in df.columns else "" for h in headers})
        return out

    # Case 2: list[ProductDraft]
    products: List[ProductDraft] = products_or_df  # type: ignore
    rows: List[dict] = []
    for p in products:
        cat = category_map.get(getattr(p, "source_url", ""), "") or ""
        row = {h: "" for h in headers}
        row["Cod Produs (SKU)"] = _shorten_sku(getattr(p, "sku", "") or "")
        row["Denumire Produs"] = getattr(p, "title", "") or ""
        row["Descriere Produs"] = getattr(p, "description_html", "") or ""
        row["Descriere Scurta a Produsului"] = getattr(p, "short_description", "") or ""
        imgs = getattr(p, "images", None) or []
        row["URL Poza de Produs"] = imgs[0] if isinstance(imgs, list) and imgs else ""
        # price_final() method if exists
        price = 1
        try:
            price = float(getattr(p, "price_final")())
        except Exception:
            try:
                price = float(getattr(p, "price", 1) or 1)
            except Exception:
                price = 1
        row["Pret"] = round(price, 2)
        row["Moneda"] = "RON"
        row["Stoc Cantitativ"] = 1
        row["Activ in Magazin"] = "DA"
        row["Categorie / Categorii"] = cat
        for k, v in list(row.items()):
            row[k] = _clean_cell(v)
        rows.append(row)
    return pd.DataFrame(rows, columns=headers)


def save_tsv(df: pd.DataFrame, path: str) -> None:
    df.to_csv(path, sep="\t", index=False, encoding="utf-8")


def save_xlsx(df: pd.DataFrame, path: str) -> None:
    # Backward compat: if they pass .tsv, write TSV
    if str(path).lower().endswith(".tsv"):
        return save_tsv(df, path)
    df.to_excel(path, index=False)
