import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime
from io import BytesIO
import time
from typing import List, Dict
import logging

# Import module custom
from gomag.api import GomagAPI
from scrapers.universal import UniversalScraper
from utils.translator import Translator
from utils.data_processor import DataProcessor

# Configurare logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configurare pagină
st.set_page_config(
    page_title="🎒 Gomag Product Importer",
    page_icon="🎒",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS Custom
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        background: linear-gradient(90deg, #1E88E5 0%, #1976D2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        padding: 1rem 0;
    }
    .success-box {
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        color: #155724;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 1rem 0;
    }
    .category-tree {
        background: #f8f9fa;
        padding: 1rem;
        border-radius: 0.5rem;
        max-height: 400px;
        overflow-y: auto;
    }
    .category-item {
        padding: 0.5rem;
        margin: 0.2rem 0;
        cursor: pointer;
        border-radius: 0.3rem;
    }
    .category-item:hover {
        background: #e9ecef;
    }
    .category-selected {
        background: #1E88E5 !important;
        color: white;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'gomag_api' not in st.session_state:
    st.session_state.gomag_api = None
if 'categories' not in st.session_state:
    st.session_state.categories = []
if 'selected_category' not in st.session_state:
    st.session_state.selected_category = None
if 'products' not in st.session_state:
    st.session_state.products = []
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False

def render_category_tree(categories: List[Dict], parent_id: int = 0, level: int = 0) -> None:
    """Randează arborele de categorii"""
    for cat in categories:
        if cat.get('parent_id') == parent_id:
            indent = "　" * level  # Indentare vizuală
            
            # Buton pentru selectare categorie
            col1, col2 = st.columns([4, 1])
            with col1:
                if st.button(
                    f"{indent}📁 {cat['name']}", 
                    key=f"cat_{cat['id']}",
                    use_container_width=True
                ):
                    st.session_state.selected_category = cat
                    st.rerun()
            
            with col2:
                if cat.get('local'):
                    st.caption("🔸 Local")
            
            # Randează subcategoriile
            render_category_tree(categories, cat['id'], level + 1)

def main():
    st.markdown('<h1 class="main-header">🎒 Gomag Product Importer</h1>', unsafe_allow_html=True)
    
    # Sidebar - Configurare
    with st.sidebar:
        st.header("⚙️ Configurare")
        
        # Conexiune Gomag
        st.subheader("🔐 Conectare Gomag")
        
        domain = st.text_input(
            "Domeniu Gomag",
            value=os.getenv("GOMAG_DOMAIN", "rucsacantifurtro.gomag.ro"),
            help="Exemplu: magazin.gomag.ro"
        )
        
        if st.button("🔍 Test Conexiune"):
            api = GomagAPI(domain)
            if api.test_connection():
                st.success(f"✅ Conexiune reușită la {domain}")
                st.session_state.gomag_api = api
            else:
                st.error("❌ Nu se poate conecta")
        
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        
        if st.button("🔓 Autentificare", type="primary"):
            if not st.session_state.gomag_api:
                st.session_state.gomag_api = GomagAPI(domain)
            
            if st.session_state.gomag_api.login(username, password):
                st.session_state.authenticated = True
                st.success("✅ Autentificat cu succes!")
                
                # Încarcă categoriile
                with st.spinner("Se încarcă categoriile..."):
                    st.session_state.categories = st.session_state.gomag_api.get_categories()
                st.rerun()
            else:
                st.error("❌ Autentificare eșuată")
        
        if st.session_state.authenticated:
            st.success("✅ Conectat la Gomag")
        
        # Mod local
        st.divider()
        use_local = st.checkbox("💾 Mod Local (fără autentificare)")
        if use_local:
            st.session_state.authenticated = True
            if not st.session_state.gomag_api:
                st.session_state.gomag_api = GomagAPI("local.gomag.ro")
            if not st.session_state.categories:
                st.session_state.categories = st.session_state.gomag_api.get_categories()
        
        # Setări Import
        st.divider()
        st.subheader("📦 Setări Import")
        
        translate_enabled = st.checkbox("🌍 Traduce în Română", value=True)
        if translate_enabled:
            source_lang = st.selectbox("Limba sursă", ["en", "de", "fr", "it", "es"])
        
        price_markup = st.number_input(
            "💰 Adaos comercial (%)",
            min_value=0,
            max_value=200,
            value=30,
            step=5
        )
        
        currency_rate = st.number_input(
            "💱 Curs EUR → RON",
            min_value=4.0,
            max_value=6.0,
            value=4.95,
            step=0.01
        )
        
        stock_default = st.number_input(
            "📦 Stoc implicit",
            min_value=0,
            max_value=1000,
            value=100
        )
    
    # Main content
    tabs = st.tabs([
        "📁 Categorii",
        "📤 Încărcare Produse", 
        "🔍 Procesare",
        "📥 Import Gomag",
        "📊 Rapoarte"
    ])
    
    # Tab 1: Categorii
    with tabs[0]:
        st.header("📁 Gestionare Categorii")
        
        if not st.session_state.categories:
            st.warning("⚠️ Te rog să te autentifici pentru a vedea categoriile")
        else:
            col1, col2 = st.columns([2, 3])
            
            with col1:
                st.subheader("🌳 Categorii Existente")
                
                # Afișare arbore categorii
                with st.container():
                    st.markdown('<div class="category-tree">', unsafe_allow_html=True)
                    render_category_tree(st.session_state.categories)
                    st.markdown('</div>', unsafe_allow_html=True)
                
                # Adaugă categorie nouă
                st.divider()
                st.subheader("➕ Adaugă Categorie Nouă")
                
                new_cat_name = st.text_input("Nume categorie")
                
                parent_options = {"0": "Categorie principală"}
                for cat in st.session_state.categories:
                    parent_options[str(cat['id'])] = cat['name']
                
                parent_id = st.selectbox(
                    "Categorie părinte",
                    options=list(parent_options.keys()),
                    format_func=lambda x: parent_options[x]
                )
                
                if st.button("➕ Creează Categorie", type="primary"):
                    if new_cat_name and st.session_state.gomag_api:
                        new_cat = st.session_state.gomag_api.create_category(
                            new_cat_name,
                            int(parent_id)
                        )
                        if new_cat:
                            st.session_state.categories.append(new_cat)
                            st.success(f"✅ Categoria '{new_cat_name}' a fost creată!")
                            time.sleep(1)
                            st.rerun()
            
            with col2:
                if st.session_state.selected_category:
                    st.subheader(f"📋 Detalii: {st.session_state.selected_category['name']}")
                    
                    # Afișare detalii categorie
                    st.json({
                        "ID": st.session_state.selected_category.get('id'),
                        "Nume": st.session_state.selected_category.get('name'),
                        "Path": st.session_state.selected_category.get('path'),
                        "Parent ID": st.session_state.selected_category.get('parent_id'),
                        "Local": st.session_state.selected_category.get('local', False)
                    })
                    
                    # Statistici categorie
                    st.divider()
                    st.subheader("📊 Statistici")
                    
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        # Număr produse în categorie
                        products_in_cat = len([
                            p for p in st.session_state.products 
                            if p.get('category_id') == st.session_state.selected_category['id']
                        ])
                        st.metric("Produse", products_in_cat)
                    
                    with col2:
                        # Subcategorii
                        subcats = len([
                            c for c in st.session_state.categories
                            if c.get('parent_id') == st.session_state.selected_category['id']
                        ])
                        st.metric("Subcategorii", subcats)
                    
                    with col3:
                        # Status
                        status = "✅ Sincronizat" if not st.session_state.selected_category.get('local') else "🔸 Local"
                        st.metric("Status", status)
                else:
                    st.info("👈 Selectează o categorie pentru a vedea detaliile")
    
    # Tab 2: Încărcare Produse
    with tabs[1]:
        st.header("📤 Încărcare Produse")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📁 Din Excel/CSV")
            
            uploaded_file = st.file_uploader(
                "Încarcă fișier",
                type=['xlsx', 'xls', 'csv'],
                help="Fișierul trebuie să conțină coloana 'url' sau 'link'"
            )
            
            if uploaded_file:
                try:
                    if uploaded_file.name.endswith('.csv'):
                        df = pd.read_csv(uploaded_file)
                    else:
                        df = pd.read_excel(uploaded_file)
                    
                    st.success(f"✅ Fișier încărcat: {len(df)} rânduri")
                    
                    # Preview
                    with st.expander("👁️ Preview date"):
                        st.dataframe(df.head())
                    
                    # Selectare coloană URL
                    url_column = st.selectbox(
                        "Selectează coloana cu URL-uri",
                        options=df.columns.tolist()
                    )
                    
                    # Selectare categorie pentru import
                    if st.session_state.categories:
                        cat_names = {str(c['id']): c['name'] for c in st.session_state.categories}
                        selected_cat_id = st.selectbox(
                            "Categoria pentru aceste produse",
                            options=list(cat_names.keys()),
                            format_func=lambda x: cat_names[x]
                        )
                    else:
                        selected_cat_id = None
                    
                    if st.button("📥 Importă URL-uri", type="primary"):
                        urls = df[url_column].dropna().tolist()
                        for url in urls:
                            if url and not any(p['url'] == url for p in st.session_state.products):
                                st.session_state.products.append({
                                    'url': url,
                                    'status': 'pending',
                                    'category_id': selected_cat_id,
                                    'added_at': datetime.now().isoformat()
                                })
                        st.success(f"✅ Am adăugat {len(urls)} produse")
                        time.sleep(1)
                        st.rerun()
                        
                except Exception as e:
                    st.error(f"❌ Eroare: {e}")
        
        with col2:
            st.subheader("✍️ Adăugare Manuală")
            
            urls_text = st.text_area(
                "URL-uri (unul per linie)",
                height=200,
                placeholder="https://www.xdconnects.com/...\nhttps://www.pfconcept.com/..."
            )
            
            # Selectare categorie
            if st.session_state.categories:
                cat_names_manual = {str(c['id']): c['name'] for c in st.session_state.categories}
                manual_cat_id = st.selectbox(
                    "Categoria pentru produse",
                    options=list(cat_names_manual.keys()),
                    format_func=lambda x: cat_names_manual[x],
                    key="manual_cat"
                )
            else:
                manual_cat_id = None
            
            if st.button("➕ Adaugă", type="primary", key="add_manual"):
                if urls_text:
                    urls = [u.strip() for u in urls_text.split('\n') if u.strip()]
                    added = 0
                    for url in urls:
                        if not any(p['url'] == url for p in st.session_state.products):
                            st.session_state.products.append({
                                'url': url,
                                'status': 'pending',
                                'category_id': manual_cat_id,
                                'added_at': datetime.now().isoformat()
                            })
                            added += 1
                    st.success(f"✅ Am adăugat {added} produse")
                    time.sleep(1)
                    st.rerun()
        
        # Lista produse
        st.divider()
        if st.session_state.products:
            st.subheader(f"📦 Produse încărcate ({len(st.session_state.products)})")
            
            # Filtre
            col1, col2, col3 = st.columns(3)
            with col1:
                filter_status = st.selectbox(
                    "Filtrează după status",
                    ["Toate", "În așteptare", "Procesate", "Erori"]
                )
            with col2:
                filter_category = st.selectbox(
                    "Filtrează după categorie",
                    ["Toate"] + [c['name'] for c in st.session_state.categories]
                )
            with col3:
                if st.button("🗑️ Șterge toate"):
                    st.session_state.products = []
                    st.rerun()
            
            # Afișare produse
            for i, product in enumerate(st.session_state.products):
                # Aplică filtre
                if filter_status != "Toate":
                    status_map = {
                        "În așteptare": "pending",
                        "Procesate": "processed",
                        "Erori": "error"
                    }
                    if product.get('status') != status_map.get(filter_status):
                        continue
                
                with st.expander(f"{product.get('name', product['url'][:50])}..."):
                    col1, col2, col3 = st.columns([2, 1, 1])
                    
                    with col1:
                        st.write(f"**URL:** {product['url']}")
                        st.write(f"**Status:** {product.get('status', 'pending')}")
                        if product.get('category_id'):
                            cat = next((c for c in st.session_state.categories if str(c['id']) == str(product['category_id'])), None)
                            if cat:
                                st.write(f"**Categorie:** {cat['name']}")
                    
                    with col2:
                        if product.get('name'):
                            st.write(f"**Nume:** {product['name']}")
                        if product.get('sku'):
                            st.write(f"**SKU:** {product['sku']}")
                        if product.get('price'):
                            st.write(f"**Preț:** {product['price']} {product.get('currency', 'EUR')}")
                    
                    with col3:
                        if st.button(f"🗑️ Șterge", key=f"del_{i}"):
                            st.session_state.products.pop(i)
                            st.rerun()
    
    # Tab 3: Procesare
    with tabs[2]:
        st.header("🔍 Procesare Produse")
        
        pending = [p for p in st.session_state.products if p.get('status') == 'pending']
        
        if not pending:
            st.info("📭 Nu există produse de procesat")
        else:
            st.success(f"📦 {len(pending)} produse în așteptare")
            
            if st.button("🚀 Procesează Toate", type="primary"):
                progress = st.progress(0)
                status_text = st.empty()
                scraper = UniversalScraper()
                
                for i, product in enumerate(st.session_state.products):
                    if product['status'] == 'pending':
                        progress.progress((i+1) / len(st.session_state.products))
                        status_text.text(f"Procesez: {product['url'][:50]}...")
                        
                        # Extract info
                        extracted = scraper.extract(product['url'])
                        
                        # Update product
                        product.update(extracted)
                        product['status'] = 'processed'
                        
                        # Translate if needed
                        if translate_enabled:
                            translator = Translator(source_lang, 'ro')
                            product = translator.translate_product(product)
                        
                        # Apply markup
                        if product.get('price'):
                            product['price'] = product['price'] * (1 + price_markup/100)
                            product['price_ron'] = product['price'] * currency_rate
                        
                        time.sleep(0.5)
                
                progress.progress(1.0)
                status_text.text("✅ Procesare completă!")
                st.rerun()
    
    # Tab 4: Import Gomag
    with tabs[3]:
        st.header("📥 Import în Gomag")
        
        processed = [p for p in st.session_state.products if p.get('status') == 'processed']
        
        if not processed:
            st.warning("⚠️ Nu există produse procesate pentru import")
        else:
            st.success(f"✅ {len(processed)} produse gata pentru import")
            
            # Opțiuni import
            col1, col2 = st.columns(2)
            
            with col1:
                import_images = st.checkbox("📷 Importă imagini", value=True)
                create_variants = st.checkbox("🎨 Creează variante", value=True)
                set_active = st.checkbox("✅ Activează produsele", value=True)
            
            with col2:
                use_special_price = st.checkbox("💰 Folosește preț special")
                if use_special_price:
                    discount = st.slider("Discount (%)", 0, 50, 10)
            
            if st.button("🚀 Începe Importul", type="primary"):
                if not st.session_state.gomag_api:
                    st.error("❌ Nu ești conectat la Gomag")
                else:
                    progress = st.progress(0)
                    results = []
                    
                    for i, product in enumerate(processed):
                        progress.progress((i+1) / len(processed))
                        
                        # Pregătește date pentru import
                        import_data = {
                            'name': product.get('name'),
                            'sku': product.get('sku'),
                            'price': product.get('price_ron', product.get('price', 0)),
                            'description': product.get('description'),
                            'category_id': product.get('category_id'),
                            'brand': product.get('brand'),
                            'images': product.get('images', []),
                            'stock': stock_default,
                            'status': 1 if set_active else 0
                        }
                        
                        if use_special_price:
                            import_data['special_price'] = import_data['price'] * (1 - discount/100)
                        
                        # Import
                        result = st.session_state.gomag_api.import_product(import_data)
                        results.append(result)
                        
                        if result['success']:
                            product['import_status'] = 'success'
                            product['gomag_id'] = result.get('product_id')
                        else:
                            product['import_status'] = 'failed'
                            product['import_error'] = result.get('message')
                    
                    # Afișare rezultate
                    success_count = len([r for r in results if r['success']])
                    st.success(f"✅ {success_count}/{len(results)} produse importate cu succes")
                    
                    # Export rezultate
                    df_results = pd.DataFrame(results)
                    csv = df_results.to_csv(index=False)
                    st.download_button(
                        "📥 Descarcă Raport Import",
                        data=csv,
                        file_name=f"import_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv"
                    )
    
    # Tab 5: Rapoarte
    with tabs[4]:
        st.header("📊 Rapoarte și Export")
        
        if st.session_state.products:
            # Statistici
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Total Produse", len(st.session_state.products))
            with col2:
                processed = len([p for p in st.session_state.products if p.get('status') == 'processed'])
                st.metric("Procesate", processed)
            with col3:
                imported = len([p for p in st.session_state.products if p.get('import_status') == 'success'])
                st.metric("Importate", imported)
            with col4:
                errors = len([p for p in st.session_state.products if p.get('status') == 'error'])
                st.metric("Erori", errors)
            
            st.divider()
            
            # Export
            st.subheader("📥 Export Date")
            
            export_format = st.radio(
                "Format export",
                ["CSV", "Excel", "JSON", "Gomag CSV"]
            )
            
            if st.button("📥 Generează Export"):
                if export_format == "CSV":
                    df = pd.DataFrame(st.session_state.products)
                    csv = df.to_csv(index=False)
                    st.download_button(
                        "Descarcă CSV",
                        data=csv,
                        file_name=f"products_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv"
                    )
                
                elif export_format == "Excel":
                    output = BytesIO()
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        df = pd.DataFrame(st.session_state.products)
                        df.to_excel(writer, sheet_name='Products', index=False)
                    
                    st.download_button(
                        "Descarcă Excel",
                        data=output.getvalue(),
                        file_name=f"products_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                
                elif export_format == "JSON":
                    json_str = json.dumps(st.session_state.products, indent=2, ensure_ascii=False)
                    st.download_button(
                        "Descarcă JSON",
                        data=json_str,
                        file_name=f"products_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                        mime="application/json"
                    )
                
                elif export_format == "Gomag CSV":
                    # Format special pentru Gomag
                    gomag_data = []
                    for p in st.session_state.products:
                        if p.get('status') == 'processed':
                            gomag_data.append({
                                'Nume': p.get('name'),
                                'SKU': p.get('sku'),
                                'Preț': p.get('price_ron', p.get('price', 0)),
                                'Descriere': p.get('description'),
                                'Categorie': next((c['name'] for c in st.session_state.categories if str(c['id']) == str(p.get('category_id'))), ''),
                                'Brand': p.get('brand'),
                                'Stoc': stock_default,
                                'Imagini': '|'.join(p.get('images', [])[:5])
                            })
                    
                    df_gomag = pd.DataFrame(gomag_data)
                    csv_gomag = df_gomag.to_csv(index=False, sep=';')
                    st.download_button(
                        "Descarcă Gomag CSV",
                        data=csv_gomag,
                        file_name=f"gomag_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv"
                    )

if __name__ == "__main__":
    main()
