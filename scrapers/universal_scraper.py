import requests
from bs4 import BeautifulSoup
import re
import json
import logging
from typing import Dict, List, Optional
import urllib3

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

class UniversalScraper:
    """Universal scraper that actually works"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
        })
    
    def extract_product(self, url: str) -> Dict:
        """Extract complete product information"""
        try:
            # Get the page
            response = self.session.get(url, timeout=15, verify=False)
            response.raise_for_status()
            
            # Parse HTML
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Remove script and style elements
            for script in soup(["script", "style"]):
                script.decompose()
            
            product = {
                'url': url,
                'status': 'success'
            }
            
            # === EXTRACT NAME ===
            name = None
            name_selectors = [
                'h1.product-title',
                'h1.product-name', 
                'h1[itemprop="name"]',
                'h1[data-testid="product-title"]',
                'h1.pdp-title',
                'h1.product__title',
                '.product-title h1',
                '.product-name h1',
                'h1'
            ]
            
            for selector in name_selectors:
                elem = soup.select_one(selector)
                if elem and elem.get_text(strip=True):
                    name = elem.get_text(strip=True)
                    # Clean the name
                    name = re.sub(r'\s+', ' ', name)
                    name = name.replace('\n', ' ').replace('\r', '')
                    if len(name) > 10 and len(name) < 300:  # Valid name length
                        product['name'] = name
                        break
            
            if 'name' not in product:
                # Try meta tags
                meta_title = soup.find('meta', {'property': 'og:title'})
                if meta_title:
                    product['name'] = meta_title.get('content', '').strip()
                else:
                    product['name'] = soup.title.string if soup.title else f"Product from {url.split('/')[2]}"
            
            # === EXTRACT SKU ===
            sku = None
            
            # Method 1: Look for SKU in page
            sku_patterns = [
                r'SKU[:\s]+([A-Z0-9\-]+)',
                r'Item[:\s]+([A-Z0-9\-]+)',
                r'Model[:\s]+([A-Z0-9\-]+)',
                r'Product Code[:\s]+([A-Z0-9\-]+)',
                r'Reference[:\s]+([A-Z0-9\-]+)'
            ]
            
            page_text = soup.get_text()
            for pattern in sku_patterns:
                match = re.search(pattern, page_text, re.IGNORECASE)
                if match:
                    sku = match.group(1).strip()
                    break
            
            # Method 2: Extract from URL
            if not sku:
                url_patterns = [
                    r'/([pP]\d{3}\.\d{2,3})',  # XD Connects format
                    r'/products/([A-Z0-9\-]+)',
                    r'/([A-Z]{2}\d{4,})',
                    r'[/-]([A-Z0-9]{5,})[/?]',
                    r'sku=([A-Z0-9\-]+)',
                    r'id=([A-Z0-9\-]+)'
                ]
                
                for pattern in url_patterns:
                    match = re.search(pattern, url)
                    if match:
                        sku = match.group(1).upper()
                        break
            
            # Method 3: Look in structured data
            if not sku:
                sku_elem = soup.select_one('[itemprop="sku"], .product-sku, .sku-value, [data-sku]')
                if sku_elem:
                    sku = sku_elem.get_text(strip=True) or sku_elem.get('data-sku', '')
                    sku = re.sub(r'SKU[:\s]+', '', sku, flags=re.IGNORECASE).strip()
            
            product['sku'] = sku if sku else f"WEB{hash(url) % 1000000}"
            
            # === EXTRACT PRICE ===
            price = None
            price_selectors = [
                '[itemprop="price"]',
                '.product-price',
                '.price-now',
                '.price-value',
                '.product-price-value',
                '[data-price]',
                '.price',
                '.amount',
                '.cost'
            ]
            
            for selector in price_selectors:
                elem = soup.select_one(selector)
                if elem:
                    # Try to get price from attributes first
                    price_str = elem.get('content') or elem.get('data-price') or elem.get_text(strip=True)
                    
                    # Extract numbers
                    numbers = re.findall(r'[\d,\.]+', price_str)
                    if numbers:
                        try:
                            # Get the largest number (usually the price)
                            price = max([float(n.replace(',', '.')) for n in numbers])
                            if price > 0 and price < 100000:  # Reasonable price range
                                product['price'] = price
                                break
                        except:
                            continue
            
            # Try meta tags for price
            if 'price' not in product:
                price_meta = soup.find('meta', {'property': 'product:price:amount'})
                if price_meta:
                    try:
                        product['price'] = float(price_meta.get('content', '0'))
                    except:
                        pass
            
            if 'price' not in product:
                product['price'] = 0
            
            # Extract currency
            currency_elem = soup.find('meta', {'property': 'product:price:currency'})
            product['currency'] = currency_elem.get('content', 'EUR') if currency_elem else 'EUR'
            
            # === EXTRACT DESCRIPTION ===
            description = ""
            desc_selectors = [
                '[itemprop="description"]',
                '.product-description',
                '.description-content',
                '.product-details',
                '.pdp-description',
                '#product-description',
                '.product__description'
            ]
            
            for selector in desc_selectors:
                elem = soup.select_one(selector)
                if elem:
                    # Get all text from description area
                    desc_parts = []
                    for p in elem.find_all(['p', 'div', 'span']):
                        text = p.get_text(strip=True)
                        if text and len(text) > 20:
                            desc_parts.append(text)
                    
                    if desc_parts:
                        description = ' '.join(desc_parts)
                        break
            
            if not description:
                # Try meta description
                meta_desc = soup.find('meta', {'property': 'og:description'}) or soup.find('meta', {'name': 'description'})
                if meta_desc:
                    description = meta_desc.get('content', '')
            
            product['description'] = description[:2000] if description else ""
            
            # === EXTRACT IMAGES ===
            images = []
            
            # Method 1: Product specific images
            img_selectors = [
                '.product-image img',
                '.product-gallery img',
                '.gallery-image img',
                '[itemprop="image"]',
                '.product-photo img',
                '.pdp-image img',
                '[data-zoom-image]'
            ]
            
            for selector in img_selectors:
                imgs = soup.select(selector)
                for img in imgs:
                    src = (img.get('src') or img.get('data-src') or 
                          img.get('data-lazy-src') or img.get('data-zoom-image') or
                          img.get('data-large-image'))
                    
                    if src and 'placeholder' not in src.lower():
                        # Make URL absolute
                        if src.startswith('//'):
                            src = 'https:' + src
                        elif src.startswith('/'):
                            base_url = '/'.join(url.split('/')[:3])
                            src = base_url + src
                        
                        if src.startswith('http') and src not in images:
                            images.append(src)
            
            # Method 2: Meta images
            if not images:
                meta_image = soup.find('meta', {'property': 'og:image'})
                if meta_image:
                    img_url = meta_image.get('content')
                    if img_url:
                        if img_url.startswith('//'):
                            img_url = 'https:' + img_url
                        images.append(img_url)
            
            product['images'] = images[:10]  # Limit to 10 images
            
            # === EXTRACT BRAND ===
            brand = None
            
            # Try structured data
            brand_elem = soup.select_one('[itemprop="brand"], .product-brand, .brand-name')
            if brand_elem:
                brand = brand_elem.get_text(strip=True)
            
            # Try from domain
            if not brand:
                domain = url.split('/')[2].lower()
                brand_map = {
                    'xdconnects': 'XD Design',
                    'pfconcept': 'PF Concept',
                    'midocean': 'Midocean',
                    'promobox': 'Promobox',
                    'andapresent': 'Anda Present',
                    'stamina': 'Stamina',
                    'utteam': 'UT Team',
                    'sipec': 'Sipec',
                    'stricker': 'Stricker',
                    'clipper': 'Clipper'
                }
                
                for key, value in brand_map.items():
                    if key in domain:
                        brand = value
                        break
            
            product['brand'] = brand if brand else url.split('/')[2].split('.')[0].title()
            
            # === EXTRACT FEATURES ===
            features = []
            feature_selectors = [
                '.product-features li',
                '.features-list li',
                
