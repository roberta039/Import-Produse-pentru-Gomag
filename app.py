from __future__ import annotations
import streamlit as st
import time
from concurrent.futures import ThreadPoolExecutor
# --- PSI ProductFinder creds -> env (for scrapers) ---
import os as _os
try:
    _os.environ["PSI_USER"] = str(st.secrets.get("SOURCES", {}).get("PSI_USER", "")).strip()
    _os.environ["PSI_PASS"] = str(st.secrets.get("SOURCES", {}).get("PSI_PASS", "")).strip()
except Exception:
    pass

# --- XDConnects creds -> env (for scrapers) ---
import os as _os
try:
    _os.environ["XD_USER"] = str(st.secrets.get("SOURCES", {}).get("XD_USER", "")).strip()
    _os.environ["XD_PASS"] = str(st.secrets.get("SOURCES", {}).get("XD_PASS", "")).strip()
except Exception:
    pass

import pandas as pd
import tempfile
from src.utils import detect_url_column
from src.pipeline import scrape_products
from src.export_gomag import to_gomag_dataframe, save_xlsx
from src.gomag_ui import GomagCreds, fetch_categories, import_file

st.set_page_config(page_title="Gomag Importer", layout="wide")
st.title("Import produse in Gomag")
st.caption("Flux: Excel -> preluare date -> tabel intermediar -> genereaza XLSX import -> (optional) browser automation import in Gomag")

with st.sidebar:
    st.divider()
    st.header("Gomag")
    gomag_enabled = st.checkbox("Activeaza conectare Gomag (Playwright)", value=False)
    if gomag_enabled:
        try:
            base_url = st.secrets["GOMAG"]["BASE_URL"]
            dashboard_path = st.secrets["GOMAG"].get("DASHBOARD_PATH", "/gomag/dashboard")
            username = st.secrets["GOMAG"]["USERNAME"]
            password = st.secrets["GOMAG"]["PASSWORD"]
            creds = GomagCreds(base_url=base_url, dashboard_path=dashboard_path, username=username, password=password)
            st.success("Secrets Gomag incarcate.")
        except Exception:
            creds = None
            st.error("Lipsesc secrets Gomag. Completeaza in Streamlit Cloud -> Settings -> Secrets.")
    else:
        creds = None

st.subheader("1) Incarca Excel cu link-uri")
uploaded = st.file_uploader("Excel (.xlsx)", type=["xlsx"])

if "drafts" not in st.session_state:
    st.session_state["drafts"] = []
if "df_edit" not in st.session_state:
    st.session_state["df_edit"] = None
if "categories" not in st.session_state:
    st.session_state["categories"] = []

if uploaded:
    df = pd.read_excel(uploaded)
    url_col = detect_url_column(df.columns)
    if not url_col:
        st.error("Nu am gasit coloana URL. Foloseste una din: url / link / product_url")
        st.stop()
    urls = df[url_col].dropna().astype(str).tolist()
    st.write(f"Gasite **{len(urls)}** link-uri in coloana **{url_col}**.")
    st.dataframe(df.head(20), use_container_width=True)

    colA, colB = st.columns([1,1])
    with colA:
        if st.button("2) Preia date din link-uri", type="primary"):
            with st.spinner("Scrape in curs (poate dura)..."):
                drafts = scrape_products(urls)
            st.session_state["drafts"] = drafts
            st.success(f"Am preluat {len(drafts)} produse.")
    with colB:
        if creds and st.button("Incarca categorii din Gomag"):
            with st.spinner("Citesc categoriile din Gomag..."):
                try:
                    cats = fetch_categories(creds)
                    st.session_state["categories"] = cats
                    st.success(f"Gasite {len(cats)} categorii.")
                except Exception as e:
                    st.error(f"Eroare la citire categorii: {e}")

if st.session_state["drafts"]:
    st.subheader("3) Tabel intermediar (verifica / corecteaza)")
    drafts = st.session_state["drafts"]
    cats = st.session_state.get("categories", [])

    # Build editable df
    base_rows = []
    for p in drafts:
        base_rows.append({
            "source_url": p.source_url,
            "sku": p.sku,
            "title_ro": p.title,
            "short_ro": p.short_description,
            "desc_html_ro": p.description_html,
            "price_source": p.price if p.price is not None else "",
            "price_final": p.price_final(),
            "images": "|".join(p.images or []),
            "category": "",
            "needs_translation": p.needs_translation,
            "notes": p.notes,
        })
    df_edit = pd.DataFrame(base_rows)

    # category dropdown
    colcfg = {}
    if cats:
        colcfg["category"] = st.column_config.SelectboxColumn(
            "category", options=[""] + cats, help="Alege categoria Gomag"
        )
    else:
        colcfg["category"] = st.column_config.TextColumn("category", help="Scrie categoria (ex: Rucsacuri>Antifurt)")

    edited = st.data_editor(
        df_edit,
        use_container_width=True,
        num_rows="fixed",
        column_config=colcfg,
        hide_index=True
    )
    st.session_state["df_edit"] = edited

    st.subheader("4) Genereaza fisier import Gomag")
    col1, col2, col3 = st.columns([1,1,1])
    with col1:
        if st.button("Genereaza XLSX"):
            # push category back into drafts via map
            category_map = {row["source_url"]: row.get("category","") for _, row in edited.iterrows()}
            df_gomag = to_gomag_dataframe(drafts, category_map=category_map)

            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
            tmp.close()
            save_xlsx(df_gomag, tmp.name)

            with open(tmp.name, "rb") as f:
                st.download_button(
                    "Descarca import_gomag.xlsx",
                    data=f,
                    file_name="import_gomag.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    type="primary"
                )
            st.dataframe(df_gomag.head(50), use_container_width=True)

            st.session_state["last_export_path"] = tmp.name

    with col2:
        if creds and st.button("5) Import in Gomag (Playwright)"):
            export_path = st.session_state.get("last_export_path")
            if not export_path:
                st.error("Genereaza mai intai XLSX (butonul de mai sus).")
            else:
                # Ruleaza importul in thread + progres, ca sa nu para blocat

                with st.status("Import in Gomag...", expanded=True) as status:

                    status.write("Pornesc automatizarea (Playwright)...")

                    executor = ThreadPoolExecutor(max_workers=1)

                    fut = executor.submit(import_file, creds, export_path)

                    t0 = time.time()

                    timeout_s = 300  # 5 minute

                    last_tick = -1


                    while not fut.done():

                        elapsed = int(time.time() - t0)

                        if elapsed != last_tick and elapsed % 3 == 0:

                            status.write(f"Inca ruleaza... {elapsed}s")

                            last_tick = elapsed

                        if elapsed >= timeout_s:

                            status.update(label="Timeout import", state="error", expanded=True)

                            st.error(

                                "Importul dureaza prea mult. Cel mai probabil Gomag ruleaza importul in fundal "

                                "sau pagina s-a blocat. Verifica in Gomag: Produse > Import (lista importuri)."

                            )

                            break

                        time.sleep(1)


                    if fut.done():

                        try:

                            msg = fut.result()

                            status.update(label="Import finalizat", state="complete", expanded=False)

                            st.success(msg)

                        except Exception as e:

                            status.update(label="Eroare import", state="error", expanded=True)

                            st.error(f"Eroare import: {e}")

    with col3:
        st.info("Tip: Fa o importare manuala o data in Gomag ca sa salvezi maparea coloanelor; apoi automatizarea devine mai stabila.")
