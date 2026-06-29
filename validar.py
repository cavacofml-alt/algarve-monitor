#!/usr/bin/env python3
"""
Validação Completa — Monitor Imóveis Algarve
=============================================
Testa todos os sites com todos os providers e gera diagnóstico detalhado.

Corre na Consola do Railway:
    python3 /app/validar.py
    python3 /app/validar.py --provider scraperapi   # testa só um provider
    python3 /app/validar.py --site "Idealista"      # testa só um site
"""
import os, requests, time, json, re, sys
from bs4 import BeautifulSoup
from datetime import datetime
from collections import defaultdict

# ── CHAVES ───────────────────────────────────────────────────
SCRAPERAPI_KEY  = os.getenv("SCRAPERAPI_KEY","")
ZENROWS_KEY     = os.getenv("ZENROWS_KEY","")
SCRAPINGBEE_KEY = os.getenv("SCRAPINGBEE_KEY","")
CRAWLBASE_KEY   = os.getenv("CRAWLBASE_KEY","")
SCRAPEDO_KEY    = os.getenv("SCRAPEDO_KEY","")

PRECO_MAX   = 250000
QUARTOS_MIN = 2

# ── FETCH POR PROVIDER ───────────────────────────────────────
def fetch_scraperapi(url):
    rp = "&render=true&wait=3000"
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
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120"
    })
    return r.status_code, r.text

PROVIDERS = []
if SCRAPERAPI_KEY:  PROVIDERS.append(("ScraperAPI",  fetch_scraperapi))
if ZENROWS_KEY:     PROVIDERS.append(("ZenRows",     fetch_zenrows))
if SCRAPINGBEE_KEY: PROVIDERS.append(("ScrapingBee", fetch_scrapingbee))
if CRAWLBASE_KEY:   PROVIDERS.append(("Crawlbase",   fetch_crawlbase))
if SCRAPEDO_KEY:    PROVIDERS.append(("Scrape.do",   fetch_scrapedo))
PROVIDERS.append(("Direto", fetch_direto))

# ── DETECÇÃO DE MOTIVO DE FALHA ──────────────────────────────
def detectar_motivo(status, html):
    """Identifica o motivo de falha com o máximo de detalhe."""
    if not html:
        return "resposta vazia"
    h = html.lower()
    if status == 403:
        if "cloudflare" in h or "cf-ray" in h or "cf_clearance" in h:
            return "Cloudflare"
        if "captcha" in h or "recaptcha" in h:
            return "CAPTCHA"
        return "Bloqueado 403"
    if status == 404:
        return "URL não existe (404)"
    if status == 429:
        return "Rate limit (429)"
    if status == 503:
        return "Serviço indisponível (503)"
    if status == 0:
        return "Timeout / sem resposta"
    if len(html) < 500:
        if "exhausted" in h or "credits" in h or "quota" in h:
            return "Proxy sem créditos"
        if "concurrency" in h:
            return "Proxy concorrência"
        return f"Resposta muito pequena ({len(html)} chars)"
    if "access denied" in h or "forbidden" in h:
        return "Acesso negado"
    if "maintenance" in h or "em manutenção" in h:
        return "Site em manutenção"
    if "no results" in h or "sem resultado" in h or "nenhum imóvel" in h:
        return "Sem resultados (filtros)"
    return f"Sem imóveis ({len(html):,} chars HTML)"

# ── ANÁLISE DE HTML ──────────────────────────────────────────
SELETORES = [
    ("article.item",                       "Idealista"),
    ("article[data-cy='listing-item']",    "Imovirtual"),
    ("[class*='property-card']",           "genérico"),
    ("[class*='listing-card']",            "genérico"),
    ("[class*='result-item']",             "genérico"),
    ("a[href*='/imovel/']",                "EgoRealEstate"),
    ("a[href*='/property/']",              "genérico"),
    (".property-info-content",             "SuperCasa"),
    (".searchResultProperty",              "SAPO"),
    ("article",                            "artigos"),
    (".card",                              "cards"),
]

