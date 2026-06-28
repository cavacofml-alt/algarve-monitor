#!/usr/bin/env python3
"""
Validação de URLs — todas as imobiliárias
Testa cada site e reporta quais funcionam e quais bloqueiam.
Corre na Consola do Railway: python3 /app/validar_imobiliarias.py

Resultados:
  ✅ Funciona — encontrou imóveis
  ⚠️  Abre mas sem imóveis — URL errado ou seletores CSS desatualizados
  ❌ Bloqueado — site bloqueia o scraper (403/captcha)
  💥 Erro — timeout ou outro erro
"""
import os, requests, time, json
from bs4 import BeautifulSoup
from datetime import datetime

KEY = os.getenv("SCRAPERAPI_KEY","")
PRECO_MAX   = 250000
QUARTOS_MIN = 2

def fetch(url, render=True, timeout=45):
    """Faz pedido via ScraperAPI."""
    try:
        if KEY:
            render_param = "&render=true&wait=3000" if render else ""
            api = f"http://api.scraperapi.com?api_key={KEY}&url={requests.utils.quote(url)}{render_param}"
            r = requests.get(api, timeout=timeout)
        else:
            r = requests.get(url, timeout=15,
                headers={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
        return r.status_code, r.text
    except Exception as e:
        return 0, str(e)

def tem_imoveis(html, url):
    """Verifica se a página tem imóveis."""
    soup = BeautifulSoup(html, "html.parser")

    # Verifica preços em euros
    precos = [e.get_text(strip=True) for e in soup.find_all(True)
              if "€" in e.get_text() and 5 < len(e.get_text(strip=True)) < 30
              and any(c.isdigit() for c in e.get_text())]

    # Verifica links de imóveis
    keywords = ["imovel","property","casa","apartamento","moradia","villa","house",
                "comprar","buy","sale","venda","for-sale"]
    links_imoveis = [a.get("href","") for a in soup.select("a[href]")
                     if any(k in a.get("href","").lower() for k in keywords)
                     and len(a.get("href","")) > 15]

    # Verifica artigos/cards
    cards = soup.select("article, .property, .card, [class*='listing'], [class*='property-card']")

    return len(precos) > 0, len(links_imoveis), len(cards), precos[:2]

def testar(nome, url, render=True):
    """Testa um URL e devolve resultado."""
    status, html = fetch(url, render=render)
    if status == 0:
        return "💥", f"Erro/Timeout"
    if status == 403:
        return "❌", f"Bloqueado (403)"
    if status == 404:
        return "❌", f"Não encontrado (404)"
    if status != 200:
        return "❌", f"HTTP {status}"

    tem_preco, n_links, n_cards, precos = tem_imoveis(html, url)

    if tem_preco and (n_links > 2 or n_cards > 0):
        return "✅", f"{n_links} links imóveis, {n_cards} cards, preços: {precos}"
    elif tem_preco:
        return "⚠️ ", f"Tem preços mas poucos links: {precos}"
    elif n_links > 5:
        return "⚠️ ", f"{n_links} links mas sem preços visíveis"
    else:
        return "❌", f"Sem conteúdo útil ({len(html)} chars, {n_links} links imoveis)"

# ============================================================
# LISTA COMPLETA DE SITES A TESTAR
# ============================================================
SITES = [
    # ── PORTAIS AGREGADORES ──────────────────────────────
    ("📡 PORTAIS AGREGADORES", [
        ("Idealista", f"https://www.idealista.pt/comprar-casas/faro/com-apartamentos/?preco-max={PRECO_MAX}&quartos-min={QUARTOS_MIN}", False),
        ("Imovirtual", f"https://www.imovirtual.com/comprar/apartamento/faro/?priceMax={PRECO_MAX}&roomsMin={QUARTOS_MIN}", False),
        ("Casa SAPO",  f"https://casa.sapo.pt/comprar-apartamentos/faro/?precomax={PRECO_MAX}&tipologia=T2,T3,T4", False),
        ("SuperCasa",  f"https://supercasa.pt/comprar-casas/faro/com-apartamentos/?preco-max={PRECO_MAX}&quartos-min={QUARTOS_MIN}", False),
    ]),

    # ── REDES NACIONAIS/INTERNACIONAIS ───────────────────
    ("🏢 REDES NACIONAIS/INTERNACIONAIS", [
        ("RE/MAX",          f"https://www.remax.pt/comprar/faro/?pricemax={PRECO_MAX}&rooms={QUARTOS_MIN}", True),
        ("ERA Imobiliária", f"https://www.era.pt/comprar/imoveis/faro/?preco_max={PRECO_MAX}&quartos_min={QUARTOS_MIN}", True),
        ("KW Portugal",     f"https://www.kwportugal.pt/pt/pesquisa/?localizacao=faro&tipo=comprar&priceMax={PRECO_MAX}", True),
        ("Engel & Völkers", f"https://www.engelvoelkers.com/pt/en/search/?adType=BUY&country=PRT&city=faro&priceMax={PRECO_MAX}", True),
        ("Coldwell Banker", f"https://www.coldwellbanker.pt/imoveis?transacao=compra&distrito=faro&preco_max={PRECO_MAX}", True),
        ("Sotheby's",       f"https://www.sothebysrealty.pt/imoveis/compra?preco_max={PRECO_MAX}&distrito=faro", True),
        ("IAD Portugal",    f"https://www.iadfrance.pt/comprar/apartamento/algarve?prix_max={PRECO_MAX}", True),
        ("Fine & Country",  f"https://www.fineandcountry.com/pt/imoveis-para-venda/algarve?max_price={PRECO_MAX}", True),
        ("Century 21",      f"https://www.century21.pt/imoveis/?local=faro&tipo=comprar&preco_max={PRECO_MAX}", True),
        ("Chave Nova",      f"https://www.chavanova.pt/imoveis?distrito=faro&tipo=venda&preco_max={PRECO_MAX}", True),
        ("Arcada Imobiliária", f"https://www.arcada.com.pt/imoveis?zona=algarve&tipo=venda&preco_max={PRECO_MAX}", True),
    ]),

    # ── ALGARVE TODA A REGIÃO ────────────────────────────
    ("🌍 ALGARVE — TODA A REGIÃO", [
        ("Garvetur",             f"https://www.garvetur.pt/imoveis/venda", True),
        ("Villas Key",           f"https://www.villaskey.com/venda?preco_max={PRECO_MAX}", True),
        ("Dils Portugal",        f"https://www.dils.pt/imoveis?tipo=venda&zona=algarve&preco_max={PRECO_MAX}", True),
        ("BuyMe Property",       f"https://www.buymeproperty.pt/comprar?preco_max={PRECO_MAX}", True),
        ("Algarve Property",     f"https://www.algarveproperty.com/properties-for-sale?max_price={PRECO_MAX}", True),
        ("Nurisimo",             f"https://www.nurisimo.com/venda?preco_max={PRECO_MAX}", True),
        ("Golden Properties",    f"https://www.goldenproperties.pt/imoveis?tipo=venda&preco_max={PRECO_MAX}", True),
        ("Sortami",              f"https://www.sortami.pt/imoveis?preco_max={PRECO_MAX}", True),
        ("Algarve Real Estate",  f"https://www.algarverealestate.com/properties-for-sale?max_price={PRECO_MAX}", True),
        ("Espaços Algarve",      f"https://www.espacos-algarve.com/comprar?preco_max={PRECO_MAX}", True),
        ("Rede Real",            f"https://www.redereal.com/imoveis?tipo=venda&zona=algarve&preco_max={PRECO_MAX}", True),
        ("D'Alma Portuguesa",    f"https://www.dalmaportuguesa.com/imoveis?preco_max={PRECO_MAX}", True),
        ("VAP Real Estate",      f"https://www.vaprealestate.com/properties?max_price={PRECO_MAX}", True),
        ("Tripalgarve",          f"https://www.tripalgarve.com/properties-for-sale?max_price={PRECO_MAX}", True),
        ("Algarve Dream Property", f"https://www.algarvedreamproperty.com/for-sale?max_price={PRECO_MAX}", True),
    ]),

    # ── BARLAVENTO ───────────────────────────────────────
    ("🌊 BARLAVENTO", [
        ("Mimosa Properties",          f"https://www.mimosaproperties.com/properties-for-sale?max_price={PRECO_MAX}&bedrooms={QUARTOS_MIN}", True),
        ("Algarve Unique Properties",  f"https://www.algarveuniqueproperties.com/for-sale?max_price={PRECO_MAX}", True),
        ("Boto Properties",            f"https://www.botoproperties.com/properties-for-sale?max_price={PRECO_MAX}", True),
        ("Vernon Algarve",             f"https://www.vernonalgarve.com/for-sale?max_price={PRECO_MAX}", True),
        ("Sunpoint Properties",        f"https://www.sunpointproperties.com/for-sale?max_price={PRECO_MAX}", True),
        ("A1 Algarve",                 f"https://www.a1-algarve.com/properties?max_price={PRECO_MAX}", True),
    ]),

    # ── TRIÂNGULO DOURADO ────────────────────────────────
    ("🏌️ TRIÂNGULO DOURADO", [
        ("QP Savills",             f"https://www.quintaproperty.com/property-for-sale?max_price={PRECO_MAX}&beds={QUARTOS_MIN}", True),
        ("JPP Properties",         f"https://www.jppproperties.com/buy?max_price={PRECO_MAX}&bedrooms={QUARTOS_MIN}", True),
        ("Your Luxury Property",   f"https://www.yourluxuryproperty.pt/imoveis-para-venda?preco_max={PRECO_MAX}", True),
        ("Barra Prime",            f"https://www.barraprime.pt/imoveis-para-venda?preco_max={PRECO_MAX}", True),
        ("Inside-Villas",          f"https://www.inside-villas.com/for-sale?max_price={PRECO_MAX}", True),
        ("Cluttons Algarve",       f"https://www.cluttons.com/algarve/properties-for-sale?max_price={PRECO_MAX}", True),
        ("Chestertons Algarve",    f"https://www.chestertons.com/algarve/properties-for-sale?max_price={PRECO_MAX}", True),
    ]),

    # ── SOTAVENTO ────────────────────────────────────────
    ("🏛️ SOTAVENTO", [
        ("Casas do Sotavento", f"https://www.casasdosotavento.pt/imoveis/venda/?preco_max={PRECO_MAX}", True),
        ("AlgarVila",          f"https://www.algarvila.com/en-gb/properties", True),
        ("Villas Tavira",      f"https://www.villastavira.pt/imoveis", True),
        ("Imocusto",           f"https://www.imocusto.pt/comprar", True),
        ("LNHouse",            f"https://www.lnhouse.pt/imoveis", True),
    ]),
]

# ============================================================
# CORRER TESTES
# ============================================================
def main():
    print(f"{'='*65}")
    print(f"Validação de Imobiliárias — {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    if not KEY:
        print("⚠️  SCRAPERAPI_KEY não definida — a usar requests direto")
    print(f"{'='*65}\n")

    resultados = {"✅":[], "⚠️ ":[], "❌":[], "💥":[]}
    total = sum(len(sites) for _, sites in SITES)
    i = 0

    for grupo, sites in SITES:
        print(f"\n{grupo}")
        print("-" * 55)
        for nome, url, render in sites:
            i += 1
            print(f"  [{i}/{total}] {nome}...", end=" ", flush=True)
            icone, detalhe = testar(nome, url, render)
            print(f"{icone} {detalhe}")
            resultados[icone].append({"nome":nome,"url":url,"detalhe":detalhe})
            time.sleep(2)  # pausa entre pedidos

    # Resumo
    print(f"\n{'='*65}")
    print(f"RESUMO:")
    print(f"  ✅ Funcionam:   {len(resultados['✅'])} sites")
    print(f"  ⚠️  Parcial:     {len(resultados['⚠️ '])} sites")
    print(f"  ❌ Bloqueados:  {len(resultados['❌'])} sites")
    print(f"  💥 Erro:        {len(resultados['💥'])} sites")
    print(f"{'='*65}")

    if resultados["✅"]:
        print(f"\n✅ Sites que funcionam:")
        for r in resultados["✅"]:
            print(f"  • {r['nome']}")

    if resultados["❌"]:
        print(f"\n❌ Sites bloqueados/com erro:")
        for r in resultados["❌"]:
            print(f"  • {r['nome']}: {r['detalhe']}")

    # Guarda resultado em ficheiro
    with open("/tmp/validacao_resultado.json", "w") as f:
        json.dump(resultados, f, ensure_ascii=False, indent=2)
    print(f"\nResultado guardado em /tmp/validacao_resultado.json")

if __name__ == "__main__":
    main()
