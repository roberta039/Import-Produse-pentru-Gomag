# Gomag Product Importer (Streamlit + GitHub)

Import produse în Gomag dintr-un Excel cu o singură coloană: `url`.

## Ce face aplicația (conform cerințelor tale)
- ia produsul din URL (titlu, descriere, specificații, imagini, SKU, preț – când există)
- **SKU**: încearcă din pagină (JSON-LD / text), apoi din URL, apoi fallback determinist `IMP-<hash>`
- **preț**: preț furnizor convertit în RON (EUR/GBP/RON) × **2** (+100%) și rotunjit **în sus** la **x.90**
  - dacă NU găsește preț: **1 RON**
- **stoc**: 1
- **vizibil imediat**: importă produsul ca activ/publicat (în limita câmpurilor acceptate de Gomag API)
- categorii: citește din Gomag, poți selecta și poți crea categorie nouă din UI
- scraping: `requests` + fallback `playwright` pentru site-uri cu JS

## Necesare (Streamlit Secrets)
În Streamlit Cloud > Settings > Secrets:

```toml
GOMAG_APIKEY = "xxxx"
GOMAG_APISHOP = "https://rucsacantifurtro.gomag.ro"

# traducere plugin-based (opțional):
# dacă există DEEPL_API_KEY => folosește DeepL
# altfel dacă există OPENAI_API_KEY => folosește OpenAI
DEEPL_API_KEY = "xxxx"
OPENAI_API_KEY = "xxxx"

# opțional, dacă vrei să forțezi playwright mereu:
FORCE_PLAYWRIGHT = "0"
```

### Observație despre Gomag API payload
Gomag Public API are endpoint-uri precum `category/read`, `category/write`, `product/write`, `product/patch` etc. Documentația e în Postman / apidocs.
- https://www.postman.com/gomagro/gomag-public-api/documentation/16119071-aafd8c5f-343f-446e-9a9d-bc86fee8585f
- https://apidocs.gomag.ro/

Diferite magazine pot avea setări/valideări diferite. În `src/gomag_api.py` și `src/gomag_payload.py` ai un singur loc unde ajustezi mapping-ul câmpurilor dacă e nevoie.

## Rulare locală (opțional)
```bash
pip install -r requirements.txt
playwright install chromium
streamlit run app.py
```

## Deploy Streamlit Cloud
- urci repo-ul în GitHub
- creezi app în Streamlit Community Cloud din repo
- adaugi `Secrets` (vezi mai sus)
- Streamlit va rula `postBuild` ca să instaleze Chromium pentru Playwright

## Adăugare furnizori noi
- Majoritatea domeniilor merg cu extractorul generic (`src/extract_generic.py`).
- Dacă un domeniu are structură specială, adaugi fișier YAML în `suppliers/<domeniu>.yaml` cu selectori (titlu, preț, imagini, descriere, sku).
  Exemple: `suppliers/andapresent.com.yaml`, `suppliers/xdconnects.com.yaml`.

## Output / debugging
- UI arată un tabel cu status per URL
- logurile apar în consola Streamlit (și în UI la “Show details”)
