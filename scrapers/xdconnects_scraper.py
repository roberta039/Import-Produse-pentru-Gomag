import re
import json
from typing import Optional, List
from .base_scraper import BaseScraper, Product, ProductVariant
import logging

logger = logging.getLogger(__name__)

class XDConnectsScraper(BaseScraper):
    def can_handle(self, url: str) -> bool:
        return 'xdconnects.com' in url
    
    def scrape(self, url: str) -> Optional[Product]:
        soup = self.fetch_page(url, use_cloudscraper=True)
        if not soup:
            return None
        
        product = Product(url=url)
        
        try:
            # Extract product name
            name_elem = soup.select_one('h1.product-title, h1[data-testid="product-title"]')
            if name_elem:
                product.name = name_elem.get_text(strip=True)
            
            # Extract SKU
            sku_elem = soup.select_one('.product-sku, [data-testid="product-sku"]')
            if sku_elem:
                product.sku = sku_elem.get_text(strip=True).replace('SKU:', '').strip()
            else:
                # Try to extract from URL
                match = re.search(r'([pP]\d{3}\.\d{2,3})', url)
                if match:
                    product.sku = match.group(1).upper()
            
            # Extract description
            desc_elem = soup.select_one('.product-description, [data-testid="product-description"]')
            if desc_elem:
                product.description = desc_elem.get_text(strip=True)
            
            # Extract features
            features_list = soup.select('.product-features li, .features-list li')
            product.features = [f.get_text(strip=True) for f in features_list]
            
            # Extract specifications
            spec_rows = soup.select('.specifications tr, .product-specs tr')
            for row in spec_rows:
                cells = row.select('td, th')
                if len(cells) >= 2:
                    key = cells[0].get_text(strip=True)
                    value = cells[1].get_text(strip=True)
                    product.specifications[key] = value
            
            # Extract images
            image_elements = soup.select('.product-gallery img, .product-images img, [data-testid="product-image"] img')
            for img in image_elements:
                src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
                if src:
                    if src.startswith('//'):
                        src = 'https:' + src
                    elif src.startswith('/'):
                        src = 'https://www.xdconnects.com' + src
                    product.images.append(src)
            
            # Extract price
            price_elem = soup.select_one('.product-price, [data-testid="product-price"]')
            if price_elem:
                price_text = price_elem.get_text(strip=True)
                price_match = re.search(r'[\d,\.]+', price_text.replace(',', '.'))
                if price_match:
                    product.price = float(price_match.group())
            
            # Extract variants (colors)
            color_options = soup.select('.color-options .color-option, [data-testid="color-option"]')
            for color_opt in color_options:
                variant = ProductVariant()
                variant.color = color_opt.get('title') or color_opt.get('data-color-name', '')
                variant.color_code = color_opt.get('data-color-code', '')
                variant_sku = color_opt.get('data-variant-sku', '')
                variant.sku = variant_sku if variant_sku else f"{product.sku}-{variant.color_code}"
                
                # Get variant-specific images
                variant_images = color_opt.get('data-images', '[]')
                try:
                    variant.images = json.loads(variant_images)
                except:
                    pass
                
                product.variants.append(variant)
            
            # Extract materials
            material_elem = soup.select_one('.product-material, [data-testid="material"]')
            if material_elem:
                product.materials = material_elem.get_text(strip=True)
            
            # Extract dimensions
            dim_elem = soup.select_one('.product-dimensions, [data-testid="dimensions"]')
            if dim_elem:
                product.dimensions = dim_elem.get_text(strip=True)
            
            # Brand
            product.brand = "XD Design"
            
            logger.info(f"Successfully scraped: {product.name}")
            return product
            
        except Exception as e:
            logger.error(f"Error parsing XD Connects product: {e}")
            return None