def analisar_html(html, url):
    """
    Análise detalhada do HTML.
    Retorna: (n_items, seletor_usado, n_euros, tamanho_kb)
    """
    if not html or len(html) < 200:
        return 0, None, 0, 0
    tamanho_kb = len(html) // 1024
    soup = BeautifulSoup(html, "html.parser")
    # Tenta seletores CSS
    for sel, _ in SELETORES:
        items = soup.select(sel)
        if len(items) > 2:
            return len(items), sel, 0, tamanho_kb
    # Conta preços em euros (proxy para imóveis encontrados)
    precos = [e.get_text(strip=True) for e in soup.find_all(True)
              if "€" in e.get_text()
              and 5 < len(e.get_text(strip=True)) < 30
              and any(c.isdigit() for c in e.get_text())]
    if precos:
        return len(precos), "€ prices", len(precos), tamanho_kb
    # Links de imóveis
    keywords = ["imovel","property","casa","apartamento","moradia","villa","sale","venda"]
    links = [a.get("href","") for a in soup.select("a[href]")
             if any(k in a.get("href","").lower() for k in keywords)
             and len(a.get("href","")) > 20]
    if len(links) > 5:
        return len(links), "links", 0, tamanho_kb
    return 0, None, 0, tamanho_kb

# ── TESTE DE UM SITE ─────────────────────────────────────────
def testar_site(nome, url, provider_filter=None):
    """
    Testa um site com todos os providers (ou só o filtrado).
    Retorna dict com resultado detalhado.
    """
    providers = [(p, fn) for p, fn in PROVIDERS
                 if not provider_filter or p.lower() == provider_filter.lower()]

    melhor = None
    tentativas = []

    for pname, fn in providers:
        t0 = time.time()
        try:
            status, html = fn(url)
            ms = int((time.time()-t0)*1000)
            items, seletor, euros, kb = analisar_html(html, url)
            motivo = None if items > 2 else detectar_motivo(status, html)
            tentativa = {
                "provider": pname,
                "http": status,
                "items": items,
                "seletor": seletor,
                "latency_ms": ms,
                "size_kb": kb,
                "motivo": motivo,
            }
            tentativas.append(tentativa)
            if items > 2 and (melhor is None or items > melhor["items"]):
                melhor = tentativa
                break  # encontrou — não precisa de tentar mais
        except requests.exceptions.Timeout:
            ms = int((time.time()-t0)*1000)
            tentativas.append({
                "provider": pname, "http": 0, "items": 0,
                "latency_ms": ms, "size_kb": 0,
                "motivo": f"Timeout ({ms}ms)", "seletor": None
            })
        except Exception as e:
            tentativas.append({
                "provider": pname, "http": 0, "items": 0,
                "latency_ms": 0, "size_kb": 0,
                "motivo": str(e)[:60], "seletor": None
            })

    if melhor:
        return {**melhor, "nome": nome, "url": url, "ok": True, "tentativas": tentativas}

    # Nenhum funcionou — usa a melhor tentativa disponível
    ultima = tentativas[-1] if tentativas else {}
    return {
        "nome": nome, "url": url, "ok": False,
        "provider": ultima.get("provider","?"),
        "http": ultima.get("http", 0),
        "items": 0,
        "seletor": None,
        "latency_ms": ultima.get("latency_ms", 0),
        "size_kb": ultima.get("size_kb", 0),
        "motivo": ultima.get("motivo","Falhou"),
        "tentativas": tentativas
    }

