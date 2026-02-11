from typing import Optional
from .base_scraper import BaseScraper, Product
import logging

logger = logging.getLogger(__name__)

class ClipperScraper(BaseScraper):
    def can_handle(self, url: str) -> bool:
        return 'clipperinterall.com' in url
    
    def scrape(self, url: str) -> Optional[Product]:
        soup = self.fetch_page(url)
        if not soup:
            return None
        
        product = Product(url=url)
        
        try:
            name = soup.select_one('h1, .product-name')
            if name:
                product.name = name.get_text(strip=True)
            
            sku = soup.select_one('.product-sku, .sku')
            if sku:
                product.sku = sku.get_text(strip=True)
            
            desc = soup.select_one('.product-description')
            if desc:
                product.description = desc.get_text(strip=True)
            
            for img in soup.select('.product-images img'):
                src = img.get('src') or img.get('data-src')
                if src:
                    if not src.startswith('http'):
                        src = 'https://www.clipperinterall.com' + src
                    product.images.append(src)
            
            product.brand = "Clipper"
            return product
            
        except Exception as e:
            logger.error(f"Error parsing Clipper: {e}")
            return None
