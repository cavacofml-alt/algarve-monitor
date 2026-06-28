#!/usr/bin/env python3
"""
Playwright Inspector v3 — Estratégia por site
==============================================
Fase 1: Abre homepage, descobre link de listagem automaticamente.
Fase 2: Abre página de listagem, captura XHR/JSON, extrai imóveis.

python3 /app/playwright_inspect.py
"""
import json, time, re, os
from urllib.parse import urljoin, urlparse

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

CHROMIUM = "/usr/bin/chromium"
LAUNCH_ARGS = ["--no-sandbox","--disable-dev-shm-usage","--disable-gpu",
               "--disable-blink-features=AutomationControlled"]

# Palavras-chave para encontrar links de listagem
LISTING_KEYWORDS = [
    "imoveis","imóveis","imovel","imóvel",
    "properties","property","for-sale","for_sale","forsale",
    "buy","sale","venda","comprar","listings","listing",
    "houses","casas","apartamentos","moradias","villas",
]

# Palavras-chave para APIs de imóveis
API_KEYWORDS = [
    "/api/", "graphql", "search", "listing", "property",
    "_next/data", "imovel", "propert", "estate", "house",
]

def criar_pagina(p):
    ctx = p.chromium.launch(
        headless=True, executable_path=CHROMIUM, args=LAUNCH_ARGS
    ).new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        viewport={"width":1920,"height":1080},
        locale="pt-PT",
    )
    return ctx, ctx.new_page()

