import re
from typing import Optional
from .base_scraper import BaseScraper, Product
import logging

logger = logging.getLogger(__name__)

class StaminaScraper(BaseScraper):
    def can_handle(self, url: str) -> bool:
        return 'stamina-shop.eu' in url
    
    def scrape(self, url: str) -> Optional[Product]:
        soup = self.fetch_page(url)
        if not soup:
            return None
        
        product = Product(url=url)
        
        try:
            name = soup.select_one('h1, .product-name')
            if name:
                product.name = name.get_text(strip=True)
            
            match = re.search(r'model_(\w+)', url)
            if match:
                product.sku = match.group(1)
            
            desc = soup.select_one('.description, .product-description')
            if desc:
                product.description = desc.get_text(strip=True)
            
            for img in soup.select('.product-image img, .gallery img'):
                src = img.get('src') or img.get('data-src')
                if src:
                    if not src.startswith('http'):
                        src = 'https://stamina-shop.eu' + src
                    product.images.append(src)
            
            product.brand = "Stamina"
            return product
            
        except Exception as e:
            logger.error(f"Error parsing Stamina: {e}")
            return None
