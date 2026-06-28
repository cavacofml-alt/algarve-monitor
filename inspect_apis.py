#!/usr/bin/env python3
"""
Inspeção Avançada de SPAs — Monitor Imóveis Algarve
====================================================
Analisa sites React/Angular/Next.js para encontrar APIs internas.

Técnicas usadas:
1. HTML base + deteção de framework
2. JSON-LD embedded
3. Análise de bundles JS externos (onde estão os endpoints)
4. GraphQL / Apollo / Algolia / Firebase
5. WordPress REST API (múltiplos plugins imobiliários)
6. Sitemaps (property-sitemap, listing-sitemap, etc.)
7. robots.txt com Sitemap: e Disallow:
8. Playwright XHR/Fetch network capture
9. Cloudflare detection
10. Relatório final por site com score

Corre na Consola do Railway: python3 /app/inspect_apis.py
"""
import os, requests, re, json, time
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

CKEY = os.getenv("CRAWLBASE_KEY","")
ZKEY = os.getenv("ZENROWS_KEY","")
BKEY = os.getenv("SCRAPINGBEE_KEY","")

# ── PROVIDERS ────────────────────────────────────────────────
def fetch_rendered(url, provider="crawlbase", timeout=60):
    """Interface comum para todos os providers."""
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
        return r.status_code, r.text, r.headers
    except Exception as e:
        return 0, str(e), {}

def fetch_direct(url, timeout=15):
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
        return r.status_code, r.text, r.headers
    except Exception as e:
        return 0, str(e), {}

# ── ANALYSIS FUNCTIONS ───────────────────────────────────────

def detect_cloudflare(html, headers):
    """Deteta proteção Cloudflare."""
    cf_headers = any(h.lower().startswith("cf-") for h in headers)
    cf_html = any(x in html for x in ["Just a moment","cf-chl","Attention Required","cf_clearance","__cf_bm"])
    return cf_headers or cf_html

def detect_framework(html):
    """Deteta framework JavaScript."""
    html_lower = html.lower()
    if "_next/static" in html or "__next" in html: return "Next.js"
    if "nuxt" in html_lower: return "Nuxt.js"
    if "__reactfiber" in html_lower or "react-dom" in html_lower: return "React"
    if "ng-version" in html_lower or "angular" in html_lower: return "Angular"
    if "__vue" in html_lower or "vue.js" in html_lower: return "Vue"
    if "gatsby" in html_lower: return "Gatsby"
    if "wp-content" in html_lower or "wp-includes" in html_lower: return "WordPress"
    return "Desconhecido"

def detect_cms(html):
    """Deteta CMS."""
    if "wp-content" in html or "wp-includes" in html: return "WordPress"
    if "Drupal" in html: return "Drupal"
    if "Joomla" in html: return "Joomla"
    if "squarespace" in html.lower(): return "Squarespace"
    if "wix.com" in html.lower(): return "Wix"
    if "webflow" in html.lower(): return "Webflow"
    return None

def extract_jsonld(html):
    """Extrai dados JSON-LD da página."""
    soup = BeautifulSoup(html, "html.parser") if "<" in html else None
    if not soup: return []
    results = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, dict):
                tipo = data.get("@type","")
                if any(t in str(tipo) for t in ["RealEstate","House","Apartment","Property","Residence"]):
                    results.append({
                        "type": tipo,
                        "price": data.get("offers",{}).get("price") if isinstance(data.get("offers"),dict) else None,
                        "address": str(data.get("address",""))[:80],
                        "name": str(data.get("name",""))[:60],
                    })
        except: pass
    return results

def find_apis_in_html(html, base_url):
    """Encontra APIs referenciadas no HTML."""
    apis = set()
    soup = BeautifulSoup(html, "html.parser") if "<" in html else None
    if not soup: return [], []

    scripts_inline = []
    js_files = []
    for s in soup.find_all("script"):
        src = s.get("src","")
        if src:
            full = urljoin(base_url, src)
            if any(x in src for x in [".js","chunk","bundle","main","app"]):
                js_files.append(full)
        else:
            scripts_inline.append(s.string or "")

    all_js = " ".join(scripts_inline)
    patterns = [
        r'["\'](/(?:api|graphql|_next/data)[^"\']{3,80})["\']',
        r'fetch\(["\']([^"\']{10,100})["\']',
        r'"baseURL":\s*"([^"]+)"',
        r'"endpoint":\s*"([^"]+)"',
        r'"apiUrl":\s*"([^"]+)"',
        r'axios\.[a-z]+\(["\']([^"\']{10,80})["\']',
    ]
    for p in patterns:
        for m in re.findall(p, all_js):
            if any(k in m.lower() for k in ["propert","imovel","search","listing","house","real","estate","sale","buy"]):
                apis.add(m)

    return list(apis), js_files[:5]

