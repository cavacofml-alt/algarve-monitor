#!/usr/bin/env python3
"""
Testa URLs alternativos para os sites que falharam.
Corre na Consola do Railway: python3 /app/fix_urls.py
"""
import os, requests, time, json
from bs4 import BeautifulSoup

ZKEY  = os.getenv("ZENROWS_KEY","")
CKEY  = os.getenv("CRAWLBASE_KEY","")
BKEY  = os.getenv("SCRAPINGBEE_KEY","")

def fetch(url, proxy="crawlbase", timeout=60):
    try:
        if proxy == "crawlbase" and CKEY:
            r = requests.get(f"https://api.crawlbase.com/?token={CKEY}&url={requests.utils.quote(url)}&ajax_wait=true&page_wait=5000", timeout=timeout)
        elif proxy == "zenrows" and ZKEY:
            r = requests.get("https://api.zenrows.com/v1/", timeout=timeout, params={"url":url,"apikey":ZKEY,"js_render":"true","premium_proxy":"true"})
        elif proxy == "scrapingbee" and BKEY:
            r = requests.get("https://app.scrapingbee.com/api/v1/", timeout=timeout, params={"api_key":BKEY,"url":url,"render_js":"true","premium_proxy":"true"})
        else:
            r = requests.get(url, timeout=20, headers={"User-Agent":"Mozilla/5.0"})
        return r.status_code, r.text
    except Exception as e:
        return 0, str(e)

def check(nome, urls, proxy="crawlbase"):
    print(f"\n🔍 {nome}")
    for url in urls:
        status, html = fetch(url, proxy)
        soup = BeautifulSoup(html, "html.parser") if "<" in html else None
        precos = []
        links_imoveis = 0
        items = 0
        if soup:
            precos = [e.get_text(strip=True) for e in soup.find_all(True)
                      if "€" in e.get_text() and 5<len(e.get_text(strip=True))<30 and any(c.isdigit() for c in e.get_text())][:2]
            links_imoveis = len([a for a in soup.select("a[href]") if any(k in a.get("href","").lower() for k in ["imovel","property","casa","buy","sale","venda","comprar"])])
            for sel in ["article",".property","[class*='card']","[class*='listing']","li[class]"]:
                found = soup.select(sel)
                if len(found) > 3: items = len(found); break
        result = "✅" if (items>2 or links_imoveis>5 or len(precos)>1) else ("⚠️" if len(precos)>0 else "❌")
        print(f"  {result} HTTP {status} | {items} items | {links_imoveis} links | preços:{precos[:1]} | {url[:70]}")
        time.sleep(2)

print("="*60)
print("Teste de URLs alternativos — sites com falha")
print("="*60)

# TIMEOUTS — provavelmente URLs errados
check("Garvetur", [
    "https://www.garvetur.pt/imoveis/venda",
    "https://www.garvetur.pt/comprar",
    "https://www.garvetur.pt/en/properties-for-sale",
    "https://www.garvetur.pt/pt/imoveis-venda",
])

check("Villas Key", [
    "https://www.villaskey.com/venda?preco_max=250000",
    "https://www.villaskey.com/en/for-sale",
    "https://www.villaskey.com/properties-for-sale",
    "https://www.villaskey.com/buy",
])

check("Sotheby's", [
    "https://www.sothebysrealty.pt/imoveis/compra",
    "https://www.sothebysrealty.pt/en/buy",
    "https://www.sothebysrealty.pt/properties",
    "https://www.sothebysrealty.pt/buy/algarve",
])

check("IAD Portugal", [
    "https://www.iadfrance.pt/comprar/apartamento/algarve",
    "https://www.iadportugal.pt/comprar",
    "https://www.iad.pt/comprar",
    "https://www.iadfrance.pt/pt/comprar/apartamento/algarve",
])

check("Chave Nova", [
    "https://www.chavanova.pt/imoveis?distrito=faro&tipo=venda",
    "https://www.chavanova.pt/comprar/algarve",
    "https://www.chavanova.pt/imoveis-para-venda/algarve",
    "https://www.chavanova.pt/en/properties/algarve",
])

check("D'Alma Portuguesa", [
    "https://www.dalmaportuguesa.com/imoveis",
    "https://www.dalmaportuguesa.com/comprar",
    "https://www.dalmaportuguesa.com/en/for-sale",
    "https://www.dalmaportuguesa.pt/imoveis",
])

check("Tripalgarve", [
    "https://www.tripalgarve.com/properties-for-sale",
    "https://www.tripalgarve.com/en/buy",
    "https://www.tripalgarve.com/comprar",
    "https://tripalgarve.com/properties",
])

check("Vernon Algarve", [
    "https://www.vernonalgarve.com/for-sale",
    "https://www.vernonalgarve.com/properties",
    "https://www.vernonalgarve.com/buy",
    "https://www.vernonalgarve.com/en/properties-for-sale",
])

check("QP Savills", [
    "https://www.quintaproperty.com/property-for-sale",
    "https://www.quintaproperty.com/en/buy",
    "https://www.qpsavills.com/properties",
    "https://www.quintaproperty.com/properties",
])

print("\n" + "="*60)
print("HTTP 200 sem conteúdo — a tentar com wait maior")
print("="*60)

# HTTP 200 sem conteúdo — tentar com mais tempo de espera
check("Coldwell Banker", [
    "https://www.coldwellbanker.pt/imoveis?transacao=compra&distrito=faro",
    "https://www.coldwellbanker.pt/comprar/algarve",
    "https://www.coldwellbanker.pt/en/buy/algarve",
])

check("Sortami", [
    "https://www.sortami.pt/imoveis",
    "https://www.sortami.pt/comprar",
    "https://www.sortami.pt/en/for-sale",
    "https://www.sortami.pt/imoveis/venda",
])

check("Nurisimo", [
    "https://www.nurisimo.com/venda",
    "https://www.nurisimo.com/comprar",
    "https://www.nurisimo.com/en/for-sale",
    "https://www.nurisimo.com/properties",
])

check("Golden Properties", [
    "https://www.goldenproperties.pt/imoveis?tipo=venda",
    "https://www.goldenproperties.pt/comprar",
    "https://www.goldenproperties.pt/en/buy",
    "https://www.goldenproperties.pt/venda",
])

check("Imocusto", [
    "https://www.imocusto.pt/comprar",
    "https://www.imocusto.pt/imoveis/venda",
    "https://www.imocusto.pt/venda",
    "https://www.imocusto.pt/imoveis?tipo=venda",
])

check("Mimosa Properties", [
    "https://www.mimosaproperties.com/properties-for-sale",
    "https://www.mimosaproperties.com/buy",
    "https://www.mimosaproperties.com/en/for-sale",
    "https://www.mimosaproperties.com/properties",
])

check("Chestertons Algarve", [
    "https://www.chestertons.com/algarve/properties-for-sale",
    "https://www.chestertons.com/en/algarve/for-sale",
    "https://www.chestertons.pt/imoveis/venda/algarve",
    "https://www.chestertons.com/en-gb/algarve/property-for-sale",
])

print("\n✅ Teste concluído!")
