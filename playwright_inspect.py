#!/usr/bin/env python3
"""
Playwright XHR Capture — encontra APIs internas de SPAs
========================================================
Abre cada site com browser real, captura todas as requisições
XHR/fetch e identifica endpoints de imóveis automaticamente.

Corre na Consola do Railway: python3 /app/playwright_inspect.py
"""
import json, time, re, os
from urllib.parse import urljoin

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_OK = True
except ImportError:
    PLAYWRIGHT_OK = False
    print("❌ Playwright não instalado. Corre: pip install playwright && playwright install chromium")
    exit(1)

# Palavras-chave que indicam endpoint de imóveis
KEYWORDS = ["propert","imovel","listing","house","villa","apartment","sale","buy",
            "search","real-estate","estate","api","graphql","_next/data"]

def captura_xhr(nome, url, wait_ms=8000):
    """
    Abre o site com Playwright, captura todas as requisições XHR/fetch
    e retorna as que parecem ser de imóveis.
    """
    resultado = {
        "nome": nome,
        "url": url,
        "apis_encontradas": [],
        "json_responses": [],
        "framework": None,
        "title": "",
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox","--disable-dev-shm-usage","--disable-gpu",
                  "--disable-blink-features=AutomationControlled"]
        )
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width":1920,"height":1080},
            locale="pt-PT",
        )
        page = ctx.new_page()

        # Captura requests
        requests_log = []
        responses_log = []

        def on_request(req):
            u = req.url
            if any(k in u.lower() for k in KEYWORDS) and req.resource_type in ["xhr","fetch","document"]:
                requests_log.append({
                    "url": u, "method": req.method,
                    "type": req.resource_type,
                    "headers": dict(req.headers),
                })

        def on_response(resp):
            u = resp.url
            ct = resp.headers.get("content-type","")
            # Captura respostas JSON que parecem ser de imóveis
            if "json" in ct and any(k in u.lower() for k in KEYWORDS):
                try:
                    body = resp.json()
                    size = len(str(body))
                    if size > 100:
                        responses_log.append({
                            "url": u,
                            "status": resp.status,
                            "size": size,
                            "preview": str(body)[:200],
                        })
                except: pass

        page.on("request", on_request)
        page.on("response", on_response)

        try:
            page.goto(url, wait_until="networkidle", timeout=30000)
        except Exception as e:
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=20000)
            except Exception as e2:
                print(f"  ❌ Erro ao carregar: {e2}")
                browser.close()
                return resultado

        # Espera adicional para AJAX
        page.wait_for_timeout(wait_ms)

        # Scroll para trigger lazy loading
        try:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight/2)")
            page.wait_for_timeout(2000)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(2000)
        except: pass

        resultado["title"] = page.title()
        html = page.content()

        # Deteta framework
        if "_next/static" in html or "__next" in html:
            resultado["framework"] = "Next.js"
        elif "nuxt" in html.lower():
            resultado["framework"] = "Nuxt.js"
        elif "__reactfiber" in html.lower():
            resultado["framework"] = "React"
        elif "ng-version" in html.lower():
            resultado["framework"] = "Angular"

        # Extrai imóveis do HTML renderizado
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        precos = [e.get_text(strip=True) for e in soup.find_all(True)
                  if "€" in e.get_text() and 5<len(e.get_text(strip=True))<30
                  and any(c.isdigit() for c in e.get_text())][:5]
        cards = 0
        for s in ["article","[class*='property']","[class*='listing']","[class*='card']"]:
            cards = max(cards, len(soup.select(s)))

        resultado["precos_no_html"] = precos
        resultado["cards_no_html"] = cards
        resultado["html_size"] = len(html)
        resultado["apis_encontradas"] = requests_log
        resultado["json_responses"] = responses_log

        # Testa _next/data se for Next.js
        if resultado["framework"] == "Next.js":
            try:
                # Encontra o build ID no HTML
                build_id = re.search(r'"buildId":"([^"]+)"', html)
                if build_id:
                    bid = build_id.group(1)
                    resultado["nextjs_build_id"] = bid
                    # Testa endpoints _next/data comuns
                    test_paths = ["/","/imoveis","/properties","/for-sale","/venda","/comprar","/search"]
                    for path in test_paths:
                        next_url = f"{url.rstrip('/')}/_next/data/{bid}{path}.json"
                        try:
                            r = ctx.request.get(next_url)
                            if r.status == 200:
                                resultado["nextjs_data_url"] = next_url
                                resultado["nextjs_data_preview"] = r.text()[:200]
                                print(f"  🎯 Next.js data: {next_url}")
                                break
                        except: pass
            except: pass

        browser.close()

    return resultado


