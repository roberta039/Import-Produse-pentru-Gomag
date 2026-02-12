import requests

def _translate_deepl(text: str, api_key: str) -> str:
    # DeepL Free/Pro endpoint
    url = "https://api-free.deepl.com/v2/translate"
    # dacă ai Pro, schimbă în: https://api.deepl.com/v2/translate
    r = requests.post(url, data={
        "auth_key": api_key,
        "text": text,
        "target_lang": "RO",
    }, timeout=60)
    r.raise_for_status()
    data = r.json()
    return data["translations"][0]["text"]

def _translate_openai(text: str, api_key: str, model: str = "gpt-4o-mini") -> str:
    # Minimal OpenAI Responses API call (manual HTTP) to avoid extra deps.
    # NOTE: if you prefer official SDK, add it to requirements and refactor.
    url = "https://api.openai.com/v1/responses"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "input": [
            {"role": "system", "content": "Tradu în limba română. Păstrează brandurile și codurile neschimbate. Nu inventa specificații."},
            {"role": "user", "content": text}
        ],
        "temperature": 0.2
    }
    r = requests.post(url, headers=headers, json=payload, timeout=90)
    r.raise_for_status()
    data = r.json()
    # responses API returns output array
    out = ""
    for item in data.get("output", []):
        for c in item.get("content", []):
            if c.get("type") == "output_text":
                out += c.get("text", "")
    return out.strip() or text

def translate_to_ro(text: str, secrets: dict) -> str:
    # plugin-based: DeepL first, then OpenAI, else passthrough.
    if not text:
        return text

    deepl = secrets.get("DEEPL_API_KEY")
    if deepl:
        try:
            return _translate_deepl(text, deepl)
        except Exception:
            pass

    openai_key = secrets.get("OPENAI_API_KEY")
    if openai_key:
        try:
            return _translate_openai(text, openai_key)
        except Exception:
            pass

    return text
