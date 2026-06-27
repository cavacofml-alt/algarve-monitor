"""
Script de verificação de URLs — corre na Consola do Railway
Cole este ficheiro em /tmp/test_urls.py e corre: python3 /tmp/test_urls.py
"""
import requests, time
from bs4 import BeautifulSoup

KEY = '3f4c5f24c9dde61ced09d8b9072ffe40'

def scrape(url, via_scraperapi=True):
    try:
        if via_scraperapi and KEY:
            api = f"http://api.scraperapi.com?api_key={KEY}&url={requests.utils.quote(url)}"
            r = requests.get(api, timeout=30)
        else:
            r = requests.get(url, timeout=15, headers={"User-Agent":"Mozilla/5.0"})
        return r.status_code, r.text
    except Exception as e:
        return 0, str(e)

def check(nome, url, seletores, via_scraperapi=True):
    status, html = scrape(url, via_scraperapi)
    soup = BeautifulSoup(html, "html.parser")
    for sel in seletores:
        items = soup.select(sel)
        if items:
            print(f"  ✅ {nome}: {len(items)} items [{sel}] (HTTP {status})")
            return
    # Tentar detetar o que há na página
    links = len(soup.select("a[href]"))
    print(f"  ❌ {nome}: 0 items (HTTP {status}, {links} links) — URL: {url}")

print("=" * 60)
print("Verificação de URLs — Algarve Sotavento")
print("=" * 60)

# ── PORTAIS (via ScraperAPI) ────────────────────────────
print("\n📡 PORTAIS (ScraperAPI):")

check("Idealista apartamentos Faro",
    "https://www.idealista.pt/comprar-casas/faro/com-apartamentos/?preco-max=200000",
    ["article.item","a.item-link"])
time.sleep(2)

check("Idealista moradias Tavira",
    "https://www.idealista.pt/comprar-casas/tavira/com-moradias-e-vivendas/?preco-max=200000",
    ["article.item","a.item-link"])
time.sleep(2)

check("Imovirtual apartamentos Faro",
    "https://www.imovirtual.com/comprar/apartamento/faro/?priceMax=200000&roomsMin=2",
    ["article[data-cy='listing-item']","[data-cy='listing-item-title']"])
time.sleep(2)

check("Imovirtual moradias Tavira",
    "https://www.imovirtual.com/comprar/moradia/tavira/?priceMax=200000&roomsMin=2",
    ["article[data-cy='listing-item']"])
time.sleep(2)

check("Casa SAPO apartamentos Faro",
    "https://casa.sapo.pt/comprar-apartamentos/faro/?precomax=200000&tipologia=T2,T3,T4",
    [".property-info-content",".searchResultProperty",".card"])
time.sleep(2)

check("SuperCasa apartamentos Faro",
    "https://supercasa.pt/comprar-apartamentos/faro/?preco-max=200000&tipologia=T2,T3",
    ["[data-id]",".property-item","article"])
time.sleep(2)

# ── IMOBILIÁRIAS LOCAIS (requests direto) ───────────────
print("\n🏢 IMOBILIÁRIAS LOCAIS (requests direto):")

check("Casas do Sotavento",
    "https://www.casasdosotavento.pt/imoveis/venda/faro/",
    [".property","article",".imovel","[class*='property']"],
    via_scraperapi=False)
time.sleep(1)

check("AlgarVila",
    "https://www.algarvila.com/en-gb/properties",
    [".property","article","[class*='property-card']","[class*='listing']"],
    via_scraperapi=False)
time.sleep(1)

check("Villas Tavira",
    "https://www.villastavira.pt/imoveis",
    [".property","article","[class*='imovel']","[class*='property']"],
    via_scraperapi=False)
time.sleep(1)

check("Imocusto",
    "https://www.imocusto.pt/imoveis/venda",
    [".property","article","[class*='property']",".imovel"],
    via_scraperapi=False)
time.sleep(1)

check("LNHouse",
    "https://www.lnhouse.pt/imoveis",
    [".property","article","[class*='imovel']","[class*='listing']"],
    via_scraperapi=False)
time.sleep(1)

check("Sortami",
    "https://www.sortami.pt/comprar?preco_max=200000&quartos_min=2",
    [".property","article","[class*='property']"],
    via_scraperapi=False)
time.sleep(1)

check("Garvetur",
    "https://www.garvetur.pt/comprar?tipo=apartamento,moradia&preco_max=200000",
    [".property","article","[class*='imovel']","[class*='listing']"],
    via_scraperapi=False)
time.sleep(1)

check("Engel & Völkers",
    "https://www.engelvoelkers.com/pt/en/search/?q=&adType=BUY&realEstateType=APARTMENT,HOUSE&country=PRT&city=faro&priceMax=200000",
    [".ev-property-card","[class*='property-card']","article"],
    via_scraperapi=False)
time.sleep(1)

check("ERA Faro",
    "https://www.era.pt/comprar/imoveis/faro/?preco_max=200000&quartos_min=2",
    [".property-card",".card","article","[class*='property']"],
    via_scraperapi=False)
time.sleep(1)

check("RE/MAX Faro",
    "https://www.remax.pt/comprar/faro/?pricemax=200000&rooms=2",
    [".property-card","article","[class*='listing']","[class*='property']"],
    via_scraperapi=False)
time.sleep(1)

check("KW Portugal Faro",
    "https://www.kwportugal.pt/pt/comprar/faro/?priceMax=200000&rooms=2",
    [".property",".listing-card","article"],
    via_scraperapi=False)

print("\n" + "=" * 60)
print("Verificação concluída!")
