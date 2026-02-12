"""
Modul pentru traducerea textelor în română
"""

from typing import Dict, List, Optional
from deep_translator import GoogleTranslator
import logging
import re
from config import COLOR_TRANSLATIONS, ProductData

logger = logging.getLogger(__name__)

class ProductTranslator:
    """Clasă pentru traducerea produselor în română"""
    
    def __init__(self, source_lang: str = 'en', target_lang: str = 'ro'):
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.translator = GoogleTranslator(source=source_lang, target=target_lang)
        self.cache = {}
    
    def _translate_text(self, text: str) -> str:
        """Traduce un text cu caching"""
        if not text or text.strip() == '':
            return text
        
        # Verifică cache
        cache_key = f"{self.source_lang}:{self.target_lang}:{text}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        try:
            # Păstrează placeholder-uri pentru numere și unități
            placeholders = {}
            placeholder_pattern = r'(\d+(?:\.\d+)?\s*(?:cm|mm|m|kg|g|L|ml|inch|"|\'|x|X|×))'
            
            def save_placeholder(match):
                key = f"__PH{len(placeholders)}__"
                placeholders[key] = match.group(0)
                return key
            
            text_with_placeholders = re.sub(placeholder_pattern, save_placeholder, text)
            
            # Traduce
            translated = self.translator.translate(text_with_placeholders)
            
            # Restaurează placeholders
            for key, value in placeholders.items():
                translated = translated.replace(key, value)
            
            self.cache[cache_key] = translated
            return translated
            
        except Exception as e:
            logger.error(f"Translation error: {e}")
            return text
    
    def translate_color(self, color: str) -> str:
        """Traduce o culoare"""
        color_lower = color.lower().strip()
        
        # Verifică traducerile predefinite
        if color_lower in COLOR_TRANSLATIONS:
            return COLOR_TRANSLATIONS[color_lower]
        
        # Încearcă traducere automată
        return self._translate_text(color)
    
    def translate_specifications(self, specs: Dict[str, str]) -> Dict[str, str]:
        """Traduce specificațiile"""
        translated = {}
        
        # Mapping pentru chei comune
        key_translations = {
            'material': 'Material',
            'color': 'Culoare',
            'colour': 'Culoare',
            'size': 'Mărime',
            'dimensions': 'Dimensiuni',
            'weight': 'Greutate',
            'capacity': 'Capacitate',
            'volume': 'Volum',
            'features': 'Caracteristici',
            'warranty': 'Garanție',
            'brand': 'Brand',
            'model': 'Model',
            'sku': 'Cod produs',
            'width': 'Lățime',
            'height': 'Înălțime',
            'depth': 'Adâncime',
            'length': 'Lungime',
            'laptop compartment': 'Compartiment laptop',
            'water resistant': 'Rezistent la apă',
            'anti-theft': 'Anti-furt',
            'rfid protection': 'Protecție RFID',
            'usb port': 'Port USB',
        }
        
        for key, value in specs.items():
            key_lower = key.lower().strip()
            
            # Traduce cheia
            if key_lower in key_translations:
                translated_key = key_translations[key_lower]
            else:
                translated_key = self._translate_text(key)
            
            # Traduce valoarea (dacă nu e doar număr)
            if re.match(r'^[\d.,\s\-xX×]+\s*(cm|mm|m|kg|g|L|ml)?$', value):
                translated_value = value
            else:
                translated_value = self._translate_text(value)
            
            translated[translated_key] = translated_value
        
        return translated
    
    def translate_product(self, product: ProductData) -> ProductData:
        """Traduce întregul produs"""
        logger.info(f"Translating product: {product.name}")
        
        # Nume
        product.name_ro = self._translate_text(product.name)
        
        # Descriere
        if product.description:
            product.description_ro = self._translate_text(product.description)
        
        # Specificații
        if product.specifications:
            product.specifications_ro = self.translate_specifications(product.specifications)
        
        # Culori
        for color in product.colors:
            if 'name' in color:
                color['name_ro'] = self.translate_color(color['name'])
        
        # Materiale
        product.materials_ro = [self._translate_text(m) for m in product.materials]
        
        # Categorie
        if product.category:
            product.category_ro = self._translate_text(product.category)
        
        # Meta
        if product.meta_title:
            product.meta_title = self._translate_text(product.meta_title)
        if product.meta_description:
            product.meta_description = self._translate_text(product.meta_description)
        
        logger.info(f"Translation complete: {product.name_ro}")
        return product
