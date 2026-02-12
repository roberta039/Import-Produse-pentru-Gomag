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
- traducere **plugin-based**: dacă există `DEEPL_API_KEY` => DeepL, altfel dacă există `OPENAI_API_KEY` => OpenAI, altfel text original

## Streamlit Secrets (obligatoriu pentru Gomag)
În Streamlit Cloud > Settings > Secrets:

```toml
GOMAG_APIKEY = "xxxx"
GOMAG_APISHOP = "https://rucsacantifurtro.gomag.ro"

# traducere plugin-based (opțional)
DEEPL_API_KEY = "xxxx"
OPENAI_API_KEY = "xxxx"

# opțional
FORCE_PLAYWRIGHT = "0"
```

## Deploy Streamlit Cloud
- urci repo-ul în GitHub
- creezi app în Streamlit Cloud din repo
- adaugi `Secrets`
- Streamlit va rula `postBuild` ca să instaleze Chromium pentru Playwright

## Fix important (Streamlit Cloud)
- NU folosim `lxml` (pe Streamlit Cloud poate pica build-ul din lipsă de libs OS)
- Forțăm Python 3.11 prin `runtime.txt`

## Adăugare furnizori noi
- Majoritatea domeniilor merg cu extractorul generic (`src/extract_generic.py`).
- Dacă un domeniu are structură specială, adaugi fișier YAML în `suppliers/<domeniu>.yaml` cu selectori (titlu, preț, imagini, descriere, sku).