def analyze_js_bundle(url, base_url):
    """Analisa um bundle JS em busca de endpoints e padrões."""
    try:
        r = requests.get(url, timeout=15, headers={"User-Agent":"Mozilla/5.0"})
        js = r.text
        found = {
            "apis": set(),
            "graphql": False,
            "algolia": False,
            "firebase": False,
            "wp_plugins": set(),
        }
        # API endpoints
        for p in [r'["\'](/api/[^"\']{3,80})["\']', r'["\'](/graphql[^"\']*)["\']',
                  r'"url":\s*"(https?://[^"]{10,100})"']:
            for m in re.findall(p, js):
                if any(k in m.lower() for k in ["propert","search","listing","imovel","sale","buy","real"]):
                    found["apis"].add(m[:80])

        # GraphQL
        if any(x in js for x in ["graphql","ApolloClient","gql`","__typename","query Properties"]):
            found["graphql"] = True

        # Algolia
        if any(x in js for x in ["algoliasearch","algolia","searchClient","indexName"]):
            found["algolia"] = True
            idx = re.findall(r'"indexName":\s*"([^"]+)"', js)
            if idx: found["algolia_index"] = idx[0]
            app_id = re.findall(r'"appId":\s*"([^"]+)"', js)
            if app_id: found["algolia_app_id"] = app_id[0]
            api_key = re.findall(r'"apiKey":\s*"([A-Za-z0-9]{20,})"', js)
            if api_key: found["algolia_key"] = api_key[0]

        # Firebase
        if any(x in js for x in ["firebase","firestore","googleapis.com/firestore"]):
            found["firebase"] = True

        # WP plugins
        wp_plugins = {
            "estatik": "estatik", "realhomes": "realhomes",
            "essential-real-estate": "essential-real-estate",
            "wp-property": "wp-property", "houzez": "houzez",
            "real-estate-7": "real-estate-7",
        }
        for key, name in wp_plugins.items():
            if key in js.lower():
                found["wp_plugins"].add(name)

        return found
    except:
        return {}

def check_sitemaps(base_url):
    """Verifica sitemaps para encontrar URLs de imóveis."""
    sitemap_urls = [
        "/sitemap.xml", "/sitemap_index.xml", "/sitemaps/sitemap.xml",
        "/property-sitemap.xml", "/listing-sitemap.xml",
        "/imoveis-sitemap.xml", "/properties-sitemap.xml",
        "/post-sitemap.xml", "/page-sitemap.xml",
    ]
    found = []
    for sm in sitemap_urls:
        url = base_url.rstrip("/") + sm
        try:
            r = requests.get(url, timeout=8, headers={"User-Agent":"Mozilla/5.0"})
            if r.status_code == 200 and ("xml" in r.headers.get("content-type","") or "<url" in r.text or "<sitemap" in r.text):
                # Count property URLs
                soup = BeautifulSoup(r.text, "xml") if "xml" in r.text else None
                urls = soup.find_all("loc") if soup else []
                prop_urls = [u.text for u in urls if any(k in u.text for k in ["property","imovel","casa","house","villa","apartamento"])]
                found.append({"path": sm, "total_urls": len(urls), "property_urls": len(prop_urls),
                               "sample": prop_urls[:2] if prop_urls else [u.text for u in urls[:2]]})
        except: pass
        time.sleep(0.3)
    return found

def check_robots(base_url):
    """Analisa robots.txt."""
    try:
        r = requests.get(base_url.rstrip("/")+"/robots.txt", timeout=8, headers={"User-Agent":"Mozilla/5.0"})
        if r.status_code == 200:
            sitemaps = re.findall(r'Sitemap:\s*(\S+)', r.text)
            disallows = re.findall(r'Disallow:\s*(\S+)', r.text)
            return {"sitemaps": sitemaps, "disallows": disallows[:10]}
    except: pass
    return {}

def check_wp_apis(base_url):
    """Testa endpoints WordPress REST API para plugins imobiliários."""
    endpoints = [
        "/wp-json/wp/v2/property",
        "/wp-json/wp/v2/properties",
        "/wp-json/estatik/v1/properties",
        "/wp-json/realhomes/v1/properties",
        "/wp-json/essential-real-estate/v1/properties",
        "/wp-json/houzez/v1/listings",
        "/wp-json/wp/v2/hm_property",
        "/wp-json/wp/v2/listings",
        "/wp-json/wp/v2/imoveis",
    ]
    found = []
    for ep in endpoints:
        try:
            r = requests.get(base_url.rstrip("/")+ep, timeout=8, headers={"User-Agent":"Mozilla/5.0"})
            if r.status_code == 200:
                try:
                    data = r.json()
                    if isinstance(data, list) and len(data) > 0:
                        found.append({"endpoint": ep, "count": len(data), "sample_title": data[0].get("title",{}).get("rendered","")[:50] if isinstance(data[0].get("title"),dict) else str(data[0].get("title",""))[:50]})
                    elif isinstance(data, dict) and data.get("properties"):
                        found.append({"endpoint": ep, "data": str(data)[:200]})
                except: pass
        except: pass
        time.sleep(0.3)
    return found

