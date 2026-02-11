import streamlit as st
import pandas as pd
import time
import json
from datetime import datetime
from typing import List, Dict
import logging
from io import BytesIO

from scrapers import ScraperFactory, Product
from utils.translator import ProductTranslator
from utils.gomag_api import GomagAPI
from utils.image_handler import ImageHandler
from config import Config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Page configuration
st.set_page_config(
    page_title="🎒 Product Importer - Gomag",
    page_icon="🎒",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1E88E5;
        text-align: center;
        margin-bottom: 2rem;
    }
    .status-success {
        color: #4CAF50;
        font-weight: bold;
    }
    .status-error {
        color: #f44336;
        font-weight: bold;
    }
    .status-pending {
        color: #FF9800;
    }
    .product-card {
        border: 1px solid #ddd;
        border-radius: 10px;
        padding: 1rem;
        margin-bottom: 1rem;
        background: #f9f9f9;
    }
    .stProgress > div > div > div > div {
        background-color: #1E88E5;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'products' not in st.session_state:
    st.session_state.products = []
if 'processed_products' not in st.session_state:
    st.session_state.processed_products = []
if 'gomag_api' not in st.session_state:
    st.session_state.gomag_api = None
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False

def main():
    st.markdown('<h1 class="main-header">🎒 Product Importer pentru Gomag</h1>', unsafe_allow_html=True)
    
    # Sidebar - Authentication
    with st.sidebar:
        st.header("⚙️ Configurare")
        
        st.subheader("🔐 Autentificare Gomag")
        gomag_username = st.text_input("Username Gomag", type="default")
        gomag_password = st.text_input("Password Gomag", type="password")
        
        if st.button("🔓 Conectare la Gomag"):
            with st.spinner("Se conectează..."):
                api = GomagAPI()
                if api.login(gomag_username, gomag_password):
                    st.session_state.gomag_api = api
                    st.session_state.authenticated = True
                    st.success("✅ Conectat cu succes!")
                else:
                    st.error("❌ Autentificare eșuată!")
        
        if st.session_state.authenticated:
            st.success("✅ Conectat la Gomag")
        
        st.divider()
        
        st.subheader("🌍 Setări Traducere")
        source_lang = st.selectbox("Limba sursă", ["en", "de", "fr", "it", "es"], index=0)
        target_lang = st.selectbox("Limba țintă", ["ro"], index=0)
        
        st.divider()
        
        st.subheader("📊 Statistici")
        st.metric("Produse încărcate", len(st.session_state.products))
        st.metric("Produse procesate", len(st.session_state.processed_products))
    
    # Main content - Tabs
    tab1, tab2, tab3, tab4 = st.tabs([
        "📤 Încărcare Link-uri",
        "👁️ Previzualizare Produse",
        "🔄 Procesare & Import",
        "📋 Istoric & Export"
    ])
    
    # Tab 1: Upload Links
    with tab1:
        st.header("📤 Încărcă Link-urile Produselor")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📁 Încărcare din Excel")
            uploaded_file = st.file_uploader(
                "Alege fișierul Excel cu link-uri",
                type=['xlsx', 'xls', 'csv'],
                help="Fișierul trebuie să conțină o coloană numită 'url' sau 'link'"
            )
            
            if uploaded_file:
                try:
                    if uploaded_file.name.endswith('.csv'):
                        df = pd.read_csv(uploaded_file)
                    else:
                        df = pd.read_excel(uploaded_file)
                    
                    # Find URL column
                    url_column = None
                    for col in df.columns:
                        if 'url' in col.lower() or 'link' in col.lower():
                            url_column = col
                            break
                    
                    if url_column is None:
                        url_column = df.columns[0]  # Use first column
                    
                    urls = df[url_column].dropna().tolist()
                    st.success(f"✅ Găsite {len(urls)} link-uri în fișier")
                    
                    with st.expander("📋 Vezi link-urile găsite"):
                        for i, url in enumerate(urls, 1):
                            st.text(f"{i}. {url}")
                    
                    if st.button("➕ Adaugă toate link-urile", key="add_excel"):
                        for url in urls:
                            if url not in st.session_state.products:
                                st.session_state.products.append({'url': url, 'status': 'pending'})
                        st.success(f"✅ Adăugate {len(urls)} produse")
                        st.rerun()
                        
                except Exception as e:
                    st.error(f"❌ Eroare la citirea fișierului: {e}")
        
        with col2:
            st.subheader("✍️ Introducere manuală")
            manual_urls = st.text_area(
                "Introdu link-urile (câte unul pe linie)",
                height=200,
                placeholder="https://www.xdconnects.com/...\nhttps://www.pfconcept.com/..."
            )
            
            if st.button("➕ Adaugă link-urile", key="add_manual"):
                urls = [url.strip() for url in manual_urls.split('\n') if url.strip()]
                added = 0
                for url in urls:
                    if url not in [p['url'] for p in st.session_state.products]:
                        st.session_state.products.append({'url': url, 'status': 'pending'})
                        added += 1
                st.success(f"✅ Adăugate {added} produse noi")
                st.rerun()
        
        # Quick add from provided URLs
        st.divider()
        st.subheader("⚡ Adăugare rapidă - Link-uri predefinite")
        
        predefined_urls = [
            "https://promobox.com/en/products/MAGNUM?color=10",
            "https://andapresent.com/ro/ro/products/AP721326-10",
            "https://www.xdconnects.com/en-gb/bags-travel/anti-theft-backpacks/bobby-hero-regular-anti-theft-backpack-p705.29?variantId=P705.291",
            "https://www.pfconcept.com/en_cz/cover-grs-rpet-anti-theft-backpack-18l-120510.html",
            "https://www.midocean.com/central-europe/us/eur/bags-travel/backpacks/laptop-backpacks/mo2739-03-zid10244354",
        ]
        
        if st.button("➕ Adaugă link-urile exemplu"):
            for url in predefined_urls:
                if url not in [p['url'] for p in st.session_state.products]:
                    st.session_state.products.append({'url': url, 'status': 'pending'})
            st.success("✅ Link-uri exemplu adăugate!")
            st.rerun()
    
    # Tab 2: Preview Products
    with tab2:
        st.header("👁️ Previzualizare Produse")
        
        if not st.session_state.products:
            st.info("📭 Nu există produse încărcate. Adaugă link-uri în tab-ul anterior.")
        else:
            # Actions
            col1, col2, col3 = st.columns(3)
            with col1:
                if st.button("🔍 Extrage informații produse"):
                    extract_products(source_lang, target_lang)
            with col2:
                if st.button("🗑️ Șterge toate produsele"):
                    st.session_state.products = []
                    st.session_state.processed_products = []
                    st.rerun()
            with col3:
                if st.button("🔄 Reîncarcă"):
                    st.rerun()
            
            st.divider()
            
            # Display products
            for i, product in enumerate(st.session_state.products):
                with st.expander(f"📦 {product.get('name', product['url'][:60])}...", expanded=False):
                    col1, col2 = st.columns([1, 3])
                    
                    with col1:
                        # Show first image if available
                        images = product.get('images', [])
                        if images:
                            st.image(images[0], width=150)
                        else:
                            st.image("https://via.placeholder.com/150x150?text=No+Image", width=150)
                    
                    with col2:
                        status = product.get('status', 'pending')
                        if status == 'success':
                            st.markdown('<span class="status-success">✅ Procesat</span>', unsafe_allow_html=True)
                        elif status == 'error':
                            st.markdown('<span class="status-error">❌ Eroare</span>', unsafe_allow_html=True)
                        else:
                            st.markdown('<span class="status-pending">⏳ În așteptare</span>', unsafe_allow_html=True)
                        
                        st.write(f"**URL:** {product['url']}")
                        st.write(f"**SKU:** {product.get('sku', 'N/A')}")
                        st.write(f"**Nume:** {product.get('name', 'N/A')}")
                        st.write(f"**Brand:** {product.get('brand', 'N/A')}")
                        st.write(f"**Preț:** {product.get('price', 'N/A')} {product.get('currency', 'EUR')}")
                        
                        if product.get('description'):
                            st.write("**Descriere:**")
                            st.write(product['description'][:300] + "..." if len(product.get('description', '')) > 300 else product['description'])
                        
                        if product.get('specifications'):
                            st.write("**Specificații:**")
                            for key, value in list(product['specifications'].items())[:5]:
                                st.write(f"  • {key}: {value}")
                        
                        if product.get('variants'):
                            st.write(f"**Variante:** {len(product['variants'])} culori/mărimi disponibile")
                    
                    if st.button(f"🗑️ Șterge", key=f"delete_{i}"):
                        st.session_state.products.pop(i)
                        st.rerun()
    
    # Tab 3: Process & Import
    with tab3:
        st.header("🔄 Procesare & Import în Gomag")
        
        if not st.session_state.authenticated:
            st.warning("⚠️ Te rog să te autentifici în Gomag din bara laterală.")
        else:
            st.success("✅ Conectat la Gomag - pregătit pentru import")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📝 Opțiuni Import")
            
            import_images = st.checkbox("📷 Importă și imaginile", value=True)
            translate_products = st.checkbox("🌍 Traduce în română", value=True)
            create_variants = st.checkbox("🎨 Creează variante culori/mărimi", value=True)
            set_active = st.checkbox("✅ Setează produsele ca active", value=True)
            
            default_category = st.text_input("📁 Categoria implicită", "Rucsacuri Anti-Furt")
            default_markup = st.number_input("💰 Adaos comercial (%)", min_value=0, max_value=200, value=30)
        
        with col2:
            st.subheader("📊 Progres Import")
            
            pending = len([p for p in st.session_state.products if p.get('status') == 'pending'])
            success = len([p for p in st.session_state.products if p.get('status') == 'success'])
            errors = len([p for p in st.session_state.products if p.get('status') == 'error'])
            
            st.metric("În așteptare", pending)
            st.metric("Importate cu succes", success)
            st.metric("Erori", errors)
        
        st.divider()
        
        if st.button("🚀 Începe Importul", disabled=not st.session_state.authenticated, use_container_width=True):
            import_products(
                translate=translate_products,
                import_images=import_images,
                create_variants=create_variants,
                category=default_category,
                markup=default_markup,
                source_lang=source_lang,
                target_lang=target_lang
            )
    
    # Tab 4: History & Export
    with tab4:
        st.header("📋 Istoric & Export")
        
        if st.session_state.processed_products:
            # Create DataFrame
            df_data = []
            for p in st.session_state.processed_products:
                df_data.append({
                    'SKU': p.get('sku', ''),
                    'Nume': p.get('name', ''),
                    'Brand': p.get('brand', ''),
                    'Preț': p.get('price', 0),
                    'Status': p.get('status', ''),
                    'URL': p.get('url', ''),
                    'Gomag ID': p.get('gomag_id', 'N/A')
                })
            
            df = pd.DataFrame(df_data)
            st.dataframe(df, use_container_width=True)
            
            # Export options
            col1, col2, col3 = st.columns(3)
            
            with col1:
                # Export to Excel
                output = BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df.to_excel(writer, index=False, sheet_name='Produse')
                
                st.download_button(
                    "📥 Descarcă Excel",
                    data=output.getvalue(),
                    file_name=f"produse_import_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            
            with col2:
                # Export to CSV
                csv = df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    "📥 Descarcă CSV",
                    data=csv,
                    file_name=f"produse_import_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )
            
            with col3:
                # Export to JSON
                json_data = json.dumps(st.session_state.processed_products, indent=2, ensure_ascii=False)
                st.download_button(
                    "📥 Descarcă JSON",
                    data=json_data,
                    file_name=f"produse_import_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    mime="application/json"
                )
        else:
            st.info("📭 Nu există produse procesate încă.")

def extract_products(source_lang: str, target_lang: str):
    """Extract product information from URLs"""
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    translator = ProductTranslator(source_lang, target_lang)
    
    for i, product in enumerate(st.session_state.products):
        if product.get('status') == 'success':
            continue
        
        progress = (i + 1) / len(st.session_state.products)
        progress_bar.progress(progress)
        status_text.text(f"Procesez: {product['url'][:50]}...")
        
        try:
            # Get appropriate scraper
            scraped = ScraperFactory.scrape_url(product['url'])
            
            if scraped:
                # Translate
                translator.translate_product(scraped)
                
                # Update product data
                st.session_state.products[i].update({
                    'sku': scraped.sku,
                    'name': scraped.name,
                    'description': scraped.description,
                    'specifications': scraped.specifications,
                    'features': scraped.features,
                    'images': scraped.images,
                    'variants': [vars(v) for v in scraped.variants],
                    'price': scraped.price,
                    'currency': scraped.currency,
                    'brand': scraped.brand,
                    'materials': scraped.materials,
                    'dimensions': scraped.dimensions,
                    'meta_title': scraped.meta_title,
                    'meta_description': scraped.meta_description,
                    'status': 'success'
                })
            else:
                st.session_state.products[i]['status'] = 'error'
                st.session_state.products[i]['error'] = 'Nu s-au putut extrage datele'
                
        except Exception as e:
            st.session_state.products[i]['status'] = 'error'
            st.session_state.products[i]['error'] = str(e)
            logger.error(f"Error processing {product['url']}: {e}")
        
        time.sleep(1)  # Rate limiting
    
    progress_bar.progress(1.0)
    status_text.text("✅ Procesare completă!")
    st.rerun()

def import_products(translate: bool, import_images: bool, create_variants: bool, 
                   category: str, markup: float, source_lang: str, target_lang: str):
    """Import products to Gomag"""
    if not st.session_state.gomag_api:
        st.error("Nu ești autentificat în Gomag!")
        return
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    api = st.session_state.gomag_api
    translator = ProductTranslator(source_lang, target_lang) if translate else None
    image_handler = ImageHandler() if import_images else None
    
    successful = 0
    failed = 0
    
    for i, product in enumerate(st.session_state.products):
        progress = (i + 1) / len(st.session_state.products)
        progress_bar.progress(progress)
        status_text.text(f"Import: {product.get('name', product['url'][:40])}...")
        
        try:
            # First extract if not already done
            if product.get('status') != 'success':
                scraped = ScraperFactory.scrape_url(product['url'])
                if scraped:
                    if translator:
                        translator.translate_product(scraped)
                    product.update(vars(scraped))
            
            # Apply markup
            if product.get('price'):
                product['price'] = product['price'] * (1 + markup / 100)
            
            # Process images if needed
            if import_images and product.get('images'):
                processed_images = []
                for img_url in product['images'][:5]:  # Limit to 5 images
                    try:
                        local_path = image_handler.download_image(img_url)
                        if local_path:
                            uploaded_url = api.upload_image(local_path)
                            if uploaded_url:
                                processed_images.append(uploaded_url)
                    except Exception as e:
                        logger.error(f"Image processing error: {e}")
                product['images'] = processed_images
            
            # Set category
            product['category'] = category
            
            # Create product in Gomag
            from scrapers.base_scraper import Product
            product_obj = Product()
            for key, value in product.items():
                if hasattr(product_obj, key):
                    setattr(product_obj, key, value)
            
            gomag_id = api.create_product(product_obj)
            
            if gomag_id:
                product['gomag_id'] = gomag_id
                product['status'] = 'imported'
                st.session_state.processed_products.append(product.copy())
                successful += 1
            else:
                product['status'] = 'error'
                product['error'] = 'Import failed'
                failed += 1
                
        except Exception as e:
            product['status'] = 'error'
            product['error'] = str(e)
            failed += 1
            logger.error(f"Import error for {product.get('url')}: {e}")
        
        time.sleep(0.5)
    
    # Cleanup
    if image_handler:
        image_handler.cleanup()
    
    progress_bar.progress(1.0)
    status_text.text(f"✅ Import finalizat! {successful} reușite, {failed} eșuate")
    
    if successful > 0:
        st.success(f"✅ {successful} produse importate cu succes!")
    if failed > 0:
        st.warning(f"⚠️ {failed} produse nu au putut fi importate")
    
    st.rerun()

if __name__ == "__main__":
    main()
