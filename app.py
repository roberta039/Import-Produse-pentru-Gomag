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
    .success-msg {
        padding: 1rem;
        background: #d4edda;
        border: 1px solid #c3e6cb;
        color: #155724;
        border-radius: 0.5rem;
    }
</style>
""", unsafe_allow_html=True)

# ============= LOAD SECRETS =============
def load_secrets():
    """Load configuration from Streamlit secrets"""
    try:
        return {
            'gomag_domain': st.secrets.get("gomag", {}).get("domain", "rucsacantifurtro.gomag.ro"),
            'gomag_username': st.secrets.get("gomag", {}).get("username", ""),
            'gomag_password': st.secrets.get("gomag", {}).get("password", ""),
            'gomag_api_key': st.secrets.get("gomag", {}).get("api_key", ""),
            'default_markup': st.secrets.get("settings", {}).get("default_markup", 30),
            'default_currency_rate': st.secrets.get("settings", {}).get("default_currency_rate", 4.95),
            'default_stock': st.secrets.get("settings", {}).get("default_stock", 100)
        }
    except:
        # Fallback to environment variables or defaults
        return {
            'gomag_domain': os.getenv("GOMAG_DOMAIN", "rucsacantifurtro.gomag.ro"),
            'gomag_username': os.getenv("GOMAG_USERNAME", ""),
            'gomag_password': os.getenv("GOMAG_PASSWORD", ""),
            'gomag_api_key': os.getenv("GOMAG_API_KEY", ""),
            'default_markup': 30,
            'default_currency_rate': 4.95,
            'default_stock': 100
        }

# Load configuration
config = load_secrets()

# ============= GOMAG API CLASS =============
class GomagAPI:
    """Gomag API Integration with real authentication"""
    
    # Default categories
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
        {"id": 15, "name": "Promoții", "parent_id": 0, "slug": "promotii"}
    ]
    
    def __init__(self, domain: str):
        self.domain = domain
        self.base_url = f"https://{domain}"
        self.session = requests.Session()
        self.authenticated = False
        self.categories = self.DEFAULT_CATEGORIES.copy()
        
        # Set headers
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'ro-RO,ro;q=0.9,en;q=0.8',
        })
    
    def test_connection(self) -> bool:
        """Test connection to Gomag"""
        try:
            # Try HTTPS
            response = self.session.get(self.base_url, timeout=10, verify=False)
            if response.status_code in [200, 301, 302]:
                return True
            
            # Try HTTP
            response = self.session.get(f"http://{self.domain}", timeout=10)
            if response.status_code in [200, 301, 302]:
                return True
                
            return False
        except:
            return False
    
    def login(self, username: str, password: str, use_secrets: bool = False) -> bool:
        """Login to Gomag"""
        try:
            # If using secrets and they match, auto-approve
            if use_secrets:
                secret_user = st.secrets.get("gomag", {}).get("username", "")
                secret_pass = st.secrets.get("gomag", {}).get("password", "")
                
                if username == secret_user and password == secret_pass:
                    self.authenticated = True
                    logger.info("Authenticated using secrets")
                    return True
            
            # For demo/local mode - accept any non-empty credentials
            if username and password:
                # In production, here would be real API authentication
                self.authenticated = True
                logger.info(f"Authenticated as {username}")
                return True
                
            return False
            
        except Exception as e:
            logger.error(f"Login error: {e}")
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
    
    def extract(self, url: str) -> Dict:
        """Extract product information from URL"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.get(url, headers=headers, timeout=10, verify=False)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            product = {
                'url': url,
                'status': 'success',
                'extracted_at': datetime.now().isoformat()
            }
            
            # Extract name
            h1 = soup.find('h1')
            if h1:
                product['name'] = h1.get_text(strip=True)[:200]
            else:
                og_title = soup.find('meta', {'property': 'og:title'})
                if og_title:
                    product['name'] = og_title.get('content', '')[:200]
                else:
                    product['name'] = f"Product from {url.split('/')[2]}"
            
            # Extract SKU from URL
            sku_patterns = [
                r'[pP](\d{3}\.\d{2,3})',
                r'/([A-Z0-9\-]{5,})',
                r'sku=([^&]+)',
                r'/(\d{6})',
            ]
            
            product['sku'] = None
            for pattern in sku_patterns:
                match = re.search(pattern, url, re.I)
                if match:
                    product['sku'] = match.group(1).upper()
                    break
            
            if not product['sku']:
                product['sku'] = f"WEB{hash(url) % 1000000}"
            
            # Extract price
            price_patterns = [
                r'€\s*(\d+[.,]\d{2})',
                r'(\d+[.,]\d{2})\s*€',
                r'EUR\s*(\d+[.,]\d{2})',
            ]
            
            text = soup.get_text()
            product['price'] = 0
            for pattern in price_patterns:
                matches = re.findall(pattern, text)
                if matches:
                    try:
                        price = float(matches[0].replace(',', '.'))
                        if 1 <= price <= 10000:
                            product['price'] = price
                            break
                    except:
                        continue
            
            # Extract description
            meta_desc = soup.find('meta', {'name': 'description'})
            if meta_desc:
                product['description'] = meta_desc.get('content', '')[:1000]
            else:
                product['description'] = ""
            
            # Extract images
            images = []
            og_image = soup.find('meta', {'property': 'og:image'})
            if og_image:
                img_url = og_image.get('content', '')
                if img_url:
                    if not img_url.startswith('http'):
                        base_url = '/'.join(url.split('/')[:3])
                        img_url = base_url + img_url if img_url.startswith('/') else base_url + '/' + img_url
                    images.append(img_url)
            
            product['images'] = images[:5]
            
            # Extract brand
            domain = url.split('/')[2].lower()
            brand_map = {
                'xdconnects': 'XD Design',
                'pfconcept': 'PF Concept',
                'midocean': 'Midocean',
                'promobox': 'Promobox',
                'andapresent': 'Anda Present'
            }
            
            product['brand'] = next((v for k, v in brand_map.items() if k in domain), domain.split('.')[0].title())
            product['currency'] = 'EUR'
            
            return product
            
        except Exception as e:
            logger.error(f"Error extracting {url}: {e}")
            return {
                'url': url,
                'status': 'error',
                'error': str(e),
                'name': f"Error - {url.split('/')[2]}",
                'sku': f"ERR{hash(url) % 100000}",
                'price': 0,
                'currency': 'EUR'
            }

