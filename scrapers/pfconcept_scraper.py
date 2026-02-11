import re
from typing import Optional
from .base_scraper import BaseScraper, Product, ProductVariant
import logging

logger = logging.getLogger(__name__)

class PFConceptScraper(BaseScraper):
    def can_handle(self, url: str) -> bool:
        return 'pfconcept.com' in url
    
    def scrape(self, url: str) -> Optional[Product]:
        soup = self.fetch_page(url, use_cloudscraper=True)
        if not soup:
            return None
        
        product = Product(url=url)
        
        try:
            # Extract product name
            name_elem = soup.select_one('h1.product-name, .product-title h1')
            if name_elem:
                product.name = name_elem.get_text(strip=True)
            
            # Extract SKU from URL
            match = re.search(r'(\d{6})', url)
            if match:
                product.sku = match.group(1)
            
            # Extract description
            desc_elem = soup.select_one('.product-description, .description-content')
            if desc_elem:
                product.description = desc_elem.get_text(strip=True)
            
            # Extract features
            features = soup.select('.product-features li, .feature-list li')
            product.features = [f.get_text(strip=True) for f in features]
            
            # Extract specifications
            spec_table = soup.select('.specifications-table tr, .product-specs tr')
            for row in spec_table:
                cells = row.select('td')
                if len(cells) >= 2:
                    key = cells[0].get_text(strip=True)
                    value = cells[1].get_text(strip=True)
                    product.specifications[key] = value
            
            # Extract images
            gallery = soup.select('.product-gallery img, .gallery-image img')
            for img in gallery:
                src = img.get('src') or img.get('data-src')
                if src:
                    if not src.startswith('http'):
                        src = 'https://www.pfconcept.com' + src
                    product.images.append(src)
            
            # Extract color variants
            colors = soup.select('.color-selector .color-item, .variant-color')
            for color in colors:
                variant = ProductVariant()
                variant.color = color.get('title') or color.get('data-color', '')
                variant.color_code = color.get('data-color-code', '')
                product.variants.append(variant)
            
            product.brand = "PF Concept"
            
            logger.info(f"Successfully scraped: {product.name}")
            return product
            
        except Exception as e:
            logger.error(f"Error parsing PF Concept product: {e}")
            return None
