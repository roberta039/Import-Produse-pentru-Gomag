"""
Scraper pentru andapresent.com
"""

import re
from typing import Optional
import logging

from .base_scraper import BaseScraper
from config import ProductData

logger = logging.getLogger(__name__)

class AndaPresentScraper(BaseScraper):
    """Scraper pentru AndaPresent"""
    
    def get_site_domain(self) -> str:
        return "andapresent.com"
    
    def scrape_product(self, url: str) -> Optional[ProductData]:
        """Scrapează un produs de pe AndaPresent"""
        logger.info(f"Scraping AndaPresent: {url}")
        
        soup = self._get_page(url)
        if not soup:
            return None
        
        product = ProductData(source_url=url)
        
        try:
            # SKU din URL (format: AP721326-10)
            match = re.search(r'/products/(AP\d+-\d+)', url, re.IGNORECASE)
            if match:
                product.sku = match.group(1)
            
            # Nume produs
            name_elem = soup.select_one('h1, .product-title, .product-name')
            if name_elem:
                product.name = self._clean_text(name_elem.text)
            
            # Descriere
            desc_elem = soup.select_one('.product-description, .description, #description')
            if desc_elem:
                product.description = self._clean_text(desc_elem.get_text(separator=' '))
            
            # Specificații
            specs = soup.select('.product-attributes tr, .specifications li, .product-info-table tr')
            for spec in specs:
                cells = spec.select('td, th')
                if len(cells) >= 2:
                    key = self._clean_text(cells[0].text)
                    value = self._clean_text(cells[1].text)
                    if key and value:
                        product.specifications[key] = value
            
            # Imagini
            images = []
            for img in soup.select('.product-images img, .gallery-image img, .product-gallery img'):
                img_url = img.get('data-zoom-image') or img.get('data-large') or img.get('src')
                if img_url:
                    img_url = self._make_absolute_url(img_url, url)
                    if img_url not in images:
                        images.append(img_url)
            product.images = images
            
            # Culori
            colors = []
            for color in soup.select('.color-selector .color, .variant-colors a'):
                color_name = color.get('title') or color.get('data-color')
                if color_name:
                    colors.append({'name': self._clean_text(color_name)})
            product.colors = colors
            
            # Preț
            price_elem = soup.select_one('.price, .product-price')
            if price_elem:
                product.price = self._extract_price(price_elem.text)
            
            logger.info(f"Successfully scraped: {product.name}")
            return product
            
        except Exception as e:
            logger.error(f"Error scraping {url}: {e}")
            return None
