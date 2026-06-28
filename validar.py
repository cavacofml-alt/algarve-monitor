#!/usr/bin/env python3
"""
Validação Completa — Monitor Imóveis Algarve
=============================================
Testa todos os 47 sites com todos os proxies disponíveis
(ScraperAPI, ZenRows, ScrapingBee) e requests direto como fallback.

Corre na Consola do Railway:
    python3 /app/validar.py

Resultados:
  ✅ Funciona — encontrou imóveis
  ⚠️  Abre mas sem imóveis — URL pode estar errado
  ❌ Bloqueado — 403/captcha mesmo com proxy
  💥 Erro — timeout ou outro erro
"""
import os, requests, time, json
from bs4 import BeautifulSoup
from datetime import datetime

# ── CHAVES ───────────────────────────────────────────────
SCRAPERAPI_KEY = os.getenv("SCRAPERAPI_KEY","")
ZENROWS_KEY    = os.getenv("ZENROWS_KEY","")
SCRAPINGBEE_KEY= os.getenv("SCRAPINGBEE_KEY","")
CRAWLBASE_KEY  = os.getenv("CRAWLBASE_KEY","")
SCRAPEDO_KEY   = os.getenv("SCRAPEDO_KEY","")

PRECO_MAX   = 250000
QUARTOS_MIN = 2

# ── PROXIES ───────────────────────────────────────────────
def fetch_scraperapi(url, render=True):
    rp = "&render=true&wait=3000" if render else ""
    api = f"http://api.scraperapi.com?api_key={SCRAPERAPI_KEY}&url={requests.utils.quote(url)}{rp}"
    r = requests.get(api, timeout=60)
    return r.status_code, r.text

def fetch_zenrows(url):
    r = requests.get("https://api.zenrows.com/v1/", timeout=60, params={
        "url": url, "apikey": ZENROWS_KEY,
        "js_render": "true", "premium_proxy": "true"
    })
    return r.status_code, r.text

def fetch_scrapingbee(url):
    r = requests.get("https://app.scrapingbee.com/api/v1/", timeout=60, params={
        "api_key": SCRAPINGBEE_KEY, "url": url,
        "render_js": "true", "premium_proxy": "true"
    })
    return r.status_code, r.text

def fetch_crawlbase(url):
    r = requests.get(
        f"https://api.crawlbase.com/?token={CRAWLBASE_KEY}&url={requests.utils.quote(url)}&ajax_wait=true&page_wait=3000",
        timeout=60)
    return r.status_code, r.text

def fetch_scrapedo(url):
    r = requests.get(
        f"https://api.scrape.do?token={SCRAPEDO_KEY}&url={requests.utils.quote(url)}&render=true",
        timeout=60)
    return r.status_code, r.text

def fetch_direto(url):
    r = requests.get(url, timeout=15, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    })
    return r.status_code, r.text

def melhor_fetch(url):
    """Usa o melhor proxy disponível com fallback automático."""
    proxies = []
    if SCRAPERAPI_KEY: proxies.append(("ScraperAPI", lambda u: fetch_scraperapi(u)))
    if ZENROWS_KEY:    proxies.append(("ZenRows",    lambda u: fetch_zenrows(u)))
    if SCRAPINGBEE_KEY:proxies.append(("ScrapingBee",lambda u: fetch_scrapingbee(u)))
    if CRAWLBASE_KEY:  proxies.append(("Crawlbase",  lambda u: fetch_crawlbase(u)))
    if SCRAPEDO_KEY:   proxies.append(("Scrape.do",  lambda u: fetch_scrapedo(u)))
    proxies.append(("Direto", lambda u: fetch_direto(u)))

    for nome_proxy, fn in proxies:
        try:
            status, html = fn(url)
            if status == 200 and len(html) > 1000:
                return nome_proxy, status, html
            elif status not in [200, 403]:
                continue
        except Exception as e:
            continue
    return "Falhou", 0, ""

# ── ANÁLISE DE HTML ───────────────────────────────────────
SELETORES_IMOVEIS = [
    "article.item", "article[data-cy='listing-item']",
    ".property-info-content", ".searchResultProperty",
    "article", "[class*='property-card']", "[class*='listing-card']",
    "[class*='result-item']", ".card-anchor", ".card",
]

