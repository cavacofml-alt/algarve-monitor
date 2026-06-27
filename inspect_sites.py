#!/usr/bin/env python3
"""
Inspeciona o HTML de cada imobiliária local com Selenium
para descobrir os seletores CSS corretos.
Corre na Consola do Railway: python3 /app/inspect_sites.py
"""
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import time

def get_driver():
    opts = Options()
    for a in ['--headless=new','--no-sandbox','--disable-dev-shm-usage',
              '--disable-gpu','--single-process','--window-size=1920,1080']:
        opts.add_argument(a)
    opts.binary_location = '/usr/bin/chromium'
    return webdriver.Chrome(service=Service('/usr/bin/chromedriver'), options=opts)

def inspect(driver, nome, url, wait=7):
    print(f"\n{'='*55}")
    print(f"🔍 {nome}")
    print(f"   URL: {url}")
    try:
        driver.get(url)
        time.sleep(wait)
        soup = BeautifulSoup(driver.page_source, 'html.parser')

        # Classes relevantes
        classes = set()
        for el in soup.find_all(True):
            for c in el.get('class', []):
                if any(x in c.lower() for x in
                       ['prop','card','item','list','imovel','result',
                        'listing','house','home','real','estate','product']):
                    classes.add(c)

        if classes:
            print(f"   Classes encontradas: {sorted(classes)[:20]}")
        else:
            print("   Nenhuma classe relevante encontrada")

        # Tags com mais conteúdo
        for tag in ['article','li','div']:
            els = soup.find_all(tag, class_=True)
            if els:
                sample = els[0]
                cs = ' '.join(sample.get('class', []))
                txt = sample.get_text(strip=True)[:80]
                print(f"   Primeiro <{tag} class='{cs}'>: {txt}")
                break

        # Links com preços
        precos = [el.get_text(strip=True) for el in soup.find_all(True)
                  if '€' in el.get_text() and len(el.get_text(strip=True)) < 30][:3]
        if precos:
            print(f"   Preços encontrados: {precos}")
        else:
            print("   ⚠️  Nenhum preço (€) encontrado — site pode precisar de mais tempo")

        # Total de texto
        total_text = len(soup.get_text())
        print(f"   Total texto: {total_text} chars | Links: {len(soup.find_all('a'))}")

    except Exception as e:
        print(f"   ERRO: {e}")

print("A iniciar Selenium...")
driver = get_driver()
print("Chrome iniciado!")

sites = [
    ("Casas do Sotavento", "https://www.casasdosotavento.pt/imoveis/venda/"),
    ("AlgarVila",          "https://www.algarvila.com/en-gb/properties"),
    ("Villas Tavira",      "https://www.villastavira.pt/imoveis"),
    ("LNHouse",            "https://www.lnhouse.pt/imoveis"),
    ("Sortami",            "https://www.sortami.pt/imoveis"),
    ("ERA Faro",           "https://www.era.pt/comprar/imoveis/faro/"),
    ("RE/MAX Faro",        "https://www.remax.pt/comprar/faro/"),
    ("KW Portugal",        "https://www.kwportugal.pt/pt/pesquisa/?localizacao=faro&tipo=comprar"),
    ("Engel & Völkers",    "https://www.engelvoelkers.com/pt/en/search/?q=&adType=BUY&country=PRT&city=faro"),
]

for nome, url in sites:
    inspect(driver, nome, url)
    time.sleep(2)

driver.quit()
print("\n✅ Inspeção concluída!")
