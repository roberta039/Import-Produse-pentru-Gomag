import re
from typing import Optional
from .base_scraper import BaseScraper, Product
import logging

logger = logging.getLogger(__name__)

class PSIScraper(BaseScraper):
    def can_handle(self, url: str) -> bool:
        return 'psiproductfinder.de' in url
    
    def scrape(self, url: str) -> Optional[Product]:
        soup = self.fetch_page(url, use_cloudscraper=True)
        if not soup:
            return None
        
        product = Product(url=url)
        
        try:
            name = soup.select_one('h1, .product-title')
            if name:
                product.name = name.get_text(strip=True)
            
            match = re.search(r'/product/p-([^/]+)', url)
            if match:
                product.sku = match.group(1)
            
            desc = soup.select_one('.product-description, .description')
            if desc:
                product.description = desc.get_text(strip=True)
            
            for img in soup.select('.product-image img, .gallery img'):
                src = img.get('src') or img.get('data-src')
                if src:
                    if not src.startswith('http'):
                        src = 'https://psiproductfinder.de' + src
                    product.images.append(src)
            
            product.brand = "PSI"
            return product
            
        except Exception as e:
            logger.error(f"Error parsing PSI: {e}")
            return None
