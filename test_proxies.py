#!/usr/bin/env python3
"""
Testa todos os 47 sites com ZenRows e ScrapingBee.
Corre na Consola do Railway: python3 /app/test_proxies.py
"""
import requests, os, time, json
from bs4 import BeautifulSoup
from datetime import datetime

ZKEY = os.getenv("ZENROWS_KEY","")
BKEY = os.getenv("SCRAPINGBEE_KEY","")
PRECO = 250000
QMIN  = 2

def fetch_zenrows(url):
    try:
        r = requests.get("https://api.zenrows.com/v1/", timeout=60, params={
            "url": url, "apikey": ZKEY,
            "js_render": "true", "premium_proxy": "true"
        })
        return r.status_code, r.text
    except Exception as e:
        return 0, str(e)

def fetch_scrapingbee(url):
    try:
        r = requests.get("https://app.scrapingbee.com/api/v1/", timeout=60, params={
            "api_key": BKEY, "url": url,
            "render_js": "true", "premium_proxy": "true"
        })
        return r.status_code, r.text
    except Exception as e:
        return 0, str(e)

def contar_imoveis(html):
    """Conta imóveis encontrados no HTML."""
    if not html or len(html) < 100: return 0, "vazio"
    soup = BeautifulSoup(html, "html.parser")
    # Verifica preços
    precos = [e for e in soup.find_all(True)
              if "€" in e.get_text() and 5 < len(e.get_text(strip=True)) < 30
              and any(c.isdigit() for c in e.get_text())]
    # Verifica artigos/cards
    sels = ["article.item","article[data-cy='listing-item']",".property-info-content",
            "article","[class*='property-card']","[class*='listing-card']",
            "[class*='result-item']",".card"]
    for sel in sels:
        items = soup.select(sel)
        if len(items) > 2:
            return len(items), sel
    if precos:
        return len(precos), "preços €"
    return 0, f"{len(html)} chars"

SITES = [
    # PORTAIS
    ("Idealista apt",    f"https://www.idealista.pt/comprar-casas/faro/com-apartamentos/?preco-max={PRECO}"),
    ("Idealista mor",    f"https://www.idealista.pt/comprar-casas/tavira/com-moradias/?preco-max={PRECO}"),
    ("Imovirtual apt",   f"https://www.imovirtual.com/comprar/apartamento/faro/?priceMax={PRECO}&roomsMin={QMIN}"),
    ("Imovirtual mor",   f"https://www.imovirtual.com/comprar/moradia/tavira/?priceMax={PRECO}&roomsMin={QMIN}"),
    ("Casa SAPO apt",    f"https://casa.sapo.pt/comprar-apartamentos/faro/?precomax={PRECO}&tipologia=T2,T3,T4"),
    ("Casa SAPO mor",    f"https://casa.sapo.pt/comprar-moradias/tavira/?precomax={PRECO}"),
    ("SuperCasa apt",    f"https://supercasa.pt/comprar-casas/faro/com-apartamentos/?preco-max={PRECO}"),
    ("SuperCasa mor",    f"https://supercasa.pt/comprar-casas/tavira/com-moradias/?preco-max={PRECO}"),
    # REDES NACIONAIS
    ("RE/MAX",           f"https://www.remax.pt/comprar/faro/?pricemax={PRECO}&rooms={QMIN}"),
    ("ERA",              f"https://www.era.pt/comprar/imoveis/faro/?preco_max={PRECO}&quartos_min={QMIN}"),
    ("KW Portugal",      f"https://www.kwportugal.pt/pt/pesquisa/?localizacao=faro&tipo=comprar&priceMax={PRECO}"),
    ("Engel & Völkers",  f"https://www.engelvoelkers.com/pt/en/search/?adType=BUY&country=PRT&city=faro&priceMax={PRECO}"),
    ("Coldwell Banker",  f"https://www.coldwellbanker.pt/imoveis?transacao=compra&distrito=faro&preco_max={PRECO}"),
    ("Sotheby's",        f"https://www.sothebysrealty.pt/imoveis/compra?preco_max={PRECO}&distrito=faro"),
    ("IAD Portugal",     f"https://www.iadfrance.pt/comprar/apartamento/algarve?prix_max={PRECO}"),
    ("Fine & Country",   f"https://www.fineandcountry.com/pt/imoveis-para-venda/algarve?max_price={PRECO}"),
    ("Century 21",       f"https://www.century21.pt/imoveis/?local=faro&tipo=comprar&preco_max={PRECO}"),
    ("Chave Nova",       f"https://www.chavanova.pt/imoveis?distrito=faro&tipo=venda&preco_max={PRECO}"),
    ("Arcada",           f"https://www.arcada.com.pt/imoveis?zona=algarve&tipo=venda&preco_max={PRECO}"),
    # ALGARVE REGIÃO
    ("Garvetur",         f"https://www.garvetur.pt/imoveis/venda"),
    ("Villas Key",       f"https://www.villaskey.com/venda?preco_max={PRECO}"),
    ("Dils Portugal",    f"https://www.dils.pt/imoveis?tipo=venda&zona=algarve&preco_max={PRECO}"),
    ("BuyMe Property",   f"https://www.buymeproperty.pt/comprar?preco_max={PRECO}"),
    ("Algarve Property", f"https://www.algarveproperty.com/properties-for-sale?max_price={PRECO}"),
    ("Nurisimo",         f"https://www.nurisimo.com/venda?preco_max={PRECO}"),
    ("Golden Properties",f"https://www.goldenproperties.pt/imoveis?tipo=venda&preco_max={PRECO}"),
    ("Sortami",          f"https://www.sortami.pt/imoveis?preco_max={PRECO}"),
    ("Algarve RE",       f"https://www.algarverealestate.com/properties-for-sale?max_price={PRECO}"),
    ("Espaços Algarve",  f"https://www.espacos-algarve.com/comprar?preco_max={PRECO}"),
    ("Rede Real",        f"https://www.redereal.com/imoveis?tipo=venda&zona=algarve&preco_max={PRECO}"),
    ("D'Alma Port.",     f"https://www.dalmaportuguesa.com/imoveis?preco_max={PRECO}"),
    ("VAP Real Estate",  f"https://www.vaprealestate.com/properties?max_price={PRECO}"),
    ("Tripalgarve",      f"https://www.tripalgarve.com/properties-for-sale?max_price={PRECO}"),
    ("Algarve Dream",    f"https://www.algarvedreamproperty.com/for-sale?max_price={PRECO}"),
    # BARLAVENTO
    ("Mimosa Props",     f"https://www.mimosaproperties.com/properties-for-sale?max_price={PRECO}"),
    ("Algarve Unique",   f"https://www.algarveuniqueproperties.com/for-sale?max_price={PRECO}"),
    ("Boto Properties",  f"https://www.botoproperties.com/properties-for-sale?max_price={PRECO}"),
    ("Vernon Algarve",   f"https://www.vernonalgarve.com/for-sale?max_price={PRECO}"),
    ("Sunpoint Props",   f"https://www.sunpointproperties.com/for-sale?max_price={PRECO}"),
    ("A1 Algarve",       f"https://www.a1-algarve.com/properties?max_price={PRECO}"),
    # TRIÂNGULO DOURADO
    ("QP Savills",       f"https://www.quintaproperty.com/property-for-sale?max_price={PRECO}"),
    ("JPP Properties",   f"https://www.jppproperties.com/buy?max_price={PRECO}"),
    ("Your Luxury Prop", f"https://www.yourluxuryproperty.pt/imoveis-para-venda?preco_max={PRECO}"),
    ("Barra Prime",      f"https://www.barraprime.pt/imoveis-para-venda?preco_max={PRECO}"),
    ("Inside-Villas",    f"https://www.inside-villas.com/for-sale?max_price={PRECO}"),
    ("Cluttons Algarve", f"https://www.cluttons.com/algarve/properties-for-sale?max_price={PRECO}"),
    ("Chestertons",      f"https://www.chestertons.com/algarve/properties-for-sale?max_price={PRECO}"),
    # SOTAVENTO
    ("Casas Sotavento",  f"https://www.casasdosotavento.pt/imoveis/venda/?preco_max={PRECO}"),
    ("AlgarVila",        f"https://www.algarvila.com/en-gb/properties"),
    ("Villas Tavira",    f"https://www.villastavira.pt/imoveis"),
    ("Imocusto",         f"https://www.imocusto.pt/comprar"),
    ("LNHouse",          f"https://www.lnhouse.pt/imoveis"),
]

