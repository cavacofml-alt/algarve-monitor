#!/usr/bin/env python3
"""
Remove imóveis inválidos da base de dados:
- Links de redes sociais
- Títulos genéricos (nome da imobiliária)
Corre na Consola do Railway: python3 /app/limpar_db.py
"""
import os, psycopg
from psycopg import rows as psycopg_rows

DATABASE_URL = os.getenv("DATABASE_URL","")

DOMINIOS_EXCLUIR = [
    "linkedin.com","facebook.com","instagram.com","twitter.com",
    "youtube.com","tiktok.com","whatsapp.com",
]

TITULOS_GENERICOS = [
    "kw portugal","era imobiliária","lnhouse","algarvila","villas tavira",
    "casas do sotavento","garvetur","sortami","imocusto",
    "concelhos","naturezas","sobre nós","contactos",
]

def main():
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor(row_factory=psycopg_rows.dict_row) as cur:
            cur.execute("SELECT id, titulo, link, fonte FROM imoveis WHERE disponivel=TRUE")
            todos = cur.fetchall()

        apagar = []
        for im in todos:
            titulo = (im["titulo"] or "").lower().strip()
            link   = (im["link"] or "").lower()
            fonte  = (im["fonte"] or "").lower()

            if any(d in link for d in DOMINIOS_EXCLUIR):
                apagar.append((im["id"], f"rede social: {link[:60]}"))
                continue
            if titulo in TITULOS_GENERICOS or titulo == fonte or len(titulo) < 5:
                apagar.append((im["id"], f"título genérico: {titulo}"))
                continue

        print(f"Total: {len(todos)} | A remover: {len(apagar)}")
        for iid, motivo in apagar:
            print(f"  ❌ {motivo}")

        if apagar:
            with conn.cursor() as cur:
                for iid, _ in apagar:
                    cur.execute("DELETE FROM imoveis WHERE id=%s", (iid,))
            conn.commit()
            print(f"\n✅ {len(apagar)} imóveis removidos da base de dados.")
        else:
            print("✅ Nada a remover.")

main()
