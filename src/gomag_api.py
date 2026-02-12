import requests

class GomagClient:
    BASE = "https://api.gomag.ro/api/v1"

    def __init__(self, apikey: str, apishop: str):
        self.apikey = apikey
        self.apishop = apishop.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "Apikey": self.apikey,
            "ApiShop": self.apishop,
            "User-Agent": "Mozilla/5.0 (Gomag Importer)",
            "Content-Type": "application/json",
        })

    def _post(self, path: str, payload: dict):
        url = f"{self.BASE}/{path}/json"
        r = self.session.post(url, json=payload, timeout=90)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, dict) and data.get("error"):
            raise RuntimeError(f"Gomag API error: {data}")
        return data.get("data", data) if isinstance(data, dict) else data

    def category_read(self, limit: int = 5000):
        return self._post("category/read", {"limit": limit})

    def category_write(self, name: str, parent_id: int | None = None):
        payload = {"name": name}
        if parent_id is not None:
            payload["parent_id"] = parent_id
        return self._post("category/write", payload)

    def product_write(self, payload: dict):
        return self._post("product/write", payload)
