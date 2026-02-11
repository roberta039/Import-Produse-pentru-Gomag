import requests
import json
import logging
from typing import Dict, List, Optional
import base64
from config import Config

logger = logging.getLogger(__name__)

class GomagAPI:
    """Gomag Platform API Integration"""
    
    def __init__(self):
        self.base_url = f"https://{Config.GOMAG_DOMAIN}"
        self.api_url = f"{self.base_url}/api"
        self.session = requests.Session()
        self.authenticated = False
        self.csrf_token = None
    
    def login(self, username: str, password: str) -> bool:
        """Authenticate with Gomag admin"""
        try:
            # Get login page for CSRF token
            login_page = self.session.get(f"{self.base_url}/gomag/login")
            
            # Extract CSRF token if present
            if 'csrf' in login_page.text.lower():
                import re
                csrf_match = re.search(r'name="csrf[_-]?token"\s+value="([^"]+)"', login_page.text)
                if csrf_match:
                    self.csrf_token = csrf_match.group(1)
            
            # Login request
            login_data = {
                'username': username,
                'password': password,
            }
            if self.csrf_token:
                login_data['csrf_token'] = self.csrf_token
            
            response = self.session.post(
                f"{self.base_url}/gomag/login",
                data=login_data,
                allow_redirects=True
            )
            
            # Check if login successful
            if 'dashboard' in response.url or response.status_code == 200:
                self.authenticated = True
                logger.info("Successfully authenticated with Gomag")
                return True
            else:
                logger.error("Authentication failed")
                return False
                
        except Exception as e:
            logger.error(f"Login error: {e}")
            return False
    
    def create_product(self, product_data: Dict) -> Optional[str]:
        """Create a new product in Gomag"""
        if not self.authenticated:
            logger.error("Not authenticated. Please login first.")
            return None
        
        try:
            # Prepare product data for Gomag format
            gomag_product = self._convert_to_gomag_format(product_data)
            
            # Try API endpoint first
            response = self.session.post(
                f"{self.api_url}/products",
                json=gomag_product,
                headers={'Content-Type': 'application/json'}
            )
            
            if response.status_code in [200, 201]:
                result = response.json()
                product_id = result.get('id') or result.get('product_id')
                logger.info(f"Product created with ID: {product_id}")
                return product_id
            else:
                # Fallback to form submission
                return self._create_product_via_form(gomag_product)
                
        except Exception as e:
            logger.error(f"Error creating product: {e}")
            return None
    
    def _create_product_via_form(self, product_data: Dict) -> Optional[str]:
        """Create product via admin form submission"""
        try:
            # Get add product page
            add_page = self.session.get(f"{self.base_url}/gomag/catalog/products/add")
            
            # Extract any required tokens
            import re
            token_match = re.search(r'name="token"\s+value="([^"]+)"', add_page.text)
            if token_match:
                product_data['token'] = token_match.group(1)
            
            # Submit form
            response = self.session.post(
                f"{self.base_url}/gomag/catalog/products/add",
                data=product_data,
                files=self._prepare_image_files(product_data.get('images', []))
            )
            
            if 'success' in response.text.lower() or response.status_code == 200:
                # Try to extract product ID from response
                id_match = re.search(r'product[_-]?id["\s:=]+(\d+)', response.text)
                if id_match:
                    return id_match.group(1)
                return "created"
            
            return None
            
        except Exception as e:
            logger.error(f"Form submission error: {e}")
            return None
    
    def _prepare_image_files(self, images: List[str]) -> Dict:
        """Prepare image files for upload"""
        files = {}
        for i, img_path in enumerate(images):
            try:
                if img_path.startswith('http'):
                    # Download image first
                    from .image_handler import ImageHandler
                    handler = ImageHandler()
                    img_path = handler.download_image(img_path)
                
                if img_path and os.path.exists(img_path):
                    with open(img_path, 'rb') as f:
                        files[f'image_{i}'] = (f'image_{i}.jpg', f.read(), 'image/jpeg')
            except Exception as e:
                logger.error(f"Error preparing image: {e}")
        
        return files
    
    def _convert_to_gomag_format(self, product) -> Dict:
        """Convert our product format to Gomag's expected format"""
        
        # Build specifications HTML
        specs_html = ""
        if hasattr(product, 'specifications') and product.specifications:
            specs_html = "<table class='specifications'>"
            for key, value in product.specifications.items():
                specs_html += f"<tr><td><strong>{key}</strong></td><td>{value}</td></tr>"
            specs_html += "</table>"
        
        # Build features HTML
        features_html = ""
        if hasattr(product, 'features') and product.features:
            features_html = "<ul class='features'>"
            for feature in product.features:
                features_html += f"<li>{feature}</li>"
            features_html += "</ul>"
        
        # Full description
        full_description = f"""
        <div class="product-description">
            {product.description if hasattr(product, 'description') else ''}
        </div>
        
        <div class="product-features">
            <h3>Caracteristici</h3>
            {features_html}
        </div>
        
        <div class="product-specifications">
            <h3>Specificații</h3>
            {specs_html}
        </div>
        """
        
        gomag_data = {
            'name': product.name if hasattr(product, 'name') else '',
            'sku': product.sku if hasattr(product, 'sku') else '',
            'model': product.sku if hasattr(product, 'sku') else '',
            'description': full_description,
            'short_description': product.description[:200] if hasattr(product, 'description') and product.description else '',
            'price': product.price if hasattr(product, 'price') else 0,
            'currency': product.currency if hasattr(product, 'currency') else 'EUR',
            'brand': product.brand if hasattr(product, 'brand') else '',
            'meta_title': product.meta_title if hasattr(product, 'meta_title') else product.name[:70],
            'meta_description': product.meta_description if hasattr(product, 'meta_description') else product.description[:160] if hasattr(product, 'description') and product.description else '',
            'status': 1,  # Active
            'stock_status': 1,  # In stock
            'images': product.images if hasattr(product, 'images') else [],
        }
        
        # Add variants if exist
        if hasattr(product, 'variants') and product.variants:
            gomag_data['variants'] = []
            for variant in product.variants:
                gomag_data['variants'].append({
                    'sku': variant.sku,
                    'color': variant.color,
                    'color_code': variant.color_code,
                    'size': variant.size,
                    'stock': variant.stock,
                    'price': variant.price if variant.price else product.price,
                    'images': variant.images
                })
        
        return gomag_data
    
    def upload_image(self, image_path: str) -> Optional[str]:
        """Upload an image to Gomag and return the URL"""
        try:
            with open(image_path, 'rb') as f:
                files = {'file': (os.path.basename(image_path), f, 'image/jpeg')}
                response = self.session.post(
                    f"{self.base_url}/gomag/media/upload",
                    files=files
                )
            
            if response.status_code == 200:
                result = response.json()
                return result.get('url') or result.get('path')
            
            return None
            
        except Exception as e:
            logger.error(f"Image upload error: {e}")
            return None
    
    def get_categories(self) -> List[Dict]:
        """Get all product categories"""
        try:
            response = self.session.get(f"{self.api_url}/categories")
            if response.status_code == 200:
                return response.json()
            return []
        except Exception as e:
            logger.error(f"Error getting categories: {e}")
            return []
    
    def create_category(self, name: str, parent_id: int = 0) -> Optional[int]:
        """Create a new category"""
        try:
            response = self.session.post(
                f"{self.api_url}/categories",
                json={'name': name, 'parent_id': parent_id}
            )
            if response.status_code in [200, 201]:
                return response.json().get('id')
            return None
        except Exception as e:
            logger.error(f"Error creating category: {e}")
            return None


import os  # Add this import at the top of the file
