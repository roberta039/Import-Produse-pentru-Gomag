import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import json
import time
from datetime import datetime
import os

# Page config
st.set_page_config(
    page_title="🎒 Simple Product Importer",
    layout="wide"
)

# Initialize session state
if 'products' not in st.session_state:
    st.session_state.products = []

def extract_basic_info(url):
    """Extract basic product info from URL"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Try to find basic elements
        product = {
            'url': url,
            'status': 'success',
            'extracted_at': datetime.now().isoformat()
        }
        
        # Title - try multiple selectors
        title_selectors = ['h1', '.product-title', '.product-name', '[itemprop="name"]']
        for selector in title_selectors:
            elem = soup.select_one(selector)
            if elem:
                product['name'] = elem.get_text(strip=True)
                break
        
        if 'name' not in product:
            product['name'] = f"Product from {url.split('/')[2]}"
        
        # Price - try multiple selectors
        price_selectors = ['.price', '.product-price', '[itemprop="price"]', '.amount']
        for selector in price_selectors:
            elem = soup.select_one(selector)
            if elem:
                price_text = elem.get_text(strip=True)
                # Extract numbers from price
                import re
                numbers = re.findall(r'[\d,\.]+', price_text)
                if numbers:
                    product['price'] = float(numbers[0].replace(',', '.'))
                    break
        
        # Description
        desc_selectors = ['.product-description', '.description', '[itemprop="description"]']
        for selector in desc_selectors:
            elem = soup.select_one(selector)
            if elem:
                product['description'] = elem.get_text(strip=True)[:500]
                break
        
        # Images
        product['images'] = []
        img_selectors = ['.product-image img', '.gallery img', 'img[itemprop="image"]']
        for selector in img_selectors:
            imgs = soup.select(selector)[:5]  # Max 5 images
            for img in imgs:
                src = img.get('src') or img.get('data-src')
                if src:
                    if not src.startswith('http'):
                        src = 'https:' + src if src.startswith('//') else url.split('/')[0] + '//' + url.split('/')[2] + src
                    product['images'].append(src)
        
        # SKU from URL
        import re
        sku_match = re.search(r'([A-Z0-9]+-[0-9]+|[pP]\d{3}\.\d{2}|[A-Z]{2}\d{4,})', url)
        if sku_match:
            product['sku'] = sku_match.group(1)
        else:
            product['sku'] = f"SKU_{hash(url) % 100000}"
        
        return product
        
    except Exception as e:
        st.error(f"Error extracting from {url}: {str(e)}")
        return {
            'url': url,
            'status': 'error',
            'error': str(e),
            'name': 'Failed to extract',
            'sku': f"ERR_{hash(url) % 10000}"
        }

def save_products_locally(products):
    """Save products to local files"""
    # Create directory
    os.makedirs("exports", exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Save as JSON
    json_file = f"exports/products_{timestamp}.json"
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(products, f, indent=2, ensure_ascii=False)
    
    # Save as CSV
    csv_file = f"exports/products_{timestamp}.csv"
    df = pd.DataFrame(products)
    df.to_csv(csv_file, index=False, encoding='utf-8-sig')
    
    return json_file, csv_file

# Main app
st.title("🎒 Simple Product Importer")

# Tabs
tab1, tab2, tab3 = st.tabs(["📤 Input URLs", "🔍 Extract", "📥 Export"])

with tab1:
    st.header("Add Product URLs")
    
    # Manual input
    urls_input = st.text_area(
        "Enter URLs (one per line)",
        height=200,
        placeholder="https://www.xdconnects.com/...\nhttps://www.pfconcept.com/..."
    )
    
    if st.button("Add URLs"):
        urls = [url.strip() for url in urls_input.split('\n') if url.strip()]
        for url in urls:
            if not any(p['url'] == url for p in st.session_state.products):
                st.session_state.products.append({
                    'url': url,
                    'status': 'pending'
                })
        st.success(f"Added {len(urls)} URLs")
        st.rerun()
    
    # Quick test URLs
    if st.button("Add Test URLs"):
        test_urls = [
            "https://www.xdconnects.com/en-gb/bags-travel/anti-theft-backpacks/bobby-hero-regular-anti-theft-backpack-p705.29?variantId=P705.291",
            "https://www.pfconcept.com/en_cz/cover-grs-rpet-anti-theft-backpack-18l-120510.html",
            "https://www.midocean.com/central-europe/us/eur/bags-travel/backpacks/laptop-backpacks/mo2739-03-zid10244354"
        ]
        for url in test_urls:
            if not any(p['url'] == url for p in st.session_state.products):
                st.session_state.products.append({
                    'url': url,
                    'status': 'pending'
                })
        st.success("Added 3 test URLs")
        st.rerun()
    
    # Show current URLs
    if st.session_state.products:
        st.subheader(f"Current Products ({len(st.session_state.products)})")
        for i, product in enumerate(st.session_state.products):
            col1, col2, col3 = st.columns([3, 1, 1])
            with col1:
                st.text(f"{i+1}. {product['url'][:80]}...")
            with col2:
                st.text(product.get('status', 'pending'))
            with col3:
                if st.button(f"Remove", key=f"del_{i}"):
                    st.session_state.products.pop(i)
                    st.rerun()

with tab2:
    st.header("Extract Product Information")
    
    pending = [p for p in st.session_state.products if p.get('status') == 'pending']
    st.info(f"Products to process: {len(pending)}")
    
    if st.button("🔍 Start Extraction", disabled=len(pending) == 0):
        progress = st.progress(0)
        status = st.empty()
        
        for i, product in enumerate(st.session_state.products):
            if product.get('status') != 'pending':
                continue
            
            progress.progress((i + 1) / len(st.session_state.products))
            status.text(f"Processing: {product['url'][:60]}...")
            
            # Extract info
            info = extract_basic_info(product['url'])
            
            # Update product
            idx = st.session_state.products.index(product)
            st.session_state.products[idx].update(info)
            
            time.sleep(1)  # Avoid rate limiting
        
        progress.progress(1.0)
        status.text("✅ Extraction complete!")
        time.sleep(1)
        st.rerun()
    
    # Show extracted products
    successful = [p for p in st.session_state.products if p.get('status') == 'success']
    if successful:
        st.subheader(f"✅ Successfully Extracted ({len(successful)})")
        for product in successful:
            with st.expander(f"📦 {product.get('name', 'Product')[:60]}..."):
                col1, col2 = st.columns([1, 2])
                with col1:
                    if product.get('images'):
                        st.image(product['images'][0], width=150)
                with col2:
                    st.write(f"**SKU:** {product.get('sku', 'N/A')}")
                    st.write(f"**Price:** {product.get('price', 'N/A')}")
                    st.write(f"**Description:** {product.get('description', 'N/A')[:200]}...")

with tab3:
    st.header("Export Products")
    
    successful = [p for p in st.session_state.products if p.get('status') == 'success']
    
    if not successful:
        st.warning("No products to export. Please extract some products first.")
    else:
        st.info(f"Ready to export: {len(successful)} products")
        
        # Export options
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("💾 Save Locally"):
                json_file, csv_file = save_products_locally(successful)
                st.success(f"✅ Saved to:\n- {json_file}\n- {csv_file}")
        
        with col2:
            # Download as CSV
            df = pd.DataFrame(successful)
            csv = df.to_csv(index=False, encoding='utf-8-sig')
            st.download_button(
                "📥 Download CSV",
                data=csv,
                file_name=f"products_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )
        
        # Preview data
        st.subheader("Data Preview")
        df_preview = pd.DataFrame([{
            'SKU': p.get('sku', ''),
            'Name': p.get('name', '')[:50],
            'Price': p.get('price', 0),
            'URL': p.get('url', '')[:50]
        } for p in successful])
        st.dataframe(df_preview)

# Sidebar info
with st.sidebar:
    st.header("ℹ️ Info")
    st.write("""
    ### How to use:
    1. Add product URLs
    2. Click 'Start Extraction'
    3. Export the results
    
    ### Status:
    """)
    
    total = len(st.session_state.products)
    pending = len([p for p in st.session_state.products if p.get('status') == 'pending'])
    success = len([p for p in st.session_state.products if p.get('status') == 'success'])
    errors = len([p for p in st.session_state.products if p.get('status') == 'error'])
    
    st.metric("Total", total)
    st.metric("Pending", pending)
    st.metric("Success", success)  
    st.metric("Errors", errors)
    
    if st.button("🗑️ Clear All"):
        st.session_state.products = []
        st.rerun()
