import streamlit as st
import pandas as pd
import cloudscraper
from bs4 import BeautifulSoup
import re
import json
import time
from datetime import datetime
from io import BytesIO

st.set_page_config(
    page_title="🎒 Product Importer - Working",
    layout="wide"
)

# Initialize session state
if 'products' not in st.session_state:
    st.session_state.products = []

def extract_product_info(url):
    """Extract product info using cloudscraper"""
    scraper = cloudscraper.create_scraper()
    
    try:
        # Get page with cloudscraper (bypasses Cloudflare)
        response = scraper.get(url, timeout=20)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        product = {
            'url': url,
            'status': 'success'
        }
        
        # Remove scripts and styles
        for script in soup(['script', 'style']):
            script.decompose()
        
        # === EXTRACT NAME ===
        # Try OpenGraph first
        og_title = soup.find('meta', property='og:title')
        if og_title and og_title.get('content'):
            product['name'] = og_title['content'].strip()
        else:
            # Try H1
            h1 = soup.find('h1')
            if h1:
                product['name'] = h1.get_text(strip=True)
            else:
                # Use title
                title = soup.find('title')
                product['name'] = title.get_text(strip=True) if title else f"Product from {url.split('/')[2]}"
        
        # Clean name
        product['name'] = re.sub(r'\s+', ' ', product['name'])[:200]
        
        # === EXTRACT SKU ===
        # From URL
        sku_patterns = [
            r'[pP](\d{3}\.\d{2,3})',  # XD format
            r'/([\w\-]+)\?',  # Before query params
            r'/products?/([^/]+)',  # Product ID
            r'sku=([^&]+)',  # From query
            r'[/-]([A-Z0-9]{5,})',  # Generic
        ]
        
        sku = None
        for pattern in sku_patterns:
            match = re.search(pattern, url)
            if match:
                sku = match.group(1)
                break
        
        # From page content
        if not sku:
            sku_text = soup.get_text()
            sku_match = re.search(r'SKU[:\s]+([A-Z0-9\-]+)', sku_text, re.I)
            if sku_match:
                sku = sku_match.group(1)
        
        product['sku'] = sku.upper() if sku else f"PROD{hash(url) % 1000000}"
        
        # === EXTRACT PRICE ===
        # Look for structured data
        scripts = soup.find_all('script', type='application/ld+json')
        price_found = False
        
        for script in scripts:
            try:
                data = json.loads(script.string)
                if isinstance(data, dict):
                    if data.get('@type') == 'Product' and 'offers' in data:
                        product['price'] = float(data['offers'].get('price', 0))
                        product['currency'] = data['offers'].get('priceCurrency', 'EUR')
                        price_found = True
                        
                        # Also get other data
                        if 'name' in data and not product.get('name'):
                            product['name'] = data['name']
                        if 'description' in data:
                            product['description'] = data['description'][:1000]
                        if 'image' in data:
                            imgs = data['image']
                            if isinstance(imgs, str):
                                product['images'] = [imgs]
                            elif isinstance(imgs, list):
                                product['images'] = imgs[:5]
                        break
            except:
                continue
        
        # Fallback price extraction
        if not price_found:
            page_text = soup.get_text()
            price_patterns = [
                r'€\s*([\d,\.]+)',
                r'EUR\s*([\d,\.]+)',
                r'([\d,\.]+)\s*€',
                r'Price[:\s]*([\d,\.]+)',
            ]
            
            for pattern in price_patterns:
                matches = re.findall(pattern, page_text)
                if matches:
                    for match in matches:
                        try:
                            price = float(match.replace(',', '.'))
                            if 1 <= price <= 10000:  # Reasonable range
                                product['price'] = price
                                product['currency'] = 'EUR'
                                price_found = True
                                break
                        except:
                            continue
                if price_found:
                    break
        
        if not price_found:
            product['price'] = 0
            product['currency'] = 'EUR'
        
        # === EXTRACT IMAGES ===
        if 'images' not in product:
            images = []
            
            # OpenGraph image
            og_img = soup.find('meta', property='og:image')
            if og_img and og_img.get('content'):
                img_url = og_img['content']
                if not img_url.startswith('http'):
                    base = '/'.join(url.split('/')[:3])
                    img_url = base + img_url if img_url.startswith('/') else base + '/' + img_url
                images.append(img_url)
            
            # Find product images
            for img in soup.find_all('img')[:30]:
                src = img.get('src') or img.get('data-src') or img.get('data-lazy')
                if src:
                    # Check if it's likely a product image
                    if any(x in src.lower() for x in ['product', 'item', 'article', '/p/', '/products/']):
                        if not src.startswith('http'):
                            if src.startswith('//'):
                                src = 'https:' + src
                            elif src.startswith('/'):
                                base = '/'.join(url.split('/')[:3])
                                src = base + src
                        
                        if src.startswith('http') and src not in images:
                            images.append(src)
            
            product['images'] = images[:5]
        
        # === EXTRACT DESCRIPTION ===
        if 'description' not in product:
            desc = soup.find('meta', name='description') or soup.find('meta', property='og:description')
            if desc:
                product['description'] = desc.get('content', '')[:1000]
            else:
                # Try to find description div
                for cls in ['description', 'product-description', 'product-details']:
                    desc_div = soup.find(class_=re.compile(cls, re.I))
                    if desc_div:
                        product['description'] = desc_div.get_text(strip=True)[:1000]
                        break
        
        # === EXTRACT BRAND ===
        domain = url.split('/')[2].lower()
        brand_map = {
            'xdconnects': 'XD Design',
            'pfconcept': 'PF Concept',
            'midocean': 'Midocean',
            'promobox': 'Promobox',
            'andapresent': 'Anda Present'
        }
        
        product['brand'] = next((v for k, v in brand_map.items() if k in domain), domain.split('.')[0].title())
        
        # === EXTRACT FEATURES ===
        features = []
        feature_lists = soup.find_all('ul', class_=re.compile('feature|highlight|benefit', re.I))
        for ul in feature_lists[:2]:
            for li in ul.find_all('li')[:10]:
                text = li.get_text(strip=True)
                if text and len(text) > 5:
                    features.append(text)
        product['features'] = features
        
        # === EXTRACT SPECIFICATIONS ===
        specs = {}
        spec_tables = soup.find_all('table', class_=re.compile('spec|detail', re.I))
        for table in spec_tables[:2]:
            for row in table.find_all('tr')[:20]:
                cells = row.find_all(['td', 'th'])
                if len(cells) >= 2:
                    key = cells[0].get_text(strip=True)
                    value = cells[1].get_text(strip=True)
                    if key and value:
                        specs[key] = value
        product['specifications'] = specs
        
        return product
        
    except Exception as e:
        return {
            'url': url,
            'status': 'error',
            'error': str(e),
            'name': f"Error extracting from {url.split('/')[2]}",
            'sku': f"ERR_{hash(url) % 100000}",
            'price': 0,
            'currency': 'EUR',
            'images': [],
            'brand': '',
            'description': ''
        }

