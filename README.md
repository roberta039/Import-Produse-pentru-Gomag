# Gomag Importer (Streamlit + Browser Automation)

Acest proiect:
- citeste un Excel cu link-uri de produse
- extrage automat: titlu, descriere, specificatii, imagini, SKU, pret (cand exista), variante (cand exista)
- afiseaza un **tabel intermediar** in Streamlit pentru verificare/corectare
- genereaza fisier de import Gomag (XLSX)
- optional: ruleaza **browser automation** (Playwright) pentru:
  - login in Gomag Dashboard
  - preluare lista categorii
  - import fisier in Gomag (upload + start import)
