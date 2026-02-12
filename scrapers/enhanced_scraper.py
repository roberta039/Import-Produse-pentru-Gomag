import requests
from bs4 import BeautifulSoup
import cloudscraper
import re
import json
import logging
from typing import Dict, Optional
import urllib3

urllib3.disable_warnings()
logger = logging.getLogger(__name__)

class EnhancedScraper:
    """Enhanced scraper with multiple strategies"""
    
    def __init__(self):
        self.session = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'windows',
                'desktop': True
            }
        )
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Cache-Control': 'max-age=0',
        }
    
    def extract_xdconnects(self, url: str, soup: BeautifulSoup) -> Dict:
        """Special handling for XD Connects"""
        product = {'url': url, 'status': 'success'}
        
        # Extract from URL
        sku_match = re.search(r'([pP]\d{3}\.\d{2,3})', url)
        if sku_match:
            product['sku'] = sku_match.group(1).upper()
        
        # Try JSON-LD structured data
        scripts = soup.find_all('script', type='application/ld+json')
        for script in scripts:
            try:
                data = json.loads(script.string)
                if '@type' in data and data['@type'] == 'Product':
                    product['name'] = data.get('name', '')
                    product['description'] = data.get('description', '')
                    product['brand'] = data.get('brand', {}).get('name', 'XD Design')
                    if 'offers' in data:
                        product['price'] = float(data['offers'].get('price', 0))
                        product['currency'] = data['offers'].get('priceCurrency', 'EUR')
                    if 'image' in data:
                        product['images'] = data['image'] if isinstance(data['image'], list) else [data['image']]
                    break
            except:
                continue
        
        # Fallback extraction
        if 'name' not in product:
            # Try meta tags
            meta_title = soup.find('meta', property='og:title')
            if meta_title:
                product['name'] = meta_title.get('content', '').strip()
            else:
                h1 = soup.find('h1')
                if h1:
                    product['name'] = h1.get_text(strip=True)
        
        if 'price' not in product:
            # Look for price in text
            price_patterns = [
                r'€\s*([\d,\.]+)',
                r'EUR\s*([\d,\.]+)',
                r'Price[:\s]*([\d,\.]+)',
            ]
            text = soup.get_text()
            for pattern in price_patterns:
                match = re.search(pattern, text)
                if match:
                    try:
                        product['price'] = float(match.group(1).replace(',', '.'))
                        break
                    except:
                        continue
        
        if 'images' not in product:
            product['images'] = []
            # Get images from meta tags
            meta_image = soup.find('meta', property='og:image')
            if meta_image:
                img_url = meta_image.get('content')
                if img_url:
                    product['images'].append(img_url)
        
        # Set defaults
        product.setdefault('name', f"XD Design {product.get('sku', 'Product')}")
        product.setdefault('brand', 'XD Design')
        product.setdefault('price', 0)
        product.setdefault('currency', 'EUR')
        product.setdefault('description', '')
        product.setdefault('images', [])
        
        return product
    
    def extract_pfconcept(self, url: str, soup: BeautifulSoup) -> Dict:
        """Special handling for PF Concept"""
        product = {'url': url, 'status': 'success'}
        
        # Extract SKU from URL
        sku_match = re.search(r'(\d{6})', url)
        if sku_match:
            product['sku'] = sku_match.group(1)
        
        # Name
        h1 = soup.find('h1', class_=re.compile('product', re.I))
        if h1:
            product['name'] = h1.get_text(strip=True)
        
        # Price
        price_elem = soup.find(class_=re.compile('price', re.I))
        if price_elem:
            price_text = price_elem.get_text()
            numbers = re.findall(r'[\d,\.]+', price_text)
            if numbers:
                try:
                    product['price'] = float(numbers[0].replace(',', '.'))
                except:
                    product['price'] = 0
        
        # Images
        images = []
        for img in soup.find_all('img', src=re.compile('product|image', re.I))[:5]:
            src = img.get('src') or img.get('data-src')
            if src:
                if not src.startswith('http'):
                    src = 'https://www.pfconcept.com' + src
                images.append(src)
        product['images'] = images
        
        # Description
        desc = soup.find(class_=re.compile('description', re.I))
        if desc:
            product['description'] = desc.get_text(strip=True)[:1000]
        
        product.setdefault('brand', 'PF Concept')
        product.setdefault('currency', 'EUR')
        
        return product
    
    def extract_midocean(self, url: str, soup: BeautifulSoup) -> Dict:
        """Special handling for Midocean"""
        product = {'url': url, 'status': 'success'}
        
        # SKU from URL
        sku_match = re.search(r'(mo\d{4}-\d{2})', url, re.I)
        if sku_match:
            product['sku'] = sku_match.group(1).upper()
        
        # Try to get from page data
        scripts = soup.find_all('script')
        for script in scripts:
            if script.string and 'productData' in script.string:
                try:
                    # Extract JSON from script
                    json_match = re.search(r'productData\s*=\s*({[^}]+})', script.string)
                    if json_match:
                        data = json.loads(json_match.group(1))
                        product['name'] = data.get('name', '')
                        product['price'] = float(data.get('price', 0))
                        product['sku'] = data.get('sku', product.get('sku', ''))
                except:
                    continue
        
        # Fallback extraction
        if 'name' not in product:
            h1 = soup.find('h1')
            if h1:
                product['name'] = h1.get_text(strip=True)
        
        # Images
        images = []
        for img in soup.find_all('img')[:10]:
            src = img.get('src') or img.get('data-src')
            if src and 'product' in src.lower():
                if not src.startswith('http'):
                    src = 'https://www.midocean.com' + src
                images.append(src)
        product['images'] = images[:5]
        
        product.setdefault('brand', 'Midocean')
        product.setdefault('price', 0)
        product.setdefault('currency', 'EUR')
        
        return product
    
    def extract_product(self, url: str) -> Dict:
        """Main extraction method"""
        try:
            # Get the page
            response = self.session.get(url, headers=self.headers, timeout=20)
            response.raise_for_status()
            
            # Parse HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Determine site and use appropriate extractor
            domain = url.split('/')[2].lower()
            
            if 'xdconnects' in domain:
                return self.extract_xdconnects(url, soup)
            elif 'pfconcept' in domain:
                return self.extract_pfconcept(url, soup)
            elif 'midocean' in domain:
                return self.extract_midocean(url, soup)
            else:
                # Generic extraction
                return self.extract_generic(url, soup)
                
        except Exception as e:
            logger.error(f"Error extracting {url}: {e}")
            return {
                'url': url,
                'status': 'error',
                'error': str(e),
                'name': f"Failed: {url.split('/')[2]}",
                'sku': f"ERR_{hash(url) % 100000}",
                'price': 0,
                'images': []
            }
    
    def extract_generic(self, url: str, soup: BeautifulSoup) -> Dict:
        """Generic extraction for any site"""
        product = {'url': url, 'status': 'success'}
        
        # Name - try multiple methods
        name = None
        
        # Method 1: OpenGraph
        og_title = soup.find('meta', property='og:title')
        if og_title:
            name = og_title.get('content', '')
        
        # Method 2: H1
        if not name:
            h1 = soup.find('h1')
            if h1:
                name = h1.get_text(strip=True)
        
        # Method 3: Title tag
        if not name:
            title = soup.find('title')
            if title:
                name = title.get_text(strip=True).split('|')[0].split('-')[0].strip()
        
        product['name'] = name or f"Product from {url.split('/')[2]}"
        
        # Price - look for any number with currency
        price_text = soup.get_text()
        price_patterns = [
            r'[€£$]\s*([\d,\.]+)',
            r'([\d,\.]+)\s*[€£$]',
            r'Price[:\s]+([\d,\.]+)',
        ]
        
        for pattern in price_patterns:
            matches = re.findall(pattern, price_text)
            if matches:
                try:
                    # Get the first reasonable price (between 1 and 10000)
                    for match in matches:
                        price = float(match.replace(',', '.'))
                        if 1 <= price <= 10000:
                            product['price'] = price
                            break
                    if 'price' in product:
                        break
                except:
                    continue
        
        if 'price' not in product:
            product['price'] = 0
        
        # Images
        images = []
        
        # OpenGraph image
        og_image = soup.find('meta', property='og:image')
        if og_image:
            img_url = og_image.get('content')
            if img_url:
                if not img_url.startswith('http'):
                    img_url = url.split('/')[0] + '//' + url.split('/')[2] + img_url
                images.append(img_url)
        
        # Product images
        for img in soup.find_all('img')[:20]:
            src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
            if src:
                # Filter product images
                if any(keyword in src.lower() for keyword in ['product', 'item', 'article', 'cdn']):
                    if not src.startswith('http'):
                        if src.startswith('//'):
                            src = 'https:' + src
                        elif src.startswith('/'):
                            src = url.split('/')[0] + '//' + url.split('/')[2] + src
                    if src not in images:
                        images.append(src)
        
        product['images'] = images[:5]
        
        # Description
        desc = soup.find('meta', property='og:description')
        if desc:
            product['description'] = desc.get('content', '')[:1000]
        else:
            product['description'] = ''
        
        # SKU from URL
        sku_patterns = [
            r'/([A-Z0-9]{4,})',
            r'[/-]([A-Z]{2,}\d{3,})',
            r'product[/_]([A-Z0-9]+)',
            r'sku=([A-Z0-9]+)',
            r'id=([A-Z0-9]+)'
        ]
        
        for pattern in sku_patterns:
            match = re.search(pattern, url, re.I)
            if match:
                product['sku'] = match.group(1).upper()
                break
        
        if 'sku' not in product:
            product['sku'] = f"WEB{hash(url) % 1000000}"
        
        # Brand from domain
        domain = url.split('/')[2]
        product['brand'] = domain.split('.')[0].title()
        
        product['currency'] = 'EUR'
        
        return product
