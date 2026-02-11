import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Gomag API Configuration
    GOMAG_DOMAIN = "rucsacantifurtro.gomag.ro"
    GOMAG_API_URL = f"https://{GOMAG_DOMAIN}/api"
    GOMAG_USERNAME = os.getenv("GOMAG_USERNAME", "")
    GOMAG_PASSWORD = os.getenv("GOMAG_PASSWORD", "")
    GOMAG_API_KEY = os.getenv("GOMAG_API_KEY", "")
    
    # Translation settings
    SOURCE_LANG = "en"
    TARGET_LANG = "ro"
    
    # Scraping settings
    REQUEST_DELAY = 1  # seconds between requests
    MAX_RETRIES = 3
    TIMEOUT = 30
    
    # Image settings
    DOWNLOAD_IMAGES = True
    IMAGE_QUALITY = 85
    MAX_IMAGE_SIZE = (1200, 1200)
