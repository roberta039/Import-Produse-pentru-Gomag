from .models import ExtractedProduct

def build_product_payload(p: ExtractedProduct) -> dict:
    """
    Un singur loc unde ajustezi mapping-ul pentru Gomag.

    Notă:
    - Gomag Public API are `product/write` și `product/patch`.
    - Schema exactă poate diferi în funcție de setările magazinului / versiune.
    - Dacă primești erori de câmpuri, ajustezi aici.
    """

    payload = {
        # Identificare
        "sku": p.sku,
        "name": p.name,

        # Conținut
        "description": p.description_html,

        # Organizare
        "category_id": p.category_id,

        # Comercial
        "price": p.price_ron,
        "stock": p.stock,

        # Vizibilitate (în funcție de API; unele magazine folosesc 'active'/'status')
        "active": 1 if p.publish_immediately else 0,

        # Imagini: de regulă listă de URL-uri; dacă API cere alt format, ajustezi aici.
        "images": p.images,

        # Atribute/specs (dacă API suportă direct)
        "attributes": p.specs,
    }

    # curățare valori None
    return {k: v for k, v in payload.items() if v is not None}
