from urllib.parse import urlparse

def domain_from_url(url: str) -> str:
    return urlparse(url).netloc.lower()

def normalize_domain(domain: str) -> str:
    d = domain.lower()
    if d.startswith("www."):
        d = d[4:]
    return d
