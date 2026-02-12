"""
Scraper pentru pfconcept.com
"""

import re
import json
from typing import Optional
from bs4 import BeautifulSoup
import logging

from .base_scraper import BaseScraper
from config import ProductData

logger = logging.getLogger(__name__)

class PFConceptScraper(BaseScraper):
    """Scraper pentru PF Concept"""
    
    def get_site_domain(self) -> str:
        return "pfconcept.com"
    
    def scrape_product(self, url: str) -> Optional[ProductData]:
        """Scrapează un produs de pe PF Concept"""
        logger.info(f"Scraping PF Concept: {url}")
        
        soup = self._get_page(url)
        if not soup:
            return None
        
        product = ProductData(source_url=url)
        
        try:
            # SKU
            sku_elem = soup.select_one('.product-sku, .sku, [data-sku]')
            if sku_elem:
                product.sku = self._clean_text(sku_elem.text.replace('SKU:', '').strip())
            else:
                # Din URL
                match = re.search(r'/([a-z0-9-]+)-(\d+)\.html', url)
                if match:
                    product.sku = match.group(2)
            
            # Nume
            name_elem = soup.select_one('h1.product-name, h1.title, h1')
            if name_elem:
                product.name = self._clean_text(name_elem.text)
            
            # Descriere
            desc_selectors = [
                '.product-description',
                '.description-content',
                '#product-description',
                '.tab-content .description'
            ]
            for selector in desc_selectors:
                desc_elem = soup.select_one(selector)
                if desc_elem:
                    product.description = self._clean_text(desc_elem.get_text(separator=' '))
                    break
            
            # Specificații
            specs_table = soup.select_one('.specifications table, .product-attributes, .specs-table')
            if specs_table:
                for row in specs_table.select('tr'):
                    cells = row.select('td, th')
                    if len(cells) >= 2:
                        key = self._clean_text(cells[0].text)
                        value = self._clean_text(cells[1].text)
                        if key and value:
                            product.specifications[key] = value
            
            # Features list
            features = soup.select('.product-features li, .features-list li')
            if features:
                product.specifications['Features'] = '; '.join([self._clean_text(f.text) for f in features])
            
            # Imagini
            images = []
            
            # Main image
            main_img = soup.select_one('.product-image-main img, .main-product-image img')
            if main_img:
                img_url = main_img.get('data-zoom') or main_img.get('data-src') or main_img.get('src')
                if img_url:
                    images.append(self._make_absolute_url(img_url, url))
            
            # Gallery images
            for img in soup.select('.product-thumbnails img, .gallery-thumbs img, .image-gallery img'):
                img_url = img.get('data-large') or img.get('data-full') or img.get('src')
                if img_url:
                    img_url = self._make_absolute_url(img_url, url)
                    if img_url not in images:
                        images.append(img_url)
            
            product.images = images
            
            # Culori
            colors = []
            for color_elem in soup.select('.color-selector [data-color], .color-swatches .swatch'):
                color_name = color_elem.get('data-color-name') or color_elem.get('title', '')
                color_code = color_elem.get('data-color-code', '')
                if color_name:
                    colors.append({
                        'name': self._clean_text(color_name),
                        'code': color_code
                    })
            product.colors = colors
            
            # Mărimi
            sizes = []
            for size_elem in soup.select('.size-selector option, .size-options .size'):
                size = self._clean_text(size_elem.text)
                if size and size.lower() not in ['select', 'choose', 'selectează']:
                    sizes.append(size)
            product.sizes = sizes
            
            # Preț
            price_elem = soup.select_one('.product-price .price, .price-box .price, [data-price]')
            if price_elem:
                product.price = self._extract_price(price_elem.get('data-price') or price_elem.text)
            
            # Brand
            brand_elem = soup.select_one('.product-brand, .brand, [itemprop="brand"]')
            if brand_elem:
                product.brand = self._clean_text(brand_elem.text)
            
            # Materiale
            material_text = product.specifications.get('Material', '')
            if material_text:
                product.materials = [m.strip() for m in material_text.split(',')]
            
            logger.info(f"Successfully scraped: {product.name}")
            return product
            
        except Exception as e:
            logger.error(f"Error scraping {url}: {e}")
            return None
