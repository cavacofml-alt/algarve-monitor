#!/usr/bin/env python3
"""
Inspeção Avançada de SPAs v2 — Monitor Imóveis Algarve
=======================================================
Diagnóstico detalhado antes de tentar scraping.

Corre na Consola do Railway: python3 /app/inspect_apis.py
"""
import os, requests, re, json, time
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

CKEY = os.getenv("CRAWLBASE_KEY","")
ZKEY = os.getenv("ZENROWS_KEY","")
BKEY = os.getenv("SCRAPINGBEE_KEY","")

# ── HTTP FETCH COM DIAGNÓSTICO COMPLETO ──────────────────────
def fetch_diagnostic(url, timeout=15, allow_redirects=True):
    """
    Fetch com diagnóstico completo.
    Retorna dict com: status, final_url, content_type, size, html, 
                      redirected, blocked_reason
    """
    result = {
        "url": url, "status": 0, "final_url": url,
        "content_type": "", "size": 0, "html": "",
        "redirected": False, "blocked_reason": None,
        "preview": ""
    }
    try:
        r = requests.get(url, timeout=timeout, allow_redirects=allow_redirects,
            verify=False,  # ignora erros TLS/SSL
            headers={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
                     "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                     "Accept-Language": "pt-PT,pt;q=0.9,en;q=0.8"})
        result["status"]       = r.status_code
        result["final_url"]    = r.url
        result["content_type"] = r.headers.get("content-type","")
        result["size"]         = len(r.text)
        result["html"]         = r.text
        result["preview"]      = repr(r.text[:300])
        result["redirected"]   = r.url != url

        # Detect block reason
        text_lower = r.text.lower()
        if r.status_code == 403:
            result["blocked_reason"] = "403 Forbidden (WAF/anti-bot)"
        elif r.status_code == 429:
            result["blocked_reason"] = "429 Rate Limited"
        elif r.status_code == 404:
            result["blocked_reason"] = "404 Not Found (URL desatualizado?)"
        elif r.status_code == 520:
            result["blocked_reason"] = "520 Proxy error (Cloudflare origin)"
        elif len(r.text) < 600:
            result["blocked_reason"] = f"Conteúdo demasiado pequeno ({len(r.text)} chars)"
        elif any(x in text_lower for x in ["access denied","just a moment","cf-chl","attention required","cf_clearance","enable javascript and cookies"]):
            result["blocked_reason"] = "Cloudflare challenge"
        elif any(x in text_lower for x in ["403 forbidden","access forbidden","blocked"]):
            result["blocked_reason"] = "Acesso bloqueado"
        elif any(x in text_lower for x in ["login","sign in","autenticate"]) and len(r.text) < 5000:
            result["blocked_reason"] = "Redireciona para login"

    except requests.exceptions.Timeout:
        result["blocked_reason"] = "Timeout"
    except requests.exceptions.ConnectionError as e:
        result["blocked_reason"] = f"Connection error: {str(e)[:60]}"
    except Exception as e:
        result["blocked_reason"] = f"Erro: {str(e)[:60]}"

    return result

def fetch_rendered(url, provider="crawlbase", timeout=60):
    """Fetch com proxy JS — interface comum."""
    try:
        if provider == "crawlbase" and CKEY:
            r = requests.get(
                f"https://api.crawlbase.com/?token={CKEY}&url={requests.utils.quote(url)}&ajax_wait=true&page_wait=5000",
                timeout=timeout)
        elif provider == "zenrows" and ZKEY:
            r = requests.get("https://api.zenrows.com/v1/", timeout=timeout, params={
                "url":url,"apikey":ZKEY,"js_render":"true","premium_proxy":"true"})
        elif provider == "scrapingbee" and BKEY:
            r = requests.get("https://app.scrapingbee.com/api/v1/", timeout=timeout, params={
                "api_key":BKEY,"url":url,"render_js":"true","premium_proxy":"true"})
        else:
            r = requests.get(url, timeout=20, headers={"User-Agent":"Mozilla/5.0"})

        blocked = None
        if r.status_code != 200:
            blocked = f"HTTP {r.status_code}"
        elif len(r.text) < 500:
            blocked = f"Conteúdo vazio ({len(r.text)} chars)"
        elif "<html" not in r.text.lower() and "<div" not in r.text.lower():
            blocked = "Resposta não é HTML"

        return r.status_code, r.text, blocked
    except Exception as e:
        return 0, "", f"Erro: {str(e)[:60]}"

# ── ANÁLISE ──────────────────────────────────────────────────
def detect_framework(html):
    if "_next/static" in html or "__next" in html: return "Next.js"
    if "nuxt" in html.lower(): return "Nuxt.js"
    if "__reactfiber" in html.lower() or "react-dom" in html.lower(): return "React"
    if "ng-version" in html.lower(): return "Angular"
    if "__vue" in html.lower(): return "Vue"
    if "gatsby" in html.lower(): return "Gatsby"
    if "wp-content" in html or "wp-includes" in html: return "WordPress"
    return None

def extract_jsonld(html):
    soup = BeautifulSoup(html, "html.parser") if "<" in html else None
    if not soup: return []
    results = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            tipo = data.get("@type","") if isinstance(data,dict) else ""
            if any(t in str(tipo) for t in ["RealEstate","House","Apartment","Property","Residence"]):
                results.append({"type":tipo,"name":str(data.get("name",""))[:60]})
        except: pass
    return results

def find_apis_in_html(html, base_url):
    soup = BeautifulSoup(html, "html.parser") if "<" in html else None
    if not soup: return [], []
    apis = set()
    js_files = [urljoin(base_url, s.get("src","")) for s in soup.find_all("script", src=True)
                if any(x in s.get("src","") for x in [".js","chunk","bundle","main","app"])]
    for s in soup.find_all("script"):
        text = s.string or ""
        for p in [r'["\'](/(?:api|graphql)[^"\']{3,80})["\']',
                  r'fetch\(["\']([^"\']{10,80})["\']',
                  r'"(?:apiUrl|baseURL|endpoint)":\s*"([^"]+)"']:
            for m in re.findall(p, text):
                if any(k in m.lower() for k in ["propert","imovel","search","listing","sale","buy"]):
                    apis.add(m)
    return list(apis), js_files[:5]

def analyze_js_bundle(url):
    try:
        r = requests.get(url, timeout=15, headers={"User-Agent":"Mozilla/5.0"})
        js = r.text
        found = {"apis":set(),"graphql":False,"algolia":False,"firebase":False,"wp_plugins":set()}
        for p in [r'["\'](/api/[^"\']{3,80})["\']', r'["\'](/graphql[^"\']*)["\']']:
            for m in re.findall(p, js):
                if any(k in m.lower() for k in ["propert","search","listing","imovel","sale","buy"]):
                    found["apis"].add(m[:80])
        if any(x in js for x in ["graphql","ApolloClient","__typename"]): found["graphql"] = True
        if any(x in js for x in ["algoliasearch","algolia","searchClient"]):
            found["algolia"] = True
            idx = re.findall(r'"indexName":\s*"([^"]+)"', js)
            app = re.findall(r'"appId":\s*"([^"]+)"', js)
            key = re.findall(r'"apiKey":\s*"([A-Za-z0-9]{20,})"', js)
            if idx: found["algolia_index"] = idx[0]
            if app: found["algolia_app_id"] = app[0]
            if key: found["algolia_key"] = key[0][:20]
        if any(x in js for x in ["firebase","firestore"]): found["firebase"] = True
        for k,v in {"estatik":"estatik","realhomes":"realhomes","houzez":"houzez","essential-real-estate":"ere"}.items():
            if k in js.lower(): found["wp_plugins"].add(v)
        return found
    except: return {}

def check_sitemaps(base_url):
    found = []
    for sm in ["/sitemap.xml","/sitemap_index.xml","/property-sitemap.xml",
               "/listing-sitemap.xml","/imoveis-sitemap.xml","/properties-sitemap.xml"]:
        try:
            r = requests.get(base_url.rstrip("/")+sm, timeout=8, headers={"User-Agent":"Mozilla/5.0"})
            if r.status_code == 200 and ("<url" in r.text or "<sitemap" in r.text):
                soup = BeautifulSoup(r.text, "lxml-xml") if "xml" in r.text else None
                urls = soup.find_all("loc") if soup else []
                prop_urls = [u.text for u in urls if any(k in u.text for k in ["property","imovel","casa","villa"])]
                found.append({"path":sm,"total":len(urls),"properties":len(prop_urls),"sample":prop_urls[:1] or ([u.text for u in urls[:1]] if urls else [])})
        except: pass
        time.sleep(0.2)
    return found

def check_wp_apis(base_url):
    found = []
    for ep in ["/wp-json/wp/v2/property","/wp-json/wp/v2/properties",
               "/wp-json/estatik/v1/properties","/wp-json/realhomes/v1/properties",
               "/wp-json/houzez/v1/listings","/wp-json/wp/v2/listings"]:
        try:
            r = requests.get(base_url.rstrip("/")+ep, timeout=8, headers={"User-Agent":"Mozilla/5.0"})
            if r.status_code == 200:
                data = r.json()
                if isinstance(data,list) and data:
                    found.append({"endpoint":ep,"count":len(data)})
        except: pass
        time.sleep(0.2)
    return found

# ── INSPECT ──────────────────────────────────────────────────
def inspect_site(nome, base_url, test_url=None):
    test_url = test_url or base_url
    report   = {"nome":nome,"base_url":base_url,"apis":[],"score":0}

    print(f"\n{'='*60}")
    print(f"🔍 {nome}  —  {base_url}")
    print(f"{'='*60}")

    # 1. Fetch homepage com diagnóstico
    d = fetch_diagnostic(base_url)
    print(f"  Homepage: HTTP {d['status']} | {d['size']} chars | {d['content_type'][:40]}")
    if d["redirected"]:
        print(f"  Redirecionou para: {d['final_url']}")
    if d["blocked_reason"]:
        print(f"  ⚠️  {d['blocked_reason']}")
    if d["status"] not in [200,301,302] and d["status"] != 0:
        print(f"  Preview: {d['preview'][:150]}")

    # 2. Se homepage OK, testa também test_url
    html = d["html"]
    if d["status"] not in [200] and test_url != base_url:
        print(f"  A tentar test_url: {test_url}")
        d2 = fetch_diagnostic(test_url)
        print(f"  test_url: HTTP {d2['status']} | {d2['size']} chars")
        if d2["blocked_reason"]:
            print(f"  ⚠️  {d2['blocked_reason']}")
        if d2["status"] == 200 and d2["size"] > 500:
            html = d2["html"]
            d = d2

    # 3. Se não temos HTML útil, abortar
    if not html or d["size"] < 500 or d["status"] not in [200]:
        print(f"  🔴 Sem HTML válido — a saltar análise profunda")
        report["blocked_reason"] = d["blocked_reason"] or f"HTTP {d['status']}"
        return report

    # 4. Score base por HTML direto
    report["score"] += 20  # homepage responde
    if d["size"] > 50000:
        report["score"] += 20
        print(f"  HTML grande: ✅ {d['size']:,} chars (scraping direto possível)")
    elif d["size"] > 5000:
        report["score"] += 10

    # Framework
    fw = detect_framework(html)
    if fw:
        print(f"  Framework: {fw}")
        report["framework"] = fw
        if fw in ["Next.js","Nuxt.js"]: report["score"] += 10  # SSR likely

    # 5. JSON-LD
    jsonld = extract_jsonld(html)
    if jsonld:
        print(f"  JSON-LD: ✅ {jsonld[0]}")
        report["jsonld"] = True
        report["score"] += 20

    # 6. APIs inline + JS bundles
    inline_apis, js_files = find_apis_in_html(html, d["final_url"])
    if inline_apis:
        print(f"  APIs inline: {inline_apis[:2]}")
        report["apis"].extend(inline_apis[:2])
        report["score"] += 15
    if js_files:
        print(f"  Bundles JS: {len(js_files)} — a analisar...")
        report["score"] += 10  # tem bundles JS
        bundle_findings = []
        for jsf in js_files[:3]:
            bundle = analyze_js_bundle(jsf)
            if not bundle: continue
            if bundle.get("apis"):
                print(f"    📦 APIs: {list(bundle['apis'])[:2]}")
                report["apis"].extend(list(bundle["apis"])[:2])
                report["score"] += 20
                bundle_findings.append(f"APIs: {list(bundle['apis'])[:1]}")
            if bundle.get("graphql"):
                print(f"    GraphQL: ✅")
                report["graphql"] = True; report["score"] += 15
                bundle_findings.append("GraphQL")
            if bundle.get("algolia"):
                print(f"    🎯 ALGOLIA: index={bundle.get('algolia_index','?')} app={bundle.get('algolia_app_id','?')}")
                report["algolia"] = bundle; report["score"] += 30
                bundle_findings.append(f"Algolia:{bundle.get('algolia_index','?')}")
            if bundle.get("firebase"):
                print(f"    Firebase: ✅")
                report["firebase"] = True; report["score"] += 15
                bundle_findings.append("Firebase")
            if bundle.get("wp_plugins"):
                print(f"    WP plugins: {bundle['wp_plugins']}")
                bundle_findings.append(f"WP:{bundle['wp_plugins']}")
            time.sleep(0.5)
        if not bundle_findings:
            print(f"    (sem APIs encontradas nos bundles — usar Playwright para XHR capture)")

    # 7. Sitemaps
    sitemaps = check_sitemaps(d["final_url"].rstrip("/").rsplit("/",1)[0] if "/" in d["final_url"][8:] else d["final_url"])
    if sitemaps:
        for sm in sitemaps:
            print(f"  Sitemap ✅ {sm['path']}: {sm['total']} URLs, {sm['properties']} imóveis")
        report["sitemaps"] = sitemaps; report["score"] += 10

    # 8. WP REST API
    wp = check_wp_apis(base_url)
    if wp:
        for w in wp:
            print(f"  WP API ✅ {w['endpoint']}: {w['count']} items")
        report["wp_apis"] = wp; report["score"] += 30

    # 9. Proxy JS
    print(f"  Proxy JS (Crawlbase)...")
    status2, html2, blocked2 = fetch_rendered(test_url)
    if blocked2:
        print(f"  Proxy: ❌ {blocked2}")
    else:
        soup2 = BeautifulSoup(html2, "html.parser")
        precos = [e.get_text(strip=True) for e in soup2.find_all(True)
                  if "€" in e.get_text() and 5<len(e.get_text(strip=True))<30 and any(c.isdigit() for c in e.get_text())][:3]
        links = len([a for a in soup2.select("a[href]") if any(k in a.get("href","").lower() for k in ["property","imovel","sale","buy","venda"])])
        cards = 0
        for s in ["article","[class*='property']","[class*='listing']","[class*='card']"]:
            cards = max(cards, len(soup2.select(s)))
        print(f"  Proxy: ✅ HTTP {status2} | {len(html2)} chars | {links} links | {cards} cards | {precos}")
        if precos or links > 3 or cards > 2:
            report["proxy_works"] = True; report["score"] += 20

    # Score
    score = min(100, report["score"])
    emoji = "🟢" if score>=60 else "🟡" if score>=30 else "🔴"
    print(f"\n  {emoji} Score: {score}/100")
    if report.get("algolia"):   print(f"  🎯 ALGOLIA — scraping direto possível!")
    if report.get("wp_apis"):   print(f"  🎯 WP REST — scraping direto possível!")
    if report.get("graphql"):   print(f"  🎯 GraphQL — queries diretas possíveis!")
    if report.get("proxy_works"): print(f"  ✅ Proxy JS funciona")
    report["score"] = score
    return report

# ── SITES ────────────────────────────────────────────────────
SITES = [
    ("Garvetur",           "https://www.garvetur.pt",              "https://www.garvetur.pt/imoveis/venda"),
    ("Sotheby's",          "https://www.sothebysrealty.pt",         "https://www.sothebysrealty.pt/imoveis/compra"),
    ("Chave Nova",         "https://www.chavanova.pt",              "https://www.chavanova.pt/imoveis?distrito=faro&tipo=venda"),
    ("D'Alma Portuguesa",  "https://www.dalmaportuguesa.com",       "https://www.dalmaportuguesa.com/imoveis"),
    ("Vernon Algarve",     "https://www.vernonalgarve.com",         "https://www.vernonalgarve.com/for-sale"),
    ("Sortami",            "https://www.sortami.pt",                "https://www.sortami.pt/imoveis"),
    ("Mimosa Properties",  "https://www.mimosaproperties.com",      "https://www.mimosaproperties.com/properties-for-sale"),
    ("Algarve Dream",      "https://www.algarvedreamproperty.com",  "https://www.algarvedreamproperty.com/for-sale"),
    ("Algarve Unique",     "https://www.algarveuniqueproperties.com","https://www.algarveuniqueproperties.com/for-sale"),
    ("Boto Properties",    "https://www.botoproperties.com",        "https://www.botoproperties.com/properties-for-sale"),
    ("Sunpoint",           "https://www.sunpointproperties.com",    "https://www.sunpointproperties.com/for-sale"),
    ("Your Luxury Prop",   "https://www.yourluxuryproperty.pt",     "https://www.yourluxuryproperty.pt/imoveis-para-venda"),
    ("Barra Prime",        "https://www.barraprime.pt",             "https://www.barraprime.pt/imoveis-para-venda"),
    ("Villas Key",         "https://www.villaskey.com",             "https://www.villaskey.com/en/for-sale"),
]

print("="*60)
print(f"Inspeção Avançada v2 — {len(SITES)} sites")
print("="*60)

all_reports = []
for nome, base, test in SITES:
    try:
        r = inspect_site(nome, base, test)
        all_reports.append(r)
    except Exception as e:
        print(f"  ❌ {nome}: erro — {e}")
        all_reports.append({"nome":nome,"base_url":base,"score":0,"apis":[],"blocked_reason":str(e)})
    time.sleep(3)

# Relatório final
print(f"\n{'='*60}")
print("RELATÓRIO FINAL")
print("="*60)

categorias = {"🟢 Possível scraper":[], "🟡 Difícil mas possível":[], "🔴 Bloqueado / Fechado":[]}
for r in sorted(all_reports, key=lambda x: -x.get("score",0)):
    score = r.get("score",0)
    techs = []
    if r.get("algolia"):      techs.append("Algolia🎯")
    if r.get("graphql"):      techs.append("GraphQL🎯")
    if r.get("wp_apis"):      techs.append("WP REST🎯")
    if r.get("jsonld"):       techs.append("JSON-LD")
    if r.get("proxy_works"):  techs.append("Proxy✅")
    if r.get("sitemaps"):     techs.append("Sitemap")
    if r.get("framework"):    techs.append(r["framework"])
    blocked = r.get("blocked_reason","")
    emoji = "🟢" if score>=60 else "🟡" if score>=30 else "🔴"
    line = f"  {emoji} {r['nome']:25s} {score:3d}pts  {', '.join(techs) or blocked or 'Sem dados'}"
    print(line)
    if score >= 60: categorias["🟢 Possível scraper"].append(r["nome"])
    elif score >= 30: categorias["🟡 Difícil mas possível"].append(r["nome"])
    else: categorias["🔴 Bloqueado / Fechado"].append(r["nome"])

print(f"\n🟢 Possível implementar: {categorias['🟢 Possível scraper']}")
print(f"🟡 Difícil: {categorias['🟡 Difícil mas possível']}")
print(f"🔴 Bloqueado/Fechado: {categorias['🔴 Bloqueado / Fechado']}")

with open("/tmp/inspect_report.json","w") as f:
    json.dump(all_reports, f, ensure_ascii=False, indent=2, default=str)
print(f"\n📄 /tmp/inspect_report.json")
