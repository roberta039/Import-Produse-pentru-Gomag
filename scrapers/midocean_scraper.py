"""
Scraper pentru midocean.com
"""

import re
import json
from typing import Optional
import logging

from .base_scraper import BaseScraper
from config import ProductData

logger = logging.getLogger(__name__)

class MidoceanScraper(BaseScraper):
    """Scraper pentru Midocean"""
    
    def get_site_domain(self) -> str:
        return "midocean.com"
    
    def scrape_product(self, url: str) -> Optional[ProductData]:
        """Scrapează un produs de pe Midocean"""
        logger.info(f"Scraping Midocean: {url}")
        
        soup = self._get_page(url)
        if not soup:
            return None
        
        product = ProductData(source_url=url)
        
        try:
            # SKU din URL
            match = re.search(r'([a-z]{2}\d{4}-\d{2})', url, re.IGNORECASE)
            if match:
                product.sku = match.group(1).upper()
            
            # Nume
            name_elem = soup.select_one('.product-name h1, h1.name, .pdp-title')
            if name_elem:
                product.name = self._clean_text(name_elem.text)
            
            # Descriere
            desc_elem = soup.select_one('.product-description, .pdp-description, .description')
            if desc_elem:
                product.description = self._clean_text(desc_elem.get_text(separator=' '))
            
            # Specificații
            for spec_row in soup.select('.product-specs tr, .specifications-list li, .attributes .attribute'):
                if spec_row.name == 'tr':
                    cells = spec_row.select('td')
                    if len(cells) >= 2:
                        key = self._clean_text(cells[0].text)
                        value = self._clean_text(cells[1].text)
                        product.specifications[key] = value
                else:
                    text = spec_row.text
                    if ':' in text:
                        parts = text.split(':', 1)
                        product.specifications[self._clean_text(parts[0])] = self._clean_text(parts[1])
            
            # Imagini
            images = []
            for img in soup.select('.product-gallery img, .pdp-images img, .image-container img'):
                img_url = img.get('data-zoom') or img.get('data-src') or img.get('src')
                if img_url:
                    # Obține versiunea de calitate maximă
                    img_url = re.sub(r'_\d+x\d+', '', img_url)
                    img_url = self._make_absolute_url(img_url, url)
                    if img_url not in images and 'placeholder' not in img_url:
                        images.append(img_url)
            product.images = images
            
            # Culori
            colors = []
            for color_elem in soup.select('.color-options .color, .variant-color'):
                color_name = color_elem.get('title') or color_elem.get('data-color')
                if color_name:
                    colors.append({'name': self._clean_text(color_name)})
            product.colors = colors
            
            # Preț
            price_elem = soup.select_one('.product-price, .pdp-price, [data-price]')
            if price_elem:
                product.price = self._extract_price(price_elem.text)
            
            # Brand
            product.brand = "Midocean"
            
            # Categorie din breadcrumbs
            breadcrumbs = soup.select('.breadcrumb a, .breadcrumbs li a')
            if len(breadcrumbs) > 1:
                product.category = self._clean_text(breadcrumbs[-1].text)
            
            logger.info(f"Successfully scraped: {product.name}")
            return product
            
        except Exception as e:
            logger.error(f"Error scraping {url}: {e}")
            return None
