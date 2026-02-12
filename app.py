import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import json
import re
import time
import os
from datetime import datetime
from io import BytesIO
from typing import Dict, List, Optional
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Page config
st.set_page_config(
    page_title="🎒 Gomag Product Importer",
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
        background: linear-gradient(90deg, #1E88E5 0%, #1976D2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        padding: 1rem 0;
    }
    .category-box {
        background: #f8f9fa;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 0.5rem 0;
        border: 2px solid transparent;
        cursor: pointer;
    }
    .category-box:hover {
        border-color: #1E88E5;
        background: #e3f2fd;
    }
    .category-selected {
        background: #1E88E5 !important;
        color: white !important;
    }
    .success-msg {
        padding: 1rem;
        background: #d4edda;
        border: 1px solid #c3e6cb;
        color: #155724;
        border-radius: 0.5rem;
    }
    .product-card {
        border: 1px solid #dee2e6;
        border-radius: 0.5rem;
        padding: 1rem;
        margin: 0.5rem 0;
    }
</style>
""", unsafe_allow_html=True)

# ============= GOMAG API CLASS =============
class GomagAPI:
    """Gomag API Integration"""
    
    # Categorii predefinite pentru magazine românești
    DEFAULT_CATEGORIES = [
        {"id": 1, "name": "Rucsacuri", "parent_id": 0, "slug": "rucsacuri"},
        {"id": 2, "name": "Rucsacuri Anti-Furt", "parent_id": 1, "slug": "rucsacuri-anti-furt"},
        {"id": 3, "name": "Rucsacuri Laptop", "parent_id": 1, "slug": "rucsacuri-laptop"},
        {"id": 4, "name": "Rucsacuri Business", "parent_id": 1, "slug": "rucsacuri-business"},
        {"id": 5, "name": "Rucsacuri Călătorie", "parent_id": 1, "slug": "rucsacuri-calatorie"},
        {"id": 6, "name": "Genți", "parent_id": 0, "slug": "genti"},
        {"id": 7, "name": "Genți Laptop", "parent_id": 6, "slug": "genti-laptop"},
        {"id": 8, "name": "Genți de Umăr", "parent_id": 6, "slug": "genti-de-umar"},
        {"id": 9, "name": "Accesorii", "parent_id": 0, "slug": "accesorii"},
        {"id": 10, "name": "Accesorii Securitate", "parent_id": 9, "slug": "accesorii-securitate"},
        {"id": 11, "name": "Portofele RFID", "parent_id": 9, "slug": "portofele-rfid"},
        {"id": 12, "name": "Încuietori", "parent_id": 9, "slug": "incuietori"},
        {"id": 13, "name": "Produse Noi", "parent_id": 0, "slug": "produse-noi"},
        {"id": 14, "name": "Outlet", "parent_id": 0, "slug": "outlet"},
        {"id": 15, "name": "Branduri", "parent_id": 0, "slug": "branduri"},
        {"id": 16, "name": "XD Design", "parent_id": 15, "slug": "xd-design"},
        {"id": 17, "name": "Bobby", "parent_id": 16, "slug": "bobby"},
        {"id": 18, "name": "PF Concept", "parent_id": 15, "slug": "pf-concept"},
        {"id": 19, "name": "Midocean", "parent_id": 15, "slug": "midocean"},
    ]
    
    def __init__(self, domain: str = "rucsacantifurtro.gomag.ro"):
        self.domain = domain
        self.base_url = f"https://{domain}"
        self.session = requests.Session()
        self.authenticated = False
        self.categories = self.DEFAULT_CATEGORIES.copy()
    
    def test_connection(self) -> bool:
        """Test connection to Gomag"""
        try:
            response = self.session.get(self.base_url, timeout=5)
            return response.status_code == 200
        except:
            return False
    
    def login(self, username: str, password: str) -> bool:
        """Login to Gomag (simulated)"""
        # În producție, aici ar fi logica reală de autentificare
        if username and password:
            self.authenticated = True
            return True
        return False
    
    def get_categories(self) -> List[Dict]:
        """Get all categories"""
        return self.categories
    
    def create_category(self, name: str, parent_id: int = 0) -> Dict:
        """Create new category"""
        new_id = max([c['id'] for c in self.categories]) + 1
        slug = self._create_slug(name)
        
        new_category = {
            "id": new_id,
            "name": name,
            "parent_id": parent_id,
            "slug": slug,
            "custom": True
        }
        
        self.categories.append(new_category)
        return new_category
    
    def _create_slug(self, text: str) -> str:
        """Create URL slug from text"""
        # Replace Romanian characters
        replacements = {
            'ă': 'a', 'â': 'a', 'î': 'i', 'ș': 's', 'ț': 't',
            'Ă': 'a', 'Â': 'a', 'Î': 'i', 'Ș': 's', 'Ț': 't'
        }
        for rom, eng in replacements.items():
            text = text.replace(rom, eng)
        
        # Convert to lowercase and replace spaces
        slug = text.lower()
        slug = re.sub(r'[^a-z0-9]+', '-', slug)
        slug = slug.strip('-')
        
        return slug

# ============= PRODUCT SCRAPER CLASS =============
class ProductScraper:
    """Universal product scraper"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def extract(self, url: str) -> Dict:
        """Extract product information from URL"""
        try:
            response = self.session.get(url, timeout=10)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            product = {
                'url': url,
                'status': 'success',
                'extracted_at': datetime.now().isoformat()
            }
            
            # Extract name
            product['name'] = self._extract_name(soup, url)
            
            # Extract SKU
            product['sku'] = self._extract_sku(url)
            
            # Extract price
            product['price'] = self._extract_price(soup)
            
            # Extract description
            product['description'] = self._extract_description(soup)
            
            # Extract images
            product['images'] = self._extract_images(soup, url)
            
            # Extract brand
            product['brand'] = self._extract_brand(url)
            
            # Set currency
            product['currency'] = 'EUR'
            
            return product
            
        except Exception as e:
            logger.error(f"Error extracting {url}: {e}")
            return {
                'url': url,
                'status': 'error',
                'error': str(e),
                'name': f"Product from {url.split('/')[2]}",
                'sku': f"ERR{hash(url) % 100000}",
                'price': 0,
                'currency': 'EUR'
            }
    
    def _extract_name(self, soup, url):
        """Extract product name"""
        # Try h1
        h1 = soup.find('h1')
        if h1:
            return h1.get_text(strip=True)[:200]
        
        # Try meta og:title
        og_title = soup.find('meta', {'property': 'og:title'})
        if og_title:
            return og_title.get('content', '')[:200]
        
        # Try title
        title = soup.find('title')
        if title:
            return title.get_text(strip=True).split('|')[0].strip()[:200]
        
        return f"Product from {url.split('/')[2]}"
    
    def _extract_sku(self, url):
        """Extract SKU from URL"""
        patterns = [
            r'[pP](\d{3}\.\d{2,3})',
            r'/([A-Z0-9\-]{5,})',
            r'product[/_]([A-Z0-9]+)',
            r'sku=([^&]+)',
            r'/(\d{6})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url, re.I)
            if match:
                return match.group(1).upper()
        
        return f"WEB{hash(url) % 1000000}"
    
    def _extract_price(self, soup):
        """Extract price"""
        price_patterns = [
            r'€\s*(\d+[.,]\d{2})',
            r'(\d+[.,]\d{2})\s*€',
            r'EUR\s*(\d+[.,]\d{2})',
        ]
        
        text = soup.get_text()
        for pattern in price_patterns:
            matches = re.findall(pattern, text)
            if matches:
                try:
                    # Get the first valid price
                    for match in matches:
                        price = float(match.replace(',', '.'))
                        if 1 <= price <= 10000:  # Reasonable price range
                            return price
                except:
                    continue
        
        return 0
    
    def _extract_description(self, soup):
        """Extract description"""
        # Try meta description
        meta_desc = soup.find('meta', {'name': 'description'})
        if meta_desc:
            return meta_desc.get('content', '')[:1000]
        
        # Try og:description
        og_desc = soup.find('meta', {'property': 'og:description'})
        if og_desc:
            return og_desc.get('content', '')[:1000]
        
        # Try to find description div
        for class_name in ['description', 'product-description', 'product-details']:
            desc_elem = soup.find(class_=re.compile(class_name, re.I))
            if desc_elem:
                return desc_elem.get_text(strip=True)[:1000]
        
        return ""
    
    def _extract_images(self, soup, url):
        """Extract product images"""
        images = []
        
        # Try og:image
        og_image = soup.find('meta', {'property': 'og:image'})
        if og_image:
            img_url = og_image.get('content', '')
            if img_url:
                if not img_url.startswith('http'):
                    base_url = '/'.join(url.split('/')[:3])
                    img_url = base_url + img_url if img_url.startswith('/') else base_url + '/' + img_url
                images.append(img_url)
        
        # Find product images
        for img in soup.find_all('img')[:20]:
            src = img.get('src') or img.get('data-src') or img.get('data-lazy')
            if src and any(keyword in src.lower() for keyword in ['product', 'item', 'article']):
                if not src.startswith('http'):
                    if src.startswith('//'):
                        src = 'https:' + src
                    elif src.startswith('/'):
                        base_url = '/'.join(url.split('/')[:3])
                        src = base_url + src
                if src.startswith('http') and src not in images:
                    images.append(src)
        
        return images[:5]
    
    def _extract_brand(self, url):
        """Extract brand from URL"""
        domain = url.split('/')[2].lower()
        
        brand_map = {
            'xdconnects': 'XD Design',
            'xd-design': 'XD Design',
            'pfconcept': 'PF Concept',
            'midocean': 'Midocean',
            'promobox': 'Promobox',
            'andapresent': 'Anda Present',
            'stamina': 'Stamina',
            'utteam': 'UT Team',
            'sipec': 'Sipec',
            'stricker': 'Stricker'
        }
        
        for key, brand in brand_map.items():
            if key in domain:
                return brand
        
        # Default: capitalize domain
        return domain.split('.')[0].title()

# ============= TRANSLATOR CLASS =============
class ProductTranslator:
    """Simple product translator"""
    
    def translate(self, text: str, target_lang: str = 'ro') -> str:
        """Translate text (placeholder - în producție ar folosi un API real)"""
        # Pentru demo, returnăm textul original
        # În producție, aici ar fi integrare cu Google Translate API sau similar
        return text
    
    def translate_product(self, product: Dict) -> Dict:
        """Translate product fields"""
        # Pentru demo, adăugăm doar un prefix
        if product.get('name'):
            product['name_ro'] = product['name']  # În producție ar fi tradus
        
        if product.get('description'):
            product['description_ro'] = product['description']  # În producție ar fi tradus
        
        return product

# ============= SESSION STATE INITIALIZATION =============
if 'gomag_api' not in st.session_state:
    st.session_state.gomag_api = GomagAPI()

if 'categories' not in st.session_state:
    st.session_state.categories = st.session_state.gomag_api.get_categories()

if 'selected_category' not in st.session_state:
    st.session_state.selected_category = None

if 'products' not in st.session_state:
    st.session_state.products = []

if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False

if 'scraper' not in st.session_state:
    st.session_state.scraper = ProductScraper()

if 'translator' not in st.session_state:
    st.session_state.translator = ProductTranslator()

# ============= HELPER FUNCTIONS =============
def render_category_tree(categories: List[Dict], parent_id: int = 0, level: int = 0):
    """Render category tree"""
    for cat in categories:
        if cat.get('parent_id') == parent_id:
            # Indentation based on level
            indent = "　" * level
            
            # Category button
            if st.button(
                f"{indent}📁 {cat['name']}", 
                key=f"cat_{cat['id']}",
                use_container_width=True
            ):
                st.session_state.selected_category = cat
                st.rerun()
            
            # Render subcategories
            render_category_tree(categories, cat['id'], level + 1)

def export_to_csv(products: List[Dict]) -> str:
    """Export products to CSV"""
    df = pd.DataFrame(products)
    return df.to_csv(index=False, encoding='utf-8-sig')

def export_to_gomag_csv(products: List[Dict]) -> str:
    """Export to Gomag-specific CSV format"""
    gomag_data = []
    
    for p in products:
        # Get category name
        cat_name = ""
        if p.get('category_id'):
            cat = next((c for c in st.session_state.categories if c['id'] == p['category_id']), None)
            if cat:
                cat_name = cat['name']
        
        gomag_data.append({
            'Nume Produs': p.get('name', ''),
            'SKU': p.get('sku', ''),
            'Preț (RON)': p.get('price_ron', p.get('price', 0)),
            'Preț Vechi (RON)': p.get('old_price', ''),
            'Descriere': p.get('description', ''),
            'Descriere Scurtă': p.get('description', '')[:200],
            'Categorie': cat_name,
            'Brand': p.get('brand', ''),
            'Stoc': p.get('stock', 100),
            'Greutate (kg)': p.get('weight', 1),
            'Imagini': '|'.join(p.get('images', [])[:5]),
            'Meta Title': p.get('name', '')[:70],
            'Meta Description': p.get('description', '')[:160],
            'Status': 'Activ'
        })
    
    df = pd.DataFrame(gomag_data)
    return df.to_csv(index=False, encoding='utf-8-sig', sep=';')

# ============= MAIN APPLICATION =============
def main():
    st.markdown('<h1 class="main-header">🎒 Gomag Product Importer</h1>', unsafe_allow_html=True)
    
    # Sidebar
    with st.sidebar:
        st.header("⚙️ Configurare")
        
        # Connection settings
        st.subheader("🔐 Conectare Gomag")
        
        domain = st.text_input(
            "Domeniu Gomag",
            value="rucsacantifurtro.gomag.ro",
            help="Domeniul magazinului tău Gomag"
        )
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔍 Test Conexiune"):
                with st.spinner("Testare..."):
                    if st.session_state.gomag_api.test_connection():
                        st.success("✅ Conexiune OK")
                    else:
                        st.info("📡 Mod offline")
        
        with col2:
            use_local = st.checkbox("💾 Mod Local", value=True)
        
        if not use_local:
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            
            if st.button("🔓 Autentificare"):
                if st.session_state.gomag_api.login(username, password):
                    st.session_state.authenticated = True
                    st.success("✅ Autentificat!")
                    st.rerun()
                else:
                    st.error("❌ Date incorecte")
        else:
            st.session_state.authenticated = True
            st.info("💾 Mod local activ")
        
        # Import settings
        st.divider()
        st.subheader("📦 Setări Import")
        
        translate = st.checkbox("🌍 Traduce în Română", value=False)
        markup = st.number_input("💰 Adaos (%)", 0, 200, 30, 5)
        currency_rate = st.number_input("💱 EUR → RON", 4.0, 6.0, 4.95, 0.01)
        default_stock = st.number_input("📦 Stoc implicit", 0, 1000, 100)
        
        # Store settings
        st.session_state.import_settings = {
            'translate': translate,
            'markup': markup,
            'currency_rate': currency_rate,
            'default_stock': default_stock
        }
    
    # Main tabs
    tabs = st.tabs([
        "📁 Categorii",
        "📤 Încărcare Produse",
        "🔍 Procesare",
        "📥 Export"
    ])
    
    # Tab 1: Categories
    with tabs[0]:
        st.header("📁 Gestionare Categorii")
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.subheader("🌳 Categorii Existente")
            
            # Category tree
            with st.container():
                render_category_tree(st.session_state.categories)
            
            # Add new category
            st.divider()
            st.subheader("➕ Categorie Nouă")
            
            new_cat_name = st.text_input("Nume categorie nouă")
            
            parent_options = {0: "-- Categorie principală --"}
            for cat in st.session_state.categories:
                parent_options[cat['id']] = cat['name']
            
            parent_id = st.selectbox(
                "Categorie părinte",
                options=list(parent_options.keys()),
                format_func=lambda x: parent_options[x]
            )
            
            if st.button("➕ Creează", type="primary"):
                if new_cat_name:
                    new_cat = st.session_state.gomag_api.create_category(new_cat_name, parent_id)
                    st.session_state.categories = st.session_state.gomag_api.get_categories()
                    st.success(f"✅ Categoria '{new_cat_name}' creată!")
                    time.sleep(1)
                    st.rerun()
        
        with col2:
            if st.session_state.selected_category:
                st.subheader(f"📋 Detalii: {st.session_state.selected_category['name']}")
                
                # Category details
                st.json({
                    "ID": st.session_state.selected_category['id'],
                    "Nume": st.session_state.selected_category['name'],
                    "Slug": st.session_state.selected_category.get('slug', ''),
                    "Părinte ID": st.session_state.selected_category.get('parent_id', 0),
                    "Personalizată": st.session_state.selected_category.get('custom', False)
                })
                
                # Products in category
                products_in_cat = [
                    p for p in st.session_state.products 
                    if p.get('category_id') == st.session_state.selected_category['id']
                ]
                
                st.metric("Produse în categorie", len(products_in_cat))
            else:
                st.info("👈 Selectează o categorie pentru detalii")
    
    # Tab 2: Upload Products
    with tabs[1]:
        st.header("📤 Încărcare Link-uri Produse")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📁 Din Excel/CSV")
            
            uploaded_file = st.file_uploader(
                "Încarcă fișier",
                type=['xlsx', 'xls', 'csv']
            )
            
            if uploaded_file:
                try:
                    if uploaded_file.name.endswith('.csv'):
                        df = pd.read_csv(uploaded_file)
                    else:
                        df = pd.read_excel(uploaded_file)
                    
                    st.success(f"✅ {len(df)} rânduri găsite")
                    
                    # Column selection
                    url_col = st.selectbox("Coloană URL", df.columns.tolist())
                    
                    # Category selection
                    cat_options = {0: "-- Fără categorie --"}
                    for cat in st.session_state.categories:
                        cat_options[cat['id']] = cat['name']
                    
                    selected_cat = st.selectbox(
                        "Categorie pentru produse",
                        options=list(cat_options.keys()),
                        format_func=lambda x: cat_options[x]
                    )
                    
                    if st.button("📥 Importă", type="primary"):
                        urls = df[url_col].dropna().tolist()
                        for url in urls:
                            if url and not any(p['url'] == url for p in st.session_state.products):
                                st.session_state.products.append({
                                    'url': url,
                                    'status': 'pending',
                                    'category_id': selected_cat if selected_cat != 0 else None
                                })
                        st.success(f"✅ {len(urls)} produse adăugate")
                        st.rerun()
                        
                except Exception as e:
                    st.error(f"❌ Eroare: {e}")
        
        with col2:
            st.subheader("✍️ Adăugare Manuală")
            
            urls_text = st.text_area(
                "URL-uri (unul pe linie)",
                height=200
            )
            
            # Category selection for manual
            cat_options_manual = {0: "-- Fără categorie --"}
            for cat in st.session_state.categories:
                cat_options_manual[cat['id']] = cat['name']
            
            manual_cat = st.selectbox(
                "Categorie",
                options=list(cat_options_manual.keys()),
                format_func=lambda x: cat_options_manual[x],
                key="manual_cat"
            )
            
            if st.button("➕ Adaugă", type="primary"):
                if urls_text:
                    urls = [u.strip() for u in urls_text.split('\n') if u.strip()]
                    for url in urls:
                        if not any(p['url'] == url for p in st.session_state.products):
                            st.session_state.products.append({
                                'url': url,
                                'status': 'pending',
                                'category_id': manual_cat if manual_cat != 0 else None
                            })
                    st.success(f"✅ {len(urls)} produse adăugate")
                    st.rerun()
        
        # Products list
        if st.session_state.products:
            st.divider()
            st.subheader(f"📦 Produse ({len(st.session_state.products)})")
            
            for i, p in enumerate(st.session_state.products):
                with st.expander(f"{p.get('name', p['url'][:50])}..."):
                    col1, col2, col3 = st.columns([3, 1, 1])
                    
                    with col1:
                        st.write(f"**URL:** {p['url'][:80]}...")
                        st.write(f"**Status:** {p.get('status', 'pending')}")
                        if p.get('category_id'):
                            cat = next((c for c in st.session_state.categories if c['id'] == p['category_id']), None)
                            if cat:
                                st.write(f"**Categorie:** {cat['name']}")
                    
                    with col2:
                        if p.get('sku'):
                            st.write(f"**SKU:** {p['sku']}")
                        if p.get('price'):
                            st.write(f"**Preț:** €{p['price']:.2f}")
                    
                    with col3:
                        if st.button("🗑️", key=f"del_{i}"):
                            st.session_state.products.pop(i)
                            st.rerun()
    
    # Tab 3: Processing
    with tabs[2]:
        st.header("🔍 Procesare Produse")
        
        pending = [p for p in st.session_state.products if p.get('status') == 'pending']
        
        if not pending:
            st.info("📭 Nu există produse de procesat")
        else:
            st.success(f"📦 {len(pending)} produse în așteptare")
            
            if st.button("🚀 Procesează Toate", type="primary"):
                progress = st.progress(0)
                
                for i, product in enumerate(st.session_state.products):
                    if product['status'] == 'pending':
                        progress.progress((i+1) / len(st.session_state.products))
                        
                        # Extract product info
                        extracted = st.session_state.scraper.extract(product['url'])
                        product.update(extracted)
                        
                        # Apply settings
                        settings = st.session_state.get('import_settings', {})
                        
                        # Apply markup
                        if product.get('price') and settings.get('markup'):
                            product['price_original'] = product['price']
                            product['price'] = product['price'] * (1 + settings['markup']/100)
                        
                        # Convert to RON
                        if product.get('price') and settings.get('currency_rate'):
                            product['price_ron'] = product['price'] * settings['currency_rate']
                        
                        # Set stock
                        product['stock'] = settings.get('default_stock', 100)
                        
                        # Translate if needed
                        if settings.get('translate'):
                            product = st.session_state.translator.translate_product(product)
                        
                        product['status'] = 'processed'
                        
                        time.sleep(0.5)
                
                progress.progress(1.0)
                st.success("✅ Procesare completă!")
                st.rerun()
        
        # Show processed products
        processed = [p for p in st.session_state.products if p.get('status') == 'processed']
        
        if processed:
            st.divider()
            st.subheader(f"✅ Produse Procesate ({len(processed)})")
            
            for p in processed[:5]:  # Show first 5
                with st.container():
                    col1, col2, col3 = st.columns([1, 2, 1])
                    
                    with col1:
                        if p.get('images'):
                            st.image(p['images'][0], width=100)
                    
                    with col2:
                        st.write(f"**{p.get('name', 'Produs')}**")
                        st.write(f"SKU: {p.get('sku', 'N/A')}")
                        st.write(f"Brand: {p.get('brand', 'N/A')}")
                    
                    with col3:
                        if p.get('price_ron'):
                            st.write(f"**{p['price_ron']:.2f} RON**")
                        elif p.get('price'):
                            st.write(f"**€{p['price']:.2f}**")
    
    # Tab 4: Export
    with tabs[3]:
        st.header("📥 Export Produse")
        
        processed = [p for p in st.session_state.products if p.get('status') == 'processed']
        
        if not processed:
            st.warning("⚠️ Nu există produse procesate pentru export")
        else:
            st.success(f"✅ {len(processed)} produse disponibile pentru export")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                # Standard CSV
                if st.button("📄 Export CSV", use_container_width=True):
                    csv = export_to_csv(processed)
                    st.download_button(
                        "💾 Descarcă CSV",
                        data=csv,
                        file_name=f"products_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                        mime="text/csv"
                    )
            
            with col2:
                # Gomag CSV
                if st.button("🛒 Export Gomag", use_container_width=True):
                    gomag_csv = export_to_gomag_csv(processed)
                    st.download_button(
                        "💾 Descarcă Gomag CSV",
                        data=gomag_csv,
                        file_name=f"gomag_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                        mime="text/csv"
                    )
            
            with col3:
                # JSON
                if st.button("🔧 Export JSON", use_container_width=True):
                    json_str = json.dumps(processed, indent=2, ensure_ascii=False)
                    st.download_button(
                        "💾 Descarcă JSON",
                        data=json_str,
                        file_name=f"products_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
                        mime="application/json"
                    )
            
            # Preview
            st.divider()
            st.subheader("👁️ Preview Export")
            
            preview_data = []
            for p in processed[:10]:
                cat_name = ""
                if p.get('category_id'):
                    cat = next((c for c in st.session_state.categories if c['id'] == p['category_id']), None)
                    if cat:
                        cat_name = cat['name']
                
                preview_data.append({
                    'SKU': p.get('sku', ''),
                    'Nume': p.get('name', '')[:40],
                    'Categorie': cat_name,
                    'Brand': p.get('brand', ''),
                    'Preț RON': f"{p.get('price_ron', 0):.2f}",
                    'Stoc': p.get('stock', 100)
                })
            
            df_preview = pd.DataFrame(preview_data)
            st.dataframe(df_preview, use_container_width=True)

if __name__ == "__main__":
    main()
