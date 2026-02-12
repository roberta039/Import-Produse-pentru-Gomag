from urllib.parse import urlparse

def domain_from_url(url: str) -> str:
    netloc = urlparse(url).netloc.lower()
    return netloc

def normalize_domain(domain: str) -> str:
    d = domain.lower()
    if d.startswith("www."):
        d = d[4:]
    return d
