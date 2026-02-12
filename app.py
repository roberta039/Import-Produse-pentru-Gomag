import streamlit as st
import pandas as pd
import json
import time
from datetime import datetime
from io import BytesIO, StringIO
import logging

# Import the universal scraper
from scrapers.universal_scraper import UniversalScraper

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Page config
st.set_page_config(
    page_title="🎒 Product Importer - Fixed Version",
    layout="wide",
    page_icon="🎒"
)

# Custom CSS
st.markdown("""
<style>
    .success-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        color: #155724;
        margin: 1rem 0;
    }
    .error-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #f8d7da;
        border: 1px solid #f5c6cb;
        color: #721c24;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'products' not in st.session_state:
    st.session_state.products = []
if 'scraper' not in st.session_state:
    st.session_state.scraper = UniversalScraper()

def export_to_csv(products):
    """Export products to CSV format with all fields"""
    # Prepare data for CSV
    csv_data = []
    
    for p in products:
        # Flatten the product data
        row = {
            'URL': p.get('url', ''),
            'Status': p.get('status', ''),
            'SKU': p.get('sku', ''),
            'Name': p.get('name', ''),
            'Brand': p.get('brand', ''),
            'Price': p.get('price', 0),
            'Currency': p.get('currency', 'EUR'),
            'Description': p.get('description', ''),
            'Materials': p.get('materials', ''),
            'Dimensions': p.get('dimensions', ''),
            'Images': '|'.join(p.get('images', [])[:5]),  # Join first 5 images with |
            'Features': '|'.join(p.get('features', [])[:10]),  # Join features with |
            'Specifications': json.dumps(p.get('specifications', {}), ensure_ascii=False),
            'Variants': json.dumps(p.get('variants', []), ensure_ascii=False),
            'Meta Title': p.get('meta_title', ''),
            'Meta Description': p.get('meta_description', ''),
            'Extracted At': p.get('extracted_at', '')
        }
        csv_data.append(row)
    
    # Create DataFrame
    df = pd.DataFrame(csv_data)
    
    # Convert to CSV
    return df.to_csv(index=False, encoding='utf-8-sig')

def export_to_excel(products):
    """Export products to Excel with multiple sheets"""
    output = BytesIO()
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # Main products sheet
        main_data = []
        for p in products:
            main_data.append({
                'SKU': p.get('sku', ''),
                'Name': p.get('name', ''),
                'Brand': p.get('brand', ''),
                'Price': p.get('price', 0),
                'Currency': p.get('currency', 'EUR'),
                'Description': p.get('description', '')[:500],
                'URL': p.get('url', ''),
                'Status': p.get('status', '')
            })
        
        df_main = pd.DataFrame(main_data)
        df_main.to_excel(writer, sheet_name='Products', index=False)
        
        # Images sheet
        img_data = []
        for p in products:
            for i, img in enumerate(p.get('images', [])[:5]):
                img_data.append({
                    'SKU': p.get('sku', ''),
                    'Image Number': i + 1,
                    'Image URL': img
                })
        
        if img_data:
            df_img = pd.DataFrame(img_data)
            df_img.to_excel(writer, sheet_name='Images', index=False)
        
        # Specifications sheet
        spec_data = []
        for p in products:
            for key, value in p.get('specifications', {}).items():
                spec_data.append({
                    'SKU': p.get('sku', ''),
                    'Specification': key,
                    'Value': value
                })
        
        if spec_data:
            df_spec = pd.DataFrame(spec_data)
            df_spec.to_excel(writer, sheet_name='Specifications', index=False)
    
    return output.getvalue()

def export_for_gomag(products):
    """Export in Gomag-compatible CSV format"""
    gomag_data = []
    
    for p in products:
        # Calculate price with markup
        price = p.get('price', 0) * 1.3  # 30% markup
        
        gomag_data.append({
            'Cod Produs': p.get('sku', ''),
            'Nume': p.get('name', ''),
            'Descriere': p.get('description', ''),
            'Pret': f"{price:.2f}",
            'Pret Vechi': f"{price * 1.2:.2f}",  # Show old price 20% higher
            'Stoc': 100,
            'Brand': p.get('brand', ''),
            'Categorie': 'Rucsacuri Anti-Furt',
            'Imagini': '|'.join(p.get('images', [])[:5]),
            'Greutate': '1',
            'Status': 'Activ'
        })
    
    df = pd.DataFrame(gomag_data)
    return df.to_csv(index=False, encoding='utf-8-sig', sep=';')  # Gomag uses semicolon

# Main app
st.title("🎒 Product Importer - Working Version")

# Tabs
tab1, tab2, tab3 = st.tabs(["📤 Add Products", "🔍 Extract & Preview", "📥 Export"])

with tab1:
    st.header("Add Product URLs")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📝 Manual Input")
        urls_text = st.text_area(
            "Enter URLs (one per line)",
            height=300,
            placeholder="https://www.xdconnects.com/...\nhttps://www.pfconcept.com/..."
        )
        
        if st.button("➕ Add URLs", type="primary", use_container_width=True):
            if urls_text:
                urls = [url.strip() for url in urls_text.split('\n') if url.strip()]
                added = 0
                for url in urls:
                    if not any(p['url'] == url for p in st.session_state.products):
                        st.session_state.products.append({
                            'url': url,
                            'status': 'pending',
                            'added_at': datetime.now().isoformat()
                        })
                        added += 1
                st.success(f"✅ Added {added} new URLs")
                time.sleep(1)
                st.rerun()
    
    with col2:
        st.subheader("📁 Upload Excel/CSV")
        uploaded_file = st.file_uploader(
            "Choose file with URLs",
            type=['xlsx', 'xls', 'csv']
        )
        
        if uploaded_file:
            try:
                if uploaded_file.name.endswith('.csv'):
                    df = pd.read_csv(uploaded_file)
                else:
                    df = pd.read_excel(uploaded_file)
                
                # Find URL column
                url_col = None
                for col in df.columns:
                    if 'url' in col.lower() or 'link' in col.lower():
                        url_col = col
                        break
                
                if url_col:
                    urls = df[url_col].dropna().tolist()
                    st.info(f"Found {len(urls)} URLs")
                    
                    if st.button("➕ Import All", type="primary", use_container_width=True):
                        added = 0
                        for url in urls:
                            if not any(p['url'] == url for p in st.session_state.products):
                                st.session_state.products.append({
                                    'url': url,
                                    'status': 'pending',
                                    'added_at': datetime.now().isoformat()
                                })
                                added += 1
                        st.success(f"✅ Imported {added} URLs")
                        time.sleep(1)
                        st.rerun()
            except Exception as e:
                st.error(f"Error reading file: {e}")
    
    # Test URLs
    st.divider()
    if st.button("🧪 Add Test URLs"):
        test_urls = [
            "https://www.xdconnects.com/en-gb/bags-travel/anti-theft-backpacks/bobby-hero-small-anti-theft-backpack-p705.70?variantId=P705.709",
            "https://www.pfconcept.com/en_cz/cover-grs-rpet-anti-theft-backpack-18l-120510.html",
            "https://www.midocean.com/central-europe/us/eur/bags-travel/backpacks/laptop-backpacks/mo2739-03-zid10244354"
        ]
        for url in test_urls:
            if not any(p['url'] == url for p in st.session_state.products):
                st.session_state.products.append({
                    'url': url,
                    'status': 'pending',
                    'added_at': datetime.now().isoformat()
                })
        st.success("✅ Added 3 test URLs")
        time.sleep(1)
        st.rerun()
    
    # Current products
    if st.session_state.products:
        st.divider()
        st.subheader(f"📋 Current Products ({len(st.session_state.products)})")
        
        for i, p in enumerate(st.session_state.products):
            cols = st.columns([4, 1, 1])
            with cols[0]:
                st.text(f"{i+1}. {p['url'][:80]}...")
            with cols[1]:
                if p.get('status') == 'success':
                    st.success("✅")
                elif p.get('status') == 'error':
                    st.error("❌")
                else:
                    st.info("⏳")
            with cols[2]:
                if st.button("🗑️", key=f"del_{i}"):
                    st.session_state.products.pop(i)
                    st.rerun()

with tab2:
    st.header("Extract Product Information")
    
    # Statistics
    col1, col2, col3 = st.columns(3)
    
    total = len(st.session_state.products)
    pending = len([p for p in st.session_state.products if p.get('status') == 'pending'])
    success = len([p for p in st.session_state.products if p.get('status') == 'success'])
    
    with col1:
        st.metric("Total Products", total)
    with col2:
        st.metric("Pending", pending)
    with col3:
        st.metric("Extracted", success)
    
    # Extract button
    if st.button("🔍 Start Extraction", type="primary", disabled=pending == 0, use_container_width=True):
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        scraper = st.session_state.scraper
        
        for i, product in enumerate(st.session_state.products):
            if product.get('status') == 'success':
                continue
            
            progress = (i + 1) / len(st.session_state.products)
            progress_bar.progress(progress)
            status_text.text(f"Extracting: {product['url'][:60]}...")
            
            # Extract product info
            extracted = scraper.extract_product(product['url'])
            extracted['extracted_at'] = datetime.now().isoformat()
            
            # Update product
            st.session_state.products[i].update(extracted)
            
            time.sleep(1)  # Rate limiting
        
        progress_bar.progress(1.0)
        status_text.text("✅ Extraction complete!")
        time.sleep(1)
        st.rerun()
    
    # Show extracted products
    st.divider()
    successful = [p for p in st.session_state.products if p.get('status') == 'success']
    
    if successful:
        st.subheader(f"✅ Extracted Products ({len(successful)})")
        
        for p in successful:
            with st.expander(f"📦 {p.get('name', 'Product')[:80]}"):
                col1, col2 = st.columns([1, 3])
                
                with col1:
                    if p.get('images'):
                        st.image(p['images'][0], width=200, caption=f"{len(p['images'])} images")
                
                with col2:
                    st.write(f"**SKU:** {p.get('sku', 'N/A')}")
                    st.write(f"**Brand:** {p.get('brand', 'N/A')}")
                    st.write(f"**Price:** {p.get('price', 0):.2f} {p.get('currency', 'EUR')}")
                    
                    if p.get('description'):
                        st.write(f"**Description:** {p['description'][:200]}...")
                    
                    if p.get('features'):
                        st.write(f"**Features:** {len(p['features'])} items")
                    
                    if p.get('specifications'):
                        st.write(f"**Specifications:** {len(p['specifications'])} items")
                    
                    if p.get('variants'):
                        st.write(f"**Variants:** {len(p['variants'])} options")

with tab3:
    st.header("Export Products")
    
    successful = [p for p in st.session_state.products if p.get('status') == 'success']
    
    if not successful:
        st.warning("⚠️ No products to export. Please extract some products first.")
    else:
        st.success(f"✅ {len(successful)} products ready for export")
        
        st.divider()
        
        # Export options in columns
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.subheader("📄 Complete CSV")
            csv_complete = export_to_csv(successful)
            st.download_button(
                label="⬇️ Download Complete CSV",
                data=csv_complete,
                file_name=f"products_complete_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                use_container_width=True
            )
        
        with col2:
            st.subheader("📊 Excel Multi-Sheet")
            excel_data = export_to_excel(successful)
            st.download_button(
                label="⬇️ Download Excel",
                data=excel_data,
                file_name=f"products_excel_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        
        with col3:
            st.subheader("🛒 Gomag CSV")
            gomag_csv = export_for_gomag(successful)
            st.download_button(
                label="⬇️ Download Gomag CSV",
                data=gomag_csv,
                file_name=f"gomag_import_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                use_container_width=True
            )
        
        with col4:
            st.subheader("🔧 JSON Data")
            json_data = json.dumps(successful, indent=2, ensure_ascii=False)
            st.download_button(
                label="⬇️ Download JSON",
                data=json_data,
                file_name=f"products_json_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json",
                use_container_width=True
            )
        
        # Data preview
        st.divider()
        st.subheader("👁️ Data Preview")
        
        preview_df = pd.DataFrame([{
            'SKU': p.get('sku', ''),
            'Name': p.get('name', '')[:50],
            'Brand': p.get('brand', ''),
            'Price': f"{p.get('price', 0):.2f} {p.get('currency', 'EUR')}",
            'Images': len(p.get('images', [])),
            'Features': len(p.get('features', [])),
            'Variants': len(p.get('variants', []))
        } for p in successful[:10]])
        
        st.dataframe(preview_df, use_container_width=True)
        
        if len(successful) > 10:
            st.info(f"Showing first 10 of {len(successful)} products")

# Sidebar
with st.sidebar:
    st.header("ℹ️ Instructions")
    st.markdown("""
    ### How to use:
    1. **Add URLs** - Tab 1
    2. **Extract Info** - Tab 2
    3. **Export Data** - Tab 3
    
    ### Export Formats:
    - **Complete CSV**: All extracted data
    - **Excel**: Multi-sheet workbook
    - **Gomag CSV**: Ready for import
    - **JSON**: Raw data backup
    
    ### Tips:
    - Files download directly to browser
    - CSV uses UTF-8 with BOM
    - Excel has separate sheets
    - Gomag CSV uses semicolons
    """)
    
    st.divider()
    
    if st.button("🗑️ Clear All Data"):
        st.session_state.products = []
        st.rerun()