def descobrir_url_listagem(page, base_url):
    """Analisa a homepage e encontra o link de listagem de imóveis."""
    try:
        page.goto(base_url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(2000)
    except Exception as e:
        return None, f"Erro ao abrir homepage: {e}"

    # Procura links com keywords
    try:
        links = page.evaluate("""() => {
            return Array.from(document.querySelectorAll('a[href]'))
                .map(a => ({href: a.href, text: a.innerText.trim().toLowerCase()}))
                .filter(a => a.href && a.href.startsWith('http'));
        }""")
    except:
        return None, "Não foi possível extrair links"

    keywords = LISTING_KEYWORDS
    # Score cada link
    scored = []
    for l in links:
        href = l["href"].lower()
        text = l["text"]
        score = 0
        for k in keywords:
            if k in href: score += 2
            if k in text: score += 1
        # Penaliza links de redes sociais e páginas de contato
        if any(x in href for x in ["facebook","instagram","linkedin","twitter","contact","about","sobre","gdpr","privacy","blog"]):
            score -= 5
        if score > 0:
            scored.append((score, l["href"], text[:40]))

    scored.sort(reverse=True)
    if scored:
        return scored[0][1], None
    return None, "Nenhum link de listagem encontrado"

def inspecionar_listagem(page, url):
    """Abre página de listagem e captura XHR/JSON."""
    apis = []
    jsons = []

    def on_response(resp):
        try:
            ct = resp.headers.get("content-type","").lower()
            u = resp.url
            if "json" in ct:
                try:
                    body = resp.json()
                    size = len(str(body))
                    if size > 200 and any(k in u.lower() for k in API_KEYWORDS):
                        jsons.append({"url":u,"status":resp.status,
                                      "size":size,"preview":str(body)[:300]})
                except: pass
            # Regista todos os requests de API
            if any(k in u.lower() for k in API_KEYWORDS) and resp.status == 200:
                if u not in [a["url"] for a in apis]:
                    apis.append({"url":u,"status":resp.status,
                                 "type":resp.request.resource_type})
        except: pass

    page.on("response", on_response)

    try:
        page.goto(url, wait_until="networkidle", timeout=30000)
    except:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(5000)
        except Exception as e:
            return {"erro": str(e), "apis":[], "jsons":[]}

    # Scroll para triggerar lazy loading
    try:
        for pos in [0.3, 0.6, 1.0]:
            page.evaluate(f"window.scrollTo(0, document.body.scrollHeight * {pos})")
            page.wait_for_timeout(1500)
    except: pass

    # Extrai imóveis do HTML renderizado
    html = page.content()
    soup = BeautifulSoup(html, "html.parser")

    precos = [e.get_text(strip=True) for e in soup.find_all(True)
              if "€" in e.get_text() and 5<len(e.get_text(strip=True))<30
              and any(c.isdigit() for c in e.get_text())][:5]

    cards = 0
    melhor_sel = None
    for s in ["article","[class*='property']","[class*='listing']",
              "[class*='card']","[class*='item']",".property","li[class]"]:
        n = len(soup.select(s))
        if n > cards:
            cards = n; melhor_sel = s

    # Links de imóveis
    links_imoveis = list(set([
        a.get("href","") for a in soup.select("a[href]")
        if any(k in a.get("href","").lower() for k in
               ["property","imovel","casa","villa","apartamento","moradia"])
        and len(a.get("href","")) > 15
    ]))[:5]

    return {
        "titulo": page.title(),
        "url_final": page.url,
        "html_size": len(html),
        "precos": precos,
        "cards": cards,
        "melhor_selector": melhor_sel,
        "links_imoveis": links_imoveis,
        "apis": apis[:10],
        "jsons": jsons[:5],
    }

def inspecionar_site(nome, base_url, url_conhecida=None):
    print(f"\n{'='*60}")
    print(f"🔍 {nome}  —  {base_url}")
    print(f"{'='*60}")

    resultado = {"nome": nome, "base_url": base_url}

    with sync_playwright() as p:
        ctx, page = criar_pagina(p)

        # Fase 1: Descobrir URL de listagem
        if url_conhecida:
            url_listagem = url_conhecida
            print(f"  URL conhecida: {url_listagem}")
        else:
            print(f"  Fase 1: A descobrir URL de listagem...")
            url_listagem, erro = descobrir_url_listagem(page, base_url)
            if erro:
                print(f"  ❌ {erro}")
                resultado["erro_fase1"] = erro
            else:
                print(f"  ✅ URL encontrada: {url_listagem}")

        resultado["url_listagem"] = url_listagem

        # Fase 2: Inspecionar listagem
        if url_listagem:
            print(f"  Fase 2: A inspecionar listagem...")
            info = inspecionar_listagem(page, url_listagem)
            resultado.update(info)

            print(f"  Título: {info.get('titulo','?')[:60]}")
            print(f"  HTML: {info.get('html_size',0):,} chars | Cards: {info.get('cards',0)} [{info.get('melhor_selector','?')}]")
            if info.get('precos'):
                print(f"  Preços: {info['precos'][:3]}")
            if info.get('links_imoveis'):
                print(f"  Links imóveis: {info['links_imoveis'][:2]}")
            if info.get('jsons'):
                print(f"\n  📦 APIs JSON ({len(info['jsons'])}):")
                for j in info['jsons']:
                    print(f"    {j['url'][:70]}")
                    print(f"    Preview: {j['preview'][:100]}")
            elif info.get('apis'):
                print(f"\n  📡 Requests API ({len(info['apis'])}):")
                for a in info['apis'][:5]:
                    print(f"    {a['url'][:70]}")
            else:
                print(f"  📡 Nenhuma API capturada")

        ctx.browser.close()

    # Diagnóstico
    imoveis_encontrados = (resultado.get('cards',0) > 2 or
                           len(resultado.get('precos',[])) > 1 or
                           len(resultado.get('jsons',[])) > 0)
    resultado["imoveis_encontrados"] = imoveis_encontrados

    if imoveis_encontrados:
        if resultado.get('jsons'):
            estrategia = "API JSON direta"
        elif resultado.get('cards',0) > 2:
            estrategia = f"HTML scraping [{resultado.get('melhor_selector','?')}]"
        else:
            estrategia = "HTML scraping (preços)"
        print(f"\n  🟢 IMÓVEIS ENCONTRADOS — Estratégia: {estrategia}")
    else:
        vercel = "vercel" in str(resultado.get('titulo','')).lower()
        cf = "cloudflare" in str(resultado.get('titulo','')).lower()
        if vercel:
            print(f"\n  🔴 Vercel anti-bot — precisa de bypass")
        elif cf:
            print(f"\n  🔴 Cloudflare — precisa de bypass")
        elif not url_listagem:
            print(f"\n  🟡 URL de listagem não encontrada — rever manualmente")
        else:
            print(f"\n  🟡 Sem imóveis detetados — possível JS dinâmico ou URL errada")

    resultado["estrategia"] = estrategia if imoveis_encontrados else (
        "Vercel bypass" if "vercel" in str(resultado.get('titulo','')).lower() else
        "Manual review"
    )
    return resultado


SITES = [
    # Sem URL conhecida — descobre automaticamente
    ("D'Alma Portuguesa",  "https://www.dalmaportuguesa.com",   None),
    ("Vernon Algarve",     "https://www.vernonalgarve.com",     None),
    ("Sortami",            "https://www.sortami.pt",            None),
    ("Mimosa Properties",  "https://www.mimosaproperties.com",  None),
    ("Algarve Dream",      "https://www.algarvedreamproperty.com", None),
    ("Algarve Unique",     "https://www.algarveuniqueproperties.com", None),
    ("Boto Properties",    "https://www.botoproperties.com",    None),
    ("Sunpoint",           "https://www.sunpoint.pt",           None),  # redirect
    ("Your Luxury Prop",   "https://www.yourluxuryproperty.pt", None),
    ("Barra Prime",        "https://www.barraprime.pt",         None),
    ("Garvetur",           "https://www.garvetur.pt",           None),
]

print("="*60)
print(f"Playwright Inspector v3 — {len(SITES)} sites")
print("="*60)

all_results = []
for nome, base, url in SITES:
    try:
        r = inspecionar_site(nome, base, url)
        all_results.append(r)
    except Exception as e:
        print(f"  ❌ {nome}: {e}")
        all_results.append({"nome":nome,"base_url":base,"erro":str(e),
                             "imoveis_encontrados":False,"estrategia":"Erro"})
    time.sleep(3)

# Tabela final
print(f"\n{'='*60}")
print("FICHA POR SITE")
print(f"{'='*60}")
print(f"{'Site':<25} {'URL Listagem':<35} {'Tech':<10} {'Estratégia'}")
print("-"*90)
for r in all_results:
    url_l = (r.get('url_listagem') or r.get('erro_fase1','?') or '')[:35]
    fw = r.get('framework','?')[:10]
    est = r.get('estrategia','?')[:30]
    emoji = "🟢" if r.get('imoveis_encontrados') else "🔴"
    print(f"  {emoji} {r['nome']:<23} {url_l:<35} {fw:<10} {est}")

with open("/tmp/playwright_report.json","w") as f:
    json.dump(all_results, f, ensure_ascii=False, indent=2, default=str)
print(f"\n📄 /tmp/playwright_report.json")