# ── LISTA DE TODOS OS SITES ───────────────────────────────────
SITES = [
    ("📡 PORTAIS", [
        ("Idealista apt. Faro",
         f"https://www.idealista.pt/comprar-casas/faro/com-apartamentos/?preco-max={PRECO_MAX}&quartos-min={QUARTOS_MIN}"),
        ("Idealista mor. Tavira",
         f"https://www.idealista.pt/comprar-casas/tavira/com-moradias/?preco-max={PRECO_MAX}"),
        ("Idealista apt. Olhão",
         f"https://www.idealista.pt/comprar-casas/olhao/com-apartamentos/?preco-max={PRECO_MAX}"),
        ("Imovirtual apt. Faro",
         f"https://www.imovirtual.com/comprar/apartamento/faro/?priceMax={PRECO_MAX}&roomsMin={QUARTOS_MIN}"),
        ("Imovirtual mor. Tavira",
         f"https://www.imovirtual.com/comprar/moradia/tavira/?priceMax={PRECO_MAX}&roomsMin={QUARTOS_MIN}"),
        ("Casa SAPO apt. Faro",
         f"https://casa.sapo.pt/comprar-apartamentos/faro/?precomax={PRECO_MAX}&tipologia=T2,T3,T4"),
        ("Casa SAPO mor. Tavira",
         f"https://casa.sapo.pt/comprar-moradias/tavira/?precomax={PRECO_MAX}"),
        ("SuperCasa apt. Faro",
         f"https://supercasa.pt/comprar-casas/faro/com-apartamentos/?preco-max={PRECO_MAX}"),
        ("SuperCasa mor. Castro Marim",
         f"https://supercasa.pt/comprar-casas/castro-marim/com-moradias/?preco-max={PRECO_MAX}"),
    ]),
    ("🏢 REDES NACIONAIS", [
        ("RE/MAX Faro",         f"https://www.remax.pt/comprar/faro/?pricemax={PRECO_MAX}&rooms={QUARTOS_MIN}"),
        ("ERA Faro",            f"https://www.era.pt/comprar/imoveis/faro/?preco_max={PRECO_MAX}&quartos_min={QUARTOS_MIN}"),
        ("KW Portugal Faro",    f"https://www.kwportugal.pt/pt/pesquisa/?localizacao=faro&tipo=comprar&priceMax={PRECO_MAX}"),
        ("Engel & Völkers",     f"https://www.engelvoelkers.com/pt/en/search/?adType=BUY&country=PRT&city=faro&priceMax={PRECO_MAX}"),
        ("Coldwell Banker",     "https://www.coldwellbanker.pt/imoveis?transacao=compra&distrito=faro"),
        ("IAD Portugal",        "https://www.iadportugal.pt/comprar"),
        ("Fine & Country",      f"https://www.fineandcountry.com/pt/imoveis-para-venda/algarve?max_price={PRECO_MAX}"),
        ("Century 21",          f"https://www.century21.pt/imoveis/?local=faro&tipo=comprar&preco_max={PRECO_MAX}"),
        ("Arcada Imobiliária",  f"https://www.arcada.com.pt/imoveis?zona=algarve&tipo=venda&preco_max={PRECO_MAX}"),
        ("Sotheby's",           "https://www.sothebysrealty.pt/imoveis/compra"),
    ]),
    ("🌍 ALGARVE REGIÃO", [
        ("Garvetur",            "https://www.garveturproperties.com/"),
        ("Dils Portugal",       "https://www.dils.pt/imoveis?tipo=venda&zona=algarve"),
        ("BuyMe Property",      f"https://www.buymeproperty.pt/comprar?preco_max={PRECO_MAX}"),
        ("Algarve Property",    f"https://www.algarveproperty.com/properties-for-sale?max_price={PRECO_MAX}"),
        ("Nurisimo",            "https://www.nurisimo.com/properties"),
        ("Golden Properties",   "https://www.goldenproperties.pt/imoveis?tipo=venda"),
        ("Sortami",             "https://www.sortami.pt/imoveis"),
        ("Algarve Real Estate", f"https://www.algarverealestate.com/properties-for-sale?max_price={PRECO_MAX}"),
        ("Espaços Algarve",     f"https://www.espacos-algarve.com/comprar?preco_max={PRECO_MAX}"),
        ("Rede Real",           f"https://www.redereal.com/imoveis?tipo=venda&zona=algarve&preco_max={PRECO_MAX}"),
        ("D'Alma Portuguesa",   "https://www.dalmaportuguesa.com/imoveis"),
        ("VAP Real Estate",     f"https://www.vaprealestate.com/properties?max_price={PRECO_MAX}"),
        ("Tripalgarve",         "https://tripalgarve.com/properties"),
        ("Algarve Dream",       "https://www.algarvedreamproperty.com/imoveis"),
    ]),
    ("🌊 BARLAVENTO", [
        ("Mimosa Properties",       "https://www.mimosaproperties.com/procuro-imovel-mimosaproperties"),
        ("Algarve Unique",          "https://www.algarveuniqueproperties.com/imoveis"),
        ("Boto Properties",         "https://www.botoproperties.com/imoveis"),
        ("Vernon Algarve",          "https://www.vernonalgarve.com/imoveis-para-venda"),
        ("Sunpoint Properties",     "https://www.sunpoint.pt/propriedades"),
        ("A1 Algarve",              f"https://www.a1-algarve.com/properties?max_price={PRECO_MAX}"),
    ]),
    ("🏌️ TRIÂNGULO DOURADO", [
        ("QP Savills",          "https://www.quintaproperty.com/en/buy"),
        ("JPP Properties",      f"https://www.jppproperties.com/buy?max_price={PRECO_MAX}&bedrooms={QUARTOS_MIN}"),
        ("Your Luxury Property","https://www.yourluxuryproperty.pt/imoveis"),
        ("Barra Prime",         "https://www.barraprime.pt/imoveis-para-venda"),
        ("Inside-Villas",       f"https://www.inside-villas.com/for-sale?max_price={PRECO_MAX}&bedrooms={QUARTOS_MIN}"),
        ("Cluttons Algarve",    f"https://www.cluttons.com/algarve/properties-for-sale?max_price={PRECO_MAX}"),
        ("Chestertons Algarve", "https://www.chestertons.com/algarve/properties-for-sale"),
    ]),
    ("🏛️ SOTAVENTO", [
        ("Casas do Sotavento",  f"https://www.casasdosotavento.pt/imoveis/venda/?preco_max={PRECO_MAX}"),
        ("AlgarVila Tavira",    "https://www.algarvila.com/en-gb/properties"),
        ("Villas Tavira",       "https://www.villastavira.pt/imoveis"),
        ("Imocusto VRSA",       "https://www.imocusto.pt/venda"),
        ("LNHouse VRSA",        "https://www.lnhouse.pt/venda"),
    ]),
]

