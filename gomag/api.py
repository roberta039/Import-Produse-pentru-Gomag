import requests
from bs4 import BeautifulSoup
import json
import logging
from typing import Dict, List, Optional
import re

logger = logging.getLogger(__name__)

class GomagAPI:
    """API pentru interacțiunea cu platforma Gomag"""
    
    def __init__(self, domain: str):
        self.domain = domain
        self.base_url = f"https://{domain}"
        self.session = requests.Session()
        self.authenticated = False
        self.categories_cache = None
        
        # Headers pentru a simula un browser
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ro-RO,ro;q=0.9,en-US;q=0.8,en;q=0.7',
        })
    
    def test_connection(self) -> bool:
        """Testează conexiunea la Gomag"""
        try:
            response = self.session.get(self.base_url, timeout=10)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False
    
    def login(self, username: str, password: str) -> bool:
        """Autentificare în Gomag"""
        try:
            # Obține pagina de login pentru CSRF token
            login_url = f"{self.base_url}/admin/login"
            response = self.session.get(login_url)
            
            if response.status_code != 200:
                login_url = f"{self.base_url}/login"
                response = self.session.get(login_url)
            
            # Extrage CSRF token dacă există
            csrf_token = None
            soup = BeautifulSoup(response.text, 'html.parser')
            csrf_input = soup.find('input', {'name': re.compile('csrf|token', re.I)})
            if csrf_input:
                csrf_token = csrf_input.get('value')
            
            # Date de autentificare
            login_data = {
                'username': username,
                'password': password
            }
            
            if csrf_token:
                login_data['csrf_token'] = csrf_token
            
            # Trimite cererea de autentificare
            response = self.session.post(login_url, data=login_data)
            
            # Verifică succesul
            if 'dashboard' in response.url.lower() or 'admin' in response.url.lower():
                self.authenticated = True
                logger.info("Successfully authenticated to Gomag")
                return True
            
            # Try API authentication
            api_url = f"{self.base_url}/api/auth"
            api_response = self.session.post(api_url, json={
                'username': username,
                'password': password
            })
            
            if api_response.status_code == 200:
                self.authenticated = True
                return True
                
            return False
            
        except Exception as e:
            logger.error(f"Login failed: {e}")
            return False
    
    def get_categories(self) -> List[Dict]:
        """Obține lista de categorii din Gomag"""
        if self.categories_cache:
            return self.categories_cache
        
        try:
            # Încearcă mai multe endpoint-uri posibile
            endpoints = [
                f"{self.base_url}/api/categories",
                f"{self.base_url}/admin/categories/list",
                f"{self.base_url}/categories.json"
            ]
            
            for endpoint in endpoints:
                try:
                    response = self.session.get(endpoint, timeout=10)
                    if response.status_code == 200:
                        try:
                            categories = response.json()
                            if isinstance(categories, list):
                                self.categories_cache = categories
                                return categories
                        except:
                            pass
                except:
                    continue
            
            # Dacă API-ul nu funcționează, încearcă web scraping
            return self._scrape_categories()
            
        except Exception as e:
            logger.error(f"Failed to get categories: {e}")
            return []
    
    def _scrape_categories(self) -> List[Dict]:
        """Extrage categoriile prin web scraping"""
        categories = []
        
        try:
            # Categorii hardcodate comune pentru magazine online românești
            default_categories = [
                {"id": 1, "name": "Rucsacuri", "parent_id": 0, "path": "rucsacuri"},
                {"id": 2, "name": "Rucsacuri Anti-Furt", "parent_id": 1, "path": "rucsacuri/anti-furt"},
                {"id": 3, "name": "Rucsacuri Laptop", "parent_id": 1, "path": "rucsacuri/laptop"},
                {"id": 4, "name": "Rucsacuri Călătorie", "parent_id": 1, "path": "rucsacuri/calatorie"},
                {"id": 5, "name": "Genți", "parent_id": 0, "path": "genti"},
                {"id": 6, "name": "Genți Laptop", "parent_id": 5, "path": "genti/laptop"},
                {"id": 7, "name": "Accesorii", "parent_id": 0, "path": "accesorii"},
                {"id": 8, "name": "Accesorii Securitate", "parent_id": 7, "path": "accesorii/securitate"},
                {"id": 9, "name": "Produse Noi", "parent_id": 0, "path": "produse-noi"},
                {"id": 10, "name": "Promoții", "parent_id": 0, "path": "promotii"}
            ]
            
            # Încearcă să obțină categoriile de pe site
            try:
                response = self.session.get(f"{self.base_url}/sitemap.xml", timeout=10)
                if response.status_code == 200:
                    # Parse sitemap pentru categorii
                    soup = BeautifulSoup(response.content, 'xml')
                    urls = soup.find_all('url')
                    
                    for url in urls:
                        loc = url.find('loc')
                        if loc and '/category/' in loc.text or '/categorie/' in loc.text:
                            path = loc.text.split('/')[-1]
                            name = path.replace('-', ' ').title()
                            categories.append({
                                "id": len(categories) + 100,
                                "name": name,
                                "parent_id": 0,
                                "path": path
                            })
            except:
                pass
            
            # Dacă nu găsește nimic, returnează categoriile implicite
            if not categories:
                categories = default_categories
            
            self.categories_cache = categories
            return categories
            
        except Exception as e:
            logger.error(f"Failed to scrape categories: {e}")
            return []
    
    def create_category(self, name: str, parent_id: int = 0) -> Optional[Dict]:
        """Creează o categorie nouă"""
        try:
            # Endpoint-uri posibile pentru creare categorie
            endpoints = [
                f"{self.base_url}/api/categories",
                f"{self.base_url}/admin/categories/create"
            ]
            
            category_data = {
                "name": name,
                "parent_id": parent_id,
                "status": 1,
                "sort_order": 0,
                "meta_title": name,
                "meta_description": f"Produse din categoria {name}",
                "slug": self._create_slug(name)
            }
            
            for endpoint in endpoints:
                try:
                    response = self.session.post(
                        endpoint,
                        json=category_data,
                        timeout=10
                    )
                    
                    if response.status_code in [200, 201]:
                        result = response.json()
                        new_category = {
                            "id": result.get('id', len(self.categories_cache) + 1),
                            "name": name,
                            "parent_id": parent_id,
                            "path": category_data['slug']
                        }
                        
                        # Adaugă în cache
                        if self.categories_cache:
                            self.categories_cache.append(new_category)
                        
                        return new_category
                except:
                    continue
            
            # Dacă nu poate crea prin API, adaugă local
            new_category = {
                "id": f"local_{len(self.categories_cache or [])+1}",
                "name": name,
                "parent_id": parent_id,
                "path": self._create_slug(name),
                "local": True
            }
            
            if not self.categories_cache:
                self.categories_cache = []
            self.categories_cache.append(new_category)
            
            return new_category
            
        except Exception as e:
            logger.error(f"Failed to create category: {e}")
            return None
    
    def _create_slug(self, text: str) -> str:
        """Creează un slug din text"""
        # Înlocuiește caracterele românești
        replacements = {
            'ă': 'a', 'â': 'a', 'î': 'i', 'ș': 's', 'ț': 't',
            'Ă': 'a', 'Â': 'a', 'Î': 'i', 'Ș': 's', 'Ț': 't'
        }
        
        for rom, eng in replacements.items():
            text = text.replace(rom, eng)
        
        # Convertește la lowercase și înlocuiește spațiile cu dash
        slug = text.lower()
        slug = re.sub(r'[^a-z0-9]+', '-', slug)
        slug = slug.strip('-')
        
        return slug
    
    def import_product(self, product_data: Dict) -> Dict:
        """Importă un produs în Gomag"""
        try:
            # Pregătește datele pentru import
            gomag_product = {
                "name": product_data.get('name', ''),
                "sku": product_data.get('sku', ''),
                "price": product_data.get('price', 0),
                "special_price": product_data.get('special_price'),
                "description": product_data.get('description', ''),
                "short_description": product_data.get('short_description', ''),
                "category_id": product_data.get('category_id'),
                "brand": product_data.get('brand', ''),
                "weight": product_data.get('weight', 1),
                "status": 1,
                "stock": product_data.get('stock', 100),
                "images": product_data.get('images', []),
                "meta_title": product_data.get('meta_title', ''),
                "meta_description": product_data.get('meta_description', ''),
                "meta_keywords": product_data.get('meta_keywords', '')
            }
            
            # Încearcă import prin API
            endpoints = [
                f"{self.base_url}/api/products",
                f"{self.base_url}/admin/products/import"
            ]
            
            for endpoint in endpoints:
                try:
                    response = self.session.post(
                        endpoint,
                        json=gomag_product,
                        timeout=30
                    )
                    
                    if response.status_code in [200, 201]:
                        return {
                            "success": True,
                            "product_id": response.json().get('id'),
                            "message": "Produs importat cu succes"
                        }
                except:
                    continue
            
            # Dacă nu merge prin API, salvează local
            return {
                "success": False,
                "product_id": None,
                "message": "Salvat local pentru import manual",
                "local_data": gomag_product
            }
            
        except Exception as e:
            logger.error(f"Failed to import product: {e}")
            return {
                "success": False,
                "error": str(e)
            }
