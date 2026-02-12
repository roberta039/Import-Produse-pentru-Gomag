"""
Scraper pentru xdconnects.com
"""

import re
import json
from typing import Optional, List, Dict
from bs4 import BeautifulSoup
import logging

from .base_scraper import BaseScraper
from config import ProductData

logger = logging.getLogger(__name__)

class XDConnectsScraper(BaseScraper):
    """Scraper pentru XD Connects (xdconnects.com)"""
    
    def get_site_domain(self) -> str:
        return "xdconnects.com"
    
    def scrape_product(self, url: str) -> Optional[ProductData]:
        """Scrapează un produs de pe XD Connects"""
        logger.info(f"Scraping XD Connects: {url}")
        
        soup = self._get_page(url)
        if not soup:
            return None
        
        product = ProductData(source_url=url)
        
        try:
            # SKU / Cod produs
            sku_elem = soup.select_one('[data-sku], .product-sku, .sku')
            if sku_elem:
                product.sku = self._clean_text(sku_elem.get('data-sku') or sku_elem.text)
            else:
                # Încearcă din URL
                match = re.search(r'([A-Z]\d{3}\.\d+)', url)
                if match:
                    product.sku = match.group(1)
            
            # Nume produs
            name_elem = soup.select_one('h1.product-title, h1.product-name, h1')
            if name_elem:
                product.name = self._clean_text(name_elem.text)
            
            # Brand
            brand_elem = soup.select_one('.product-brand, .brand-name, [itemprop="brand"]')
            if brand_elem:
                product.brand = self._clean_text(brand_elem.text)
            else:
                product.brand = "XD Design"
            
            # Descriere
            desc_elem = soup.select_one('.product-description, .description, [itemprop="description"]')
            if desc_elem:
                product.description = self._clean_text(desc_elem.get_text(separator=' '))
            
            # Specificații
            specs_container = soup.select_one('.product-specifications, .specifications, .product-details')
            if specs_container:
                for row in specs_container.select('tr, .spec-row, li'):
                    cols = row.select('td, .spec-label, .spec-value')
                    if len(cols) >= 2:
                        key = self._clean_text(cols[0].text)
                        value = self._clean_text(cols[1].text)
                        if key and value:
                            product.specifications[key] = value
                    elif ':' in row.text:
                        parts = row.text.split(':', 1)
                        if len(parts) == 2:
                            product.specifications[self._clean_text(parts[0])] = self._clean_text(parts[1])
            
            # Imagini
            images = []
            
            # Imagini principale
            for img in soup.select('.product-gallery img, .product-images img, .main-image img, [data-zoom-image]'):
                img_url = img.get('data-zoom-image') or img.get('data-src') or img.get('src')
                if img_url:
                    img_url = self._make_absolute_url(img_url, url)
                    if img_url not in images and 'placeholder' not in img_url.lower():
                        images.append(img_url)
            
            # Imagini thumbnail
            for img in soup.select('.thumbnail img, .thumb img'):
                img_url = img.get('data-large') or img.get('data-src') or img.get('src')
                if img_url:
                    # Încearcă să obții versiunea mare
                    img_url = re.sub(r'_thumb|_small|_medium', '', img_url)
                    img_url = self._make_absolute_url(img_url, url)
                    if img_url not in images:
                        images.append(img_url)
            
            product.images = images[:10]  # Maxim 10 imagini
            
            # Culori și variante
            colors = []
            color_container = soup.select_one('.color-options, .variant-colors, .product-variants')
            if color_container:
                for color_elem in color_container.select('[data-color], .color-option, .swatch'):
                    color_name = color_elem.get('data-color') or color_elem.get('title') or self._clean_text(color_elem.text)
                    color_code = color_elem.get('data-color-code', '')
                    color_image = color_elem.select_one('img')
                    
                    if color_name:
                        colors.append({
                            'name': color_name,
                            'code': color_code,
                            'image': self._make_absolute_url(color_image.get('src', ''), url) if color_image else ''
                        })
            
            product.colors = colors
            
            # Preț
            price_elem = soup.select_one('[itemprop="price"], .price, .product-price')
            if price_elem:
                price_text = price_elem.get('content') or price_elem.text
                product.price = self._extract_price(price_text)
            
            # Categorie
            breadcrumbs = soup.select('.breadcrumb a, .breadcrumbs a')
            if len(breadcrumbs) > 1:
                product.category = self._clean_text(breadcrumbs[-1].text)
            
            # Materiale
            materials = []
            material_elem = soup.select_one('.materials, [data-materials]')
            if material_elem:
                materials = [self._clean_text(m) for m in material_elem.text.split(',')]
            product.materials = materials
            
            # Dimensiuni
            dims_elem = soup.select_one('.dimensions, .size-info')
            if dims_elem:
                dims_text = dims_elem.text
                # Parsează dimensiunile (ex: "30 x 20 x 10 cm")
                match = re.search(r'(\d+(?:\.\d+)?)\s*[xX×]\s*(\d+(?:\.\d+)?)\s*[xX×]\s*(\d+(?:\.\d+)?)', dims_text)
                if match:
                    product.dimensions = {
                        'width': float(match.group(1)),
                        'height': float(match.group(2)),
                        'depth': float(match.group(3))
                    }
            
            # Greutate
            weight_elem = soup.select_one('.weight, [data-weight]')
            if weight_elem:
                weight_text = weight_elem.get('data-weight') or weight_elem.text
                match = re.search(r'(\d+(?:\.\d+)?)', weight_text)
                if match:
                    product.weight = float(match.group(1))
            
            # JSON-LD data (dacă există)
            json_ld = soup.select_one('script[type="application/ld+json"]')
            if json_ld:
                try:
                    data = json.loads(json_ld.string)
                    if isinstance(data, list):
                        data = data[0]
                    if data.get('@type') == 'Product':
                        product.name = product.name or data.get('name', '')
                        product.description = product.description or data.get('description', '')
                        product.brand = product.brand or data.get('brand', {}).get('name', '')
                        if 'offers' in data:
                            offers = data['offers']
                            if isinstance(offers, list):
                                offers = offers[0]
                            product.price = product.price or float(offers.get('price', 0))
                            product.currency = offers.get('priceCurrency', 'EUR')
                except:
                    pass
            
            logger.info(f"Successfully scraped: {product.name}")
            return product
            
        except Exception as e:
            logger.error(f"Error scraping {url}: {e}")
            return None
