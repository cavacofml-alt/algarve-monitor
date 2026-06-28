#!/usr/bin/env python3
"""
Inspeciona SPAs React/Angular para encontrar APIs JSON internas.
Corre na Consola do Railway: python3 /app/inspect_apis.py

Para cada site, tenta:
1. Encontrar chamadas API no código JS
2. Testar endpoints comuns (/api/properties, /api/imoveis, etc.)
3. Ver se há sitemap.xml com links de imóveis
"""
import os, requests, re, json, time
from bs4 import BeautifulSoup

CKEY = os.getenv("CRAWLBASE_KEY","")
ZKEY = os.getenv("ZENROWS_KEY","")

def fetch(url, timeout=30):
    """Fetch simples sem proxy para ver o HTML base."""
    try:
        r = requests.get(url, timeout=timeout, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        return r.status_code, r.text
    except Exception as e:
        return 0, str(e)

def fetch_proxy(url, timeout=60):
    """Fetch com Crawlbase JS."""
    try:
        r = requests.get(
            f"https://api.crawlbase.com/?token={CKEY}&url={requests.utils.quote(url)}&ajax_wait=true&page_wait=5000",
            timeout=timeout)
        return r.status_code, r.text
    except Exception as e:
        return 0, str(e)

def find_api_in_js(html, base_url):
    """Procura chamadas API no código JavaScript da página."""
    apis = set()
    # Encontra scripts inline
    soup = BeautifulSoup(html, "html.parser") if "<" in html else None
    if not soup: return []

    # Procura padrões de API em scripts
    scripts = soup.find_all("script")
    for script in scripts:
        text = script.string or ""
        # Padrões comuns de chamadas API
        patterns = [
            r'["\'](/api/[^"\']+)["\']',
            r'["\'](/_next/data/[^"\']+\.json)["\']',
            r'fetch\(["\']([^"\']+)["\']',
            r'axios\.[a-z]+\(["\']([^"\']+)["\']',
            r'url:\s*["\']([^"\']+properties[^"\']*)["\']',
            r'endpoint:\s*["\']([^"\']+)["\']',
            r'"apiUrl":\s*"([^"]+)"',
        ]
        for p in patterns:
            matches = re.findall(p, text)
            for m in matches:
                if any(k in m.lower() for k in ["property","imovel","house","search","listing","real"]):
                    apis.add(m)

    # Procura links para JS bundle files
    js_files = [s.get("src","") for s in soup.find_all("script", src=True)]

    return list(apis), js_files[:3]

def test_common_apis(base_url):
    """Testa endpoints JSON comuns."""
    endpoints = [
        "/api/properties", "/api/imoveis", "/api/listings",
        "/api/v1/properties", "/api/v2/properties",
        "/_next/data/properties.json",
        "/wp-json/wp/v2/properties",
        "/wp-json/properties/v1/listings",
        "/feed/properties.json",
        "/sitemap.xml",
        "/robots.txt",
    ]
    results = []
    for ep in endpoints:
        url = base_url.rstrip("/") + ep
        try:
            r = requests.get(url, timeout=10, headers={"User-Agent":"Mozilla/5.0"})
            if r.status_code == 200 and len(r.text) > 100:
                is_json = r.headers.get("content-type","").startswith("application/json") or r.text.strip().startswith("{") or r.text.strip().startswith("[")
                if is_json or "xml" in r.headers.get("content-type",""):
                    results.append((ep, r.status_code, len(r.text), r.text[:200]))
        except: pass
        time.sleep(0.5)
    return results

def inspect_site(nome, base_url, test_url=None):
    print(f"\n{'='*55}")
    print(f"🔍 {nome}")
    print(f"   Base: {base_url}")

    test_url = test_url or base_url

    # 1. Fetch direto (sem proxy) para ver HTML base
    status, html = fetch(test_url)
    print(f"   Fetch direto: HTTP {status}, {len(html)} chars")

    # Detecta framework
    if "react" in html.lower() or "_react" in html.lower():
        print(f"   Framework: ⚛️  React")
    elif "vue" in html.lower():
        print(f"   Framework: 💚 Vue")
    elif "angular" in html.lower():
        print(f"   Framework: 🔴 Angular")
    elif "next" in html.lower():
        print(f"   Framework: ▲ Next.js")

    # 2. Procura APIs no JS
    if html and "<" in html:
        apis, js_files = find_api_in_js(html, base_url)
        if apis:
            print(f"   APIs encontradas no JS: {apis[:5]}")
        if js_files:
            print(f"   JS bundles: {js_files[:2]}")

    # 3. Testa endpoints comuns
    print(f"   A testar endpoints comuns...")
    api_results = test_common_apis(base_url)
    if api_results:
        for ep, status, size, preview in api_results:
            print(f"   ✅ {ep} → HTTP {status}, {size} chars: {preview[:80]}")
    else:
        print(f"   ❌ Nenhum endpoint JSON encontrado")

    # 4. Tenta com proxy JS para ver conteúdo renderizado
    print(f"   A tentar com proxy JS...")
    status2, html2 = fetch_proxy(test_url)
    if html2 and "<" in html2:
        soup2 = BeautifulSoup(html2, "html.parser")
        precos = [e.get_text(strip=True) for e in soup2.find_all(True)
                  if "€" in e.get_text() and 5<len(e.get_text(strip=True))<30 and any(c.isdigit() for c in e.get_text())][:3]
        links = len([a for a in soup2.select("a[href]") if any(k in a.get("href","").lower() for k in ["property","imovel","sale","buy","venda"])])
        print(f"   Proxy JS: HTTP {status2}, {len(html2)} chars, {links} links imóveis, preços: {precos}")
    else:
        print(f"   Proxy JS: HTTP {status2} — sem conteúdo")

SITES = [
    ("Garvetur",          "https://www.garvetur.pt",      "https://www.garvetur.pt/imoveis/venda"),
    ("Sotheby's",         "https://www.sothebysrealty.pt", "https://www.sothebysrealty.pt/imoveis/compra"),
    ("Chave Nova",        "https://www.chavanova.pt",      "https://www.chavanova.pt/imoveis?distrito=faro&tipo=venda"),
    ("D'Alma Portuguesa", "https://www.dalmaportuguesa.com","https://www.dalmaportuguesa.com/imoveis"),
    ("Vernon Algarve",    "https://www.vernonalgarve.com", "https://www.vernonalgarve.com/for-sale"),
    ("Sortami",           "https://www.sortami.pt",        "https://www.sortami.pt/imoveis"),
    ("Mimosa Properties", "https://www.mimosaproperties.com","https://www.mimosaproperties.com/properties-for-sale"),
    ("Algarve Dream",     "https://www.algarvedreamproperty.com","https://www.algarvedreamproperty.com/for-sale"),
    ("Algarve Unique",    "https://www.algarveuniqueproperties.com","https://www.algarveuniqueproperties.com/for-sale"),
    ("Boto Properties",   "https://www.botoproperties.com","https://www.botoproperties.com/properties-for-sale"),
    ("Sunpoint",          "https://www.sunpointproperties.com","https://www.sunpointproperties.com/for-sale"),
    ("Your Luxury Prop",  "https://www.yourluxuryproperty.pt","https://www.yourluxuryproperty.pt/imoveis-para-venda"),
    ("Barra Prime",       "https://www.barraprime.pt",     "https://www.barraprime.pt/imoveis-para-venda"),
    ("Villas Key",        "https://www.villaskey.com",     "https://www.villaskey.com/en/for-sale"),
]

for nome, base, test in SITES:
    inspect_site(nome, base, test)
    time.sleep(3)

print(f"\n{'='*55}")
print("✅ Inspeção concluída!")
print("Cola o resultado aqui para implementar os scrapers API.")