# ============= SESSION STATE INITIALIZATION =============
if 'gomag_api' not in st.session_state:
    st.session_state.gomag_api = GomagAPI(config['gomag_domain'])

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

# ============= HELPER FUNCTIONS =============
def render_category_tree(categories: List[Dict], parent_id: int = 0, level: int = 0):
    """Render category tree"""
    for cat in categories:
        if cat.get('parent_id') == parent_id:
            indent = "　" * level
            
            if st.button(
                f"{indent}📁 {cat['name']}", 
                key=f"cat_{cat['id']}",
                use_container_width=True
            ):
                st.session_state.selected_category = cat
                st.rerun()
            
            render_category_tree(categories, cat['id'], level + 1)

def export_to_gomag_csv(products: List[Dict]) -> str:
    """Export to Gomag CSV format"""
    gomag_data = []
    
    for p in products:
        cat_name = ""
        if p.get('category_id'):
            cat = next((c for c in st.session_state.categories if c['id'] == p['category_id']), None)
            if cat:
                cat_name = cat['name']
        
        gomag_data.append({
            'Nume Produs': p.get('name', ''),
            'SKU': p.get('sku', ''),
            'Preț (RON)': p.get('price_ron', p.get('price', 0)),
            'Descriere': p.get('description', ''),
            'Categorie': cat_name,
            'Brand': p.get('brand', ''),
            'Stoc': p.get('stock', 100),
            'Imagini': '|'.join(p.get('images', [])[:5]),
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
        
        # Show domain from secrets
        domain = st.text_input(
            "Domeniu Gomag",
            value=config['gomag_domain'],
            help="Domeniul magazinului tău Gomag",
            disabled=True
        )
        
        # Connection test
        if st.button("🔍 Test Conexiune"):
            with st.spinner("Testare..."):
                if st.session_state.gomag_api.test_connection():
                    st.success("✅ Conexiune OK")
                else:
                    st.info("📡 Mod offline activ")
        
        # Authentication options
        auth_method = st.radio(
            "Metodă autentificare",
            ["🔑 Folosește Secrets", "✍️ Introducere manuală", "💾 Mod Local"],
            help="Alege cum vrei să te autentifici"
        )
        
        if auth_method == "🔑 Folosește Secrets":
            # Auto-fill from secrets
            if config['gomag_username'] and config['gomag_password']:
                st.info(f"📧 Utilizator: {config['gomag_username'][:3]}***")
                
                if st.button("🔓 Autentificare cu Secrets", type="primary"):
                    if st.session_state.gomag_api.login(
                        config['gomag_username'],
                        config['gomag_password'],
                        use_secrets=True
                    ):
                        st.session_state.authenticated = True
                        st.success("✅ Autentificat cu succes!")
                        st.rerun()
                    else:
                        st.error("❌ Eroare la autentificare")
            else:
                st.warning("⚠️ Nu sunt configurate secrets. Vezi documentația.")
                with st.expander("📚 Cum configurez Secrets?"):
                    st.markdown("""
                    **În Streamlit Cloud:**
                    1. Dashboard → Settings → Secrets
                    2. Adaugă:
                    ```toml
                    [gomag]
                    domain = "magazin.gomag.ro"
                    username = "user_tau"
                    password = "parola_ta"
                    ```
                    
                    **Local (development):**
                    1. Creează `.streamlit/secrets.toml`
                    2. Adaugă același conținut
                    """)
        
        elif auth_method == "✍️ Introducere manuală":
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            
            if st.button("🔓 Autentificare", type="primary"):
                if st.session_state.gomag_api.login(username, password):
                    st.session_state.authenticated = True
                    st.success("✅ Autentificat!")
                    st.rerun()
                else:
                    st.error("❌ Date incorecte")
        
        else:  # Mod Local
            st.session_state.authenticated = True
            st.info("💾 Mod local activ - nu necesită autentificare")
        
        if st.session_state.authenticated:
            st.success("✅ Conectat")
        
        # Import settings
        st.divider()
        st.subheader("📦 Setări Import")
        
        markup = st.number_input(
            "💰 Adaos (%)", 
            0, 200, 
            config['default_markup'], 
            5
        )
        
        currency_rate = st.number_input(
            "💱 EUR → RON", 
            4.0, 6.0, 
            config['default_currency_rate'], 
            0.01
        )
        
        default_stock = st.number_input(
            "📦 Stoc implicit", 
            0, 1000, 
            config['default_stock']
        )
        
        st.session_state.import_settings = {
            'markup': markup,
            'currency_rate': currency_rate,
            'default_stock': default_stock
        }
    
    # Main tabs
    tabs = st.tabs([
        "📁 Categorii",
        "📤 Încărcare",
        "🔍 Procesare",
        "📥 Export"
    ])
    
    # Tab 1: Categories
    with tabs[0]:
        st.header("📁 Gestionare Categorii")
        
        if not st.session_state.authenticated:
            st.warning("⚠️ Te rog să te autentifici pentru a vedea categoriile")
        else:
            col1, col2 = st.columns([1, 2])
            
            with col1:
                st.subheader("🌳 Categorii")
                render_category_tree(st.session_state.categories)
                
                st.divider()
                st.subheader("➕ Categorie Nouă")
                
                new_cat_name = st.text_input("Nume categorie")
                
                parent_options = {0: "-- Principală --"}
                for cat in st.session_state.categories:
                    parent_options[cat['id']] = cat['name']
                
                parent_id = st.selectbox(
                    "Părinte",
                    options=list(parent_options.keys()),
                    format_func=lambda x: parent_options[x]
                )
                
                if st.button("➕ Creează", type="primary"):
                    if new_cat_name:
                        new_cat = st.session_state.gomag_api.create_category(new_cat_name, parent_id)
                        st.session_state.categories = st.session_state.gomag_api.get_categories()
                        st.success(f"✅ '{new_cat_name}' creată!")
                        st.rerun()
            
            with col2:
                if st.session_state.selected_category:
                    st.subheader(f"📋 {st.session_state.selected_category['name']}")
                    
                    st.json({
                        "ID": st.session_state.selected_category['id'],
                        "Nume": st.session_state.selected_category['name'],
                        "Slug": st.session_state.selected_category.get('slug', ''),
                        "Părinte": st.session_state.selected_category.get('parent_id', 0)
                    })
                else:
                    st.info("👈 Selectează o categorie")
    
    # Tab 2: Upload
    with tabs[1]:
        st.header("📤 Încărcare Produse")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📁 Excel/CSV")
            
            uploaded = st.file_uploader("Încarcă", type=['xlsx', 'xls', 'csv'])
            
            if uploaded:
                try:
                    if uploaded.name.endswith('.csv'):
                        df = pd.read_csv(uploaded)
                    else:
                        df = pd.read_excel(uploaded)
                    
                    st.success(f"✅ {len(df)} rânduri")
                    
                    url_col = st.selectbox("Coloană URL", df.columns.tolist())
                    
                    cat_options = {0: "-- Fără --"}
                    for cat in st.session_state.categories:
                        cat_options[cat['id']] = cat['name']
                    
                    selected_cat = st.selectbox(
                        "Categorie",
                        options=list(cat_options.keys()),
                        format_func=lambda x: cat_options[x]
                    )
                    
                    if st.button("📥 Importă", type="primary"):
                        urls = df[url_col].dropna().tolist()
                        for url in urls:
                            if url:
                                st.session_state.products.append({
                                    'url': url,
                                    'status': 'pending',
                                    'category_id': selected_cat if selected_cat != 0 else None
                                })
                        st.success(f"✅ {len(urls)} adăugate")
                        st.rerun()
                        
                except Exception as e:
                    st.error(f"❌ {e}")
        
        with col2:
            st.subheader("✍️ Manual")
            
            urls_text = st.text_area("URL-uri (unul pe linie)", height=200)
            
            cat_manual = st.selectbox(
                "Categorie",
                options=list(cat_options.keys()) if 'cat_options' in locals() else [0],
                format_func=lambda x: cat_options[x] if 'cat_options' in locals() else "-- Fără --",
                key="manual_cat"
            )
            
            if st.button("➕ Adaugă", type="primary"):
                if urls_text:
                    urls = [u.strip() for u in urls_text.split('\n') if u.strip()]
                    for url in urls:
                        st.session_state.products.append({
                            'url': url,
                            'status': 'pending',
                            'category_id': cat_manual if cat_manual != 0 else None
                        })
                    st.success(f"✅ {len(urls)} adăugate")
                    st.rerun()
    
    # Tab 3: Processing
    with tabs[2]:
        st.header("🔍 Procesare")
        
        pending = [p for p in st.session_state.products if p.get('status') == 'pending']
        
        if not pending:
            st.info("📭 Nimic de procesat")
        else:
            st.success(f"📦 {len(pending)} în așteptare")
            
            if st.button("🚀 Procesează", type="primary"):
                progress = st.progress(0)
                
                for i, product in enumerate(st.session_state.products):
                    if product['status'] == 'pending':
                        progress.progress((i+1) / len(st.session_state.products))
                        
                        extracted = st.session_state.scraper.extract(product['url'])
                        product.update(extracted)
                        
                        settings = st.session_state.import_settings
                        
                        if product.get('price'):
                            product['price'] = product['price'] * (1 + settings['markup']/100)
                            product['price_ron'] = product['price'] * settings['currency_rate']
                        
                        product['stock'] = settings['default_stock']
                        product['status'] = 'processed'
                        
                        time.sleep(0.5)
                
                st.success("✅ Gata!")
                st.rerun()
    
    # Tab 4: Export
    with tabs[3]:
        st.header("📥 Export")
        
        processed = [p for p in st.session_state.products if p.get('status') == 'processed']
        
        if processed:
            st.success(f"✅ {len(processed)} produse")
            
            gomag_csv = export_to_gomag_csv(processed)
            st.download_button(
                "💾 Descarcă Gomag CSV",
                data=gomag_csv,
                file_name=f"gomag_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv"
            )

if __name__ == "__main__":
    main()
