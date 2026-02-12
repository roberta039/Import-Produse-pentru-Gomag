"""
Scraper pentru promobox.com
"""

import re
import json
from typing import Optional
import logging

from .base_scraper import BaseScraper
from config import ProductData

logger = logging.getLogger(__name__)

class PromoboxScraper(BaseScraper):
    """Scraper pentru Promobox"""
    
    def get_site_domain(self) -> str:
        return "promobox.com"
    
    def scrape_product(self, url: str) -> Optional[ProductData]:
        """Scrapează un produs de pe Promobox"""
        logger.info(f"Scraping Promobox: {url}")
        
        soup = self._get_page(url)
        if not soup:
            return None
        
        product = ProductData(source_url=url)
        
        try:
            # SKU din URL
            match = re.search(r'/products/([A-Z0-9_-]+)', url, re.IGNORECASE)
            if match:
                product.sku = match.group(1)
            
            # Nume produs
            name_elem = soup.select_one('h1.product-title, .product-name, h1')
            if name_elem:
                product.name = self._clean_text(name_elem.text)
            
            # Descriere
            desc_elem = soup.select_one('.product-description, .description, .product-details')
            if desc_elem:
                product.description = self._clean_text(desc_elem.get_text(separator=' '))
            
            # Specificații
            specs_container = soup.select_one('.specifications, .product-specs, .technical-details')
            if specs_container:
                for item in specs_container.select('li, tr, .spec-item'):
                    text = item.text
                    if ':' in text:
                        parts = text.split(':', 1)
                        key = self._clean_text(parts[0])
                        value = self._clean_text(parts[1])
                        if key and value:
                            product.specifications[key] = value
            
            # Imagini
            images = []
            for img in soup.select('.product-image img, .gallery img, .product-gallery img'):
                img_url = img.get('data-src') or img.get('data-zoom') or img.get('src')
                if img_url:
                    img_url = self._make_absolute_url(img_url, url)
                    if img_url not in images and 'placeholder' not in img_url.lower():
                        images.append(img_url)
            product.images = images
            
            # Culori - din parametrul URL sau din pagină
            color_match = re.search(r'color=(\d+)', url)
            if color_match:
                product.extra_data['color_code'] = color_match.group(1)
            
            colors = []
            for color_elem in soup.select('.color-options a, .color-swatches .swatch, [data-color]'):
                color_name = color_elem.get('title') or color_elem.get('data-color-name')
                color_code = color_elem.get('data-color') or color_elem.get('href', '').split('=')[-1]
                if color_name:
                    colors.append({
                        'name': self._clean_text(color_name),
                        'code': color_code
                    })
            product.colors = colors
            
            # Preț
            price_elem = soup.select_one('.price, .product-price, [data-price]')
            if price_elem:
                product.price = self._extract_price(price_elem.text)
            
            # Brand
            brand_elem = soup.select_one('.brand, .product-brand')
            if brand_elem:
                product.brand = self._clean_text(brand_elem.text)
            
            # Dimensiuni
            for key, value in product.specifications.items():
                if 'dimension' in key.lower() or 'size' in key.lower():
                    match = re.search(r'(\d+(?:\.\d+)?)\s*[xX×]\s*(\d+(?:\.\d+)?)\s*[xX×]?\s*(\d+(?:\.\d+)?)?', value)
                    if match:
                        product.dimensions = {
                            'width': float(match.group(1)),
                            'height': float(match.group(2)),
                            'depth': float(match.group(3)) if match.group(3) else 0
                        }
            
            logger.info(f"Successfully scraped: {product.name}")
            return product
            
        except Exception as e:
            logger.error(f"Error scraping {url}: {e}")
            return None
