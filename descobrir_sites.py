#!/usr/bin/env python3
"""
Auto-descoberta dos sites problemáticos — corre na Consola do Railway:

    python3 descobrir_sites.py

Para cada site: renderiza a homepage (Browserless/Playwright), encontra os
links de listagem na navegação, renderiza os melhores candidatos e testa a
extracção completa (cards → keywords → payloads JS). Imprime um relatório
compacto por site com a evidência necessária para fixar cada scraper.

Não escreve nada na base de dados.
"""
import re, sys, time
from urllib.parse import urljoin, urlparse

import algarve_monitor as M   # reutiliza render + extracção + validar reais

SITES = {
    "Vernon Algarve":     "https://www.vernonalgarve.com",
    "D'Alma Portuguesa":  "https://www.dalmaportuguesa.com",
    "Barra Prime":        "https://www.barraprime.pt",
    "Your Luxury":        "https://www.yourluxuryproperty.pt",
    "Villas Key":         "https://www.villaskey.com",
    "Sotheby's":          "https://www.sothebysrealty.pt",
    "Mimosa":             "https://www.mimosaproperties.com",
    "Tripalgarve":        "https://www.tripalgarve.com",
    "JPP":                "https://jppproperties.com",
    "Nurisimo":           "https://www.nurisimo.com",
}

NAV_KEYWORDS = ("venda", "sale", "propert", "imove", "imóve", "comprar", "buy",
                "listing", "portfolio", "casas", "villas", "apartament")

PERFIL = {"preco_max": 250_000, "quartos_min": 2}


def render(url):
    """Renderiza via a máquina real do monitor (Browserless → chromium)."""
    try:
        return M._pw_open_page("descobrir", url, "a[href]") or ""
    except Exception as e:
        print(f"      render falhou: {e}")
        return ""


def candidatos_de_listagem(html, base):
    """Extrai da navegação os links que parecem páginas de listagem."""
    soup = M.safe_soup(html, "descobrir")
    if not soup:
        return []
    vistos, cand = set(), []
    for a in soup.select("a[href]"):
        h = (a.get("href") or "").strip()
        if not h or h.startswith(("#", "javascript", "mailto", "tel:")):
            continue
        u = urljoin(base, h)
        if urlparse(u).netloc != urlparse(base).netloc:
            continue
        low = u.lower()
        if any(k in low for k in NAV_KEYWORDS) and u not in vistos:
            # descarta links de detalhe individuais (têm slug longo/ID)
            if re.search(r"/(imovel|property|propriedade)/[a-z0-9\-]{10,}", low):
                continue
            vistos.add(u)
            texto = a.get_text(strip=True)[:30]
            cand.append((u, texto))
    return cand[:6]


def testar_extraccao(nome, url, html):
    """Corre a extracção real e devolve (raw, validos, metodo)."""
    items = M._api_scrape_html(html, url, nome)
    metodo = "cards/keywords/payload"
    validos = [i for i in items if M.validar(i, PERFIL)]
    return len(items), len(validos), metodo, items[:3]


def hrefs_da_pagina(html, base):
    from collections import Counter
    soup = M.safe_soup(html, "d")
    segs = Counter()
    if soup:
        for a in soup.select("a[href]")[:400]:
            h = (a.get("href") or "").strip()
            if not h or len(h) < 2:
                continue
            path = urlparse(h).path if h.startswith("http") else h
            partes = [s for s in path.split("/") if s]
            if partes:
                segs[partes[0][:22]] += 1
    return segs.most_common(6)


def main():
    alvo = sys.argv[1] if len(sys.argv) > 1 else None
    sites = {k: v for k, v in SITES.items()
             if not alvo or alvo.lower() in k.lower()}

    for nome, base in sites.items():
        print("\n" + "=" * 62)
        print(f"█ {nome}  —  {base}")
        html = render(base)
        print(f"  homepage: {len(html)//1024}KB")
        if len(html) < 3000:
            print("  ⛔ homepage vazia/bloqueada — site possivelmente morto p/ bots")
            continue

        # 1) A própria homepage já tem anúncios?
        raw, ok, met, amostra = testar_extraccao(nome, base, html)
        print(f"  homepage → extracção: raw={raw} válidos={ok}")

        # 2) Candidatos de listagem da navegação
        cands = candidatos_de_listagem(html, base)
        if not cands:
            print(f"  sem candidatos na nav | hrefs: {hrefs_da_pagina(html, base)}")
        for u, txt in cands:
            h2 = render(u)
            if len(h2) < 3000:
                print(f"  • '{txt}' {u[:58]} → {len(h2)//1024}KB (vazio)")
                continue
            raw, ok, met, amostra = testar_extraccao(nome, u, h2)
            marca = "✅" if ok else ("⚠️ " if raw else "❌")
            print(f"  {marca} '{txt}' {u[:58]}")
            print(f"      raw={raw} válidos={ok} ({len(h2)//1024}KB)")
            if raw and not ok:
                # porquê? mostra os 2 primeiros motivos
                for it in amostra[:2]:
                    M.validar(it, PERFIL, _log_descarte=True)
            if not raw:
                print(f"      hrefs: {hrefs_da_pagina(h2, base)}")
            if ok:
                for it in amostra[:2]:
                    print(f"      ex: {str(it.get('titulo'))[:44]} | {str(it.get('preco'))[:12]}")
        time.sleep(1)

    print("\n" + "=" * 62)
    print("Cola este output completo na conversa para eu fixar cada scraper.")


if __name__ == "__main__":
    main()