# ── MAIN INSPECTION ──────────────────────────────────────────
def inspect_site(nome, base_url, test_url=None):
    test_url = test_url or base_url
    report = {"nome": nome, "base_url": base_url, "apis": [], "score": 0}

    print(f"\n{'='*60}")
    print(f"🔍 {nome}  —  {base_url}")
    print(f"{'='*60}")

    # 1. Fetch direto
    status, html, headers = fetch_direct(test_url)
    size = len(html) if html else 0
    print(f"  HTTP direto: {status} | {size} chars")

    # Cloudflare?
    if detect_cloudflare(html or "", headers):
        print(f"  ⚠️  Cloudflare detetado!")
        report["cloudflare"] = True

    # Framework + CMS
    fw = detect_framework(html or "")
    cms = detect_cms(html or "")
    report["framework"] = fw
    report["cms"] = cms
    print(f"  Framework: {fw}" + (f"  |  CMS: {cms}" if cms else ""))

    # 2. JSON-LD
    jsonld = extract_jsonld(html or "")
    if jsonld:
        print(f"  JSON-LD: ✅ {len(jsonld)} propriedades — ex: {jsonld[0]}")
        report["jsonld"] = True
        report["score"] += 20
    else:
        print(f"  JSON-LD: ❌")

    # 3. APIs no HTML + JS files
    inline_apis, js_files = find_apis_in_html(html or "", base_url)
    if inline_apis:
        print(f"  APIs inline: {inline_apis[:3]}")
        report["apis"].extend(inline_apis[:3])
        report["score"] += 15

    # 4. Analisar bundles JS
    if js_files:
        print(f"  Bundles JS: {len(js_files)} ficheiros — a analisar...")
        for jsf in js_files[:3]:
            bundle = analyze_js_bundle(jsf, base_url)
            if bundle.get("apis"):
                print(f"    📦 {jsf[-40:]}: {list(bundle['apis'])[:2]}")
                report["apis"].extend(list(bundle["apis"])[:2])
                report["score"] += 20
            if bundle.get("graphql"):
                print(f"    GraphQL: ✅")
                report["graphql"] = True
                report["score"] += 15
            if bundle.get("algolia"):
                print(f"    Algolia: ✅ index={bundle.get('algolia_index','?')} appId={bundle.get('algolia_app_id','?')} key={bundle.get('algolia_key','?')[:20] if bundle.get('algolia_key') else '?'}")
                report["algolia"] = bundle
                report["score"] += 25
            if bundle.get("firebase"):
                print(f"    Firebase: ✅")
                report["firebase"] = True
                report["score"] += 15
            if bundle.get("wp_plugins"):
                print(f"    WP plugins: {bundle['wp_plugins']}")
                report["wp_plugins"] = list(bundle["wp_plugins"])
        time.sleep(1)

    # 5. robots.txt
    robots = check_robots(base_url)
    if robots.get("sitemaps"):
        print(f"  robots.txt sitemaps: {robots['sitemaps'][:3]}")
        report["extra_sitemaps"] = robots["sitemaps"]

    # 6. Sitemaps
    sitemaps = check_sitemaps(base_url)
    if sitemaps:
        for sm in sitemaps:
            print(f"  Sitemap ✅ {sm['path']}: {sm['total_urls']} URLs, {sm['property_urls']} imóveis — {sm['sample'][:1]}")
        report["sitemaps"] = sitemaps
        report["score"] += 10

    # 7. WordPress REST API
    wp_apis = check_wp_apis(base_url)
    if wp_apis:
        for wp in wp_apis:
            print(f"  WP API ✅ {wp['endpoint']}: {wp.get('count','?')} items — {wp.get('sample_title','')}")
        report["wp_apis"] = wp_apis
        report["score"] += 30

    # 8. Fetch com proxy JS
    print(f"  A tentar proxy JS (Crawlbase)...")
    status2, html2, _ = fetch_rendered(test_url, "crawlbase")
    if html2 and "<" in html2:
        soup2 = BeautifulSoup(html2, "html.parser")
        precos = [e.get_text(strip=True) for e in soup2.find_all(True)
                  if "€" in e.get_text() and 5<len(e.get_text(strip=True))<30 and any(c.isdigit() for c in e.get_text())][:3]
        links = len([a for a in soup2.select("a[href]") if any(k in a.get("href","").lower() for k in ["property","imovel","sale","buy","venda","comprar"])])
        cards = max(len(soup2.select(s)) for s in ["article","[class*='property']","[class*='listing']","[class*='card']"] if soup2.select(s))
        print(f"  Proxy JS: HTTP {status2} | {len(html2)} chars | {links} links | {cards} cards | preços: {precos}")
        if precos or links > 5 or cards > 2:
            report["proxy_works"] = True
            report["score"] += 20
    else:
        print(f"  Proxy JS: HTTP {status2} — sem conteúdo")

    # Score final
    score = min(100, report["score"])
    emoji = "🟢" if score>=60 else "🟡" if score>=30 else "🔴"
    print(f"\n  {emoji} Score: {score}/100")
    print(f"  APIs encontradas: {report['apis'][:3] or 'Nenhuma'}")
    if report.get("algolia"): print(f"  🎯 ALGOLIA ENCONTRADO — pode scraping direto!")
    if report.get("wp_apis"): print(f"  🎯 WP REST API — scraping direto possível!")
    if report.get("graphql"): print(f"  🎯 GRAPHQL — pode fazer queries diretas!")
    if report.get("jsonld"): print(f"  📋 JSON-LD disponível")

    return report

