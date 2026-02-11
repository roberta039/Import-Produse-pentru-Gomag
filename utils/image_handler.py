import requests
import os
from PIL import Image
from io import BytesIO
import hashlib
import logging
from typing import List, Tuple, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

class ImageHandler:
    def __init__(self, download_dir: str = "temp_images"):
        self.download_dir = download_dir
        os.makedirs(download_dir, exist_ok=True)
    
    def download_image(self, url: str) -> Optional[str]:
        """Download image and return local path"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            
            # Generate filename from URL hash
            url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
            ext = self._get_extension(url, response.headers.get('Content-Type', ''))
            filename = f"{url_hash}{ext}"
            filepath = os.path.join(self.download_dir, filename)
            
            # Save image
            with open(filepath, 'wb') as f:
                f.write(response.content)
            
            return filepath
            
        except Exception as e:
            logger.error(f"Error downloading image {url}: {e}")
            return None
    
    def _get_extension(self, url: str, content_type: str) -> str:
        """Get image extension from URL or content type"""
        # Try from URL
        parsed = urlparse(url)
        path = parsed.path.lower()
        for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
            if path.endswith(ext):
                return ext
        
        # Try from content type
        content_type = content_type.lower()
        if 'jpeg' in content_type or 'jpg' in content_type:
            return '.jpg'
        elif 'png' in content_type:
            return '.png'
        elif 'gif' in content_type:
            return '.gif'
        elif 'webp' in content_type:
            return '.webp'
        
        return '.jpg'  # Default
    
    def optimize_image(self, filepath: str, max_size: Tuple[int, int] = (1200, 1200), 
                       quality: int = 85) -> str:
        """Optimize image for web"""
        try:
            img = Image.open(filepath)
            
            # Convert to RGB if necessary
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            
            # Resize if larger than max size
            if img.size[0] > max_size[0] or img.size[1] > max_size[1]:
                img.thumbnail(max_size, Image.LANCZOS)
            
            # Save optimized
            optimized_path = filepath.replace('.', '_opt.')
            img.save(optimized_path, 'JPEG', quality=quality, optimize=True)
            
            return optimized_path
            
        except Exception as e:
            logger.error(f"Error optimizing image {filepath}: {e}")
            return filepath
    
    def process_product_images(self, image_urls: List[str]) -> List[str]:
        """Download and optimize all product images"""
        processed = []
        for url in image_urls:
            local_path = self.download_image(url)
            if local_path:
                optimized = self.optimize_image(local_path)
                processed.append(optimized)
        return processed
    
    def cleanup(self):
        """Remove all temporary images"""
        import shutil
        if os.path.exists(self.download_dir):
            shutil.rmtree(self.download_dir)
