import re
from typing import Optional
from .base_scraper import BaseScraper, Product
import logging

logger = logging.getLogger(__name__)

class UTTeamScraper(BaseScraper):
    def can_handle(self, url: str) -> bool:
        return 'utteam.com' in url
    
    def scrape(self, url: str) -> Optional[Product]:
        soup = self.fetch_page(url)
        if not soup:
            return None
        
        product = Product(url=url)
        
        try:
            name = soup.select_one('h1, .product-title')
            if name:
                product.name = name.get_text(strip=True)
            
            match = re.search(r'product/(\w+)', url, re.IGNORECASE)
            if match:
                product.sku = match.group(1).upper()
            
            desc = soup.select_one('.product-description, .description')
            if desc:
                product.description = desc.get_text(strip=True)
            
            for img in soup.select('.product-images img, .gallery img'):
                src = img.get('src') or img.get('data-src')
                if src:
                    if not src.startswith('http'):
                        src = 'https://utteam.com' + src
                    product.images.append(src)
            
            product.brand = "UT Team"
            return product
            
        except Exception as e:
            logger.error(f"Error parsing UT Team: {e}")
            return None
