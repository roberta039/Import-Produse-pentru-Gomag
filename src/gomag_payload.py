from .models import ExtractedProduct

def build_product_payload(p: ExtractedProduct) -> dict:
    payload = {
        "sku": p.sku,
        "name": p.name,
        "description": p.description_html,
        "category_id": p.category_id,
        "price": p.price_ron,
        "stock": p.stock,
        "active": 1 if p.publish_immediately else 0,
        "images": p.images,
        "attributes": p.specs,
    }
    return {k: v for k, v in payload.items() if v is not None}
