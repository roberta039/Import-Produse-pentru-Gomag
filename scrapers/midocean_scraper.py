import re
from typing import Optional
from .base_scraper import BaseScraper, Product, ProductVariant
import logging

logger = logging.getLogger(__name__)

class MidoceanScraper(BaseScraper):
    def can_handle(self, url: str) -> bool:
        return 'midocean.com' in url
    
    def scrape(self, url: str) -> Optional[Product]:
        soup = self.fetch_page(url, use_cloudscraper=True)
        if not soup:
            return None
        
        product = Product(url=url)
        
        try:
            # Extract product name
            name_elem = soup.select_one('h1.product-name, .pdp-title')
            if name_elem:
                product.name = name_elem.get_text(strip=True)
            
            # Extract SKU
            sku_elem = soup.select_one('.product-sku, .sku-number')
            if sku_elem:
                product.sku = sku_elem.get_text(strip=True)
            else:
                match = re.search(r'mo\d{4}-\d{2}', url, re.IGNORECASE)
                if match:
                    product.sku = match.group().upper()
            
            # Extract description
            desc_elem = soup.select_one('.product-description, .pdp-description')
            if desc_elem:
                product.description = desc_elem.get_text(strip=True)
            
            # Extract specifications
            specs = soup.select('.specifications-list li, .spec-item')
            for spec in specs:
                text = spec.get_text(strip=True)
                if ':' in text:
                    parts = text.split(':', 1)
                    product.specifications[parts[0].strip()] = parts[1].strip()
            
            # Extract images
            images = soup.select('.product-gallery img, .pdp-gallery img')
            for img in images:
                src = img.get('src') or img.get('data-src')
                if src:
                    if not src.startswith('http'):
                        src = 'https://www.midocean.com' + src
                    # Get high-res version
                    src = re.sub(r'_\d+x\d+', '', src)
                    product.images.append(src)
            
            # Extract variants
            color_options = soup.select('.color-selector .color-option')
            for opt in color_options:
                variant = ProductVariant()
                variant.color = opt.get('title', '')
                variant.color_code = opt.get('data-color-id', '')
                product.variants.append(variant)
            
            product.brand = "Midocean"
            
            logger.info(f"Successfully scraped: {product.name}")
            return product
            
        except Exception as e:
            logger.error(f"Error parsing Midocean product: {e}")
            return None
