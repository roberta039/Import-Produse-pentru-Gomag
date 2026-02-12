import requests
from bs4 import BeautifulSoup
import re
import json
import time
import logging
from typing import Dict, Optional
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

logger = logging.getLogger(__name__)

class SeleniumScraper:
    """Scraper using Selenium for JavaScript-heavy sites"""
    
    def __init__(self):
        self.driver = None
    
    def setup_driver(self):
        """Setup Chrome driver with options"""
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        
        try:
            self.driver = webdriver.Chrome(options=chrome_options)
        except:
            # Try Firefox as fallback
            from selenium.webdriver.firefox.options import Options as FirefoxOptions
            firefox_options = FirefoxOptions()
            firefox_options.add_argument("--headless")
            self.driver = webdriver.Firefox(options=firefox_options)
    
    def extract_product(self, url: str) -> Dict:
        """Extract product with Selenium"""
        if not self.driver:
            self.setup_driver()
        
        try:
            # Load page
            self.driver.get(url)
            
            # Wait for content to load
            wait = WebDriverWait(self.driver, 10)
            
            product = {
                'url': url,
                'status': 'success'
            }
            
            # Extract name
            try:
                name_elem = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "h1")))
                product['name'] = name_elem.text
            except:
                product['name'] = "Product"
            
            # Extract price
            try:
                price_elem = self.driver.find_element(By.CSS_SELECTOR, "[class*='price'], [class*='Price']")
                price_text = price_elem.text
                numbers = re.findall(r'[\d,\.]+', price_text)
                if numbers:
                    product['price'] = float(numbers[0].replace(',', '.'))
            except:
                product['price'] = 0
            
            # Extract images
            images = []
            try:
                img_elements = self.driver.find_elements(By.CSS_SELECTOR, "img[src*='product'], img[src*='cdn']")
                for img in img_elements[:5]:
                    src = img.get_attribute('src')
                    if src and 'data:' not in src:
                        images.append(src)
            except:
                pass
            product['images'] = images
            
            # Get page source for BeautifulSoup parsing
            page_source = self.driver.page_source
            soup = BeautifulSoup(page_source, 'html.parser')
            
            # Extract more details with BeautifulSoup
            desc_elem = soup.find(class_=re.compile('description', re.I))
            if desc_elem:
                product['description'] = desc_elem.get_text(strip=True)[:1000]
            
            # Extract SKU
            sku_match = re.search(r'[pP](\d{3}\.\d{2,3})', url)
            if sku_match:
                product['sku'] = sku_match.group(0).upper()
            
            return product
            
        except Exception as e:
            logger.error(f"Selenium error: {e}")
            return {
                'url': url,
                'status': 'error',
                'error': str(e)
            }
    
    def __del__(self):
        """Clean up driver"""
        if self.driver:
            self.driver.quit()
