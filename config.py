"""
Configurări globale pentru aplicație
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import Enum

class ScraperType(Enum):
    PROMOBOX = "promobox.com"
    ANDAPRESENT = "andapresent.com"
    PSIPRODUCTFINDER = "psiproductfinder.de"
    STAMINA = "stamina-shop.eu"
    UTTEAM = "utteam.com"
    CLIPPER = "clipperinterall.com"
    MIDOCEAN = "midocean.com"
    PFCONCEPT = "pfconcept.com"
    SIPEC = "sipec.com"
    STRICKER = "stricker-europe.com"
    XDCONNECTS = "xdconnects.com"

@dataclass
class ProductData:
    """Structura pentru datele produsului"""
    source_url: str
    sku: str = ""
    name: str = ""
    name_ro: str = ""
    description: str = ""
    description_ro: str = ""
    specifications: Dict[str, str] = field(default_factory=dict)
    specifications_ro: Dict[str, str] = field(default_factory=dict)
    price: float = 0.0
    currency: str = "EUR"
    images: List[str] = field(default_factory=list)
    local_images: List[str] = field(default_factory=list)
    colors: List[Dict[str, str]] = field(default_factory=list)
    sizes: List[str] = field(default_factory=list)
    variants: List[Dict] = field(default_factory=list)
    category: str = ""
    category_ro: str = ""
    brand: str = ""
    stock: int = 0
    weight: float = 0.0
    dimensions: Dict[str, float] = field(default_factory=dict)
    materials: List[str] = field(default_factory=list)
    materials_ro: List[str] = field(default_factory=list)
    meta_title: str = ""
    meta_description: str = ""
    tags: List[str] = field(default_factory=list)
    extra_data: Dict = field(default_factory=dict)

# Mapping culori EN -> RO
COLOR_TRANSLATIONS = {
    "black": "negru",
    "white": "alb",
    "red": "roșu",
    "blue": "albastru",
    "green": "verde",
    "yellow": "galben",
    "orange": "portocaliu",
    "purple": "mov",
    "pink": "roz",
    "brown": "maro",
    "grey": "gri",
    "gray": "gri",
    "navy": "bleumarin",
    "navy blue": "bleumarin",
    "dark blue": "albastru închis",
    "light blue": "albastru deschis",
    "dark green": "verde închis",
    "light green": "verde deschis",
    "beige": "bej",
    "silver": "argintiu",
    "gold": "auriu",
    "bronze": "bronz",
    "burgundy": "vișiniu",
    "turquoise": "turcoaz",
    "olive": "oliv",
    "coral": "coral",
    "cyan": "cyan",
    "magenta": "magenta",
    "lime": "lime",
    "maroon": "bordo",
    "teal": "teal",
    "khaki": "kaki",
}

# User agents pentru rotație
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
]

# Rate limiting settings
RATE_LIMIT_DELAY = 2  # secunde între requests
MAX_RETRIES = 3
TIMEOUT = 30