def analisar(html, url):
    """Verifica se a página tem imóveis e retorna contagem."""
    if not html or len(html) < 500:
        return 0, "resposta vazia"
    soup = BeautifulSoup(html, "html.parser")
    # Tenta seletores específicos
    for sel in SELETORES_IMOVEIS:
        items = soup.select(sel)
        if len(items) > 2:
            return len(items), sel
    # Verifica preços em euros
    precos = [e.get_text(strip=True) for e in soup.find_all(True)
              if "€" in e.get_text()
              and 5 < len(e.get_text(strip=True)) < 30
              and any(c.isdigit() for c in e.get_text())]
    if precos:
        return len(precos), f"preços: {precos[:2]}"
    # Links de imóveis
    keywords = ["imovel","property","casa","apartamento","moradia","villa","comprar","buy","sale","venda"]
    links = [a.get("href","") for a in soup.select("a[href]")
             if any(k in a.get("href","").lower() for k in keywords)
             and len(a.get("href","")) > 20]
    if len(links) > 5:
        return len(links), f"{len(links)} links imóveis"
    return 0, f"sem conteúdo ({len(html)} chars)"

# ── LISTA DE TODOS OS SITES ───────────────────────────────
SITES = [
    # ── PORTAIS AGREGADORES ──────────────────────────────
    ("📡 PORTAIS", [
        ("Idealista apartamentos Faro",
         f"https://www.idealista.pt/comprar-casas/faro/com-apartamentos/?preco-max={PRECO_MAX}&quartos-min={QUARTOS_MIN}"),
        ("Idealista moradias Tavira",
         f"https://www.idealista.pt/comprar-casas/tavira/com-moradias/?preco-max={PRECO_MAX}"),
        ("Idealista apartamentos Olhão",
         f"https://www.idealista.pt/comprar-casas/olhao/com-apartamentos/?preco-max={PRECO_MAX}"),
        ("Imovirtual apartamentos Faro",
         f"https://www.imovirtual.com/comprar/apartamento/faro/?priceMax={PRECO_MAX}&roomsMin={QUARTOS_MIN}"),
        ("Imovirtual moradias Tavira",
         f"https://www.imovirtual.com/comprar/moradia/tavira/?priceMax={PRECO_MAX}&roomsMin={QUARTOS_MIN}"),
        ("Casa SAPO apartamentos Faro",
         f"https://casa.sapo.pt/comprar-apartamentos/faro/?precomax={PRECO_MAX}&tipologia=T2,T3,T4"),
        ("Casa SAPO moradias Tavira",
         f"https://casa.sapo.pt/comprar-moradias/tavira/?precomax={PRECO_MAX}"),
        ("SuperCasa apartamentos Faro",
         f"https://supercasa.pt/comprar-casas/faro/com-apartamentos/?preco-max={PRECO_MAX}"),
        ("SuperCasa moradias Castro Marim",
         f"https://supercasa.pt/comprar-casas/castro-marim/com-moradias/?preco-max={PRECO_MAX}"),
    ]),

    # ── REDES NACIONAIS/INTERNACIONAIS ───────────────────
    ("🏢 REDES NACIONAIS", [
        ("RE/MAX Faro",
         f"https://www.remax.pt/comprar/faro/?pricemax={PRECO_MAX}&rooms={QUARTOS_MIN}"),
        ("ERA Faro",
         f"https://www.era.pt/comprar/imoveis/faro/?preco_max={PRECO_MAX}&quartos_min={QUARTOS_MIN}"),
        ("KW Portugal Faro",
         f"https://www.kwportugal.pt/pt/pesquisa/?localizacao=faro&tipo=comprar&priceMax={PRECO_MAX}"),
        ("Engel & Völkers Faro",
         f"https://www.engelvoelkers.com/pt/en/search/?adType=BUY&country=PRT&city=faro&priceMax={PRECO_MAX}"),
        ("Coldwell Banker",
         "https://www.coldwellbanker.pt/imoveis?transacao=compra&distrito=faro"),
        ("Sotheby's [BLOQUEADO]",
         f"https://www.sothebysrealty.pt/imoveis/compra?preco_max={PRECO_MAX}&distrito=faro"),
        ("IAD Portugal",
         "https://www.iadportugal.pt/comprar"),
        ("Fine & Country",
         f"https://www.fineandcountry.com/pt/imoveis-para-venda/algarve?max_price={PRECO_MAX}"),
        ("Century 21",
         f"https://www.century21.pt/imoveis/?local=faro&tipo=comprar&preco_max={PRECO_MAX}"),
        ("Chave Nova [BLOQUEADO]",
         f"https://www.chavanova.pt/imoveis?distrito=faro&tipo=venda&preco_max={PRECO_MAX}"),
        ("Arcada Imobiliária",
         f"https://www.arcada.com.pt/imoveis?zona=algarve&tipo=venda&preco_max={PRECO_MAX}"),
    ]),

    # ── ALGARVE TODA A REGIÃO ─────────────────────────────
    ("🌍 ALGARVE — TODA A REGIÃO", [
        ("Garvetur [BLOQUEADO]",
         f"https://www.garvetur.pt/imoveis/venda"),
        ("Villas Key [BLOQUEADO]",
         f"https://www.villaskey.com/venda?preco_max={PRECO_MAX}"),
        ("Dils Portugal",
         f"https://www.dils.pt/imoveis?tipo=venda&zona=algarve&preco_max={PRECO_MAX}"),
        ("BuyMe Property",
         f"https://www.buymeproperty.pt/comprar?preco_max={PRECO_MAX}"),
        ("Algarve Property",
         f"https://www.algarveproperty.com/properties-for-sale?max_price={PRECO_MAX}"),
        ("Nurisimo",
         "https://www.nurisimo.com/properties"),
        ("Golden Properties",
         "https://www.goldenproperties.pt/imoveis?tipo=venda"),
        ("Sortami [BLOQUEADO]",
         f"https://www.sortami.pt/imoveis?preco_max={PRECO_MAX}"),
        ("Algarve Real Estate",
         f"https://www.algarverealestate.com/properties-for-sale?max_price={PRECO_MAX}"),
        ("Espaços Algarve",
         f"https://www.espacos-algarve.com/comprar?preco_max={PRECO_MAX}"),
        ("Rede Real",
         f"https://www.redereal.com/imoveis?tipo=venda&zona=algarve&preco_max={PRECO_MAX}"),
        ("D'Alma Portuguesa [BLOQUEADO]",
         f"https://www.dalmaportuguesa.com/imoveis?preco_max={PRECO_MAX}"),
        ("VAP Real Estate",
         f"https://www.vaprealestate.com/properties?max_price={PRECO_MAX}"),
        ("Tripalgarve",
         "https://tripalgarve.com/properties"),
        ("Algarve Dream Property [BLOQUEADO]",
         f"https://www.algarvedreamproperty.com/for-sale?max_price={PRECO_MAX}"),
    ]),

    # ── BARLAVENTO ───────────────────────────────────────
    ("🌊 BARLAVENTO", [
        ("Mimosa Properties [BLOQUEADO]",
         f"https://www.mimosaproperties.com/properties-for-sale?max_price={PRECO_MAX}&bedrooms={QUARTOS_MIN}"),
        ("Algarve Unique Properties [BLOQUEADO]",
         f"https://www.algarveuniqueproperties.com/for-sale?max_price={PRECO_MAX}"),
        ("Boto Properties [BLOQUEADO]",
         f"https://www.botoproperties.com/properties-for-sale?max_price={PRECO_MAX}"),
        ("Vernon Algarve [BLOQUEADO]",
         f"https://www.vernonalgarve.com/for-sale?max_price={PRECO_MAX}"),
        ("Sunpoint Properties [BLOQUEADO]",
         f"https://www.sunpointproperties.com/for-sale?max_price={PRECO_MAX}"),
        ("A1 Algarve",
         f"https://www.a1-algarve.com/properties?max_price={PRECO_MAX}"),
    ]),

    # ── TRIÂNGULO DOURADO ────────────────────────────────
    ("🏌️ TRIÂNGULO DOURADO", [
        ("QP Savills",
         "https://www.quintaproperty.com/en/buy"),
        ("JPP Properties",
         f"https://www.jppproperties.com/buy?max_price={PRECO_MAX}&bedrooms={QUARTOS_MIN}"),
        ("Your Luxury Property [BLOQUEADO]",
         f"https://www.yourluxuryproperty.pt/imoveis-para-venda?preco_max={PRECO_MAX}"),
        ("Barra Prime [BLOQUEADO]",
         f"https://www.barraprime.pt/imoveis-para-venda?preco_max={PRECO_MAX}"),
        ("Inside-Villas",
         f"https://www.inside-villas.com/for-sale?max_price={PRECO_MAX}&bedrooms={QUARTOS_MIN}"),
        ("Cluttons Algarve",
         f"https://www.cluttons.com/algarve/properties-for-sale?max_price={PRECO_MAX}"),
        ("Chestertons Algarve",
         "https://www.chestertons.com/algarve/properties-for-sale"),
    ]),

    # ── SOTAVENTO ────────────────────────────────────────
    ("🏛️ SOTAVENTO", [
        ("Casas do Sotavento",
         f"https://www.casasdosotavento.pt/imoveis/venda/?preco_max={PRECO_MAX}"),
        ("AlgarVila Tavira",
         f"https://www.algarvila.com/en-gb/properties"),
        ("Villas Tavira",
         f"https://www.villastavira.pt/imoveis"),
        ("Imocusto VRSA",
         "https://www.imocusto.pt/venda"),
        ("LNHouse VRSA",
         f"https://www.lnhouse.pt/imoveis"),
    ]),
]

