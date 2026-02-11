import re
from typing import Optional
from .base_scraper import BaseScraper, Product, ProductVariant
import logging

logger = logging.getLogger(__name__)

class AndaPresentScraper(BaseScraper):
    def can_handle(self, url: str) -> bool:
        return 'andapresent.com' in url
    
    def scrape(self, url: str) -> Optional[Product]:
        soup = self.fetch_page(url)
        if not soup:
            return None
        
        product = Product(url=url)
        
        try:
            name_elem = soup.select_one('h1.product-title, h1')
            if name_elem:
                product.name = name_elem.get_text(strip=True)
            
            # SKU from URL
            match = re.search(r'products/(AP\d+-\d+)', url)
            if match:
                product.sku = match.group(1)
            
            desc = soup.select_one('.product-description')
            if desc:
                product.description = desc.get_text(strip=True)
            
            for img in soup.select('.product-gallery img'):
                src = img.get('src') or img.get('data-src')
                if src and src.startswith('http'):
                    product.images.append(src)
            
            product.brand = "Anda Present"
            return product
            
        except Exception as e:
            logger.error(f"Error parsing Anda Present: {e}")
            return None
