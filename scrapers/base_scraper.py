"""
Clasa de bază pentru toate scraperele
"""

import cloudscraper
import requests
from abc import ABC, abstractmethod
from bs4 import BeautifulSoup
from typing import Optional, Dict, List, Any
import time
import random
import logging
from fake_useragent import UserAgent
from urllib.parse import urljoin, urlparse
import hashlib
import os

from config import ProductData, USER_AGENTS, RATE_LIMIT_DELAY, MAX_RETRIES, TIMEOUT

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BaseScraper(ABC):
    """Clasă de bază pentru scraping"""
    
    def __init__(self, credentials: Optional[Dict[str, str]] = None):
        self.credentials = credentials or {}
        self.session = None
        self.scraper = None
        self.last_request_time = 0
        self.ua = UserAgent()
        self._setup_session()
    
    def _setup_session(self):
        """Configurează sesiunea cu cloudscraper"""
        try:
            self.scraper = cloudscraper.create_scraper(
                browser={
                    'browser': 'chrome',
                    'platform': 'windows',
                    'mobile': False
                },
                delay=10
            )
        except Exception as e:
            logger.warning(f"CloudScraper failed, using requests: {e}")
            self.scraper = requests.Session()
        
        self.scraper.headers.update({
            'User-Agent': random.choice(USER_AGENTS),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
    
    def _rate_limit(self):
        """Implementează rate limiting"""
        current_time = time.time()
        elapsed = current_time - self.last_request_time
        if elapsed < RATE_LIMIT_DELAY:
            time.sleep(RATE_LIMIT_DELAY - elapsed + random.uniform(0.5, 1.5))
        self.last_request_time = time.time()
    
    def _get_page(self, url: str, retry: int = 0) -> Optional[BeautifulSoup]:
        """Obține și parsează o pagină"""
        self._rate_limit()
        
        try:
            # Rotație user agent
            self.scraper.headers['User-Agent'] = self.ua.random
            
            response = self.scraper.get(url, timeout=TIMEOUT)
            response.raise_for_status()
            
            return BeautifulSoup(response.content, 'lxml')
            
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            if retry < MAX_RETRIES:
                time.sleep(2 ** retry)  # Exponential backoff
                return self._get_page(url, retry + 1)
            return None
    
    def _get_json(self, url: str, retry: int = 0) -> Optional[Dict]:
        """Obține date JSON de la un endpoint"""
        self._rate_limit()
        
        try:
            self.scraper.headers['User-Agent'] = self.ua.random
            self.scraper.headers['Accept'] = 'application/json'
            
            response = self.scraper.get(url, timeout=TIMEOUT)
            response.raise_for_status()
            
            return response.json()
            
        except Exception as e:
            logger.error(f"Error fetching JSON {url}: {e}")
            if retry < MAX_RETRIES:
                time.sleep(2 ** retry)
                return self._get_json(url, retry + 1)
            return None
    
    def _clean_text(self, text: Optional[str]) -> str:
        """Curăță și normalizează text"""
        if not text:
            return ""
        return ' '.join(text.split()).strip()
    
    def _extract_price(self, text: str) -> float:
        """Extrage prețul dintr-un string"""
        import re
        if not text:
            return 0.0
        # Înlocuiește virgula cu punct și elimină tot ce nu e număr sau punct
        cleaned = re.sub(r'[^\d.,]', '', text)
        cleaned = cleaned.replace(',', '.')
        # Păstrează doar ultimul punct (pentru zecimale)
        parts = cleaned.rsplit('.', 1)
        if len(parts) == 2 and len(parts[1]) <= 2:
            cleaned = parts[0].replace('.', '') + '.' + parts[1]
        else:
            cleaned = cleaned.replace('.', '')
        try:
            return float(cleaned)
        except:
            return 0.0
    
    def _make_absolute_url(self, url: str, base_url: str) -> str:
        """Transformă URL relativ în absolut"""
        if url.startswith('//'):
            return 'https:' + url
        if url.startswith('/'):
            parsed = urlparse(base_url)
            return f"{parsed.scheme}://{parsed.netloc}{url}"
        if not url.startswith('http'):
            return urljoin(base_url, url)
        return url
    
    def _download_image(self, url: str, save_dir: str = "images") -> Optional[str]:
        """Descarcă o imagine și returnează calea locală"""
        try:
            os.makedirs(save_dir, exist_ok=True)
            
            # Generează nume unic pentru imagine
            url_hash = hashlib.md5(url.encode()).hexdigest()[:10]
            ext = os.path.splitext(urlparse(url).path)[1] or '.jpg'
            filename = f"{url_hash}{ext}"
            filepath = os.path.join(save_dir, filename)
            
            if os.path.exists(filepath):
                return filepath
            
            response = self.scraper.get(url, timeout=TIMEOUT)
            response.raise_for_status()
            
            with open(filepath, 'wb') as f:
                f.write(response.content)
            
            return filepath
            
        except Exception as e:
            logger.error(f"Error downloading image {url}: {e}")
            return None
    
    @abstractmethod
    def scrape_product(self, url: str) -> Optional[ProductData]:
        """Metodă abstractă pentru scraping-ul unui produs"""
        pass
    
    @abstractmethod
    def get_site_domain(self) -> str:
        """Returnează domeniul site-ului"""
        pass
    
    def login(self) -> bool:
        """Login pe site (dacă e necesar)"""
        return True  # Implicit fără login