# ── MAIN ─────────────────────────────────────────────────
def main():
    total = sum(len(s) for _,s in SITES)
    proxies_ativos = []
    if SCRAPERAPI_KEY: proxies_ativos.append("ScraperAPI")
    if ZENROWS_KEY:    proxies_ativos.append("ZenRows")
    if SCRAPINGBEE_KEY:proxies_ativos.append("ScrapingBee")
    if CRAWLBASE_KEY:  proxies_ativos.append("Crawlbase")
    if SCRAPEDO_KEY:   proxies_ativos.append("Scrape.do")

    print(f"{'='*65}")
    print(f"Validação Completa — {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print(f"Proxies: {', '.join(proxies_ativos) or 'Nenhum — requests direto'}")
    print(f"Total de URLs: {total}")
    print(f"{'='*65}")

    todos_resultados = []
    i = 0

    for grupo, sites in SITES:
        print(f"\n{grupo}")
        print("─" * 55)
        for nome, url in sites:
            i += 1
            print(f"  [{i:02d}/{total}] {nome}...", end=" ", flush=True)
            try:
                proxy_usado, status, html = melhor_fetch(url)
                n, detalhe = analisar(html, url)
                if n > 2:
                    icone = "✅"
                elif n > 0:
                    icone = "⚠️ "
                elif status == 403:
                    icone = "❌"
                    detalhe = "Bloqueado (403)"
                elif status == 404:
                    icone = "❌"
                    detalhe = "URL não existe (404)"
                elif status == 0:
                    icone = "💥"
                    detalhe = "Timeout/Erro"
                else:
                    icone = "❌"
                    detalhe = f"HTTP {status} sem conteúdo"
                print(f"{icone} [{proxy_usado}] {detalhe}")
                todos_resultados.append({
                    "nome": nome, "grupo": grupo, "url": url,
                    "proxy": proxy_usado, "status": status,
                    "items": n, "detalhe": detalhe,
                    "ok": n > 2
                })
            except Exception as e:
                print(f"💥 Erro: {e}")
                todos_resultados.append({
                    "nome": nome, "grupo": grupo, "url": url,
                    "proxy": "erro", "status": 0,
                    "items": 0, "detalhe": str(e), "ok": False
                })
            time.sleep(2)

    # ── RESUMO ───────────────────────────────────────────
    ok   = [r for r in todos_resultados if r["ok"]]
    warn = [r for r in todos_resultados if not r["ok"] and r["items"] > 0]
    nok  = [r for r in todos_resultados if not r["ok"] and r["items"] == 0]

    print(f"\n{'='*65}")
    print(f"RESUMO FINAL")
    print(f"{'='*65}")
    print(f"  ✅ Funcionam:    {len(ok)}/{total}")
    print(f"  ⚠️  Parciais:    {len(warn)}/{total}")
    print(f"  ❌ Sem imóveis: {len(nok)}/{total}")

    if ok:
        print(f"\n✅ SITES COM IMÓVEIS ({len(ok)}):")
        for r in ok:
            print(f"  • {r['nome']}: {r['items']} items via {r['proxy']}")

    if warn:
        print(f"\n⚠️  SITES PARCIAIS ({len(warn)}):")
        for r in warn:
            print(f"  • {r['nome']}: {r['detalhe']}")

    if nok:
        print(f"\n❌ SITES SEM IMÓVEIS ({len(nok)}):")
        for r in nok:
            print(f"  • {r['nome']}: {r['detalhe']}")

    # Guarda resultado
    with open("/tmp/validacao.json","w") as f:
        json.dump(todos_resultados, f, ensure_ascii=False, indent=2)
    print(f"\n💡 SUGESTÃO: Sites com timeout ou sem conteúdo podem ser desativados")
    print(f"   para poupar créditos. Edita SCRAPERS_DESATIVADOS no algarve_monitor.py")
    print(f"\n📄 Resultado completo: /tmp/validacao.json")
    print(f"{'='*65}")

if __name__ == "__main__":
    main()
