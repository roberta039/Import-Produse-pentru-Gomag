"""
Modul pentru integrarea cu Gomag API
"""

import requests
from typing import Optional, List, Dict, Any
import logging
import json
import re
from bs4 import BeautifulSoup
import cloudscraper
from config import ProductData

logger = logging.getLogger(__name__)

class GomagAPI:
    """Clasă pentru interacțiunea cu Gomag"""
    
    def __init__(self, base_url: str, username: str, password: str, api_key: str = ""):
        self.base_url = base_url.rstrip('/')
        self.username = username
        self.password = password
        self.api_key = api_key
        self.session = cloudscraper.create_scraper()
        self.logged_in = False
        self.csrf_token = None
        self.categories_cache = None
    
    def login(self) -> bool:
        """Autentificare în panoul Gomag"""
        try:
            # Obține pagina de login pentru CSRF
            login_url = f"{self.base_url}/gomag/login"
            response = self.session.get(login_url)
            
            if response.status_code != 200:
                logger.error(f"Cannot access login page: {response.status_code}")
                return False
            
            # Extrage CSRF token
            soup = BeautifulSoup(response.text, 'lxml')
            csrf_input = soup.select_one('input[name="_token"], input[name="csrf_token"]')
            if csrf_input:
                self.csrf_token = csrf_input.get('value')
            
            # Efectuează login
            login_data = {
                'email': self.username,
                'password': self.password,
            }
            if self.csrf_token:
                login_data['_token'] = self.csrf_token
            
            response = self.session.post(
                login_url,
                data=login_data,
                headers={'Referer': login_url}
            )
            
            # Verifică dacă login-ul a reușit
            if 'dashboard' in response.url or response.status_code == 200:
                self.logged_in = True
                logger.info("Successfully logged into Gomag")
                return True
            else:
                logger.error("Login failed")
                return False
                
        except Exception as e:
            logger.error(f"Login error: {e}")
            return False
    
    def get_categories(self) -> List[Dict[str, Any]]:
        """Obține lista de categorii din Gomag"""
        if self.categories_cache:
            return self.categories_cache
        
        if not self.logged_in:
            if not self.login():
                return []
        
        try:
            # Încearcă API endpoint
            api_url = f"{self.base_url}/api/categories"
            headers = {'Authorization': f'Bearer {self.api_key}'} if self.api_key else {}
            
            response = self.session.get(api_url, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                self.categories_cache = data.get('data', data)
                return self.categories_cache
            
            # Fallback: scrape din admin panel
            categories_url = f"{self.base_url}/gomag/catalog/categories"
            response = self.session.get(categories_url)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'lxml')
                categories = []
                
                for option in soup.select('select[name="category_id"] option, .category-list .category-item'):
                    cat_id = option.get('value') or option.get('data-id')
                    cat_name = self._clean_text(option.text)
                    if cat_id and cat_name:
                        # Calculează nivelul din indentare
                        level = len(re.findall(r'^[-–—\s]+', cat_name))
                        cat_name = re.sub(r'^[-–—\s]+', '', cat_name)
                        
                        categories.append({
                            'id': cat_id,
                            'name': cat_name,
                            'level': level,
                            'full_path': cat_name
                        })
                
                self.categories_cache = categories
                return categories
            
            return []
            
        except Exception as e:
            logger.error(f"Error getting categories: {e}")
            return []
    
    def create_category(self, name: str, parent_id: Optional[str] = None) -> Optional[str]:
        """Creează o categorie nouă"""
        if not self.logged_in:
            if not self.login():
                return None
        
        try:
            create_url = f"{self.base_url}/gomag/catalog/categories/create"
            
            # Obține formularul pentru CSRF
            response = self.session.get(create_url)
            soup = BeautifulSoup(response.text, 'lxml')
            
            csrf_input = soup.select_one('input[name="_token"]')
            csrf_token = csrf_input.get('value') if csrf_input else self.csrf_token
            
            data = {
                '_token': csrf_token,
                'name': name,
                'status': '1',
                'parent_id': parent_id or '0',
            }
            
            response = self.session.post(
                f"{self.base_url}/gomag/catalog/categories",
                data=data,
                headers={'Referer': create_url}
            )
            
            if response.status_code in [200, 201, 302]:
                # Încearcă să extragă ID-ul categoriei create
                if 'categories/' in response.url:
                    match = re.search(r'categories/(\d+)', response.url)
                    if match:
                        return match.group(1)
                
                # Reîncarcă categoriile pentru a găsi noua categorie
                self.categories_cache = None
                categories = self.get_categories()
                for cat in categories:
                    if cat['name'] == name:
                        return cat['id']
                
                return "created"
            
            return None
            
        except Exception as e:
            logger.error(f"Error creating category: {e}")
            return None
    
    def import_product(self, product: ProductData, category_id: str) -> bool:
        """Importă un produs în Gomag"""
        if not self.logged_in:
            if not self.login():
                return False
        
        try:
            # Obține pagina de creare produs
            create_url = f"{self.base_url}/gomag/catalog/products/create"
            response = self.session.get(create_url)
            
            soup = BeautifulSoup(response.text, 'lxml')
            csrf_input = soup.select_one('input[name="_token"]')
            csrf_token = csrf_input.get('value') if csrf_input else self.csrf_token
            
            # Pregătește datele produsului
            product_data = {
                '_token': csrf_token,
                'name': product.name_ro or product.name,
                'sku': product.sku,
                'description': product.description_ro or product.description,
                'price': str(product.price) if product.price else '0',
                'status': '1',
                'category_id': category_id,
                'brand': product.brand,
                'weight': str(product.weight) if product.weight else '',
                'meta_title': product.meta_title or (product.name_ro or product.name),
                'meta_description': product.meta_description or (product.description_ro or product.description)[:160],
            }
            
            # Adaugă specificații
            specs_html = ""
            specs = product.specifications_ro or product.specifications
            for key, value in specs.items():
                specs_html += f"<tr><td><strong>{key}</strong></td><td>{value}</td></tr>"
            if specs_html:
                product_data['specifications'] = f"<table>{specs_html}</table>"
            
            # Adaugă dimensiuni
            if product.dimensions:
                product_data['width'] = str(product.dimensions.get('width', ''))
                product_data['height'] = str(product.dimensions.get('height', ''))
                product_data['depth'] = str(product.dimensions.get('depth', ''))
            
            # Trimite datele produsului
            response = self.session.post(
                f"{self.base_url}/gomag/catalog/products",
                data=product_data,
                headers={'Referer': create_url}
            )
            
            if response.status_code in [200, 201, 302]:
                product_id = None
                if 'products/' in response.url:
                    match = re.search(r'products/(\d+)', response.url)
                    if match:
                        product_id = match.group(1)
                
                # Upload imagini
                if product_id and product.images:
                    self._upload_images(product_id, product.images)
                
                # Adaugă variante (culori, mărimi)
                if product_id and (product.colors or product.sizes):
                    self._add_variants(product_id, product)
                
                logger.info(f"Product imported successfully: {product.name_ro or product.name}")
                return True
            else:
                logger.error(f"Failed to import product: {response.status_code}")
                return False
            
        except Exception as e:
            logger.error(f"Error importing product: {e}")
            return False
    
    def _upload_images(self, product_id: str, images: List[str]) -> bool:
        """Upload imagini pentru un produs"""
        try:
            upload_url = f"{self.base_url}/gomag/catalog/products/{product_id}/images"
            
            for idx, img_url in enumerate(images[:10]):  # Maxim 10 imagini
                try:
                    # Descarcă imaginea
                    img_response = self.session.get(img_url, timeout=30)
                    if img_response.status_code != 200:
                        continue
                    
                    # Determină extensia
                    content_type = img_response.headers.get('content-type', '')
                    ext = '.jpg'
                    if 'png' in content_type:
                        ext = '.png'
                    elif 'webp' in content_type:
                        ext = '.webp'
                    
                    filename = f"product_{product_id}_{idx}{ext}"
                    
                    # Upload
                    files = {
                        'image': (filename, img_response.content, content_type or 'image/jpeg')
                    }
                    data = {
                        '_token': self.csrf_token,
                        'is_main': '1' if idx == 0 else '0'
                    }
                    
                    self.session.post(upload_url, files=files, data=data)
                    
                except Exception as e:
                    logger.warning(f"Error uploading image {img_url}: {e}")
                    continue
            
            return True
            
        except Exception as e:
            logger.error(f"Error in image upload: {e}")
            return False
    
    def _add_variants(self, product_id: str, product: ProductData) -> bool:
        """Adaugă variante (culori, mărimi) pentru un produs"""
        try:
            variants_url = f"{self.base_url}/gomag/catalog/products/{product_id}/variants"
            
            # Adaugă culori ca variante
            for color in product.colors:
                color_name = color.get('name_ro') or color.get('name', '')
                if color_name:
                    data = {
                        '_token': self.csrf_token,
                        'attribute_type': 'color',
                        'attribute_value': color_name,
                        'sku_suffix': color.get('code', ''),
                        'price_modifier': '0',
                        'stock': '100',
                    }
                    self.session.post(variants_url, data=data)
            
            # Adaugă mărimi ca variante
            for size in product.sizes:
                data = {
                    '_token': self.csrf_token,
                    'attribute_type': 'size',
                    'attribute_value': size,
                    'sku_suffix': size,
                    'price_modifier': '0',
                    'stock': '100',
                }
                self.session.post(variants_url, data=data)
            
            return True
            
        except Exception as e:
            logger.error(f"Error adding variants: {e}")
            return False
    
    def _clean_text(self, text: Optional[str]) -> str:
        """Curăță text"""
        if not text:
            return ""
        return ' '.join(text.split()).strip()
    
    def check_product_exists(self, sku: str) -> bool:
        """Verifică dacă un produs există deja"""
        if not self.logged_in:
            if not self.login():
                return False
        
        try:
            search_url = f"{self.base_url}/gomag/catalog/products?search={sku}"
            response = self.session.get(search_url)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'lxml')
                # Caută SKU în tabelul de produse
                for cell in soup.select('table td'):
                    if sku.lower() in cell.text.lower():
                        return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking product: {e}")
            return False
