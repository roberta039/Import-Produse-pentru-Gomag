import requests
from bs4 import BeautifulSoup
import cloudscraper
from fake_useragent import UserAgent
import time
import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from dataclasses import dataclass, field

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class ProductVariant:
    sku: str = ""
    color: str = ""
    color_code: str = ""
    size: str = ""
    stock: int = 0
    price: float = 0.0
    images: List[str] = field(default_factory=list)

@dataclass
class Product:
    url: str = ""
    sku: str = ""
    name: str = ""
    description: str = ""
    specifications: Dict[str, str] = field(default_factory=dict)
    category: str = ""
    brand: str = ""
    price: float = 0.0
    currency: str = "EUR"
    images: List[str] = field(default_factory=list)
    variants: List[ProductVariant] = field(default_factory=list)
    materials: str = ""
    dimensions: str = ""
    weight: str = ""
    features: List[str] = field(default_factory=list)
    meta_title: str = ""
    meta_description: str = ""

class BaseScraper(ABC):
    def __init__(self):
        self.ua = UserAgent()
        self.scraper = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'windows',
                'desktop': True
            }
        )
        self.session = requests.Session()
        
    def get_headers(self) -> Dict[str, str]:
        return {
            'User-Agent': self.ua.random,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
    
    def fetch_page(self, url: str, use_cloudscraper: bool = False) -> Optional[BeautifulSoup]:
        """Fetch and parse a webpage"""
        try:
            if use_cloudscraper:
                response = self.scraper.get(url, headers=self.get_headers(), timeout=30)
            else:
                response = self.session.get(url, headers=self.get_headers(), timeout=30)
            
            response.raise_for_status()
            return BeautifulSoup(response.content, 'lxml')
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            return None
    
    @abstractmethod
    def scrape(self, url: str) -> Optional[Product]:
        """Scrape product data from URL"""
        pass
    
    @abstractmethod
    def can_handle(self, url: str) -> bool:
        """Check if this scraper can handle the given URL"""
        pass