# UI
st.title("🎒 Product Importer - CloudScraper Version")

tab1, tab2, tab3 = st.tabs(["📤 Add URLs", "🔍 Extract", "📥 Export"])

with tab1:
    urls_input = st.text_area(
        "Enter URLs (one per line)",
        height=200,
        placeholder="https://www.xdconnects.com/...\nhttps://www.pfconcept.com/..."
    )
    
    if st.button("Add URLs"):
        urls = [u.strip() for u in urls_input.split('\n') if u.strip()]
        for url in urls:
            if not any(p['url'] == url for p in st.session_state.products):
                st.session_state.products.append({'url': url, 'status': 'pending'})
        st.success(f"Added {len(urls)} URLs")
        st.rerun()
    
    if st.button("Add Test URL"):
        test_url = "https://www.xdconnects.com/en-gb/bags-travel/anti-theft-backpacks/bobby-hero-small-anti-theft-backpack-p705.70?variantId=P705.709"
        if not any(p['url'] == test_url for p in st.session_state.products):
            st.session_state.products.append({'url': test_url, 'status': 'pending'})
            st.success("Added test URL")
            st.rerun()

with tab2:
    if st.button("🔍 Extract Products"):
        progress = st.progress(0)
        
        for i, product in enumerate(st.session_state.products):
            if product['status'] == 'pending':
                progress.progress((i + 1) / len(st.session_state.products))
                
                # Extract info
                info = extract_product_info(product['url'])
                info['extracted_at'] = datetime.now().isoformat()
                
                # Update product
                st.session_state.products[i].update(info)
                
                # Show what was extracted
                st.write(f"✅ Extracted: {info.get('name', 'Unknown')[:50]}... - SKU: {info.get('sku')} - Price: {info.get('price')}")
                
                time.sleep(1)  # Rate limit
        
        st.success("Extraction complete!")
        st.rerun()
    
    # Show products
    for p in st.session_state.products:
        if p.get('status') == 'success':
            with st.expander(f"{p.get('name', 'Product')[:60]}"):
                col1, col2 = st.columns([1, 2])
                with col1:
                    if p.get('images'):
                        st.image(p['images'][0], width=150)
                with col2:
                    st.write(f"**SKU:** {p.get('sku')}")
                    st.write(f"**Brand:** {p.get('brand')}")
                    st.write(f"**Price:** {p.get('price')} {p.get('currency')}")
                    st.write(f"**Description:** {p.get('description', '')[:200]}...")

with tab3:
    successful = [p for p in st.session_state.products if p.get('status') == 'success']
    
    if successful:
        # Create CSV
        df = pd.DataFrame(successful)
        csv = df.to_csv(index=False, encoding='utf-8-sig')
        
        st.download_button(
            "📥 Download CSV (All Fields)",
            data=csv,
            file_name=f"products_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv"
        )
        
        # Preview
        st.dataframe(df[['sku', 'name', 'brand', 'price', 'currency']].head())
