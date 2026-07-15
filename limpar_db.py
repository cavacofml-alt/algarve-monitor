#!/usr/bin/env python3
"""
Limpa da base de dados os registos que não são imóveis.

Reutiliza EXACTAMENTE as regras do algarve_monitor.py (TITULOS_LIXO_RE,
URLS_LIXO_RE, DOMINIOS_EXCLUIR) — não duplica lógica, para não divergirem.

Corre na Consola do Railway:
    python3 limpar_db.py           # simulação (não apaga nada)
    python3 limpar_db.py --apagar  # apaga a sério
"""
import os, sys, re
import psycopg
from psycopg import rows as psycopg_rows

DATABASE_URL = os.getenv("DATABASE_URL", "")
APAGAR = "--apagar" in sys.argv

# ── Regras: lidas do algarve_monitor.py sem executar o módulo ──
# (importar o módulo arrancaria o scheduler/Flask)
_src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "algarve_monitor.py"), encoding="utf-8").read()
_ns = {"re": re}
for _nome in ["DOMINIOS_EXCLUIR", "TITULOS_GENERICOS"]:
    _i = _src.find(f"\n{_nome} = ["); _j = _src.find("\n]", _i)
    exec(_src[_i:_j+2], _ns)
for _nome in ["TITULOS_LIXO_RE", "URLS_LIXO_RE"]:
    _i = _src.find(f"\n{_nome} = re.compile("); _j = _src.find("\n\n", _i)
    exec(_src[_i:_j], _ns)

DOMINIOS_EXCLUIR  = _ns["DOMINIOS_EXCLUIR"]
TITULOS_GENERICOS = _ns["TITULOS_GENERICOS"]
TITULOS_LIXO_RE   = _ns["TITULOS_LIXO_RE"]
URLS_LIXO_RE      = _ns["URLS_LIXO_RE"]


def e_lixo(titulo, link):
    """Devolve o motivo se o registo não for um imóvel; None se for válido."""
    t = (titulo or "").strip()
    u = (link or "").lower()
    if any(d in u for d in DOMINIOS_EXCLUIR):
        return "rede social / link não-imóvel"
    if TITULOS_LIXO_RE.search(t):
        return f"título institucional: {t[:40]}"
    if URLS_LIXO_RE.search(u):
        return "URL institucional ou página de listagem"
    if t.lower() in TITULOS_GENERICOS or len(t) < 5:
        return f"título genérico: {t[:40]}"
    return None


def main():
    if not DATABASE_URL:
        print("ERRO: DATABASE_URL não definida"); return

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor(row_factory=psycopg_rows.dict_row) as cur:
            cur.execute("SELECT id, titulo, link, fonte FROM imoveis")
            todos = cur.fetchall()

        apagar = []
        for im in todos:
            motivo = e_lixo(im["titulo"], im["link"] or im["id"])
            if motivo:
                apagar.append((im["id"], im["fonte"], motivo))

        print(f"Total na BD : {len(todos)}")
        print(f"A remover   : {len(apagar)}")
        print(f"Ficam       : {len(todos) - len(apagar)}\n")

        from collections import Counter
        for fonte, n in Counter(f for _, f, _ in apagar).most_common():
            print(f"  {n:>4}  {fonte}")

        print("\nExemplos:")
        for iid, fonte, motivo in apagar[:10]:
            print(f"  - [{fonte}] {motivo}")
            print(f"    {iid[:78]}")

        if not apagar:
            print("\nOK Nada a remover - a base esta limpa.")
            return
        if not APAGAR:
            print("\nSIMULACAO - nada foi apagado.")
            print("Para apagar a serio:  python3 limpar_db.py --apagar")
            return

        with conn.cursor() as cur:
            for iid, _, _ in apagar:
                try: cur.execute("DELETE FROM historico_precos WHERE imovel_id=%s", (iid,))
                except Exception: conn.rollback()
                cur.execute("DELETE FROM imoveis WHERE id=%s", (iid,))
        conn.commit()
        print(f"\nOK {len(apagar)} registos removidos da base de dados.")


main()
