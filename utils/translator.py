from deep_translator import GoogleTranslator

class Translator:
    def __init__(self, source='en', target='ro'):
        self.translator = GoogleTranslator(source=source, target=target)
    
    def translate_product(self, product):
        """Traduce câmpurile produsului"""
        if product.get('name'):
            product['name'] = self.translator.translate(product['name'])
        
        if product.get('description'):
            product['description'] = self.translator.translate(product['description'])
        
        return product