# ── RUN ──────────────────────────────────────────────────────
SITES = [
    ("Garvetur",           "https://www.garvetur.pt",           "https://www.garvetur.pt/imoveis/venda"),
    ("Sotheby's",          "https://www.sothebysrealty.pt",      "https://www.sothebysrealty.pt/imoveis/compra"),
    ("Chave Nova",         "https://www.chavanova.pt",           "https://www.chavanova.pt/imoveis?distrito=faro&tipo=venda"),
    ("D'Alma Portuguesa",  "https://www.dalmaportuguesa.com",    "https://www.dalmaportuguesa.com/imoveis"),
    ("Vernon Algarve",     "https://www.vernonalgarve.com",      "https://www.vernonalgarve.com/for-sale"),
    ("Sortami",            "https://www.sortami.pt",             "https://www.sortami.pt/imoveis"),
    ("Mimosa Properties",  "https://www.mimosaproperties.com",   "https://www.mimosaproperties.com/properties-for-sale"),
    ("Algarve Dream",      "https://www.algarvedreamproperty.com","https://www.algarvedreamproperty.com/for-sale"),
    ("Algarve Unique",     "https://www.algarveuniqueproperties.com","https://www.algarveuniqueproperties.com/for-sale"),
    ("Boto Properties",    "https://www.botoproperties.com",     "https://www.botoproperties.com/properties-for-sale"),
    ("Sunpoint",           "https://www.sunpointproperties.com", "https://www.sunpointproperties.com/for-sale"),
    ("Your Luxury Prop",   "https://www.yourluxuryproperty.pt",  "https://www.yourluxuryproperty.pt/imoveis-para-venda"),
    ("Barra Prime",        "https://www.barraprime.pt",          "https://www.barraprime.pt/imoveis-para-venda"),
    ("Villas Key",         "https://www.villaskey.com",          "https://www.villaskey.com/en/for-sale"),
]

print("="*60)
print(f"Inspeção Avançada de SPAs — {len(SITES)} sites")
print("="*60)

all_reports = []
for nome, base, test in SITES:
    report = inspect_site(nome, base, test)
    all_reports.append(report)
    time.sleep(3)

# Resumo final
print(f"\n{'='*60}")
print("RELATÓRIO FINAL")
print("="*60)
for r in sorted(all_reports, key=lambda x: -x["score"]):
    score = min(100, r["score"])
    emoji = "🟢" if score>=60 else "🟡" if score>=30 else "🔴"
    techs = []
    if r.get("algolia"): techs.append("Algolia")
    if r.get("graphql"): techs.append("GraphQL")
    if r.get("wp_apis"): techs.append("WP REST")
    if r.get("jsonld"):  techs.append("JSON-LD")
    if r.get("proxy_works"): techs.append("Proxy OK")
    if r.get("cloudflare"): techs.append("⚠️Cloudflare")
    print(f"  {emoji} {r['nome']:25s} Score:{score:3d}  {r['framework']:10s}  {', '.join(techs) or 'Bloqueado'}")

# Save full report
with open("/tmp/inspect_report.json","w") as f:
    json.dump(all_reports, f, ensure_ascii=False, indent=2, default=str)
print(f"\n📄 Relatório completo: /tmp/inspect_report.json")
