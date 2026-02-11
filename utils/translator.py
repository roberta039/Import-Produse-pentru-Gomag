from deep_translator import GoogleTranslator
import logging
from typing import Dict, List
import time

logger = logging.getLogger(__name__)

class ProductTranslator:
    def __init__(self, source_lang: str = 'en', target_lang: str = 'ro'):
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.translator = GoogleTranslator(source=source_lang, target=target_lang)
        self.cache = {}
    
    def translate_text(self, text: str) -> str:
        """Translate a single text string"""
        if not text or text.strip() == '':
            return text
        
        # Check cache
        if text in self.cache:
            return self.cache[text]
        
        try:
            # Split long texts into chunks (Google Translate limit)
            if len(text) > 4500:
                chunks = [text[i:i+4500] for i in range(0, len(text), 4500)]
                translated_chunks = []
                for chunk in chunks:
                    translated = self.translator.translate(chunk)
                    translated_chunks.append(translated)
                    time.sleep(0.5)  # Rate limiting
                result = ' '.join(translated_chunks)
            else:
                result = self.translator.translate(text)
            
            self.cache[text] = result
            return result
            
        except Exception as e:
            logger.error(f"Translation error: {e}")
            return text
    
    def translate_dict(self, data: Dict[str, str]) -> Dict[str, str]:
        """Translate dictionary values"""
        translated = {}
        for key, value in data.items():
            translated_key = self.translate_text(key)
            translated_value = self.translate_text(value)
            translated[translated_key] = translated_value
        return translated
    
    def translate_list(self, items: List[str]) -> List[str]:
        """Translate a list of strings"""
        return [self.translate_text(item) for item in items]
    
    def translate_product(self, product) -> None:
        """Translate all text fields of a product in-place"""
        try:
            # Translate name
            if product.name:
                product.name = self.translate_text(product.name)
            
            # Translate description
            if product.description:
                product.description = self.translate_text(product.description)
            
            # Translate features
            if product.features:
                product.features = self.translate_list(product.features)
            
            # Translate specifications
            if product.specifications:
                product.specifications = self.translate_dict(product.specifications)
            
            # Translate materials
            if product.materials:
                product.materials = self.translate_text(product.materials)
            
            # Translate variant colors
            for variant in product.variants:
                if variant.color:
                    variant.color = self.translate_text(variant.color)
            
            # Generate meta
            product.meta_title = product.name[:70] if product.name else ""
            product.meta_description = product.description[:160] if product.description else ""
            
            logger.info(f"Translated product: {product.name}")
            
        except Exception as e:
            logger.error(f"Error translating product: {e}")
