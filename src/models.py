from dataclasses import dataclass, field
from typing import Optional, Dict, List

@dataclass
class ExtractedProduct:
    url: str
    name: str
    sku: str
    description_html: str = ""
    specs: Dict[str, str] = field(default_factory=dict)
    images: List[str] = field(default_factory=list)
    source_price_value: Optional[float] = None
    source_price_currency: Optional[str] = None

    # computed
    price_ron: float = 1.0
    stock: int = 1
    category_id: Optional[int] = None
    publish_immediately: bool = True
