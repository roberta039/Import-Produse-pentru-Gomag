"""
Aplicație Streamlit pentru importul automatizat de produse în Gomag
"""

import streamlit as st
import pandas as pd
from typing import List, Dict, Optional
import time
import logging
from io import BytesIO
import json

from scrapers import get_scraper_for_url, get_supported_domains
from utils.translator import ProductTranslator
from utils.gomag_api import GomagAPI
from config import ProductData

# Configurare logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configurare pagină
st.set_page_config(
    page_title="Import Produse Gomag",
    page_icon="🛒",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS personalizat
st.markdown("""
<style>
    .stProgress > div > div > div > div {
        background-color: #1f77b4;
    }
    .success-box {
        padding: 10px;
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        border-radius: 5px;
        margin: 5px 0;
    }
    .error-box {
        padding: 10px;
        background-color: #f8d7da;
        border: 1px solid #f5c6cb;
        border-radius: 5px;
        margin: 5px 0;
    }
    .info-box {
        padding: 10px;
        background-color: #cce5ff;
        border: 1px solid #b8daff;
        border-radius: 5px;
        margin: 5px 0;
    }
</style>
""", unsafe_allow_html=True)

def init_session_state():
    """Inițializează variabilele de sesiune"""
    if 'products' not in st.session_state:
        st.session_state.products = []
    if 'scraped_products' not in st.session_state:
        st.session_state.scraped_products = []
    if 'gomag_api' not in st.session_state:
        st.session_state.gomag_api = None
    if 'categories' not in st.session_state:
        st.session_state.categories = []
    if 'import_log' not in st.session_state:
        st.session_state.import_log = []

def get_credentials(site_key: str) -> Dict[str, str]:
    """Obține credențialele pentru un site din Secrets"""
    try:
        if site_key in st.secrets:
            return dict(st.secrets[site_key])
    except:
        pass
    return {}

def connect_to_gomag() -> Optional[GomagAPI]:
    """Conectează la Gomag"""
    try:
        gomag_config = st.secrets.get("gomag", {})
        
        if not gomag_config:
            st.sidebar.error("⚠️ Credențiale Gomag lipsă! Configurează în Secrets.")
            return None
        
        api = GomagAPI(
            base_url=gomag_config.get("url", ""),
            username=gomag_config.get("username", ""),
            password=gomag_config.get("password", ""),
            api_key=gomag_config.get("api_key", "")
        )
        
        if api.login():
            st.sidebar.success("✅ Conectat la Gomag")
            return api
        else:
            st.sidebar.error("❌ Eroare la conectarea la Gomag")
            return None
            
    except Exception as e:
        st.sidebar.error(f"❌ Eroare: {e}")
        return None

def scrape_product(url: str) -> Optional[ProductData]:
    """Scrapează un produs"""
    # Determină site-ul și obține credențialele
    scraper = get_scraper_for_url(url)
    
    if not scraper:
        st.warning(f"⚠️ Site nesuportat: {url}")
        return None
    
    try:
        product = scraper.scrape_product(url)
        return product
    except Exception as e:
        st.error(f"❌ Eroare la scraping {url}: {e}")
        return None

def translate_product(product: ProductData) -> ProductData:
    """Traduce un produs"""
    translator = ProductTranslator()
    return translator.translate_product(product)

def main():
    """Funcția principală"""
    init_session_state()
    
    # Header
    st.title("🛒 Import Automatizat Produse în Gomag")
    st.markdown("---")
    
    # Sidebar - Configurări
    with st.sidebar:
        st.header("⚙️ Configurări")
        
        # Conexiune Gomag
        st.subheader("🔗 Conexiune Gomag")
        
        # Afișează status conexiune
        if st.button("🔌 Conectează la Gomag"):
            st.session_state.gomag_api = connect_to_gomag()
            if st.session_state.gomag_api:
                st.session_state.categories = st.session_state.gomag_api.get_categories()
        
        # Site-uri suportate
        st.subheader("🌐 Site-uri Suportate")
        supported = get_supported_domains()
        for domain in supported:
            st.markdown(f"• {domain}")
        
        st.markdown("---")
        
        # Opțiuni
        st.subheader("📝 Opțiuni")
        auto_translate = st.checkbox("Traducere automată în română", value=True)
        download_images = st.checkbox("Descarcă imagini local", value=False)
        skip_existing = st.checkbox("Sari peste produse existente", value=True)
    
    # Main content - Tabs
    tab1, tab2, tab3, tab4 = st.tabs([
        "📤 Upload Link-uri",
        "🔍 Previzualizare Produse",
        "📁 Gestionare Categorii",
        "📊 Import & Raport"
    ])
    
    # Tab 1: Upload
    with tab1:
        st.header("📤 Încarcă Link-uri Produse")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📎 Upload Excel/CSV")
            uploaded_file = st.file_uploader(
                "Încarcă fișierul cu link-uri",
                type=['xlsx', 'xls', 'csv'],
                help="Fișierul trebuie să conțină o coloană cu link-uri"
            )
            
            if uploaded_file:
                try:
                    if uploaded_file.name.endswith('.csv'):
                        df = pd.read_csv(uploaded_file)
                    else:
                        df = pd.read_excel(uploaded_file)
                    
                    st.success(f"✅ Fișier încărcat: {len(df)} rânduri")
                    
                    # Selectează coloana cu link-uri
                    columns = df.columns.tolist()
                    url_column = st.selectbox(
                        "Selectează coloana cu link-uri:",
                        columns,
                        index=0 if columns else None
                    )
                    
                    if url_column:
                        urls = df[url_column].dropna().tolist()
                        st.info(f"📝 {len(urls)} link-uri găsite")
                        
                        if st.button("➕ Adaugă link-uri la coadă"):
                            st.session_state.products.extend([
                                {'url': url, 'status': 'pending'} 
                                for url in urls if url.startswith('http')
                            ])
                            st.success(f"✅ {len(urls)} link-uri adăugate")
                            st.rerun()
                
                except Exception as e:
                    st.error(f"❌ Eroare la citirea fișierului: {e}")
        
        with col2:
            st.subheader("✏️ Adaugă Manual")
            manual_urls = st.text_area(
                "Introdu link-uri (unul pe linie):",
                height=200,
                placeholder="https://example.com/product1\nhttps://example.com/product2"
            )
            
            if st.button("➕ Adaugă link-uri"):
                urls = [url.strip() for url in manual_urls.split('\n') if url.strip().startswith('http')]
                if urls:
                    st.session_state.products.extend([
                        {'url': url, 'status': 'pending'} 
                        for url in urls
                    ])
                    st.success(f"✅ {len(urls)} link-uri adăugate")
                    st.rerun()
        
        # Afișează coada
        st.markdown("---")
        st.subheader("📋 Coada de Produse")
        
        if st.session_state.products:
            df_queue = pd.DataFrame(st.session_state.products)
            st.dataframe(df_queue, use_container_width=True)
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                if st.button("🔄 Scrapează Toate"):
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    scraped = []
                    total = len(st.session_state.products)
                    
                    for idx, item in enumerate(st.session_state.products):
                        if item['status'] == 'pending':
                            status_text.text(f"Scraping: {item['url'][:50]}...")
                            
                            product = scrape_product(item['url'])
                            
                            if product:
                                if auto_translate:
                                    product = translate_product(product)
                                
                                scraped.append(product)
                                item['status'] = 'scraped'
                                item['name'] = product.name_ro or product.name
                            else:
                                item['status'] = 'error'
                        
                        progress_bar.progress((idx + 1) / total)
                    
                    st.session_state.scraped_products.extend(scraped)
                    status_text.text(f"✅ Completat! {len(scraped)} produse extrase.")
                    st.rerun()
            
            with col2:
                if st.button("🗑️ Golește Coada"):
                    st.session_state.products = []
                    st.rerun()
            
            with col3:
                pending = len([p for p in st.session_state.products if p['status'] == 'pending'])
                scraped = len([p for p in st.session_state.products if p['status'] == 'scraped'])
                errors = len([p for p in st.session_state.products if p['status'] == 'error'])
                st.metric("Status", f"⏳{pending} ✅{scraped} ❌{errors}")
        else:
            st.info("📭 Coada este goală. Încarcă link-uri pentru a începe.")
    
    # Tab 2: Previzualizare
    with tab2:
        st.header("🔍 Previzualizare Produse Extrase")
        
        if st.session_state.scraped_products:
            for idx, product in enumerate(st.session_state.scraped_products):
                with st.expander(f"📦 {product.name_ro or product.name} ({product.sku})", expanded=False):
                    col1, col2 = st.columns([1, 2])
                    
                    with col1:
                        # Imagini
                        if product.images:
                            st.image(product.images[0], width=200)
                            if len(product.images) > 1:
                                st.caption(f"+{len(product.images)-1} imagini")
                    
                    with col2:
                        st.markdown(f"**SKU:** {product.sku}")
                        st.markdown(f"**Brand:** {product.brand}")
                        st.markdown(f"**Preț:** {product.price} {product.currency}")
                        
                        if product.colors:
                            colors = [c.get('name_ro') or c.get('name') for c in product.colors]
                            st.markdown(f"**Culori:** {', '.join(colors)}")
                        
                        if product.sizes:
                            st.markdown(f"**Mărimi:** {', '.join(product.sizes)}")
                    
                    # Descriere
                    st.markdown("**Descriere:**")
                    st.text_area(
                        "Descriere",
                        value=product.description_ro or product.description,
                        height=100,
                        key=f"desc_{idx}",
                        label_visibility="collapsed"
                    )
                    
                    # Specificații
                    if product.specifications_ro or product.specifications:
                        st.markdown("**Specificații:**")
                        specs = product.specifications_ro or product.specifications
                        specs_df = pd.DataFrame(
                            list(specs.items()),
                            columns=['Atribut', 'Valoare']
                        )
                        st.dataframe(specs_df, use_container_width=True)
        else:
            st.info("📭 Nu există produse extrase. Mergi la tab-ul Upload pentru a începe.")
    
    # Tab 3: Categorii
    with tab3:
        st.header("📁 Gestionare Categorii Gomag")
        
        if st.session_state.gomag_api:
            # Reîncarcă categorii
            if st.button("🔄 Reîncarcă Categorii"):
                st.session_state.categories = st.session_state.gomag_api.get_categories()
                st.rerun()
            
            # Afișează categorii existente
            if st.session_state.categories:
                st.subheader("📂 Categorii Existente")
                
                categories_df = pd.DataFrame(st.session_state.categories)
                st.dataframe(categories_df, use_container_width=True)
                
                # Selectează categorie pentru import
                category_names = [c['name'] for c in st.session_state.categories]
                selected_category = st.selectbox(
                    "Selectează categoria pentru import:",
                    options=category_names,
                    key="import_category"
                )
                
                if selected_category:
                    # Găsește ID-ul categoriei
                    for cat in st.session_state.categories:
                        if cat['name'] == selected_category:
                            st.session_state.selected_category_id = cat['id']
                            st.info(f"📁 Categorie selectată: {selected_category} (ID: {cat['id']})")
                            break
            
            # Creare categorie nouă
            st.markdown("---")
            st.subheader("➕ Creare Categorie Nouă")
            
            col1, col2 = st.columns(2)
            with col1:
                new_category_name = st.text_input("Nume categorie:")
            with col2:
                parent_category = st.selectbox(
                    "Categorie părinte (opțional):",
                    options=["Niciuna"] + [c['name'] for c in st.session_state.categories],
                    key="parent_category"
                )
            
            if st.button("➕ Creează Categorie"):
                if new_category_name:
                    parent_id = None
                    if parent_category != "Niciuna":
                        for cat in st.session_state.categories:
                            if cat['name'] == parent_category:
                                parent_id = cat['id']
                                break
                    
                    result = st.session_state.gomag_api.create_category(
                        new_category_name,
                        parent_id
                    )
                    
                    if result:
                        st.success(f"✅ Categorie '{new_category_name}' creată cu succes!")
                        st.session_state.categories = st.session_state.gomag_api.get_categories()
                        st.rerun()
                    else:
                        st.error("❌ Eroare la crearea categoriei")
                else:
                    st.warning("⚠️ Introdu un nume pentru categorie")
        else:
            st.warning("⚠️ Conectează-te la Gomag pentru a gestiona categoriile")
    
    # Tab 4: Import & Raport
    with tab4:
        st.header("📊 Import Produse & Raport")
        
        if st.session_state.gomag_api and st.session_state.scraped_products:
            # Selectează categoria
            if st.session_state.categories:
                import_category = st.selectbox(
                    "Selectează categoria pentru import:",
                    options=[c['name'] for c in st.session_state.categories],
                    key="final_import_category"
                )
                
                # Găsește ID-ul
                category_id = None
                for cat in st.session_state.categories:
                    if cat['name'] == import_category:
                        category_id = cat['id']
                        break
                
                # Opțiuni import
                col1, col2 = st.columns(2)
                with col1:
                    products_to_import = st.multiselect(
                        "Selectează produsele de importat:",
                        options=[p.name_ro or p.name for p in st.session_state.scraped_products],
                        default=[p.name_ro or p.name for p in st.session_state.scraped_products]
                    )
                
                with col2:
                    st.metric("Produse selectate", len(products_to_import))
                
                # Buton import
                if st.button("🚀 Începe Importul", type="primary"):
                    if category_id and products_to_import:
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        
                        success_count = 0
                        error_count = 0
                        
                        for idx, product in enumerate(st.session_state.scraped_products):
                            product_name = product.name_ro or product.name
                            
                            if product_name in products_to_import:
                                status_text.text(f"Importare: {product_name}...")
                                
                                # Verifică dacă există
                                if skip_existing and st.session_state.gomag_api.check_product_exists(product.sku):
                                    st.session_state.import_log.append({
                                        'product': product_name,
                                        'status': 'skipped',
                                        'message': 'Produs existent'
                                    })
                                    continue
                                
                                # Import
                                result = st.session_state.gomag_api.import_product(
                                    product,
                                    category_id
                                )
                                
                                if result:
                                    success_count += 1
                                    st.session_state.import_log.append({
                                        'product': product_name,
                                        'status': 'success',
                                        'message': 'Importat cu succes'
                                    })
                                else:
                                    error_count += 1
                                    st.session_state.import_log.append({
                                        'product': product_name,
                                        'status': 'error',
                                        'message': 'Eroare la import'
                                    })
                            
                            progress_bar.progress((idx + 1) / len(st.session_state.scraped_products))
                        
                        status_text.text(f"✅ Import completat! Succes: {success_count}, Erori: {error_count}")
                    else:
                        st.warning("⚠️ Selectează o categorie și cel puțin un produs")
            else:
                st.warning("⚠️ Nu există categorii. Creează una în tab-ul Categorii.")
            
            # Log import
            st.markdown("---")
            st.subheader("📋 Jurnal Import")
            
            if st.session_state.import_log:
                log_df = pd.DataFrame(st.session_state.import_log)
                st.dataframe(log_df, use_container_width=True)
                
                # Export raport
                col1, col2 = st.columns(2)
                with col1:
                    csv = log_df.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        "📥 Descarcă Raport (CSV)",
                        csv,
                        "import_report.csv",
                        "text/csv"
                    )
                
                with col2:
                    if st.button("🗑️ Golește Log"):
                        st.session_state.import_log = []
                        st.rerun()
        
        elif not st.session_state.gomag_api:
            st.warning("⚠️ Conectează-te la Gomag pentru a importa produse")
        else:
            st.info("📭 Nu există produse de importat. Extrage produse mai întâi.")
    
    # Footer
    st.markdown("---")
    st.markdown(
        """
        <div style='text-align: center; color: gray;'>
            🛒 Product Importer for Gomag | v1.0
        </div>
        """,
        unsafe_allow_html=True
    )

if __name__ == "__main__":
    main()