def main():
    print(f"{'='*65}")
    print(f"Teste de Proxies — {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print(f"ZenRows: {'✅' if ZKEY else '❌'}  ScrapingBee: {'✅' if BKEY else '❌'}")
    print(f"Total de sites: {len(SITES)}")
    print(f"{'='*65}\n")

    resultados = []
    for i, (nome, url) in enumerate(SITES, 1):
        print(f"[{i:02d}/{len(SITES)}] {nome}...", end=" ", flush=True)

        # Alterna entre ZenRows e ScrapingBee
        if i % 2 == 1:
            proxy = "ZenRows"
            status, html = fetch_zenrows(url)
        else:
            proxy = "ScrapingBee"
            status, html = fetch_scrapingbee(url)

        n, detalhe = contar_imoveis(html)
        icone = "✅" if n > 2 else ("⚠️ " if n > 0 else "❌")
        print(f"{icone} {proxy} | HTTP {status} | {n} items [{detalhe}]")

        resultados.append({
            "nome": nome, "proxy": proxy, "status": status,
            "items": n, "detalhe": detalhe, "url": url,
            "ok": n > 2
        })
        time.sleep(2)

    # Resumo
    ok   = [r for r in resultados if r["ok"]]
    nok  = [r for r in resultados if not r["ok"]]
    print(f"\n{'='*65}")
    print(f"✅ Funcionam: {len(ok)}/{len(SITES)}")
    print(f"❌ Sem items: {len(nok)}/{len(SITES)}")
    print(f"\n✅ Sites com imóveis:")
    for r in ok:
        print(f"  • {r['nome']} ({r['proxy']}): {r['items']} items")
    print(f"\n❌ Sites sem imóveis:")
    for r in nok:
        print(f"  • {r['nome']} ({r['proxy']}): HTTP {r['status']} — {r['detalhe']}")

    # Guarda resultado
    with open("/tmp/test_proxies_result.json","w") as f:
        json.dump(resultados, f, ensure_ascii=False, indent=2)
    print(f"\nResultado guardado em /tmp/test_proxies_result.json")
    print(f"{'='*65}")

if __name__ == "__main__":
    main()
