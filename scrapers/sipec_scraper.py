import re
from typing import Optional
from .base_scraper import BaseScraper, Product
import logging

logger = logging.getLogger(__name__)

class SipecScraper(BaseScraper):
    def can_handle(self, url: str) -> bool:
        return 'sipec.com' in url
    
    def scrape(self, url: str) -> Optional[Product]:
        soup = self.fetch_page(url)
        if not soup:
            return None
        
        product = Product(url=url)
        
        try:
            name = soup.select_one('h1, .product-name')
            if name:
                product.name = name.get_text(strip=True)
            
            # Extract SKU from URL
            match = re.search(r'/p/(\w+)/', url)
            if match:
                product.sku = match.group(1)
            
            desc = soup.select_one('.product-description')
            if desc:
                product.description = desc.get_text(strip=True)
            
            for img in soup.select('.product-image img'):
                src = img.get('src') or img.get('data-src')
                if src:
                    if not src.startswith('http'):
                        src = 'https://www.sipec.com' + src
                    product.images.append(src)
            
            product.brand = "Sipec"
            return product
            
        except Exception as e:
            logger.error(f"Error parsing Sipec: {e}")
            return None
