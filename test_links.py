#!/usr/bin/env python3
"""
Testa todos os links de imóveis na base de dados.
Verifica se cada URL ainda está acessível.
Corre na Consola do Railway: python3 /app/test_links.py
"""
import os, requests, psycopg
from psycopg import rows as psycopg_rows
from datetime import datetime

DATABASE_URL = os.getenv("DATABASE_URL","")
SCRAPERAPI_KEY = os.getenv("SCRAPERAPI_KEY","")

def get_db():
    return psycopg.connect(DATABASE_URL)

def testar_link(url, timeout=10):
    """Testa se um URL está acessível. Devolve (status_code, ok)."""
    try:
        # Usa ScraperAPI para evitar bloqueios
        if SCRAPERAPI_KEY:
            api = f"http://api.scraperapi.com?api_key={SCRAPERAPI_KEY}&url={requests.utils.quote(url)}"
            r = requests.get(api, timeout=30)
        else:
            r = requests.get(url, timeout=timeout,
                headers={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
        ok = r.status_code == 200
        return r.status_code, ok
    except Exception as e:
        return 0, False

def main():
    print(f"{'='*60}")
    print(f"Teste de Links — {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print(f"{'='*60}\n")

    with get_db() as conn:
        with conn.cursor(row_factory=psycopg_rows.dict_row) as cur:
            cur.execute("""
                SELECT id, titulo, link, fonte, zona, disponivel
                FROM imoveis
                WHERE disponivel = TRUE
                ORDER BY criado_em DESC
            """)
            imoveis = cur.fetchall()

    print(f"Total a testar: {len(imoveis)} imóveis\n")

    ok_count = 0
    nok_count = 0
    nok_ids = []

    for i, im in enumerate(imoveis, 1):
        status, ok = testar_link(im["link"])
        if ok:
            ok_count += 1
            print(f"  ✅ [{i}/{len(imoveis)}] {im['fonte']} — {im['titulo'][:50]}")
        else:
            nok_count += 1
            nok_ids.append(im["id"])
            print(f"  ❌ [{i}/{len(imoveis)}] HTTP {status} — {im['fonte']} — {im['titulo'][:50]}")
            print(f"     URL: {im['link']}")

    print(f"\n{'='*60}")
    print(f"Resultado: {ok_count} ✅ OK  |  {nok_count} ❌ Quebrados")

    if nok_ids:
        print(f"\nA marcar {len(nok_ids)} imóveis como indisponíveis...")
        with get_db() as conn:
            with conn.cursor() as cur:
                for iid in nok_ids:
                    cur.execute("""
                        UPDATE imoveis
                        SET disponivel = FALSE, removido_em = NOW()
                        WHERE id = %s
                    """, (iid,))
            conn.commit()
        print(f"✅ {len(nok_ids)} imóveis marcados como removidos.")
    else:
        print("\n✅ Todos os links estão válidos!")

    print(f"{'='*60}")

if __name__ == "__main__":
    main()
