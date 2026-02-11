import re
from typing import Optional
from .base_scraper import BaseScraper, Product, ProductVariant
import logging

logger = logging.getLogger(__name__)

class PromoboxScraper(BaseScraper):
    def can_handle(self, url: str) -> bool:
        return 'promobox.com' in url
    
    def scrape(self, url: str) -> Optional[Product]:
        soup = self.fetch_page(url)
        if not soup:
            return None
        
        product = Product(url=url)
        
        try:
            # Extract product name
            name_elem = soup.select_one('h1, .product-name')
            if name_elem:
                product.name = name_elem.get_text(strip=True)
            
            # Extract SKU from URL
            match = re.search(r'/products/([^?]+)', url)
            if match:
                product.sku = match.group(1)
            
            # Description
            desc = soup.select_one('.product-description, .description')
            if desc:
                product.description = desc.get_text(strip=True)
            
            # Images
            for img in soup.select('.product-image img, .gallery img'):
                src = img.get('src') or img.get('data-src')
                if src:
                    if not src.startswith('http'):
                        src = 'https://promobox.com' + src
                    product.images.append(src)
            
            # Specifications
            for row in soup.select('.specs tr, .specifications li'):
                text = row.get_text(strip=True)
                if ':' in text:
                    parts = text.split(':', 1)
                    product.specifications[parts[0].strip()] = parts[1].strip()
            
            product.brand = "Promobox"
            return product
            
        except Exception as e:
            logger.error(f"Error parsing Promobox: {e}")
            return None
