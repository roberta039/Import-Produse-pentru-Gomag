import requests
from bs4 import BeautifulSoup
import re
import json
from typing import Dict

class UniversalScraper:
    """Scraper universal pentru orice site"""
    
    def extract(self, url: str) -> Dict:
        """Extrage informații produs din URL"""
        try:
            response = requests.get(url, timeout=10, headers={
                'User-Agent': 'Mozilla/5.0'
            })
            soup = BeautifulSoup(response.content, 'html.parser')
            
            product = {
                'name': self._extract_name(soup, url),
                'sku': self._extract_sku(soup, url),
                'price': self._extract_price(soup),
                'description': self._extract_description(soup),
                'images': self._extract_images(soup, url),
                'brand': self._extract_brand(soup, url),
                'currency': 'EUR'
            }
            
            return product
            
        except Exception as e:
            return {
                'error': str(e),
                'status': 'error'
            }
    
    def _extract_name(self, soup, url):
        # Încearcă mai multe metode
        h1 = soup.find('h1')
        if h1:
            return h1.get_text(strip=True)
        
        og_title = soup.find('meta', property='og:title')
        if og_title:
            return og_title.get('content', '')
        
        title = soup.find('title')
        if title:
            return title.get_text(strip=True).split('|')[0].strip()
        
        return f"Product from {url.split('/')[2]}"
    
    def _extract_sku(self, soup, url):
        # Din URL
        patterns = [
            r'[pP](\d{3}\.\d{2,3})',
            r'/(\w+)$',
            r'product[/_]([A-Z0-9]+)',
            r'sku=([^&]+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1).upper()
        
        return f"WEB{hash(url) % 1000000}"
    
    def _extract_price(self, soup):
        # Caută preț în pagină
        price_patterns = [
            r'[€$]\s*(\d+[.,]\d{2})',
            r'(\d+[.,]\d{2})\s*[€$]'
        ]
        
        text = soup.get_text()
        for pattern in price_patterns:
            match = re.search(pattern, text)
            if match:
                return float(match.group(1).replace(',', '.'))
        
        return 0
    
    def _extract_description(self, soup):
        desc = soup.find('meta', {'name': 'description'})
        if desc:
            return desc.get('content', '')
        
        desc_div = soup.find(class_=re.compile('description', re.I))
        if desc_div:
            return desc_div.get_text(strip=True)[:1000]
        
        return ""
    
    def _extract_images(self, soup, url):
        images = []
        
        # OpenGraph
        og_img = soup.find('meta', property='og:image')
        if og_img:
            images.append(og_img.get('content'))
        
        # Product images
        for img in soup.find_all('img')[:10]:
            src = img.get('src') or img.get('data-src')
            if src and 'product' in src.lower():
                if not src.startswith('http'):
                    base = '/'.join(url.split('/')[:3])
                    src = base + src if src.startswith('/') else base + '/' + src
                images.append(src)
        
        return images[:5]
    
    def _extract_brand(self, soup, url):
        domain = url.split('/')[2].lower()
        
        brand_map = {
            'xdconnects': 'XD Design',
            'pfconcept': 'PF Concept',
            'midocean': 'Midocean'
        }
        
        for key, value in brand_map.items():
            if key in domain:
                return value
        
        return domain.split('.')[0].title()
