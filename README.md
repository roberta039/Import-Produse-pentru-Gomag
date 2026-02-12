# 🛒 Import Automatizat Produse în Gomag

Aplicație Streamlit pentru importul automatizat de produse din diverse surse în platforma Gomag.

## ✨ Funcționalități

- 📤 Upload link-uri din Excel/CSV sau manual
- 🔍 Scraping automat cu CloudScraper (bypass Cloudflare)
- 🌍 Traducere automată în română
- 📁 Gestionare categorii Gomag
- 🚀 Import automat în Gomag
- 📊 Raportare și export

## 🌐 Site-uri Suportate

- xdconnects.com
- pfconcept.com
- midocean.com
- promobox.com
- andapresent.com
- psiproductfinder.de
- stamina-shop.eu
- utteam.com
- clipperinterall.com
- sipec.com
- stricker-europe.com

## 🚀 Instalare

### Local

```bash
# Clonează repository
git clone https://github.com/username/product-importer.git
cd product-importer

# Creează environment virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# Instalează dependențele
pip install -r requirements.txt

# Configurează secrets
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# Editează secrets.toml cu credențialele tale

# Rulează aplicația
streamlit run app.py
