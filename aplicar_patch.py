#!/usr/bin/env python3
"""
PATCH DEFINITIVO — aplica todos os fixes críticos.
Corre em D:\algarve-monitor\: python aplicar_patch.py
"""
import os, re, sys

f = "algarve_monitor.py"
if not os.path.exists(f):
    print("ERRO: algarve_monitor.py nao encontrado"); sys.exit(1)

content = open(f, encoding='utf-8').read()
dashboard = open("dashboard.html", encoding='utf-8').read() if os.path.exists("dashboard.html") else ""
changes = 0

FIXES = [
    # (descricao, old, new)
    ("proxy_cooldown limpo no reset",
     "if provider in _proxy_exhausted: del _proxy_exhausted[provider]\n        log.info(f\"  ✅ {provider} resetou — novo ciclo\")\n        return False",
     "if provider in _proxy_exhausted: del _proxy_exhausted[provider]\n        _proxy_cooldown.pop(provider, None)\n        _session_exhausted.discard(provider)\n        log.info(f\"  ✅ {provider} resetou — novo ciclo\")\n        return False"),
    ("playwright semaphore 2→1",
     "threading.Semaphore(2)",
     "threading.Semaphore(1)"),
    ("historico_precos guarded",
     'cur.execute("SELECT COUNT(*) FROM historico_precos"); baixas=cur.fetchone()[0]',
     'try:\n                cur.execute("SELECT COUNT(*) FROM historico_precos"); baixas=cur.fetchone()[0]\n            except Exception:\n                conn.rollback(); baixas=0'),
    ("resend domain gmail fix",
     'remetente = os.getenv("EMAIL_REMETENTE","monitor@algarve-imoveis.pt")',
     '_rem = os.getenv("EMAIL_REMETENTE","")\n    remetente = "Monitor <onboarding@resend.dev>" if not _rem or "@gmail" in _rem else _rem'),
    ("marcar_removidos protection",
     'def marcar_removidos(ids_vistos, perfil_nome):',
     'def marcar_removidos(ids_vistos, perfil_nome, total_encontrados=0):\n    if total_encontrados > 0 and total_encontrados < 10:\n        log.warning(f"  Apenas {total_encontrados} items — a saltar marcar_removidos (possivel falha scrapers)")\n        return []'),
    ("marcar_removidos total passado",
     'removidos=marcar_removidos(ids_ronda,perfil["nome"])',
     'removidos=marcar_removidos(ids_ronda,perfil["nome"], total_encontrados=len(todos))'),
]

for desc, old, new in FIXES:
    if old in content:
        content = content.replace(old, new, 1)
        changes += 1
        print(f"  ✅ {desc}")
    elif old.replace("\\n", "\n") in content:
        content = content.replace(old.replace("\\n", "\n"), new.replace("\\n", "\n"), 1)
        changes += 1
        print(f"  ✅ {desc}")
    else:
        already = any(x in content for x in [new[:30], new.replace("\\n","\n")[:30]])
        print(f"  {'✅ já aplicado' if already else '⚠️  não encontrado'}: {desc}")

if changes > 0:
    open(f, 'w', encoding='utf-8').write(content)
    print(f"\n{changes} fixes aplicados. Agora:")
    print("  git add algarve_monitor.py dashboard.html")
    print('  git commit -m "fix: 6 bugs criticos definitivos"')
    print("  git push")
else:
    print("\nNenhum fix necessário — ficheiro já actualizado.")
