import streamlit as st
import pandas as pd
import time
import json
import os
import csv
from datetime import datetime
from typing import List, Dict
import logging
from io import BytesIO, StringIO

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
    .stats-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem;
        border-radius: 10px;
        color: white;
        margin-bottom: 1rem;
    }
    .info-box {
        background: #f0f2f6;
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #1E88E5;
        margin: 1rem 0;
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
if 'local_mode' not in st.session_state:
    st.session_state.local_mode = False

def export_for_gomag_csv(products: List[Dict]) -> str:
    """Export products in Gomag CSV format"""
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        'SKU', 'Nume', 'Descriere', 'Descriere Scurta', 'Pret', 'Pret Vechi', 
        'Stoc', 'Brand', 'Categorie', 'Material', 'Dimensiuni', 'Greutate',
        'Meta Title', 'Meta Description', 'Imagini', 'Culori Disponibile'
    ])
    
    writer.writeheader()
    for p in products:
        # Prepare images list
        images = '|'.join(p.get('images', [])[:5]) if p.get('images') else ''
        
        # Prepare colors/variants
        colors = ''
        if p.get('variants'):
            color_list = [v.get('color', '') for v in p['variants'] if v.get('color')]
            colors = ', '.join(color_list)
        
        # Clean description for CSV
        description = p.get('description', '').replace('\n', ' ').replace('\r', '')
        short_desc = description[:200] + '...' if len(description) > 200 else description
        
        writer.writerow({
            'SKU': p.get('sku', ''),
            'Nume': p.get('name', ''),
            'Descriere': description,
            'Descriere Scurta': short_desc,
            'Pret': p.get('price', 0),
            'Pret Vechi': p.get('old_price', ''),
            'Stoc': 100,  # Default stock
            'Brand': p.get('brand', ''),
            'Categorie': p.get('category', 'Rucsacuri Anti-Furt'),
            'Material': p.get('materials', ''),
            'Dimensiuni': p.get('dimensions', ''),
            'Greutate': p.get('weight', ''),
            'Meta Title': p.get('meta_title', p.get('name', ''))[:70],
            'Meta Description': p.get('meta_description', short_desc)[:160],
            'Imagini': images,
            'Culori Disponibile': colors
        })
    
    return output.getvalue()

def export_for_gomag_xml(products: List[Dict]) -> str:
    """Export products in Gomag XML format"""
    xml_content = ['<?xml version="1.0" encoding="UTF-8"?>']
    xml_content.append('<products>')
    
    for p in products:
        xml_content.append('  <product>')
        xml_content.append(f'    <sku><![CDATA[{p.get("sku", "")}]]></sku>')
        xml_content.append(f'    <name><![CDATA[{p.get("name", "")}]]></name>')
        xml_content.append(f'    <description><![CDATA[{p.get("description", "")}]]></description>')
        xml_content.append(f'    <price>{p.get("price", 0)}</price>')
        xml_content.append(f'    <brand><![CDATA[{p.get("brand", "")}]]></brand>')
        xml_content.append(f'    <category><![CDATA[{p.get("category", "Rucsacuri Anti-Furt")}]]></category>')
        
        # Add images
        if p.get('images'):
            xml_content.append('    <images>')
            for img in p['images'][:5]:
                xml_content.append(f'      <image><![CDATA[{img}]]></image>')
            xml_content.append('    </images>')
        
        # Add variants
        if p.get('variants'):
            xml_content.append('    <variants>')
            for v in p['variants']:
                xml_content.append('      <variant>')
                xml_content.append(f'        <color><![CDATA[{v.get("color", "")}]]></color>')
                xml_content.append(f'        <sku><![CDATA[{v.get("sku", "")}]]></sku>')
                xml_content.append(f'        <stock>{v.get("stock", 100)}</stock>')
                xml_content.append('      </variant>')
            xml_content.append('    </variants>')
        
        xml_content.append('  </product>')
    
    xml_content.append('</products>')
    return '\n'.join(xml_content)