# ── MAIN ─────────────────────────────────────────────────────
def main():
    # Parse args
    pf = next((sys.argv[i+1] for i,a in enumerate(sys.argv) if a=="--provider" and i+1<len(sys.argv)), None)
    sf = next((sys.argv[i+1] for i,a in enumerate(sys.argv) if a=="--site"     and i+1<len(sys.argv)), None)

    total = sum(len(s) for _,s in SITES)
    nomes_prov = [p for p,_ in PROVIDERS]

    print(f"{'═'*65}")
    print(f"  Validação Completa — {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print(f"  Providers: {', '.join(nomes_prov)}")
    print(f"  Sites: {total} | Delay: 1s entre pedidos")
    if pf: print(f"  ⚡ Filtro provider: {pf}")
    if sf: print(f"  ⚡ Filtro site: {sf}")
    print(f"{'═'*65}")

    resultados = []
    i = 0

    for grupo, sites in SITES:
        sites_grupo = [(n,u) for n,u in sites if not sf or sf.lower() in n.lower()]
        if not sites_grupo: continue
        print(f"\n{grupo}")
        print("─" * 55)

        for nome, url in sites_grupo:
            i += 1
            label = f"{nome[:32]:<32}"
            print(f"  [{i:02d}/{total}] {label}", end=" ", flush=True)

            t0 = time.time()
            r  = testar_site(nome, url, pf)
            elapsed = int((time.time()-t0)*1000)

            # Ícone
            if r["ok"] and r["items"] > 10:
                icone = "✅"
            elif r["ok"]:
                icone = "✅"
            elif r["items"] > 0:
                icone = "⚠️ "
            elif r.get("http") == 403:
                icone = "🔒"
            elif r.get("http") == 0:
                icone = "💥"
            else:
                icone = "❌"

            # Linha de resultado detalhada
            kb_str  = f"{r['size_kb']}KB" if r['size_kb'] else "0KB"
            ms_str  = f"{r['latency_ms']}ms"
            prov_str= f"[{r['provider']}]"
            http_str= f"HTTP {r['http']}" if r['http'] else "TIMEOUT"

            if r["ok"]:
                sel = r.get("seletor","?")
                print(f"{icone} {prov_str} {r['items']} itens | {ms_str} | {kb_str} | sel: {sel}")
            else:
                print(f"{icone} {prov_str} {http_str} | {ms_str} | {kb_str} | {r['motivo']}")

            r["grupo"] = grupo
            resultados.append(r)
            time.sleep(1)

    # ── RANKINGS ─────────────────────────────────────────────
    ok   = [r for r in resultados if r["ok"]]
    warn = [r for r in resultados if not r["ok"] and r["items"] > 0]
    nok  = [r for r in resultados if r["items"] == 0]

    print(f"\n{'═'*65}")
    print(f"  RESULTADOS — {len(ok)}/{total} OK · {len(warn)} parciais · {len(nok)} falhas")
    print(f"{'═'*65}")

    # TOP PROVIDERS
    prov_ok    = defaultdict(int)
    prov_total = defaultdict(int)
    prov_items = defaultdict(int)
    for r in resultados:
        prov = r["provider"]
        prov_total[prov] += 1
        if r["ok"]:
            prov_ok[prov] += 1
            prov_items[prov] += r["items"]

    all_provs = sorted(set(prov_total.keys()), key=lambda p: -prov_ok.get(p,0))
    print(f"\n  TOP PROVIDERS:")
    print(f"  {'Provider':<14} {'✔ Sites':>7} {'Itens':>7} {'Taxa':>6}")
    print(f"  {'─'*38}")
    for p in all_provs:
        tot  = prov_total[p]
        ok_n = prov_ok[p]
        its  = prov_items[p]
        taxa = f"{ok_n/tot*100:.0f}%" if tot else "—"
        bar  = "█" * int(ok_n/max(max(prov_ok.values()),1) * 12)
        print(f"  {p:<14} {ok_n:>4}/{tot:<2}  {its:>5}  {taxa:>5}  {bar}")

    # TOP SITES por itens encontrados
    top_sites = sorted(ok, key=lambda r: -r["items"])[:15]
    print(f"\n  TOP SITES (por nº de itens):")
    print(f"  {'Site':<32} {'Itens':>6} {'Provider':<14} {'ms':>6}")
    print(f"  {'─'*60}")
    for r in top_sites:
        print(f"  {r['nome']:<32} {r['items']:>6}  {r['provider']:<14} {r['latency_ms']:>5}ms")

    # FALHAS por motivo
    motivos = defaultdict(list)
    for r in nok:
        motivos[r.get("motivo","?")].append(r["nome"])
    if motivos:
        print(f"\n  DIAGNÓSTICO DE FALHAS:")
        for motivo, nomes in sorted(motivos.items(), key=lambda x: -len(x[1])):
            print(f"  ⚠️  {motivo}: {', '.join(nomes[:4])}{'...' if len(nomes)>4 else ''}")

    # Aviso sites sem imóveis que podem ser desativados
    sem_imoveis = [r for r in nok if "Cloudflare" in r.get("motivo","") or "403" in r.get("motivo","")]
    if sem_imoveis:
        print(f"\n  💡 Bloqueados definitivamente (considera desativar):")
        for r in sem_imoveis:
            print(f"     • {r['nome']} — {r['motivo']}")

    # Guarda JSON detalhado
    with open("/tmp/validacao.json","w") as f:
        json.dump(resultados, f, ensure_ascii=False, indent=2)
    print(f"\n  📄 JSON completo: /tmp/validacao.json")
    print(f"{'═'*65}")

if __name__ == "__main__":
    main()
