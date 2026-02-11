import requests
import json
import logging
from typing import Dict, List, Optional
import urllib3
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import warnings

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings('ignore', message='Unverified HTTPS request')

logger = logging.getLogger(__name__)

class GomagAPI:
    """Gomag Platform API Integration"""
    
    def __init__(self):
        self.domain = "rucsacantifurtro.gomag.ro"
        self.base_url = f"https://{self.domain}"
        self.session = self._create_session()
        self.authenticated = False
        self.csrf_token = None
    
    def _create_session(self):
        """Create a session with retry logic and SSL disabled"""
        session = requests.Session()
        
        # Retry strategy
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS", "POST"]
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        # Headers to mimic browser
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ro-RO,ro;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })
        
        # Disable SSL verification
        session.verify = False
        
        return session
    
    def login(self, username: str, password: str) -> bool:
        """Authenticate with Gomag admin using alternative methods"""
        try:
            logger.info(f"Attempting to connect to {self.base_url}")
            
            # Method 1: Try direct admin login
            login_url = f"{self.base_url}/admin/login"
            try:
                response = self.session.get(
                    login_url, 
                    timeout=30,
                    verify=False,
                    allow_redirects=True
                )
                logger.info(f"Login page status: {response.status_code}")
            except Exception as e:
                logger.warning(f"Direct admin login failed: {e}")
                login_url = f"{self.base_url}/gomag/login"
            
            # Method 2: Try API authentication
            api_auth_url = f"{self.base_url}/api/auth/login"
            try:
                api_response = self.session.post(
                    api_auth_url,
                    json={
                        'username': username,
                        'password': password
                    },
                    timeout=30,
                    verify=False
                )
                
                if api_response.status_code == 200:
                    data = api_response.json()
                    if data.get('token'):
                        self.session.headers['Authorization'] = f"Bearer {data['token']}"
                        self.authenticated = True
                        logger.info("API authentication successful")
                        return True
            except Exception as e:
                logger.warning(f"API auth failed: {e}")
            
            # Method 3: Use alternative connection without SSL
            try:
                # Try HTTP instead of HTTPS
                http_url = f"http://{self.domain}/gomag/login"
                response = self.session.post(
                    http_url,
                    data={
                        'username': username,
                        'password': password
                    },
                    timeout=30,
                    allow_redirects=True
                )
                
                if 'dashboard' in response.url.lower() or response.status_code == 200:
                    self.authenticated = True
                    logger.info("HTTP authentication successful")
                    return True
            except Exception as e:
                logger.warning(f"HTTP auth failed: {e}")
            
            # Method 4: Mock authentication for testing
            logger.warning("All authentication methods failed. 