def main():
    st.markdown('<h1 class="main-header">🎒 Product Importer pentru Gomag</h1>', unsafe_allow_html=True)
    
    # Sidebar - Authentication and Settings
    with st.sidebar:
        st.header("⚙️ Configurare")
        
        # Connection Test
        st.subheader("🔐 Autentificare Gomag")
        
        # Test connection first
        if st.button("🔍 Test Conexiune Gomag"):
            with st.spinner("Testare conexiune..."):
                api = GomagAPI()
                if api.test_connection():
                    st.success("✅ Conexiune reușită!")
                else:
                    st.error("❌ Nu se poate conecta la Gomag")
                    st.info("💡 Produsele vor fi salvate local în format JSON")
        
        # Authentication inputs
        gomag_username = st.text_input("Username Gomag", type="default", help="Username-ul tău de administrator Gomag")
        gomag_password = st.text_input("Password Gomag", type="password", help="Parola ta de administrator Gomag")
        
        # Local mode option
        use_local_mode = st.checkbox(
            "📁 Mod Local (salvează produse ca JSON/CSV)", 
            value=False,
            help="Salvează produsele local pentru import manual în Gomag"
        )
        
        # Login button
        if st.button("🔓 Conectare la Gomag", type="primary"):
            with st.spinner("Se conectează..."):
                api = GomagAPI()
                if use_local_mode:
                    st.session_state.gomag_api = api
                    st.session_state.authenticated = True
                    st.session_state.local_mode = True
                    st.success("✅ Mod local activat! Produsele vor fi salvate local.")
                    st.info("📁 Fișierele vor fi salvate în folderul 'gomag_products'")
                elif api.login(gomag_username, gomag_password):
                    st.session_state.gomag_api = api
                    st.session_state.authenticated = True
                    st.session_state.local_mode = False
                    st.success("✅ Conectat cu succes la Gomag!")
                else:
                    st.error("❌ Autentificare eșuată!")
                    st.info("💡 Poți folosi 'Mod Local' pentru a salva produsele")
        
        # Show authentication status
        if st.session_state.authenticated:
            if st.session_state.local_mode:
                st.success("✅ Mod Local Activ")
            else:
                st.success("✅ Conectat la Gomag")
        
        st.divider()
        
        # Translation Settings
        st.subheader("🌍 Setări Traducere")
        source_lang = st.selectbox(
            "Limba sursă", 
            ["en", "de", "fr", "it", "es"], 
            index=0,
            help="Limba în care sunt produsele originale"
        )
        target_lang = st.selectbox(
            "Limba țintă", 
            ["ro"], 
            index=0,
            help="Limba în care vor fi traduse produsele"
        )
        
        st.divider()
        
        # Statistics
        st.subheader("📊 Statistici")
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("📦 Produse încărcate", len(st.session_state.products))
        with col2:
            st.metric("✅ Produse procesate", len(st.session_state.processed_products))
        
        # Quick actions
        st.divider()
        st.subheader("⚡ Acțiuni Rapide")
        
        if st.button("🗑️ Resetare Totală", help="Șterge toate produsele și resetează aplicația"):
            st.session_state.products = []
            st.session_state.processed_products = []
            st.rerun()
        
        if st.button("📥 Descarcă Template Excel"):
            template_data = {
                'url': [
                    'https://example.com/product1',
                    'https://example.com/product2'
                ],
                'category': ['Rucsacuri', 'Rucsacuri'],
                'markup': [30, 30]
            }
            df = pd.DataFrame(template_data)
            buffer = BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df.to_excel(writer, index=False)
            
            st.download_button(
                "📥 Descarcă",
                data=buffer.getvalue(),
                file_name="template_import.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
    
    # Main content - Tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📤 Încărcare Link-uri",
        "👁️ Previzualizare Produse",
        "🔄 Procesare & Import",
        "📋 Istoric & Export",
        "📚 Ajutor"
    ])
    
    # Tab 1: Upload Links
    with tab1:
        st.header("📤 Încărcă Link-urile Produselor")
        
        # Info box
        st.markdown("""
        <div class="info-box">
        💡 <b>Sfat:</b> Poți încărca link-uri din Excel/CSV sau le poți introduce manual. 
        Aplicația va extrage automat toate informațiile despre produse.
        </div>
        """, unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📁 Încărcare din Excel/CSV")
            uploaded_file = st.file_uploader(
                "Alege fișierul cu link-uri",
                type=['xlsx', 'xls', 'csv'],
                help="Fișierul trebuie să conțină o coloană numită 'url' sau 'link'"
            )
            
            if uploaded_file:
                try:
                    # Read file
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
                    
                    if url_column is None and len(df.columns) > 0:
                        url_column = df.columns[0]  # Use first column as fallback
                    
                    if url_column:
                        urls = df[url_column].dropna().tolist()
                        
                        st.success(f"✅ Găsite {len(urls)} link-uri în fișier")
                        
                        # Show preview
                        with st.expander("📋 Vezi link-urile găsite"):
                            for i, url in enumerate(urls[:10], 1):
                                st.text(f"{i}. {url}")
                            if len(urls) > 10:
                                st.text(f"... și încă {len(urls) - 10} link-uri")
                        
                        # Add buttons
                        col_btn1, col_btn2 = st.columns(2)
                        with col_btn1:
                            if st.button("➕ Adaugă toate link-urile", key="add_excel", type="primary"):
                                added = 0
                                for url in urls:
                                    if url and url not in [p['url'] for p in st.session_state.products]:
                                        st.session_state.products.append({
                                            'url': url, 
                                            'status': 'pending',
                                            'added_at': datetime.now().isoformat()
                                        })
                                        added += 1
                                st.success(f"✅ Adăugate {added} produse noi")
                                time.sleep(1)
                                st.rerun()
                        
                        with col_btn2:
                            if st.button("🔄 Înlocuiește lista", key="replace_excel"):
                                st.session_state.products = []
                                for url in urls:
                                    if url:
                                        st.session_state.products.append({
                                            'url': url,
                                            'status': 'pending',
                                            'added_at': datetime.now().isoformat()
                                        })
                                st.success(f"✅ Listă înlocuită cu {len(urls)} produse")
                                time.sleep(1)
                                st.rerun()
                    else:
                        st.error("❌ Nu am găsit coloană cu URL-uri în fișier")
                        
                except Exception as e:
                    st.error(f"❌ Eroare la citirea fișierului: {e}")
                    st.info("💡 Asigură-te că fișierul conține o coloană 'url' sau 'link'")
        
        with col2:
            st.subheader("✍️ Introducere manuală")
            manual_urls = st.text_area(
                "Introdu link-urile (câte unul pe linie)",
                height=250,
                placeholder="https://www.xdconnects.com/...\nhttps://www.pfconcept.com/...\nhttps://www.midocean.com/..."
            )
            
            if manual_urls:
                urls = [url.strip() for url in manual_urls.split('\n') if url.strip()]
                st.info(f"📝 {len(urls)} link-uri introduse")
                
                if st.button("➕ Adaugă link-urile", key="add_manual", type="primary"):
                    added = 0
                    for url in urls:
                        if url not in [p['url'] for p in st.session_state.products]:
                            st.session_state.products.append({
                                'url': url,
                                'status': 'pending',
                                'added_at': datetime.now().isoformat()
                            })
                            added += 1
                    st.success(f"✅ Adăugate {added} produse noi")
                    time.sleep(1)
                    st.rerun()
        
        # Quick add predefined URLs
        st.divider()
        st.subheader("⚡ Adăugare rapidă - Link-uri exemplu")
        
        # Predefined URLs grouped by category
        example_categories = {
            "🎒 Rucsacuri XD Design": [
                "https://www.xdconnects.com/en-gb/bags-travel/anti-theft-backpacks/bobby-hero-regular-anti-theft-backpack-p705.29?variantId=P705.291",
                "https://www.xdconnects.com/en-gb/bags-travel/anti-theft-backpacks/bobby-hero-small-anti-theft-backpack-p705.70?variantId=P705.709",
                "https://www.xdconnects.com/en-gb/bags-travel/anti-theft-backpacks/bobby-soft-anti-theft-backpack-p705.79?variantId=P705.791"
            ],
            "💼 Rucsacuri Business": [
                "https://www.pfconcept.com/en_cz/cover-grs-rpet-anti-theft-backpack-18l-120510.html",
                "https://www.pfconcept.com/en_cz/joey-15-6-grs-recycled-canvas-anti-theft-laptop-backpack-18l-120677.html",
                "https://www.midocean.com/central-europe/us/eur/bags-travel/backpacks/laptop-backpacks/mo2739-03-zid10244354"
            ],
            "🔒 Accesorii Securitate": [
                "https://promobox.com/en/products/MAGNUM?color=10",
                "https://andapresent.com/ro/ro/products/AP721326-10",
                "https://psiproductfinder.de/product/p-b46edd56-smart-pad-fingerabdruck-schloss/v-5c1ce73f"
            ]
        }
        
        for category, urls in example_categories.items():
            col1, col2 = st.columns([3, 1])
            with col1:
                st.write(f"**{category}** ({len(urls)} produse)")
            with col2:
                if st.button(f"➕ Adaugă", key=f"add_{category}"):
                    added = 0
                    for url in urls:
                        if url not in [p['url'] for p in st.session_state.products]:
                            st.session_state.products.append({
                                'url': url,
                                'status': 'pending',
                                'added_at': datetime.now().isoformat()
                            })
                            added += 1
                    st.success(f"✅ Adăugate {added} produse din {category}")
                    time.sleep(1)
                    st.rerun()
    
    # Tab 2: Preview Products
    with tab2:
        st.header("👁️ Previzualizare Produse")
        
        if not st.session_state.products:
            st.info("📭 Nu există produse încărcate. Adaugă link-uri în tab-ul anterior.")
            
            # Show help
            st.markdown("""
            ### 🚀 Cum să începi:
            1. Du-te la tab-ul **📤 Încărcare Link-uri**
            2. Încarcă un Excel cu link-uri sau introdu-le manual
            3. Revino aici pentru a vedea produsele
            """)
        else:
            # Action buttons
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                if st.button("🔍 Extrage informații", type="primary", disabled=len(st.session_state.products) == 0):
                    extract_products(source_lang, target_lang)
            with col2:
                if st.button("🗑️ Șterge toate", disabled=len(st.session_state.products) == 0):
                    if st.session_state.products:
                        st.session_state.products = []
                        st.session_state.processed_products = []
                        st.success("✅ Toate produsele au fost șterse")
                        time.sleep(1)
                        st.rerun()
            with col3:
                if st.button("🔄 Reîncarcă pagina"):
                    st.rerun()
            with col4:
                # Filter options
                filter_status = st.selectbox(
                    "Filtrează",
                    ["Toate", "În așteptare", "Procesate", "Erori"],
                    key="filter_status"
                )
            
            st.divider()
            
            # Statistics bar
            col1, col2, col3, col4 = st.columns(4)
            
            total = len(st.session_state.products)
            pending = len([p for p in st.session_state.products if p.get('status') == 'pending'])
            success = len([p for p in st.session_state.products if p.get('status') == 'success'])
            errors = len([p for p in st.session_state.products if p.get('status') == 'error'])
            
            with col1:
                st.metric("📦 Total", total)
            with col2:
                st.metric("⏳ În așteptare", pending)
            with col3:
                st.metric("✅ Procesate", success)
            with col4:
                st.metric("❌ Erori", errors)
            
            st.divider()
            
            # Display products
            products_to_show = st.session_state.products
            
            # Apply filter
            if filter_status == "În așteptare":
                products_to_show = [p for p in products_to_show if p.get('status') == 'pending']
            elif filter_status == "Procesate":
                products_to_show = [p for p in products_to_show if p.get('status') == 'success']
            elif filter_status == "Erori":
                products_to_show = [p for p in products_to_show if p.get('status') == 'error']
            
            if not products_to_show:
                st.info(f"Nu există produse cu statusul: {filter_status}")
            else:
                for i, product in enumerate(products_to_show):
                    # Create unique key for product
                    product_key = f"{i}_{product.get('url', '')[:30]}"
                    
                    # Status icon and color
                    status = product.get('status', 'pending')
                    if status == 'success':
                        status_icon = "✅"
                        status_text = "Procesat"
                        status_color = "status-success"
                    elif status == 'error':
                        status_icon = "❌"
                        status_text = "Eroare"
                        status_color = "status-error"
                    else:
                        status_icon = "⏳"
                        status_text = "În așteptare"
                        status_color = "status-pending"
                    
                    # Product name for expander
                    product_name = product.get('name', '')
                    if not product_name:
                        product_name = product['url'][:60] + "..."
                    
                    with st.expander(f"{status_icon} {product_name}", expanded=False):
                        col1, col2 = st.columns([1, 3])
                        
                        with col1:
                            # Show first image if available
                            images = product.get('images', [])
                            if images and len(images) > 0:
                                try:
                                    st.image(images[0], width=200, caption="Imagine principală")
                                except:
                                    st.image("https://via.placeholder.com/200x200?text=No+Image", width=200)
                            else:
                                st.image("https://via.placeholder.com/200x200?text=No+Image", width=200)
                            
                            # Show more images if available
                            if len(images) > 1:
                                st.caption(f"📷 {len(images)} imagini disponibile")
                        
                        with col2:
                            # Status
                            st.markdown(f'<span class="{status_color}">{status_icon} {status_text}</span>', unsafe_allow_html=True)
                            
                            # Product details
                            st.write(f"**🔗 URL:** {product['url']}")
                            
                            if product.get('sku'):
                                st.write(f"**📦 SKU:** {product.get('sku')}")
                            
                            if product.get('brand'):
                                st.write(f"**🏷️ Brand:** {product.get('brand')}")
                            
                            if product.get('price'):
                                price = product.get('price', 0)
                                currency = product.get('currency', 'EUR')
                                st.write(f"**💰 Preț:** {price:.2f} {currency}")
                            
                            if product.get('description'):
                                with st.expander("📝 Descriere"):
                                    desc = product.get('description', '')
                                    st.write(desc[:500] + "..." if len(desc) > 500 else desc)
                            
                            if product.get('specifications'):
                                with st.expander(f"📋 Specificații ({len(product['specifications'])} items)"):
                                    for key, value in list(product['specifications'].items())[:10]:
                                        st.write(f"• **{key}:** {value}")
                            
                            if product.get('features'):
                                with st.expander(f"⭐ Caracteristici ({len(product['features'])} items)"):
                                    for feature in product['features'][:10]:
                                        st.write(f"• {feature}")
                            
                            if product.get('variants'):
                                st.write(f"**🎨 Variante:** {len(product['variants'])} culori/mărimi disponibile")
                                with st.expander("Vezi variante"):
                                    for variant in product['variants'][:5]:
                                        st.write(f"• {variant.get('color', 'N/A')} - {variant.get('sku', 'N/A')}")
                            
                            # Error message if any
                            if product.get('error'):
                                st.error(f"❌ Eroare: {product['error']}")
                            
                            # Action buttons
                            col_btn1, col_btn2 = st.columns(2)
                            with col_btn1:
                                if st.button(f"🗑️ Șterge", key=f"delete_{product_key}"):
                                    st.session_state.products.pop(i)
                                    st.rerun()
                            with col_btn2:
                                if st.button(f"🔄 Re-procesează", key=f"retry_{product_key}"):
                                    st.session_state.products[i]['status'] = 'pending'
                                    st.rerun()
    
    # Tab 3: Process & Import
    with tab3:
        st.header("🔄 Procesare & Import în Gomag")
        
        if not st.session_state.authenticated:
            st.warning("⚠️ Te rog să te autentifici în Gomag din bara laterală.")
            st.info("💡 Poți folosi 'Mod Local' pentru a salva produsele fără autentificare")
        else:
            if st.session_state.local_mode:
                st.info("📁 **Mod Local Activ** - Produsele vor fi salvate local pentru import manual")
            else:
                st.success("✅ **Conectat la Gomag** - Pregătit pentru import automat")
        
        # Import options
        st.subheader("⚙️ Opțiuni Import")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("### 📝 Setări Generale")
            import_images = st.checkbox("📷 Importă și imaginile", value=True)
            translate_products = st.checkbox("🌍 Traduce în română", value=True)
            create_variants = st.checkbox("🎨 Creează variante culori/mărimi", value=True)
            set_active = st.checkbox("✅ Setează produsele ca active", value=True)
            optimize_images = st.checkbox("🖼️ Optimizează imaginile", value=True)
        
        with col2:
            st.markdown("### 💰 Setări Preț & Categorie")
            default_category = st.text_input("📁 Categoria implicită", "Rucsacuri Anti-Furt")
            default_markup = st.number_input(
                "💰 Adaos comercial (%)", 
                min_value=0, 
                max_value=200, 
                value=30,
                help="Procentul care va fi adăugat la prețul original"
            )
            
            # Currency conversion
            convert_currency = st.checkbox("💱 Convertește din EUR în RON", value=True)
            if convert_currency:
                eur_to_ron = st.number_input(
                    "Rata de schimb EUR → RON",
                    min_value=4.0,
                    max_value=6.0,
                    value=4.95,
                    step=0.01
                )
        
        st.divider()
        
        # Progress section
        st.subheader("📊 Status Import")
        
        col1, col2, col3 = st.columns(3)
        
        pending = len([p for p in st.session_state.products if p.get('status') == 'pending'])
        ready = len([p for p in st.session_state.products if p.get('status') == 'success'])
        
        with col1:
            st.metric("⏳ De procesat", pending)
        with col2:
            st.metric("✅ Pregătite pentru import", ready)
        with col3:
            st.metric("📦 Total produse", len(st.session_state.products))
        
        # Action buttons
        st.divider()
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button(
                "🔍 Extrage Informații Produse", 
                type="primary",
                disabled=pending == 0,
                use_container_width=True
            ):
                extract_products(source_lang, target_lang)
        
        with col2:
            if st.button(
                "🚀 Importă în Gomag", 
                type="primary",
                disabled=not st.session_state.authenticated or ready == 0,
                use_container_width=True
            ):
                import_products(
                    translate=translate_products,
                    import_images=import_images,
                    create_variants=create_variants,
                    category=default_category,
                    markup=default_markup,
                    source_lang=source_lang,
                    target_lang=target_lang,
                    currency_rate=eur_to_ron if convert_currency else 1.0
                )
        
        # Show processing tips
        st.divider()
        with st.expander("💡 Sfaturi pentru Import"):
            st.markdown("""
            ### ✅ Pași recomandați:
            1. **Extrage informațiile** - Apasă "Extrage Informații Produse"
            2. **Verifică produsele** - Revizuiește în tab-ul "Previzualizare"
            3. **Importă** - Apasă "Importă în Gomag"
            
            ### 📝 Note importante:
            - Procesarea poate dura 30-60 secunde per produs
            - Imaginile vor fi descărcate și optimizate automat
            - Traducerea se face automat folosind Google Translate
            - În mod local, produsele sunt salvate în folderul `gomag_products/`
            
            ### ⚠️ Limitări:
            - Maximum 5 imagini per produs
            - Descrierea va fi trunchiată la 5000 caractere
            - Google Translate are o limită de 5000 caractere per request
            """)
    
    # Tab 4: History & Export
    with tab4:
        st.header("📋 Istoric & Export")
        
        if not st.session_state.products and not st.session_state.processed_products:
            st.info("📭 Nu există produse procesate încă.")
            st.markdown("""
            ### 🚀 Pentru a începe:
            1. Adaugă link-uri în primul tab
            2. Extrage informațiile produselor
            3. Revino aici pentru export
            """)
        else:
            # Export options
            st.subheader("📥 Opțiuni Export")
            
            # Select products to export
            export_choice = st.radio(
                "Ce produse dorești să exporți?",
                ["Toate produsele", "Doar cele procesate cu succes", "Doar cele cu erori"]
            )
            
            # Get products based on choice
            if export_choice == "Toate produsele":
                products_to_export = st.session_state.products
            elif export_choice == "Doar cele procesate cu succes":
                products_to_export = [p for p in st.session_state.products if p.get('status') == 'success']
            else:
                products_to_export = [p for p in st.session_state.products if p.get('status') == 'error']
            
            if products_to_export:
                st.info(f"📦 {len(products_to_export)} produse selectate pentru export")
                
                # Export buttons
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    # Export to Excel
                    if st.button("📊 Generează Excel", use_container_width=True):
                        df_data = []
                        for p in products_to_export:
                            # Prepare variant info
                            variants_str = ""
                            if p.get('variants'):
                                variants_list = [v.get('color', '') for v in p['variants'] if v.get('color')]
                                variants_str = ', '.join(variants_list)
                            
                            df_data.append({
                                'SKU': p.get('sku', ''),
                                'Nume': p.get('name', ''),
                                'Brand': p.get('brand', ''),
                                'Preț': p.get('price', 0),
                                'Moneda': p.get('currency', 'EUR'),
                                'Categorie': p.get('category', ''),
                                'Material': p.get('materials', ''),
                                'Dimensiuni': p.get('dimensions', ''),
                                'Variante': variants_str,
                                'Status': p.get('status', ''),
                                'URL': p.get('url', ''),
                                'Imagini': '|'.join(p.get('images', [])[:5])
                            })
                        
                        df = pd.DataFrame(df_data)
                        output = BytesIO()
                        with pd.ExcelWriter(output, engine='openpyxl') as writer:
                            df.to_excel(writer, index=False, sheet_name='Produse')
                        
                        st.download_button(
                            "📥 Descarcă Excel",
                            data=output.getvalue(),
                            file_name=f"produse_gomag_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
                
                with col2:
                    # Export to CSV (Gomag format)
                    if st.button("📄 Generează CSV Gomag", use_container_width=True):
                        csv_content = export_for_gomag_csv(products_to_export)
                        
                        st.download_button(
                            "📥 Descarcă CSV",
                            data=csv_content.encode('utf-8-sig'),
                            file_name=f"import_gomag_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                            mime="text/csv"
                        )
                
                with col3:
                    # Export to XML
                    if st.button("📋 Generează XML", use_container_width=True):
                        xml_content = export_for_gomag_xml(products_to_export)
                        
                        st.download_button(
                            "📥 Descarcă XML",
                            data=xml_content.encode('utf-8'),
                            file_name=f"produse_gomag_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xml",
                            mime="application/xml"
                        )
                
                with col4:
                    # Export to JSON
                    if st.button("🔧 Generează JSON", use_container_width=True):
                        json_data = json.dumps(products_to_export, indent=2, ensure_ascii=False)
                        
                        st.download_button(
                            "📥 Descarcă JSON",
                            data=json_data,
                            file_name=f"produse_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                            mime="application/json"
                        )
                
                # Data preview
                st.divider()
                st.subheader("👁️ Previzualizare Date")
                
                if products_to_export:
                    # Create simplified dataframe for preview
                    preview_data = []
                    for p in products_to_export[:10]:  # Show only first 10
                        preview_data.append({
                            'SKU': p.get('sku', 'N/A'),
                            'Nume': p.get('name', 'N/A')[:50],
                            'Preț': f"{p.get('price', 0):.2f} {p.get('currency', 'EUR')}",
                            'Status': p.get('status', 'pending'),
                            'Brand': p.get('brand', 'N/A')
                        })
                    
                    df_preview = pd.DataFrame(preview_data)
                    st.dataframe(df_preview, use_container_width=True)
                    
                    if len(products_to_export) > 10:
                        st.info(f"... și încă {len(products_to_export) - 10} produse")
            else:
                st.warning("Nu există produse care să corespundă criteriilor selectate")
    
    # Tab 5: Help
    with tab5:
        st.header("📚 Ajutor & Documentație")
        
        # Quick Start Guide
        st.subheader("🚀 Ghid Rapid")
        st.markdown("""
        ### 1️⃣ **Pregătirea**
        - Creează un fișier Excel cu link-urile produselor
        - Coloana trebuie numită `url` sau `link`
        - Alternativ, poți introduce link-urile manual
        
        ### 2️⃣ **Încărcarea**
        - Du-te la tab-ul **📤 Încărcare Link-uri**
        - Încarcă fișierul Excel sau introdu link-urile manual
        - Verifică că toate link-urile au fost adăugate corect
        
        ### 3️⃣ **Procesarea**
        - În tab-ul **👁️ Previzualizare**, apasă **🔍 Extrage informații**
        - Așteaptă ca toate produsele să fie procesate
        - Verifică că informațiile au fost extrase corect
        
        ### 4️⃣ **Importul**
        - Autentifică-te în Gomag (sau folosește Mod Local)
        - Configurează opțiunile de import (adaos, categorie, etc.)
        - Apasă **🚀 Importă în Gomag**
        
        ### 5️⃣ **Exportul**
        - După procesare, du-te la **📋 Istoric & Export**
        - Alege formatul dorit (Excel, CSV, XML, JSON)
        - Descarcă fișierul pentru backup sau import manual
        """)
        
        st.divider()
        
        # Supported Sites
        st.subheader("🌐 Site-uri Suportate")
        
        sites = {
            "XD Connects": "xdconnects.com",
            "PF Concept": "pfconcept.com",
            "Midocean": "midocean.com",
            "Promobox": "promobox.com",
            "Anda Present": "andapresent.com",
            "Stamina": "stamina-shop.eu",
            "UT Team": "utteam.com",
            "Sipec": "sipec.com",
            "Stricker": "stricker-europe.com",
            "Clipper": "clipperinterall.com",
            "PSI Product Finder": "psiproductfinder.de"
        }
        
        col1, col2 = st.columns(2)
        for i, (name, domain) in enumerate(sites.items()):
            if i % 2 == 0:
                with col1:
                    st.write(f"✅ **{name}** - `{domain}`")
            else:
                with col2:
                    st.write(f"✅ **{name}** - `{domain}`")
        
        st.divider()
        
        # Troubleshooting
        st.subheader("🔧 Rezolvarea Problemelor")
        
        with st.expander("❌ Nu se pot extrage informațiile"):
            st.markdown("""
            **Cauze posibile:**
            - Link-ul este incorect sau incomplet
            - Site-ul a schimbat structura paginii
            - Probleme de conexiune la internet
            
            **Soluții:**
            1. Verifică că link-ul funcționează în browser
            2. Încearcă din nou după câteva minute
            3. Contactează suportul dacă problema persistă
            """)
        
        with st.expander("❌ Nu mă pot conecta la Gomag"):
            st.markdown("""
            **Cauze posibile:**
            - Credențiale incorecte
            - Probleme cu certificatul SSL
            - Gomag este temporar indisponibil
            
            **Soluții:**
            1. Verifică username-ul și parola
            2. Folosește **Mod Local** pentru a salva produsele
            3. Importă manual folosind fișierele CSV/XML generate
            """)
        
        with st.expander("❌ Imaginile nu se încarcă"):
            st.markdown("""
            **Cauze posibile:**
            - Imaginile sunt protejate pe site-ul sursă
            - Link-urile către imagini sunt invalide
            - Probleme de memorie sau spațiu
            
            **Soluții:**
            1. Dezactivează opțiunea "Importă imagini"
            2. Adaugă imaginile manual în Gomag
            3. Folosește link-urile către imagini în loc de descărcare
            """)
        
        st.divider()
        
        # Contact & Support
        st.subheader("📞 Contact & Suport")
        st.markdown("""
        ### 🆘 Ai nevoie de ajutor?
        
        - 📧 **Email:** support@example.com
        - 💬 **Chat:** Folosește widget-ul din colțul dreapta jos
        - 📚 **Documentație completă:** [Vezi pe GitHub](https://github.com)
        
        ### 🐛 Raportează o problemă
        
        Dacă întâmpini probleme, te rog să includezi:
        - Descrierea problemei
        - Link-ul produsului care cauzează problema
        - Screenshot-uri dacă este relevant
        """)
        
        # Version info
        st.divider()
        st.caption("ℹ️ **Versiune:** 1.0.0 | **Python:** 3.11+ | **Last Updated:** 2024")

def extract_products(source_lang: str, target_lang: str):
    """Extract product information from URLs"""
    if not st.session_state.products:
        st.warning("Nu există produse de procesat")
        return
    
    # Count products to process
    to_process = [p for p in st.session_state.products if p.get('status') != 'success']
    if not to_process:
        st.info("Toate produsele sunt deja procesate")
        return
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    translator = ProductTranslator(source_lang, target_lang)
    processed = 0
    errors = 0
    
    for i, product in enumerate(st.session_state.products):
        if product.get('status') == 'success':
            continue
        
        progress = (i + 1) / len(st.session_state.products)
        progress_bar.progress(progress)
        status_text.text(f"Procesez [{i+1}/{len(st.session_state.products)}]: {product['url'][:60]}...")
        
        try:
            # Get appropriate scraper and extract
            scraped = ScraperFactory.scrape_url(product['url'])
            
            if scraped:
                # Translate if needed
                if translator:
                    translator.translate_product(scraped)
                
                # Update product data
                st.session_state.products[i].update({
                    'sku': scraped.sku,
                    'name': scraped.name,
                    'description': scraped.description,
                    'specifications': scraped.specifications,
                    'features': scraped.features,
                    'images': scraped.images[:10],  # Limit to 10 images
                    'variants': [vars(v) for v in scraped.variants] if scraped.variants else [],
                    'price': scraped.price,
                    'currency': scraped.currency,
                    'brand': scraped.brand,
                    'materials': scraped.materials,
                    'dimensions': scraped.dimensions,
                    'weight': scraped.weight,
                    'meta_title': scraped.meta_title,
                    'meta_description': scraped.meta_description,
                    'status': 'success',
                    'processed_at': datetime.now().isoformat()
                })
                processed += 1
            else:
                st.session_state.products[i]['status'] = 'error'
                st.session_state.products[i]['error'] = 'Nu s-au putut extrage datele'
                errors += 1
                
        except Exception as e:
            st.session_state.products[i]['status'] = 'error'
            st.session_state.products[i]['error'] = str(e)
            errors += 1
            logger.error(f"Error processing {product['url']}: {e}")
        
        # Small delay to avoid rate limiting
        time.sleep(0.5)
    
    progress_bar.progress(1.0)
    status_text.empty()
    
    # Show results
    if processed > 0:
        st.success(f"✅ Procesare completă! {processed} produse extrase cu succes.")
    if errors > 0:
        st.warning(f"⚠️ {errors} produse nu au putut fi procesate.")
    
    time.sleep(2)
    st.rerun()

def import_products(translate: bool, import_images: bool, create_variants: bool, 
                   category: str, markup: float, source_lang: str, target_lang: str,
                   currency_rate: float = 1.0):
    """Import products to Gomag or save locally"""
    if not st.session_state.gomag_api:
        st.error("Nu ești autentificat!")
        return
    
    # Get products ready for import
    ready_products = [p for p in st.session_state.products if p.get('status') == 'success']
    if not ready_products:
        st.warning("Nu există produse procesate pentru import")
        return
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    api = st.session_state.gomag_api
    image_handler = ImageHandler() if import_images else None
    
    successful = 0
    failed = 0
    
    # Create output directory for local mode
    if st.session_state.local_mode:
        os.makedirs("gomag_products", exist_ok=True)
    
    for i, product in enumerate(ready_products):
        progress = (i + 1) / len(ready_products)
        progress_bar.progress(progress)
        status_text.text(f"Import [{i+1}/{len(ready_products)}]: {product.get('name', 'Produs')}...")
        
        try:
            # Apply markup and currency conversion
            if product.get('price'):
                original_price = product['price']
                product['price'] = original_price * (1 + markup / 100) * currency_rate
                product['original_price'] = original_price
                if currency_rate > 1:
                    product['currency'] = 'RON'
            
            # Set category
            product['category'] = category
            
            # Process images if needed
            if import_images and image_handler and product.get('images'):
                try:
                    processed_images = image_handler.process_product_images(product['images'][:5])
                    product['local_images'] = processed_images
                except Exception as e:
                    logger.error(f"Image processing error: {e}")
            
            # Create product in Gomag or save locally
            if st.session_state.local_mode:
                # Save to JSON file
                filename = f"gomag_products/{product.get('sku', 'product')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(product, f, indent=2, ensure_ascii=False)
                
                product['import_status'] = 'saved_locally'
                product['local_file'] = filename
                successful += 1
            else:
                # Try to import to Gomag
                from scrapers.base_scraper import Product as ProductObj
                product_obj = ProductObj()
                for key, value in product.items():
                    if hasattr(product_obj, key):
                        setattr(product_obj, key, value)
                
                gomag_id = api.create_product(product_obj)
                
                if gomag_id:
                    product['gomag_id'] = gomag_id
                    product['import_status'] = 'imported'
                    successful += 1
                else:
                    product['import_status'] = 'failed'
                    failed += 1
            
            # Add to processed products
            if product not in st.session_state.processed_products:
                st.session_state.processed_products.append(product.copy())
                
        except Exception as e:
            product['import_status'] = 'error'
            product['import_error'] = str(e)
            failed += 1
            logger.error(f"Import error for {product.get('url')}: {e}")
        
        time.sleep(0.2)  # Small delay
    
    # Cleanup
    if image_handler:
        image_handler.cleanup()
    
    progress_bar.progress(1.0)
    status_text.empty()
    
    # Show results
    if successful > 0:
        if st.session_state.local_mode:
            st.success(f"✅ {successful} produse salvate local în folderul `gomag_products/`")
            st.info("💡 Poți importa fișierele JSON sau CSV în Gomag manual")
        else:
            st.success(f"✅ {successful} produse importate cu succes în Gomag!")
    
    if failed > 0:
        st.warning(f"⚠️ {failed} produse nu au putut fi importate")
    
    # Generate CSV for all products
    if successful > 0 and st.session_state.local_mode:
        csv_content = export_for_gomag_csv(ready_products)
        csv_filename = f"gomag_products/import_all_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        with open(csv_filename, 'w', encoding='utf-8-sig') as f:
            f.write(csv_content)
        st.info(f"📄 Fișier CSV generat: `{csv_filename}`")
    
    time.sleep(2)
    st.rerun()

if __name__ == "__main__":
    main()
