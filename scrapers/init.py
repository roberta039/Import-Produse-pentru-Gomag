"""
Modul de inițializare pentru scrapere
"""

from typing import Optional, Dict
from urllib.parse import urlparse

from .base_scraper import BaseScraper
from .xdconnects_scraper import XDConnectsScraper
from .pfconcept_scraper import PFConceptScraper
from .midocean_scraper import MidoceanScraper
from .promobox_scraper import PromoboxScraper
from .andapresent_scraper import AndaPresentScraper

# Import restul scraperelor (le poți adăuga pe măsură ce le creezi)
# from .psiproductfinder_scraper import PSIProductFinderScraper
# from .stamina_scraper import StaminaScraper
# from .utteam_scraper import UTTeamScraper
# from .clipper_scraper import ClipperScraper
# from .sipec_scraper import SipecScraper
# from .stricker_scraper import StrickerScraper

# Mapping domeniu -> scraper
SCRAPERS = {
    'xdconnects.com': XDConnectsScraper,
    'pfconcept.com': PFConceptScraper,
    'midocean.com': MidoceanScraper,
    'promobox.com': PromoboxScraper,
    'andapresent.com': AndaPresentScraper,
    # Adaugă restul pe măsură ce le implementezi
}

def get_scraper_for_url(url: str, credentials: Optional[Dict[str, str]] = None) -> Optional[BaseScraper]:
    """Returnează scraperul potrivit pentru un URL"""
    parsed = urlparse(url)
    domain = parsed.netloc.replace('www.', '')
    
    # Caută domeniul în mapping
    for scraper_domain, scraper_class in SCRAPERS.items():
        if scraper_domain in domain:
            return scraper_class(credentials)
    
    return None

def get_supported_domains() -> list:
    """Returnează lista domeniilor suportate"""
    return list(SCRAPERS.keys())

__all__ = [
    'get_scraper_for_url',
    'get_supported_domains',
    'BaseScraper',
    'XDConnectsScraper',
    'PFConceptScraper',
    'MidoceanScraper',
    'PromoboxScraper',
    'AndaPresentScraper',
]