def analisar_resultado(r):
    """Analisa e imprime o resultado de forma clara."""
    print(f"\n{'='*60}")
    print(f"🔍 {r['nome']}  —  {r['url']}")
    print(f"{'='*60}")
    print(f"  Título: {r.get('title','?')[:60]}")
    print(f"  HTML: {r.get('html_size',0):,} chars | Framework: {r.get('framework','?')}")
    print(f"  Cards no HTML: {r.get('cards_no_html',0)} | Preços: {r.get('precos_no_html',[])[:3]}")

    # APIs capturadas
    apis = r.get("apis_encontradas",[])
    if apis:
        print(f"\n  📡 Requests XHR/fetch ({len(apis)}):")
        for a in apis[:8]:
            print(f"    {a['method']} {a['url'][:80]}")
    else:
        print(f"  📡 Nenhum request XHR/fetch capturado")

    # JSON responses
    jsons = r.get("json_responses",[])
    if jsons:
        print(f"\n  📦 Respostas JSON ({len(jsons)}):")
        for j in jsons[:5]:
            print(f"    HTTP {j['status']} {j['url'][:70]}")
            print(f"      Preview: {j['preview'][:100]}")
    else:
        print(f"  📦 Nenhuma resposta JSON de imóveis capturada")

    # Next.js
    if r.get("nextjs_data_url"):
        print(f"\n  🎯 Next.js DATA URL: {r['nextjs_data_url']}")
        print(f"     Preview: {r.get('nextjs_data_preview','')[:100]}")

    # Conclusão
    if r.get("json_responses") or r.get("nextjs_data_url"):
        print(f"\n  ✅ API ENCONTRADA — scraping direto possível!")
    elif r.get("precos_no_html") or r.get("cards_no_html",0) > 2:
        print(f"\n  ✅ IMÓVEIS NO HTML — scraping com Playwright possível!")
    elif r.get("apis_encontradas"):
        print(f"\n  🟡 APIs capturadas mas sem JSON de imóveis — analisar manualmente")
    else:
        print(f"\n  🔴 Sem imóveis detetados — site pode requerer login ou estar vazio")


SITES = [
    ("D'Alma Portuguesa",  "https://www.dalmaportuguesa.com/imoveis"),
    ("Vernon Algarve",     "https://www.vernonalgarve.com/for-sale"),
    ("Sortami",            "https://www.sortami.pt/imoveis"),
    ("Mimosa Properties",  "https://www.mimosaproperties.com/properties-for-sale"),
    ("Algarve Dream",      "https://www.algarvedreamproperty.com/for-sale"),
    ("Algarve Unique",     "https://www.algarveuniqueproperties.com/for-sale"),
    ("Boto Properties",    "https://www.botoproperties.com/properties-for-sale"),
    ("Sunpoint",           "https://www.sunpoint.pt/imoveis"),  # note: redirect to sunpoint.pt
    ("Your Luxury Prop",   "https://www.yourluxuryproperty.pt/imoveis-para-venda"),
    ("Barra Prime",        "https://www.barraprime.pt/imoveis-para-venda"),
    ("Garvetur",           "https://garvetur.pt/imoveis/venda"),
]

print("="*60)
print(f"Playwright XHR Capture — {len(SITES)} sites")
print("="*60)

all_results = []
for nome, url in SITES:
    try:
        print(f"\n⏳ {nome}...")
        r = captura_xhr(nome, url)
        analisar_resultado(r)
        all_results.append(r)
    except Exception as e:
        print(f"  ❌ {nome}: {e}")
        all_results.append({"nome":nome,"url":url,"erro":str(e)})
    time.sleep(2)

# Resumo
print(f"\n{'='*60}")
print("RESUMO")
print("="*60)
for r in all_results:
    nome = r.get("nome","?")
    if r.get("json_responses") or r.get("nextjs_data_url"):
        print(f"  🟢 {nome}: API JSON encontrada")
    elif r.get("precos_no_html") or r.get("cards_no_html",0)>2:
        print(f"  🟢 {nome}: Imóveis no HTML renderizado")
    elif r.get("apis_encontradas"):
        print(f"  🟡 {nome}: APIs capturadas, analisar")
    else:
        print(f"  🔴 {nome}: Sem resultados")

with open("/tmp/playwright_report.json","w") as f:
    json.dump(all_results, f, ensure_ascii=False, indent=2, default=str)
print(f"\n📄 /tmp/playwright_report.json")
