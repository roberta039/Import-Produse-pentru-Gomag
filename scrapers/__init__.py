from .base_scraper import BaseScraper, Product, ProductVariant
from .xdconnects_scraper import XDConnectsScraper
from .pfconcept_scraper import PFConceptScraper
from .midocean_scraper import MidoceanScraper
from .promobox_scraper import PromoboxScraper
from .andapresent_scraper import AndaPresentScraper
from .stamina_scraper import StaminaScraper
from .utteam_scraper import UTTeamScraper
from .sipec_scraper import SipecScraper
from .stricker_scraper import StrickerScraper
from .clipper_scraper import ClipperScraper
from .psi_scraper import PSIScraper

class ScraperFactory:
    """Factory to get the appropriate scraper for a URL"""
    
    scrapers = [
        XDConnectsScraper(),
        PFConceptScraper(),
        MidoceanScraper(),
        PromoboxScraper(),
        AndaPresentScraper(),
        StaminaScraper(),
        UTTeamScraper(),
        SipecScraper(),
        StrickerScraper(),
        ClipperScraper(),
        PSIScraper(),
    ]
    
    @classmethod
    def get_scraper(cls, url: str) -> BaseScraper:
        """Get the appropriate scraper for a URL"""
        for scraper in cls.scrapers:
            if scraper.can_handle(url):
                return scraper
        return None
    
    @classmethod
    def scrape_url(cls, url: str) -> Product:
        """Scrape a product from URL"""
        scraper = cls.get_scraper(url)
        if scraper:
            return scraper.scrape(url)
        return None
