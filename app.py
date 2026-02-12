import asyncio
import pandas as pd
import streamlit as st

from src.gomag_api import GomagClient
from src.pipeline import process_one_url, ImportSettings

st.set_page_config(page_title="Importer produse → Gomag", layout="wide")
st.title("Importer produse din URL-uri → Gomag")

if "GOMAG_APIKEY" not in st.secrets or "GOMAG_APISHOP" not in st.secrets:
    st.error("Lipsesc secretele: GOMAG_APIKEY și/sau GOMAG_APISHOP în Streamlit Secrets.")
    st.stop()

gomag = GomagClient(apikey=st.secrets["GOMAG_APIKEY"], apishop=st.secrets["GOMAG_APISHOP"])

uploaded = st.file_uploader("Încarcă Excel cu o coloană numită `url`", type=["xlsx", "xls"])
if not uploaded:
    st.info("Încarcă un fișier Excel cu coloana `url`.")
    st.stop()

df = pd.read_excel(uploaded)
if "url" not in df.columns:
    st.error("Excel-ul trebuie să aibă o coloană numită: url")
    st.stop()

urls = df["url"].dropna().astype(str).tolist()
st.caption(f"URL-uri găsite: {len(urls)}")

with st.spinner("Citesc categoriile din Gomag..."):
    cats = gomag.category_read(limit=5000)

cat_options = []
for c in cats or []:
    name = c.get("name") or c.get("title") or f"cat_{c.get('id')}"
    cid = c.get("id")
    if cid is not None:
        cat_options.append((name, cid))

selected_cat_id = None
if cat_options:
    selected_cat_id = st.selectbox("Alege categoria Gomag pentru import", options=cat_options, format_func=lambda x: x[0])[1]
else:
    st.warning("Nu am putut citi categoriile sau lista e goală. Poți crea una nouă.")

colA, colB = st.columns([2, 1])
with colA:
    new_cat_name = st.text_input("Creează categorie nouă (opțional)")
with colB:
    if st.button("Creează", use_container_width=True) and new_cat_name.strip():
        created = gomag.category_write(name=new_cat_name.strip(), parent_id=selected_cat_id)
        st.success(f"Categorie creată: {created}")
        st.rerun()

st.divider()

st.subheader("Setări import")
c1, c2, c3, c4 = st.columns(4)
with c1:
    eur_ron = st.number_input("Curs EUR→RON", min_value=0.01, value=4.97, step=0.01)
with c2:
    gbp_ron = st.number_input("Curs GBP→RON", min_value=0.01, value=5.80, step=0.01)
with c3:
    markup = st.number_input("Markup % (100% = dublu)", min_value=0.0, value=100.0, step=5.0)
with c4:
    force_pw = st.checkbox("Forțează Playwright (mai lent, dar compatibil JS)", value=str(st.secrets.get("FORCE_PLAYWRIGHT", "0")) == "1")

st.caption("Reguli: preț×(1+markup%), rotunjire în sus la x.90; dacă lipsește preț → 1 RON. Stoc=1. Produse vizibile imediat.")

with st.expander("Preview (primele 5 URL-uri)", expanded=False):
    st.write(urls[:5])

if st.button("Importă în Gomag", type="primary"):
    settings = ImportSettings(
        category_id=selected_cat_id,
        eur_ron=eur_ron,
        gbp_ron=gbp_ron,
        markup_percent=markup,
        stock_default=1,
        missing_price_fallback_ron=1.0,
        publish_immediately=True,
        force_playwright=force_pw,
    )

    progress = st.progress(0.0)
    results = []
    details = []

    for i, url in enumerate(urls, start=1):
        try:
            out = asyncio.run(process_one_url(url, settings, gomag, dict(st.secrets)))
            results.append({"url": url, "status": "OK", "sku": out.get("sku"), "price_ron": out.get("price_ron"), "name": out.get("name")})
            details.append({"url": url, "result": out})
        except Exception as e:
            results.append({"url": url, "status": "ERR", "sku": "", "price_ron": "", "name": "", "error": str(e)})
            details.append({"url": url, "error": str(e)})
        progress.progress(i / max(1, len(urls)))

    st.success("Gata.")
    st.dataframe(pd.DataFrame(results))

    with st.expander("Show details (debug)", expanded=False):
        st.json(details)
