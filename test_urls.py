"""
Script de verificação de URLs v2 — corre na Consola do Railway
python3 /app/test_urls.py
"""
import requests, time
from bs4 import BeautifulSoup

KEY = '3f4c5f24c9dde61ced09d8b9072ffe40'

def check(nome, url, seletores, via_api=True):
    try:
        if via_api and KEY:
            api = f"http://api.scraperapi.com?api_key={KEY}&url={requests.utils.quote(url)}"
            r = requests.get(api, timeout=30)
        else:
            r = requests.get(url, timeout=15, headers={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
        soup = BeautifulSoup(r.text, "html.parser")
        for sel in seletores:
            items = soup.select(sel)
            if items:
                print(f"  ✅ {nome}: {len(items)} items [{sel}] (HTTP {r.status_code})")
                return True
        links = len(soup.select("a[href]"))
        print(f"  ❌ {nome}: 0 items (HTTP {r.status_code}, {links} links)")
        return False
    except Exception as e:
        print(f"  💥 {nome}: ERRO — {e}")
        return False

print("=" * 65)
print("Verificação de URLs v2 — Algarve Sotavento")
print("=" * 65)

print("\n📡 PORTAIS (ScraperAPI):")
check("Idealista apartamentos Faro",
    "https://www.idealista.pt/comprar-casas/faro/com-apartamentos/?preco-max=200000&quartos-min=2",
    ["article.item","a.item-link"])
time.sleep(2)
check("Idealista moradias Tavira",
    "https://www.idealista.pt/comprar-casas/tavira/com-moradias/?preco-max=200000",
    ["article.item","a.item-link"])
time.sleep(2)
check("Imovirtual apartamentos Faro",
    "https://www.imovirtual.com/comprar/apartamento/faro/?priceMax=200000&roomsMin=2",
    ["article[data-cy='listing-item']","[data-cy='listing-item-title']"])
time.sleep(2)
check("Imovirtual moradias Olhão",
    "https://www.imovirtual.com/comprar/moradia/olhao/?priceMax=200000&roomsMin=2",
    ["article[data-cy='listing-item']","[data-cy='listing-item-title']"])
time.sleep(2)
check("Casa SAPO apartamentos Faro",
    "https://casa.sapo.pt/comprar-apartamentos/faro/?precomax=200000&tipologia=T2,T3,T4",
    [".property-info-content",".searchResultProperty"])
time.sleep(2)
check("SuperCasa apartamentos Faro",
    "https://supercasa.pt/comprar-casas/faro/com-apartamentos/?preco-max=200000&quartos-min=2",
    [".property-item","article","[class*='listing']","h2","h3"])
time.sleep(2)

print("\n🏢 IMOBILIÁRIAS LOCAIS (requests direto — sem JS):")
check("Casas do Sotavento",
    "https://www.casasdosotavento.pt/imoveis/venda/?concelho=faro&preco_max=200000",
    [".property","article",".imovel","[class*='card']"], via_api=False)
time.sleep(1)
check("AlgarVila",
    "https://www.algarvila.com/en-gb/properties",
    [".property","article","[class*='property-card']","[class*='listing']"], via_api=False)
time.sleep(1)
check("Villas Tavira",
    "https://www.villastavira.pt/imoveis",
    [".property","article","[class*='property']"], via_api=False)
time.sleep(1)
check("Imocusto",
    "https://www.imocusto.pt/comprar",
    [".property","article","[class*='property']",".imovel"], via_api=False)
time.sleep(1)
check("LNHouse",
    "https://www.lnhouse.pt/imoveis",
    [".property","article","[class*='listing']"], via_api=False)
time.sleep(1)
check("Sortami",
    "https://www.sortami.pt/imoveis?preco_max=200000",
    [".property","article","[class*='property']"], via_api=False)
time.sleep(1)
check("Garvetur",
    "https://www.garvetur.pt/imoveis/venda",
    [".property","article","[class*='listing']"], via_api=False)
time.sleep(1)
check("ERA Faro",
    "https://www.era.pt/comprar/imoveis/faro/?preco_max=200000&quartos_min=2",
    [".property-card",".card","article","[class*='property']"], via_api=False)
time.sleep(1)
check("RE/MAX Faro",
    "https://www.remax.pt/comprar/faro/?pricemax=200000&rooms=2",
    [".property-card","article","[class*='listing']"], via_api=False)
time.sleep(1)
check("KW Portugal",
    "https://www.kwportugal.pt/pt/pesquisa/?localizacao=faro&tipo=comprar&priceMax=200000",
    [".property",".listing-card","article"], via_api=False)
time.sleep(1)
check("Engel & Völkers",
    "https://www.engelvoelkers.com/pt/en/search/?q=&adType=BUY&realEstateType=APARTMENT,HOUSE&country=PRT&city=faro&priceMax=200000",
    [".ev-property-card","[class*='property-card']","article"], via_api=False)

print("\n" + "=" * 65)
