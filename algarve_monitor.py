#!/usr/bin/env python3
"""
Monitor de Imóveis — Algarve  v4.0
====================================
Novidades v4:
  1. Autenticação (login com password)
  2. Extração de detalhes completos (área, ano, GPS, descrição)
  3. Alertas de scraper com falha persistente (3+ rondas)
  4. Comparação lado a lado (até 3 imóveis)
  5. Exportar favoritos para Excel
  6. Mapa interativo (Leaflet + OpenStreetMap)
  7. Estimativa de custos (IMT, Imposto de Selo, Registo, etc.)
  8. Histórico de visitas com notas
"""

import os, re, time, json, random, logging, smtplib, schedule, threading
import hashlib, secrets, functools
import requests
import psycopg
from psycopg import rows as psycopg_rows
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from bs4 import BeautifulSoup
from flask import (Flask, render_template_string, jsonify, request,
                   session, redirect, url_for, make_response)
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%d/%m/%Y %H:%M:%S")
log = logging.getLogger("algarve-monitor")

# ============================================================
# CONFIG
# ============================================================
EMAIL_REMETENTE    = os.getenv("EMAIL_REMETENTE",    "o_teu_email@gmail.com")
EMAIL_PASSWORD     = os.getenv("EMAIL_PASSWORD",     "a_tua_app_password")
EMAIL_DESTINATARIO = os.getenv("EMAIL_DESTINATARIO", EMAIL_REMETENTE)
INTERVALO_HORAS    = int(os.getenv("INTERVALO_HORAS", "24"))
DATABASE_URL       = os.getenv("DATABASE_URL", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
SCRAPERAPI_KEY     = os.getenv("SCRAPERAPI_KEY", "")
ZENROWS_KEY        = os.getenv("ZENROWS_KEY", "")
SCRAPINGBEE_KEY    = os.getenv("SCRAPINGBEE_KEY", "")
PORT               = int(os.getenv("PORT", "8080"))
GOOGLE_MAPS_KEY    = os.getenv("GOOGLE_MAPS_KEY", "")    # opcional para geocoding
VAPID_PUBLIC_KEY   = os.getenv("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY  = os.getenv("VAPID_PRIVATE_KEY", "")
VAPID_EMAIL        = os.getenv("VAPID_EMAIL", EMAIL_REMETENTE)

# Autenticação
DASHBOARD_USERNAME = os.getenv("DASHBOARD_USERNAME", "admin")
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "algarve2024")
SECRET_KEY         = os.getenv("SECRET_KEY", secrets.token_hex(32))

PERFIS = [
    {
        "nome":          "Sotavento — T2+ até 200k",
        "email":         os.getenv("PERFIL_1_EMAIL", EMAIL_DESTINATARIO),
        "telegram_chat": os.getenv("PERFIL_1_TELEGRAM_CHAT", ""),
        "preco_max":     int(os.getenv("PERFIL_1_PRECO_MAX",  "200000")),
        "quartos_min":   int(os.getenv("PERFIL_1_QUARTOS_MIN", "2")),
        "tipos":         ["apartamentos", "moradias-e-vivendas"],
        "zonas":         ["faro", "tavira", "olhao",
                          "vila-real-de-santo-antonio", "castro-marim"],
    },
    # {
    #     "nome":          "Lagos — Moradia T3+ até 400k",
    #     "email":         os.getenv("PERFIL_2_EMAIL", "outro@gmail.com"),
    #     "telegram_chat": os.getenv("PERFIL_2_TELEGRAM_CHAT", ""),
    #     "preco_max":     int(os.getenv("PERFIL_2_PRECO_MAX",  "400000")),
    #     "quartos_min":   int(os.getenv("PERFIL_2_QUARTOS_MIN", "3")),
    #     "tipos":         ["moradias-e-vivendas"],
    #     "zonas":         ["lagos", "portimao", "silves"],
    # },
]

TODAS_AS_ZONAS = {
    "faro": "Faro", "tavira": "Tavira", "olhao": "Olhão",
    "vila-real-de-santo-antonio": "VRSA", "castro-marim": "Castro Marim",
    "lagos": "Lagos", "portimao": "Portimão", "silves": "Silves",
    "aljezur": "Aljezur", "albufeira": "Albufeira",
    "lagoa-algarve": "Lagoa", "loul": "Loulé", "monchique": "Monchique",
}

ZONA_SCORE = {
    "Tavira": 10, "Faro": 9, "Olhão": 9, "VRSA": 8, "Castro Marim": 7,
    "Lagos": 8, "Portimão": 7,
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
]

def random_headers():
    return {"User-Agent": random.choice(USER_AGENTS),
            "Accept-Language": "pt-PT,pt;q=0.9,en;q=0.8",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8"}

_proxy_counter = 0
_proxy_stats = {"scraperapi":0,"zenrows":0,"scrapingbee":0,"direto":0}

def proxied_get(url, render=False, **kwargs):
    """Rotação automática entre ScraperAPI, ZenRows e ScrapingBee."""
    global _proxy_counter
    proxies = []
    if SCRAPERAPI_KEY:  proxies.append("scraperapi")
    if ZENROWS_KEY:     proxies.append("zenrows")
    if SCRAPINGBEE_KEY: proxies.append("scrapingbee")
    if not proxies:
        _proxy_stats["direto"] += 1
        return requests.get(url, headers=random_headers(), timeout=15)
    proxy = proxies[_proxy_counter % len(proxies)]
    _proxy_counter += 1
    _proxy_stats[proxy] += 1
    log.debug(f"Proxy: {proxy} ({_proxy_counter})")
    try:
        if proxy == "scraperapi":
            rp = "&render=true&wait=3000" if render else ""
            api = f"http://api.scraperapi.com?api_key={SCRAPERAPI_KEY}&url={requests.utils.quote(url)}{rp}"
            return requests.get(api, timeout=60, headers=random_headers())
        elif proxy == "zenrows":
            params = {"url":url,"apikey":ZENROWS_KEY,
                      "js_render":"true" if render else "false","premium_proxy":"true"}
            return requests.get("https://api.zenrows.com/v1/", params=params, timeout=60)
        elif proxy == "scrapingbee":
            params = {"api_key":SCRAPINGBEE_KEY,"url":url,
                      "render_js":"true" if render else "false","premium_proxy":"true"}
            return requests.get("https://app.scrapingbee.com/api/v1/", params=params, timeout=60)
    except Exception as e:
        log.warning(f"Proxy {proxy} falhou: {e} — a tentar direto")
        return requests.get(url, headers=random_headers(), timeout=15)

def get_proxy_stats():
    total = sum(_proxy_stats.values())
    return {k:{"pedidos":v,"pct":round(v/total*100) if total else 0}
            for k,v in _proxy_stats.items() if v>0}

# ============================================================
# BASE DE DADOS
# ============================================================

def get_db():
    if not DATABASE_URL: raise RuntimeError("DATABASE_URL não definida.")
    return psycopg.connect(DATABASE_URL)

def init_db():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS imoveis (
                    id              TEXT PRIMARY KEY,
                    perfil_nome     TEXT NOT NULL,
                    titulo          TEXT,
                    preco           TEXT,
                    preco_valor     INTEGER,
                    area_m2         INTEGER,
                    preco_m2        INTEGER,
                    quartos         INTEGER,
                    ano_construcao  INTEGER,
                    descricao       TEXT,
                    lat             DOUBLE PRECISION,
                    lng             DOUBLE PRECISION,
                    morada          TEXT,
                    link            TEXT,
                    fonte           TEXT,
                    zona            TEXT,
                    imagem_url      TEXT,
                    imagens         TEXT[],
                    score           INTEGER DEFAULT 0,
                    disponivel      BOOLEAN DEFAULT TRUE,
                    estado          TEXT DEFAULT 'novo',
                    nota            TEXT DEFAULT '',
                    criado_em       TIMESTAMP DEFAULT NOW(),
                    atualizado_em   TIMESTAMP DEFAULT NOW(),
                    removido_em     TIMESTAMP,
                    reativado_em    TIMESTAMP,
                    favorito        BOOLEAN DEFAULT FALSE,
                    detalhes_extra  JSONB DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS historico_precos (
                    id           SERIAL PRIMARY KEY,
                    imovel_id    TEXT REFERENCES imoveis(id),
                    preco_antigo TEXT,
                    preco_novo   TEXT,
                    alterado_em  TIMESTAMP DEFAULT NOW()
                );
                CREATE TABLE IF NOT EXISTS scraper_logs (
                    id           SERIAL PRIMARY KEY,
                    fonte        TEXT,
                    perfil_nome  TEXT,
                    total        INTEGER,
                    novos        INTEGER,
                    paginas      INTEGER DEFAULT 1,
                    erros        TEXT,
                    executado_em TIMESTAMP DEFAULT NOW()
                );
                CREATE TABLE IF NOT EXISTS push_subscriptions (
                    id        SERIAL PRIMARY KEY,
                    endpoint  TEXT UNIQUE,
                    p256dh    TEXT,
                    auth      TEXT,
                    criado_em TIMESTAMP DEFAULT NOW()
                );
                CREATE TABLE IF NOT EXISTS mercado_snapshot (
                    id           SERIAL PRIMARY KEY,
                    zona         TEXT,
                    perfil_nome  TEXT,
                    preco_medio  INTEGER,
                    total_ativos INTEGER,
                    data         DATE DEFAULT CURRENT_DATE,
                    UNIQUE(zona, perfil_nome, data)
                );
                CREATE TABLE IF NOT EXISTS visitas (
                    id          SERIAL PRIMARY KEY,
                    imovel_id   TEXT REFERENCES imoveis(id),
                    data_visita DATE NOT NULL,
                    nota        TEXT DEFAULT '',
                    avaliacao   INTEGER CHECK(avaliacao BETWEEN 1 AND 5),
                    criado_em   TIMESTAMP DEFAULT NOW()
                );
                CREATE TABLE IF NOT EXISTS perfis_config (
                    id           SERIAL PRIMARY KEY,
                    nome         TEXT NOT NULL,
                    email        TEXT NOT NULL,
                    ativo        BOOLEAN DEFAULT TRUE,
                    preco_max    INTEGER DEFAULT 200000,
                    quartos_min  INTEGER DEFAULT 2,
                    tipos        TEXT[] DEFAULT ARRAY['apartamentos','moradias-e-vivendas'],
                    zonas        TEXT[] DEFAULT ARRAY['faro','tavira','olhao','vila-real-de-santo-antonio','castro-marim'],
                    criado_em    TIMESTAMP DEFAULT NOW(),
                    atualizado_em TIMESTAMP DEFAULT NOW()
                );
            """)
        conn.commit()
    log.info("Base de dados v4 inicializada.")

def get_perfis_db():
    """Lê perfis da base de dados. Se não houver, usa os do código."""
    try:
        with get_db() as conn:
            with conn.cursor(row_factory=psycopg_rows.dict_row) as cur:
                cur.execute("SELECT * FROM perfis_config WHERE ativo=TRUE ORDER BY id")
                rows = cur.fetchall()
                if rows:
                    return [{
                        "nome": r["nome"], "email": r["email"],
                        "preco_max": r["preco_max"], "quartos_min": r["quartos_min"],
                        "tipos": list(r["tipos"]), "zonas": list(r["zonas"]),
                        "telegram_chat": "",
                        "_db_id": r["id"],
                    } for r in rows]
    except Exception as e:
        log.warning(f"get_perfis_db: {e}")
    return PERFIS  # fallback para perfis do código

def get_todos_perfis_db():
    """Lê todos os perfis (ativos e inativos)."""
    try:
        with get_db() as conn:
            with conn.cursor(row_factory=psycopg_rows.dict_row) as cur:
                cur.execute("SELECT * FROM perfis_config ORDER BY id")
                return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        log.warning(f"get_todos_perfis_db: {e}")
        return []

def criar_perfil_db(nome, email, preco_max, quartos_min, tipos, zonas):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO perfis_config (nome, email, preco_max, quartos_min, tipos, zonas)
                VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
            """, (nome, email, preco_max, quartos_min, tipos, zonas))
            new_id = cur.fetchone()[0]
        conn.commit()
    return new_id

def atualizar_perfil_db(pid, nome, email, preco_max, quartos_min, tipos, zonas, ativo):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE perfis_config SET nome=%s, email=%s, preco_max=%s,
                quartos_min=%s, tipos=%s, zonas=%s, ativo=%s, atualizado_em=NOW()
                WHERE id=%s
            """, (nome, email, preco_max, quartos_min, tipos, zonas, ativo, pid))
        conn.commit()

def apagar_perfil_db(pid):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM perfis_config WHERE id=%s", (pid,))
        conn.commit()

def sincronizar_perfis_iniciais():
    """Se não há perfis na DB, copia os do código."""
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM perfis_config")
                count = cur.fetchone()[0]
        if count == 0:
            for p in PERFIS:
                criar_perfil_db(p["nome"], p["email"], p["preco_max"],
                    p["quartos_min"], p["tipos"], p["zonas"])
            log.info(f"Perfis iniciais copiados para a DB ({len(PERFIS)})")
    except Exception as e:
        log.warning(f"sincronizar_perfis_iniciais: {e}")

def geocodificar_existentes():
    """Geocodifica imóveis que ainda não têm coordenadas GPS."""
    try:
        with get_db() as conn:
            with conn.cursor(row_factory=psycopg_rows.dict_row) as cur:
                cur.execute("""
                    SELECT id, titulo, zona FROM imoveis
                    WHERE lat IS NULL AND disponivel=TRUE
                    LIMIT 50
                """)
                sem_coords = cur.fetchall()

        if not sem_coords:
            log.info("Geocoding: todos os imóveis já têm coordenadas.")
            return

        log.info(f"A geocodificar {len(sem_coords)} imóveis...")
        atualizados = 0
        for im in sem_coords:
            lat, lng = geocodificar(im["titulo"], im["zona"])
            if lat and lng:
                with get_db() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "UPDATE imoveis SET lat=%s, lng=%s WHERE id=%s",
                            (lat, lng, im["id"]))
                    conn.commit()
                atualizados += 1

        log.info(f"Geocoding concluído: {atualizados}/{len(sem_coords)} atualizados")
    except Exception as e:
        log.error(f"geocodificar_existentes: {e}")

def extrair_preco_valor(p):
    if not p: return None
    d = re.sub(r"[^\d]", "", p)
    return int(d) if d else None

def extrair_area(t):
    if not t: return None
    m = re.search(r"(\d+)\s*m[²2]", t, re.I)
    return int(m.group(1)) if m else None

def extrair_quartos(t):
    if not t: return None
    m = re.search(r"[Tt](\d)", t)
    if m: return int(m.group(1))
    m = re.search(r"(\d)\s*quarto", t, re.I)
    return int(m.group(1)) if m else None

# Cache de geocoding para não repetir pedidos
_geocoding_cache = {}

def geocodificar(titulo, zona):
    """
    Converte zona/título em coordenadas GPS usando Nominatim (OpenStreetMap).
    Completamente gratuito, sem API key.
    """
    if not zona: return None, None

    # Mapeamento direto de zonas conhecidas (mais rápido e fiável)
    COORDS_ZONAS = {
        "Faro":         (37.0193, -7.9304),
        "Tavira":       (37.1241, -7.6507),
        "Olhão":        (37.0290, -7.8418),
        "VRSA":         (37.1940, -7.4148),
        "Castro Marim": (37.2147, -7.4440),
        "Lagos":        (37.1019, -8.6752),
        "Portimão":     (37.1358, -8.5380),
        "Silves":       (37.1897, -8.4388),
        "Albufeira":    (37.0882, -8.2506),
        "Loulé":        (37.1435, -8.0240),
        "VRSA/Castro Marim": (37.2040, -7.4300),
        "Algarve Sotavento": (37.1000, -7.7000),
        "Algarve":      (37.0902, -8.0902),
    }

    if zona in COORDS_ZONAS:
        lat, lng = COORDS_ZONAS[zona]
        # Adiciona pequena variação aleatória para não sobrepor pins no mesmo ponto
        import random
        lat += random.uniform(-0.02, 0.02)
        lng += random.uniform(-0.02, 0.02)
        return round(lat, 6), round(lng, 6)

    # Tenta geocodificar via Nominatim se zona não está no mapa
    cache_key = zona.lower().strip()
    if cache_key in _geocoding_cache:
        return _geocoding_cache[cache_key]

    try:
        url = f"https://nominatim.openstreetmap.org/search?q={requests.utils.quote(zona+', Algarve, Portugal')}&format=json&limit=1"
        r = requests.get(url, headers={"User-Agent":"AlgarveMonitor/1.0"}, timeout=5)
        data = r.json()
        if data:
            lat = float(data[0]["lat"])
            lng = float(data[0]["lon"])
            _geocoding_cache[cache_key] = (lat, lng)
            time.sleep(1)  # respeitar rate limit Nominatim
            return lat, lng
    except Exception as e:
        log.debug(f"Geocoding {zona}: {e}")

    _geocoding_cache[cache_key] = (None, None)
    return None, None

def calcular_score(item, perfil):
    score = 0
    preco = item.get("preco_valor"); area = item.get("area_m2")
    zona  = item.get("zona","");    quartos = item.get("quartos")
    if preco and preco > 0:
        score += max(0, min(40, int((1-(preco/perfil["preco_max"]))*40)))
    if preco and area and area > 0:
        ratio = 1 - min(1,(preco/area-1000)/2000)
        score += max(0, min(30, int(ratio*30)))
    score += int((ZONA_SCORE.get(zona,5)/10)*20)
    if quartos: score += min(10,(quartos-perfil["quartos_min"]+1)*3)
    return min(100,score)

def imovel_existe(imovel_id):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT preco, disponivel FROM imoveis WHERE id=%s", (imovel_id,))
            row = cur.fetchone()
            return (row[0], row[1]) if row else (None, None)

def guardar_imovel(item, perfil_nome, score):
    pv  = item.get("preco_valor") or extrair_preco_valor(item.get("preco"))
    a   = item.get("area_m2");  pm2 = int(pv/a) if pv and a else None

    # Geocodifica se não tem coordenadas
    if not item.get("lat") and not item.get("lng"):
        zona = item.get("zona","")
        titulo = item.get("titulo","")
        lat, lng = geocodificar(titulo, zona)
        if lat and lng:
            item["lat"] = lat
            item["lng"] = lng
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO imoveis
                    (id,perfil_nome,titulo,preco,preco_valor,area_m2,preco_m2,
                     quartos,ano_construcao,descricao,lat,lng,morada,
                     link,fonte,zona,imagem_url,imagens,score,disponivel,atualizado_em,detalhes_extra)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE,NOW(),%s)
                ON CONFLICT(id) DO UPDATE SET
                    preco=EXCLUDED.preco, preco_valor=EXCLUDED.preco_valor,
                    area_m2=COALESCE(EXCLUDED.area_m2,imoveis.area_m2),
                    preco_m2=COALESCE(EXCLUDED.preco_m2,imoveis.preco_m2),
                    quartos=COALESCE(EXCLUDED.quartos,imoveis.quartos),
                    ano_construcao=COALESCE(EXCLUDED.ano_construcao,imoveis.ano_construcao),
                    descricao=COALESCE(EXCLUDED.descricao,imoveis.descricao),
                    lat=COALESCE(EXCLUDED.lat,imoveis.lat),
                    lng=COALESCE(EXCLUDED.lng,imoveis.lng),
                    morada=COALESCE(EXCLUDED.morada,imoveis.morada),
                    imagens=COALESCE(EXCLUDED.imagens,imoveis.imagens),
                    score=EXCLUDED.score, disponivel=TRUE, atualizado_em=NOW(),
                    detalhes_extra=EXCLUDED.detalhes_extra
            """, (item["id"],perfil_nome,item.get("titulo"),item.get("preco"),pv,a,pm2,
                  item.get("quartos"),item.get("ano_construcao"),item.get("descricao"),
                  item.get("lat"),item.get("lng"),item.get("morada"),
                  item.get("link"),item.get("fonte"),item.get("zona"),
                  item.get("imagem_url"),item.get("imagens",[]),score,
                  json.dumps(item.get("detalhes_extra",{}))))
        conn.commit()

def marcar_removidos(ids_vistos, perfil_nome):
    removidos = []
    with get_db() as conn:
        with conn.cursor(row_factory=psycopg_rows.dict_row) as cur:
            cur.execute("""
                SELECT id,titulo,link,zona FROM imoveis
                WHERE perfil_nome=%s AND disponivel=TRUE
                AND atualizado_em < NOW()-INTERVAL '12 hours'
            """, (perfil_nome,))
            for c in cur.fetchall():
                if c["id"] not in ids_vistos:
                    cur.execute("UPDATE imoveis SET disponivel=FALSE,removido_em=NOW() WHERE id=%s",(c["id"],))
                    removidos.append(dict(c))
        conn.commit()
    return removidos

def marcar_reativado(imovel_id):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE imoveis SET disponivel=TRUE,reativado_em=NOW(),removido_em=NULL WHERE id=%s",(imovel_id,))
        conn.commit()

def registar_mudanca_preco(imovel_id, p_ant, p_nov):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO historico_precos(imovel_id,preco_antigo,preco_novo) VALUES(%s,%s,%s)",
                        (imovel_id,p_ant,p_nov))
        conn.commit()

def registar_log_scraper(fonte, perfil_nome, total, novos, paginas=1, erros=""):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO scraper_logs(fonte,perfil_nome,total,novos,paginas,erros) VALUES(%s,%s,%s,%s,%s,%s)",
                        (fonte,perfil_nome,total,novos,paginas,erros))
        conn.commit()

def verificar_scrapers_com_falha():
    """Envia email se um scraper falhou 3+ rondas consecutivas."""
    with get_db() as conn:
        with conn.cursor(row_factory=psycopg_rows.dict_row) as cur:
            cur.execute("""
                SELECT fonte, perfil_nome,
                       COUNT(*) FILTER (WHERE erros!='' AND erros IS NOT NULL) as falhas,
                       COUNT(*) FILTER (WHERE total=0) as zero_resultados
                FROM scraper_logs
                WHERE executado_em > NOW()-INTERVAL '24 hours'
                GROUP BY fonte, perfil_nome
                HAVING COUNT(*) FILTER (WHERE erros!='' OR total=0) >= 3
            """)
            scrapers_com_falha = cur.fetchall()
    if scrapers_com_falha:
        linhas = "\n".join([
            f"• {r['fonte']} ({r['perfil_nome']}): {r['falhas']} erros, {r['zero_resultados']} sem resultados"
            for r in scrapers_com_falha])
        assunto = f"⚠️ {len(scrapers_com_falha)} scraper(s) com falhas — Monitor Algarve"
        msg = MIMEMultipart("alternative")
        msg["Subject"] = assunto
        msg["From"] = EMAIL_REMETENTE
        msg["To"]   = EMAIL_DESTINATARIO
        msg.attach(MIMEText(f"<pre>{linhas}</pre>","html"))
        try:
            with smtplib.SMTP_SSL("smtp.gmail.com",465) as smtp:
                smtp.login(EMAIL_REMETENTE, EMAIL_PASSWORD)
                smtp.sendmail(EMAIL_REMETENTE, EMAIL_DESTINATARIO, msg.as_string())
            log.warning(f"⚠️  Alerta de scrapers com falha enviado.")
        except Exception as e:
            log.error(f"Email alerta falha: {e}")

def atualizar_snapshot_mercado(perfil_nome):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT zona, AVG(preco_valor)::INTEGER, COUNT(*)
                FROM imoveis WHERE perfil_nome=%s AND disponivel=TRUE AND preco_valor IS NOT NULL
                GROUP BY zona
            """, (perfil_nome,))
            for zona, pm, total in cur.fetchall():
                cur.execute("""
                    INSERT INTO mercado_snapshot(zona,perfil_nome,preco_medio,total_ativos)
                    VALUES(%s,%s,%s,%s)
                    ON CONFLICT(zona,perfil_nome,data) DO UPDATE SET
                        preco_medio=EXCLUDED.preco_medio, total_ativos=EXCLUDED.total_ativos
                """, (zona,perfil_nome,pm,total))
        conn.commit()

def get_imoveis(perfil_nome=None, limite=300):
    with get_db() as conn:
        with conn.cursor(row_factory=psycopg_rows.dict_row) as cur:
            q = "SELECT * FROM imoveis"
            p = []
            if perfil_nome: q+=" WHERE perfil_nome=%s"; p.append(perfil_nome)
            q+=" ORDER BY score DESC, criado_em DESC LIMIT %s"; p.append(limite)
            cur.execute(q,p)
            rows = cur.fetchall()
            result = []
            for r in rows:
                d = dict(r)
                for k in ["criado_em","atualizado_em","removido_em","reativado_em"]:
                    if d.get(k): d[k] = d[k].isoformat()
                result.append(d)
            return result

def get_stats():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM imoveis WHERE disponivel=TRUE"); total=cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM imoveis WHERE criado_em>NOW()-INTERVAL '24 hours'"); ult=cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM historico_precos"); baixas=cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM imoveis WHERE disponivel=FALSE"); rem=cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM imoveis WHERE reativado_em IS NOT NULL"); reat=cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM imoveis WHERE favorito=TRUE"); favs=cur.fetchone()[0]
            return {"total":total,"ultimas_24h":ult,"baixas_preco":baixas,
                    "removidos":rem,"reativados":reat,"favoritos":favs}

def get_dados_mercado():
    try:
        with get_db() as conn:
            with conn.cursor(row_factory=psycopg_rows.dict_row) as cur:
                cur.execute("""
                    SELECT zona, AVG(preco_valor)::INTEGER preco_medio,
                           COUNT(*) total, AVG(preco_m2)::INTEGER preco_m2_medio
                    FROM imoveis WHERE disponivel=TRUE AND preco_valor IS NOT NULL
                    GROUP BY zona ORDER BY preco_medio ASC
                """)
                por_zona = [dict(r) for r in cur.fetchall()]
                cur.execute("""
                    SELECT data::TEXT, zona, preco_medio, total_ativos
                    FROM mercado_snapshot WHERE data>CURRENT_DATE-INTERVAL '90 days'
                    ORDER BY data ASC
                """)
                evolucao = [dict(r) for r in cur.fetchall()]
                cur.execute("""
                    SELECT
                        COUNT(*) FILTER (WHERE preco_valor<100000) ate_100k,
                        COUNT(*) FILTER (WHERE preco_valor BETWEEN 100000 AND 150000) ate_150k,
                        COUNT(*) FILTER (WHERE preco_valor BETWEEN 150000 AND 200000) ate_200k,
                        COUNT(*) FILTER (WHERE preco_valor BETWEEN 200000 AND 300000) ate_300k,
                        COUNT(*) FILTER (WHERE preco_valor>300000) acima_300k
                    FROM imoveis WHERE disponivel=TRUE AND preco_valor IS NOT NULL
                """)
                row = cur.fetchone()
                if row:
                    dist = {"<100k": row[0] or 0,"100-150k": row[1] or 0,
                            "150-200k": row[2] or 0,"200-300k": row[3] or 0,">300k": row[4] or 0}
                else:
                    dist = {"<100k":0,"100-150k":0,"150-200k":0,"200-300k":0,">300k":0}
                return {"por_zona": por_zona, "evolucao": evolucao, "distribuicao": dist}
    except Exception as e:
        log.error(f"get_dados_mercado: {e}")
        return {"por_zona":[], "evolucao":[], "distribuicao":{"<100k":0,"100-150k":0,"150-200k":0,"200-300k":0,">300k":0}}

def get_visitas(imovel_id=None):
    with get_db() as conn:
        with conn.cursor(row_factory=psycopg_rows.dict_row) as cur:
            if imovel_id:
                cur.execute("SELECT * FROM visitas WHERE imovel_id=%s ORDER BY data_visita DESC",(imovel_id,))
            else:
                cur.execute("""
                    SELECT v.*, i.titulo, i.zona, i.preco
                    FROM visitas v JOIN imoveis i ON v.imovel_id=i.id
                    ORDER BY v.data_visita DESC LIMIT 50
                """)
            rows = cur.fetchall()
            result = []
            for r in rows:
                d = dict(r)
                for k in ["data_visita","criado_em"]:
                    if d.get(k): d[k] = str(d[k])
                result.append(d)
            return result

# ============================================================
# EXTRAÇÃO DE DETALHES (entra em cada anúncio)
# ============================================================

def extrair_detalhes_idealista(link):
    """Extrai detalhes completos de um anúncio do Idealista."""
    try:
        r = proxied_get(link); time.sleep(1)
        soup = BeautifulSoup(r.text,"html.parser")
        detalhes = {}
        # Área
        for item in soup.select(".details-property_features li, .feature"):
            txt = item.get_text(strip=True)
            if m := re.search(r"(\d+)\s*m[²2]",txt,re.I): detalhes["area_m2"]=int(m.group(1))
            if m := re.search(r"(\d{4})",txt) and "constru" in txt.lower(): detalhes["ano_construcao"]=int(m.group(1))
        # Descrição
        desc = soup.select_one(".comment .description, #description")
        if desc: detalhes["descricao"] = desc.get_text(strip=True)[:500]
        # Imagens
        imgs = [img.get("src") or img.get("data-src")
                for img in soup.select(".detail-image-gallery img, .multimedia-slider img")
                if img.get("src") or img.get("data-src")]
        detalhes["imagens"] = imgs[:8]
        # GPS (some listings have it)
        if m := re.search(r'"latitude":\s*([\d.]+).*?"longitude":\s*([\d.]+)', r.text, re.S):
            detalhes["lat"] = float(m.group(1)); detalhes["lng"] = float(m.group(2))
        return detalhes
    except Exception as e:
        log.debug(f"Detalhe Idealista: {e}"); return {}

def extrair_detalhes_imovirtual(link):
    """Extrai detalhes de um anúncio do Imovirtual."""
    try:
        r = proxied_get(link); time.sleep(1)
        soup = BeautifulSoup(r.text,"html.parser")
        detalhes = {}
        for item in soup.select("[aria-label], .listing-item-info"):
            txt = item.get_text(strip=True)
            if m := re.search(r"(\d+)\s*m[²2]",txt,re.I): detalhes["area_m2"]=int(m.group(1))
        desc = soup.select_one("[data-cy='advert-description']")
        if desc: detalhes["descricao"] = desc.get_text(strip=True)[:500]
        imgs = [img.get("src") for img in soup.select("img[data-cy='gallery-image']") if img.get("src")]
        detalhes["imagens"] = imgs[:8]
        if m := re.search(r'"lat":\s*([\d.]+).*?"lng":\s*([\d.]+)', r.text, re.S):
            detalhes["lat"] = float(m.group(1)); detalhes["lng"] = float(m.group(2))
        return detalhes
    except Exception as e:
        log.debug(f"Detalhe Imovirtual: {e}"); return {}

def extrair_detalhes_generico(link):
    """Extração genérica para imobiliárias locais."""
    try:
        r = proxied_get(link); time.sleep(1)
        soup = BeautifulSoup(r.text,"html.parser")
        detalhes = {}
        texto_completo = soup.get_text(" ")
        if m := re.search(r"(\d{2,3})\s*m[²2]", texto_completo, re.I):
            detalhes["area_m2"] = int(m.group(1))
        if m := re.search(r"(19[5-9]\d|20[0-2]\d)", texto_completo):
            detalhes["ano_construcao"] = int(m.group(1))
        desc_el = soup.select_one(".description,.descricao,.detail-description,#description,[class*='desc']")
        if desc_el: detalhes["descricao"] = desc_el.get_text(strip=True)[:500]
        imgs = []
        for img in soup.select("img"):
            src = img.get("src") or img.get("data-src","")
            if src and any(ext in src.lower() for ext in [".jpg",".jpeg",".png",".webp"]):
                if not any(x in src.lower() for x in ["logo","icon","avatar","placeholder"]):
                    imgs.append(src)
        detalhes["imagens"] = imgs[:8]
        return detalhes
    except Exception as e:
        log.debug(f"Detalhe genérico: {e}"); return {}

def enriquecer_com_detalhes(item):
    """Entra no anúncio e extrai detalhes completos."""
    link = item.get("link","")
    if "idealista" in link:       extra = extrair_detalhes_idealista(link)
    elif "imovirtual" in link:    extra = extrair_detalhes_imovirtual(link)
    else:                         extra = extrair_detalhes_generico(link)
    for k,v in extra.items():
        if v and not item.get(k): item[k] = v
    if extra.get("imagens") and not item.get("imagem_url"):
        item["imagem_url"] = extra["imagens"][0]
    return item

# ============================================================
# DEDUPLICAÇÃO
# ============================================================

def extrair_referencia(titulo):
    """Extrai referência do imóvel do título (ex: REF: 12345, T/123456)."""
    if not titulo: return None
    import re
    m = re.search(r'(?:ref[:\s#.]+|t/)(\w{4,})', titulo, re.I)
    return m.group(1).upper() if m else None

def gerar_chave_dedup(item):
    """
    Gera chave de deduplicação. Usa referência se disponível,
    senão usa zona+preço+quartos+área.
    """
    zona  = (item.get("zona") or "").lower().strip()
    preco = round((item.get("preco_valor") or 0)/1000)*1000
    qts   = item.get("quartos") or 0
    area  = round((item.get("area_m2") or 0)/5)*5

    # Se tem referência, usa como chave primária
    ref = extrair_referencia(item.get("titulo",""))
    if ref and zona:
        return hashlib.md5(f"ref|{zona}|{ref}".encode()).hexdigest()

    # Fallback: zona+preço+quartos+área
    return hashlib.md5(f"{zona}|{preco}|{qts}|{area}".encode()).hexdigest()

def deduplicar(items):
    por_chave = {}; sem_chave = []
    for item in items:
        if not item.get("preco_valor"):
            item["preco_valor"] = extrair_preco_valor(item.get("preco"))
        if not item.get("area_m2"):
            item["area_m2"] = extrair_area(item.get("titulo"))
        if not item.get("quartos"):
            item["quartos"] = extrair_quartos(item.get("titulo"))
        if not item.get("preco_valor"):
            sem_chave.append(item); continue
        chave = gerar_chave_dedup(item)
        if chave not in por_chave:
            por_chave[chave] = item
        else:
            ex = por_chave[chave]
            if (len(item.get("titulo","")) > len(ex.get("titulo",""))
                    or (item.get("imagem_url") and not ex.get("imagem_url"))):
                por_chave[chave] = item
            else:
                fontes = ex.get("_fontes", [ex["fonte"]])
                fontes.append(item["fonte"])
                ex["_fontes"] = list(set(fontes))
                ex["fonte"] = ", ".join(ex["_fontes"])
    r = list(por_chave.values()) + sem_chave
    log.info(f"  Dedup: {len(items)} → {len(r)} ({len(items)-len(r)} dup. removidos)")
    return r

# ============================================================
# SELENIUM
# ============================================================

_driver = None

def get_driver():
    global _driver
    if _driver is not None:
        try: _ = _driver.title; return _driver
        except: _driver = None
    import glob, subprocess
    opts = Options()
    for a in ["--headless=new","--no-sandbox","--disable-dev-shm-usage",
              "--disable-gpu","--disable-setuid-sandbox","--single-process",
              "--window-size=1920,1080","--disable-blink-features=AutomationControlled",
              "--disable-extensions","--no-first-run","--disable-default-apps"]:
        opts.add_argument(a)
    opts.add_argument(f"user-agent={random.choice(USER_AGENTS)}")
    opts.add_experimental_option("excludeSwitches",["enable-automation"])
    opts.add_experimental_option("useAutomationExtension",False)

    import subprocess
    # Check env vars first (set by Dockerfile)
    chromium_bin = os.getenv("CHROME_BIN")
    chromedriver_bin = os.getenv("CHROMEDRIVER_BIN")

    # Auto-detect if not set
    if not chromium_bin or not os.path.exists(chromium_bin):
        chromium_bin = None
        for path in ["/usr/bin/chromium", "/usr/bin/chromium-browser",
                     "/usr/bin/google-chrome", "/usr/bin/google-chrome-stable"]:
            if os.path.exists(path):
                chromium_bin = path; break
        if not chromium_bin:
            for pattern in ["/nix/store/*/bin/chromium","/nix/store/*/bin/chromium-browser"]:
                matches = glob.glob(pattern)
                if matches: chromium_bin = matches[0]; break
        if not chromium_bin:
            try:
                result = subprocess.run(["which","chromium"], capture_output=True, text=True)
                if result.returncode == 0: chromium_bin = result.stdout.strip()
            except: pass

    if not chromedriver_bin or not os.path.exists(chromedriver_bin):
        chromedriver_bin = None
        for path in ["/usr/bin/chromedriver", "/usr/bin/chromium-driver"]:
            if os.path.exists(path):
                chromedriver_bin = path; break
        if not chromedriver_bin:
            for pattern in ["/nix/store/*/bin/chromedriver"]:
                matches = glob.glob(pattern)
                if matches: chromedriver_bin = matches[0]; break

    if chromium_bin:
        opts.binary_location = chromium_bin
        log.info(f"Chromium: {chromium_bin}")
    else:
        log.warning("Chromium não encontrado!")

    if chromedriver_bin:
        svc = Service(chromedriver_bin)
        log.info(f"ChromeDriver: {chromedriver_bin}")
    else:
        log.warning("ChromeDriver não encontrado, a usar webdriver-manager")
        svc = Service(ChromeDriverManager().install())

    _driver = webdriver.Chrome(service=svc, options=opts)
    _driver.set_page_load_timeout(30)
    return _driver

def quit_driver():
    global _driver
    if _driver:
        try: _driver.quit()
        except: pass
        _driver=None

def selenium_get(url, wait_sel=None, wait_s=5):
    d=get_driver()
    try:
        d.get(url)
        if wait_sel: WebDriverWait(d,wait_s).until(EC.presence_of_element_located((By.CSS_SELECTOR,wait_sel)))
        else: time.sleep(wait_s)
        return d.page_source
    except TimeoutException: return d.page_source
    except WebDriverException as e: log.warning(f"Selenium: {e}"); return ""

def com_retry(fn,n=3,w=5):
    for i in range(n):
        try: return fn()
        except Exception as e:
            if i<n-1: log.warning(f"  T{i+1} falhou: {e}. Em {w}s..."); time.sleep(w)
            else: raise

# ============================================================
# HELPERS / SCRAPERS
# ============================================================

MAX_PAGINAS = 2  # max 2 páginas por zona

def fazer_item(link,titulo,preco,fonte,zona,img=None):
    pv=extrair_preco_valor(preco)
    return {"id":link,"titulo":titulo or "Sem título","preco":preco or "N/D",
            "preco_valor":pv,"link":link,"fonte":fonte,"zona":zona,"imagem_url":img,
            "area_m2":extrair_area(titulo),"quartos":extrair_quartos(titulo)}

# Palavras que indicam arrendamento — exclui estes imóveis
PALAVRAS_ARRENDAMENTO = [
    "arrendar","arrendamento","arrendado","aluguer","alugar","aluga-se",
    "renda","rent","rental","arenda","para arrendar","por mês","€/mês",
    "/mês","mensal","mes","month","monthly","trespasse","trespass",
    "arrendamento habitacional","arrendamento comercial",
    "para arrendamento","disponível para arrendar",
]
PALAVRAS_VENDA = ["venda","comprar","compra","vende-se","para venda","sale","sell"]

# Domínios que não são imóveis (redes sociais, etc.)
DOMINIOS_EXCLUIR = [
    "linkedin.com","facebook.com","instagram.com","twitter.com",
    "youtube.com","tiktok.com","whatsapp.com","t.me","telegram.me",
    "google.com","maps.google","mailto:","tel:","javascript:",
]

# Títulos genéricos que indicam que não é um imóvel real
TITULOS_GENERICOS = [
    "kw portugal","era imobiliária","lnhouse","algarvila","villas tavira",
    "casas do sotavento","garvetur","sortami","imocusto","engel","völkers",
    "remax","re/max","century 21","coldwell","keller williams",
    "concelhos","naturezas","sobre nós","contactos","homepage",
    "facebook","instagram","linkedin","twitter","youtube",
]

def validar(item, perfil):
    """Valida imóvel contra filtros do perfil."""
    titulo    = (item.get("titulo") or "").lower().strip()
    preco_str = (item.get("preco") or "").lower()
    link      = (item.get("link") or "").lower()

    # Excluir redes sociais e links de navegação
    if any(d in link for d in DOMINIOS_EXCLUIR):
        return False

    # Excluir títulos genéricos (nome da imobiliária em vez do imóvel)
    if titulo in TITULOS_GENERICOS or len(titulo) < 5:
        return False

    # Excluir se título é exatamente o nome da fonte
    fonte = (item.get("fonte") or "").lower()
    if titulo == fonte or titulo.replace(" ","") == fonte.replace(" ",""):
        return False

    # Excluir arrendamentos
    for palavra in PALAVRAS_ARRENDAMENTO:
        if palavra in titulo or palavra in preco_str:
            return False

    # Excluir por URL
    if any(x in link for x in ["/arrendar/","/arrendamento/","/alugar/","/rent/"]):
        return False

    # Validar preço máximo
    pv = item.get("preco_valor")
    if pv and pv > perfil["preco_max"]:
        return False

    # Excluir preços mensais (arrendamento)
    if pv and pv < 10000:
        return False

    return True

def paginar_requests(url_tpl, parse_fn):
    todos=[]; pag=1
    for pag in range(1,MAX_PAGINAS+1):
        url=url_tpl.format(page=pag)
        def _f(u=url):
            r=proxied_get(u); return parse_fn(r.text)
        try:
            items=com_retry(_f)
            if not items: break
            todos.extend(items); time.sleep(random.uniform(1.5,3))
        except Exception as e: log.error(f"Pag {pag}: {e}"); break
    return todos,pag

def paginar_scraperapi(url_tpl, parse_fn):
    """Usa ScraperAPI para contornar bloqueios. Fallback para requests se não houver key."""
    todos=[]; pag=1
    for pag in range(1,MAX_PAGINAS+1):
        url=url_tpl.format(page=pag)
        def _fetch(u=url):
            if SCRAPERAPI_KEY:
                api_url=f"http://api.scraperapi.com?api_key={SCRAPERAPI_KEY}&url={requests.utils.quote(u)}&render=true"
                r=requests.get(api_url,timeout=45,headers=random_headers())
            else:
                r=requests.get(u,headers=random_headers(),timeout=15)
            return parse_fn(r.text)
        try:
            items=com_retry(_fetch)
            log.info(f"    scraperapi pag {pag}: {len(items)} items")
            if not items: break
            todos.extend(items); time.sleep(random.uniform(1,2))
        except Exception as e:
            log.error(f"  scraperapi pag {pag}: {e}"); break
    return todos,pag

def paginar_selenium(url_tpl,parse_fn):
    todos=[]; pag=1
    for pag in range(1,MAX_PAGINAS+1):
        html=selenium_get(url_tpl.format(page=pag),wait_sel="article,.property,.listing,h2,h3",wait_s=5)
        items=parse_fn(html)
        if not items: break
        todos.extend(items); time.sleep(random.uniform(2,4))
    return todos,pag

def _parse_generic(html,base,fonte,zona):
    soup=BeautifulSoup(html,"html.parser"); items=[]
    for sel in [".property","article",".imovel","[class*='property-card']"]:
        found=soup.select(sel)
        for it in found:
            lt=it.select_one("a"); pt=it.select_one(".price,.preco,[class*='price']")
            tt=it.select_one("h2,h3,.title,[class*='title']"); img=it.select_one("img")
            if not lt: continue
            href=lt.get("href","")
            link=href if href.startswith("http") else base.rstrip("/")+"/"+href.lstrip("/")
            if link==base or not href: continue
            items.append(fazer_item(link,
                tt.get_text(strip=True) if tt else fonte,
                pt.get_text(strip=True) if pt else "N/D",
                fonte,zona,
                img.get("src") or img.get("data-src") if img else None))
        if found: break
    return items

def scrape_idealista(perfil):
    res=[]; pags=0
    for ts in perfil["tipos"]:
        tl={"apartamentos":"Apartamento","moradias-e-vivendas":"Moradia"}.get(ts,ts)
        for zs in perfil["zonas"]:
            zl=TODAS_AS_ZONAS.get(zs,zs)
            # Idealista PT URL format: /comprar-casas/{zona}/com-{tipo},t{q}/
            # Idealista PT: com-apartamentos ou com-moradias (sem "e-vivendas")
            tipo_slug = "apartamentos" if "apart" in ts else "moradias"
            filtro_tipo = f"com-{tipo_slug}"
            tpl=(f"https://www.idealista.pt/comprar-casas/{zs}/{filtro_tipo}/"
                 f"?preco-max={perfil['preco_max']}&quartos-min={perfil['quartos_min']}&pagina={{page}}")
            def parse(html,tl=tl,zl=zl):
                soup=BeautifulSoup(html,"html.parser"); its=[]
                for it in soup.select("article.item"):
                    lt=it.select_one("a.item-link"); pt=it.select_one(".item-price")
                    tt=it.select_one(".item-title"); img=it.select_one("img")
                    if not lt: continue
                    its.append(fazer_item("https://www.idealista.pt"+lt.get("href",""),
                        tt.get_text(strip=True) if tt else tl,
                        pt.get_text(strip=True) if pt else "N/D",
                        "Idealista",zl,img.get("src") or img.get("data-src") if img else None))
                return its
            items,p=paginar_scraperapi(tpl,parse); res.extend(items); pags+=p
    return res,pags

def scrape_imovirtual(perfil):
    res=[]; pags=0
    for ts in perfil["tipos"]:
        tl={"apartamentos":"Apartamento","moradias-e-vivendas":"Moradia"}.get(ts,ts)
        tiv="apartamento" if "apart" in ts else "moradia"
        for zs in perfil["zonas"]:
            zl=TODAS_AS_ZONAS.get(zs,zs)
            # Imovirtual URL format (apartamento/moradia before zona)
            tpl=(f"https://www.imovirtual.com/comprar/{tiv}/{zs}/"
                 f"?priceMax={perfil['preco_max']}&roomsMin={perfil['quartos_min']}&nrAdsPerPage=36&page={{page}}")
            def parse(html,tl=tl,zl=zl):
                soup=BeautifulSoup(html,"html.parser"); its=[]
                for it in soup.select("article[data-cy='listing-item']"):
                    lt=it.select_one("a"); pt=it.select_one("[data-cy='listing-item-price']")
                    tt=it.select_one("[data-cy='listing-item-title']"); img=it.select_one("img")
                    if not lt: continue
                    its.append(fazer_item("https://www.imovirtual.com"+lt.get("href",""),
                        tt.get_text(strip=True) if tt else tl,
                        pt.get_text(strip=True) if pt else "N/D",
                        "Imovirtual",zl,img.get("src") or img.get("data-src") if img else None))
                return its
            items,p=paginar_scraperapi(tpl,parse); res.extend(items); pags+=p
    return res,pags

def scrape_casasapo(perfil):
    res=[]; pags=0
    for ts in perfil["tipos"]:
        tl={"apartamentos":"Apartamento","moradias-e-vivendas":"Moradia"}.get(ts,ts)
        tsk="apartamentos" if "apart" in ts else "moradias"
        for zs in perfil["zonas"]:
            zl=TODAS_AS_ZONAS.get(zs,zs)
            tips=",".join([f"T{i}" for i in range(perfil["quartos_min"],7)])
            tpl=(f"https://casa.sapo.pt/comprar-{tsk}/{zs}/"
                 f"?precomax={perfil['preco_max']}&tipologia={tips}&pn={{page}}")
            def parse(html,tl=tl,zl=zl):
                soup=BeautifulSoup(html,"html.parser"); its=[]
                for it in soup.select(".property-info-content,.searchResultProperty"):
                    lt=it.select_one("a"); pt=it.select_one(".property-price,.price")
                    tt=it.select_one(".property-title,h2"); img=it.select_one("img")
                    if not lt: continue
                    href=lt.get("href","")
                    link=href if href.startswith("http") else "https://casa.sapo.pt"+href
                    its.append(fazer_item(link,tt.get_text(strip=True) if tt else tl,
                        pt.get_text(strip=True) if pt else "N/D","Casa SAPO",zl,
                        img.get("src") if img else None))
                return its
            items,p=paginar_scraperapi(tpl,parse); res.extend(items); pags+=p
    return res,pags

def scrape_supercasa(perfil):
    res=[]; pags=0
    for ts in perfil["tipos"]:
        tl={"apartamentos":"Apartamento","moradias-e-vivendas":"Moradia"}.get(ts,ts)
        tsc="apartamentos" if "apart" in ts else "moradias"
        for zs in perfil["zonas"]:
            zl=TODAS_AS_ZONAS.get(zs,zs)
            tips=",".join([f"T{i}" for i in range(perfil["quartos_min"],6)])
            # SuperCasa URL: /comprar-casas/{zona}/com-apartamentos ou com-moradias
            tipo_sc2 = "apartamentos" if "apart" in ts else "moradias"
            tpl=(f"https://supercasa.pt/comprar-casas/{zs}/com-{tipo_sc2}/"
                 f"?preco-max={perfil['preco_max']}&quartos-min={perfil['quartos_min']}&pagina={{page}}")
            def parse(html,tl=tl,zl=zl):
                soup=BeautifulSoup(html,"html.parser"); its=[]
                for it in soup.select("[data-id],.property-item,article"):
                    lt=it.select_one("a"); pt=it.select_one(".price,[class*='price']")
                    tt=it.select_one("h2,h3,[class*='title']"); img=it.select_one("img")
                    if not lt: continue
                    href=lt.get("href","")
                    link=href if href.startswith("http") else "https://supercasa.pt"+href
                    its.append(fazer_item(link,tt.get_text(strip=True) if tt else tl,
                        pt.get_text(strip=True) if pt else "N/D","SuperCasa",zl,
                        img.get("src") if img else None))
                return its
            items,p=paginar_scraperapi(tpl,parse); res.extend(items); pags+=p
    return res,pags

def _api_scrape(url_tpl, base, fonte, zona, extra_sels=None):
    """Usa ScraperAPI com render=true para sites com JavaScript."""
    def parse(html):
        soup = BeautifulSoup(html, "html.parser")
        items = []
        # Seletores genéricos + específicos por fonte
        sels = [".property",".card","article",".imovel",
                ".listing-item","[class*='property-card']",
                "[class*='card-anchor']","[class*='listing']","li[class]"]
        if extra_sels:
            sels = extra_sels + sels
        for sel in sels:
            found = soup.select(sel)
            for it in found:
                lt = it.select_one("a")
                pt = it.select_one("[class*='price'],[class*='preco'],.price,.preco")
                tt = it.select_one("h2,h3,h4,[class*='title'],[class*='name']")
                img = it.select_one("img")
                if not lt or not lt.get("href"): continue
                href = lt.get("href","")
                link = href if href.startswith("http") else base.rstrip("/")+"/"+href.lstrip("/")
                if link == base: continue
                titulo = tt.get_text(strip=True) if tt else fonte
                preco  = pt.get_text(strip=True) if pt else "N/D"
                # Filtrar entradas sem preço nem título útil
                if len(titulo) < 5 and preco == "N/D": continue
                imagem = img.get("src") or img.get("data-src") if img else None
                items.append(fazer_item(link, titulo, preco, fonte, zona, imagem))
            if items: break
        return items

    todos = []; pag = 1
    for pag in range(1, MAX_PAGINAS+1):
        url = url_tpl.format(page=pag)
        def _fetch(u=url):
            r = proxied_get(u, render=True)
            return parse(r.text)
        try:
            items = com_retry(_fetch)
            log.info(f"    api_scrape pag {pag}: {len(items)} items")
            if not items: break
            todos.extend(items)
            time.sleep(random.uniform(1,2))
        except Exception as e:
            log.error(f"  api_scrape pag {pag}: {e}"); break
    return todos, pag

def _sel_scrape(url_tpl,base,fonte,zona):
    """Mantido para compatibilidade — usa _api_scrape."""
    return _api_scrape(url_tpl, base, fonte, zona)

def scrape_casasdosotavento(p):
    res=[]; pags=0
    for zs in p["zonas"]:
        zl=TODAS_AS_ZONAS.get(zs,zs)
        url=(f"https://www.casasdosotavento.pt/imoveis/venda/"
             f"?concelho={zs}&preco_max={p['preco_max']}&quartos_min={p['quartos_min']}&page={{page}}")
        try: its,pg=_api_scrape(url,"https://www.casasdosotavento.pt","Casas do Sotavento",zl); res.extend(its); pags+=pg
        except Exception as e: log.error(f"CasasSotavento/{zs}: {e}")
        time.sleep(random.uniform(2,4))
    return res,pags

def scrape_algarvila(p):
    try: return _api_scrape("https://www.algarvila.com/en-gb/properties?page={page}","https://www.algarvila.com","AlgarVila","Tavira")
    except Exception as e: log.error(f"AlgarVila: {e}"); return [],0

def scrape_villastavira(p):
    try: return _api_scrape("https://www.villastavira.pt/imoveis?page={page}","https://www.villastavira.pt","Villas Tavira","Tavira")
    except Exception as e: log.error(f"VillasTavira: {e}"); return [],0

def scrape_imocusto(p):
    try: return _sel_scrape("https://www.imocusto.pt/imoveis/venda?page={page}","https://www.imocusto.pt","Imocusto","VRSA/Castro Marim")
    except Exception as e: log.error(f"Imocusto: {e}"); return [],0

def scrape_lnhouse(p):
    try: return _api_scrape("https://www.lnhouse.pt/imoveis?page={page}","https://www.lnhouse.pt","LNHouse","VRSA/Castro Marim")
    except Exception as e: log.error(f"LNHouse: {e}"); return [],0

def scrape_sortami(p):
    url=f"https://www.sortami.pt/imoveis/comprar?preco_max={p['preco_max']}&quartos_min={p['quartos_min']}&page={{page}}"
    try: return _api_scrape(url,"https://www.sortami.pt","Sortami","Algarve Sotavento")
    except Exception as e: log.error(f"Sortami: {e}"); return [],0

def scrape_garvetur(p):
    url=(f"https://www.garvetur.pt/imoveis/venda"
         f"&preco_max={p['preco_max']}&quartos_min={p['quartos_min']}&zona={','.join(p['zonas'])}&page={{page}}")
    try: return _api_scrape(url,"https://www.garvetur.pt","Garvetur","Algarve")
    except Exception as e: log.error(f"Garvetur: {e}"); return [],0

def scrape_engelvoelkers(p):
    res=[]; pags=0
    for zs in p["zonas"]:
        zl=TODAS_AS_ZONAS.get(zs,zs)
        url=(f"https://www.engelvoelkers.com/pt/en/search/?q=&pageSize=20&adType=BUY"
             f"&realEstateType=APARTMENT,HOUSE&country=PRT&city={zs}"
             f"&priceMax={p['preco_max']}&roomsMin={p['quartos_min']}&page={{page}}")
        try:
            its,pg=_api_scrape(url,"https://www.engelvoelkers.com","Engel & Völkers",zl,
                extra_sels=["[class*='property-card']","[class*='PropertyCard']","[class*='ev-property']"])
            res.extend(its); pags+=pg
        except Exception as e: log.error(f"E&V/{zs}: {e}")
        time.sleep(random.uniform(1,2))
    return res,pags

def scrape_era(p):
    res=[]; pags=0
    for zs in p["zonas"]:
        zl=TODAS_AS_ZONAS.get(zs,zs)
        url=(f"https://www.era.pt/comprar/imoveis/{zs}/?preco_max={p['preco_max']}"
             f"&quartos_min={p['quartos_min']}&tipologia=apartamento,moradia&page={{page}}")
        try:
            its,pg=_api_scrape(url,"https://www.era.pt","ERA Imobiliária",zl,
                extra_sels=[".card-anchor",".card",".filter--results .card"])
            res.extend(its); pags+=pg
        except Exception as e: log.error(f"ERA/{zs}: {e}")
        time.sleep(random.uniform(1,2))
    return res,pags

def scrape_remax(p):
    res=[]; pags=0
    for zs in p["zonas"]:
        zl=TODAS_AS_ZONAS.get(zs,zs)
        url=(f"https://www.remax.pt/comprar/{zs}/?pricemax={p['preco_max']}"
             f"&rooms={p['quartos_min']}&type=apartamento,moradia&page={{page}}")
        try:
            its,pg=_api_scrape(url,"https://www.remax.pt","RE/MAX",zl,
                extra_sels=["[class*='listing-card']","[class*='property-card']","a[href*='/imoveis/']"])
            res.extend(its); pags+=pg
        except Exception as e: log.error(f"REMAX/{zs}: {e}")
        time.sleep(random.uniform(1,2))
    return res,pags

def scrape_kwportugal(p):
    res=[]; pags=0
    for zs in p["zonas"]:
        zl=TODAS_AS_ZONAS.get(zs,zs)
        url=f"https://www.kwportugal.pt/pt/pesquisa/?localizacao={zs}&tipo=comprar&priceMax={p['preco_max']}&rooms={p['quartos_min']}&page={{page}}"
        try: its,pg=_api_scrape(url,"https://www.kwportugal.pt","KW Portugal",zl); res.extend(its); pags+=pg
        except Exception as e: log.error(f"KW/{zs}: {e}")
        time.sleep(random.uniform(2,4))
    return res,pags

# ============================================================
# SCRAPER GENÉRICO PARA TODAS AS IMOBILIÁRIAS
# ============================================================

def scrape_generico(nome, urls, perfil, seletores_extra=None):
    """
    Scraper genérico para imobiliárias — tenta ScraperAPI com render=true.
    urls: lista de URLs a verificar (uma por zona/tipo)
    """
    resultados = []
    for url in urls:
        def _fetch(u=url):
            r = proxied_get(u, render=True)
            return _api_scrape_html(r.text, u, nome, seletores_extra)
        try:
            items = com_retry(_fetch, tentativas=2)
            items = [i for i in items if validar(i, perfil)]
            log.info(f"    {nome}: {len(items)} items de {url[:60]}")
            resultados.extend(items)
        except Exception as e:
            log.error(f"  {nome}: {e}")
        time.sleep(random.uniform(2, 4))
    return resultados, 1

def _api_scrape_html(html, base_url, fonte, extra_sels=None):
    """Extrai imóveis de HTML usando seletores CSS."""
    soup = BeautifulSoup(html, "html.parser")
    items = []
    sels = (extra_sels or []) + [
        "article", ".property", ".card", ".imovel", ".listing-item",
        "[class*='property-card']", "[class*='listing-card']",
        "[class*='result-item']", "[class*='property-item']",
    ]
    zona = "Algarve"
    # Tentar determinar zona pelo URL
    for slug, label in TODAS_AS_ZONAS.items():
        if slug in base_url.lower():
            zona = label; break

    for sel in sels:
        found = soup.select(sel)
        for it in found:
            lt  = it.select_one("a[href]")
            pt  = it.select_one("[class*='price'],[class*='preco'],.price,.preco")
            tt  = it.select_one("h1,h2,h3,h4,[class*='title'],[class*='name']")
            img = it.select_one("img[src]")
            if not lt or not lt.get("href"): continue
            href = lt.get("href","")
            link = href if href.startswith("http") else base_url.split("/")[0]+"//"+base_url.split("/")[2]+href
            titulo = tt.get_text(strip=True) if tt else fonte
            preco  = pt.get_text(strip=True) if pt else "N/D"
            imagem = img.get("src") or img.get("data-src","") if img else None
            item = fazer_item(link, titulo, preco, fonte, zona, imagem)
            items.append(item)
        if items: break
    return items

# ── REDES NACIONAIS/INTERNACIONAIS ───────────────────────

def scrape_coldwell(p):
    urls=[f"https://www.coldwellbanker.pt/imoveis?transacao=compra&distrito=faro&preco_max={p['preco_max']}&quartos_min={p['quartos_min']}"]
    return scrape_generico("Coldwell Banker", urls, p)

def scrape_sothebys(p):
    urls=[f"https://www.sothebysrealty.pt/imoveis/compra?preco_max={p['preco_max']}&distrito=faro"]
    return scrape_generico("Sotheby's", urls, p)

def scrape_iad(p):
    urls=[f"https://www.iadfrance.pt/comprar/apartamento/algarve?prix_max={p['preco_max']}",
          f"https://www.iadfrance.pt/comprar/moradia/algarve?prix_max={p['preco_max']}"]
    return scrape_generico("IAD Portugal", urls, p)

def scrape_fineandcountry(p):
    urls=[f"https://www.fineandcountry.com/pt/imoveis-para-venda/algarve?max_price={p['preco_max']}"]
    return scrape_generico("Fine & Country", urls, p)

def scrape_century21(p):
    urls=[f"https://www.century21.pt/imoveis/?local=faro&tipo=comprar&preco_max={p['preco_max']}&quartos={p['quartos_min']}"]
    return scrape_generico("Century 21", urls, p)

def scrape_chavanova(p):
    urls=[f"https://www.chavanova.pt/imoveis?distrito=faro&tipo=venda&preco_max={p['preco_max']}"]
    return scrape_generico("Chave Nova", urls, p)

def scrape_arcada(p):
    urls=[f"https://www.arcada.com.pt/imoveis?zona=algarve&tipo=venda&preco_max={p['preco_max']}"]
    return scrape_generico("Arcada Imobiliária", urls, p)

# ── ALGARVE TODA A REGIÃO ────────────────────────────────

def scrape_villaskey(p):
    urls=[f"https://www.villaskey.com/venda?preco_max={p['preco_max']}&zona=algarve"]
    return scrape_generico("Villas Key", urls, p)

def scrape_dils(p):
    urls=[f"https://www.dils.pt/imoveis?tipo=venda&zona=algarve&preco_max={p['preco_max']}"]
    return scrape_generico("Dils Portugal", urls, p)

def scrape_buyme(p):
    urls=[f"https://www.buymeproperty.pt/comprar?preco_max={p['preco_max']}&quartos_min={p['quartos_min']}"]
    return scrape_generico("BuyMe Property", urls, p)

def scrape_algarveproperty(p):
    urls=[f"https://www.algarveproperty.com/properties-for-sale?max_price={p['preco_max']}&bedrooms={p['quartos_min']}"]
    return scrape_generico("Algarve Property", urls, p)

def scrape_nurisimo(p):
    urls=[f"https://www.nurisimo.com/venda?preco_max={p['preco_max']}"]
    return scrape_generico("Nurisimo", urls, p)

def scrape_goldenproperties(p):
    urls=[f"https://www.goldenproperties.pt/imoveis?tipo=venda&preco_max={p['preco_max']}"]
    return scrape_generico("Golden Properties", urls, p)

def scrape_algarverealestate(p):
    urls=[f"https://www.algarverealestate.com/properties-for-sale?max_price={p['preco_max']}&bedrooms={p['quartos_min']}"]
    return scrape_generico("Algarve Real Estate", urls, p)

def scrape_espacosalgarve(p):
    urls=[f"https://www.espacos-algarve.com/comprar?preco_max={p['preco_max']}"]
    return scrape_generico("Espaços Algarve", urls, p)

def scrape_redereal(p):
    urls=[f"https://www.redereal.com/imoveis?tipo=venda&zona=algarve&preco_max={p['preco_max']}"]
    return scrape_generico("Rede Real", urls, p)

def scrape_dalmaportuguesa(p):
    urls=[f"https://www.dalmaportuguesa.com/imoveis?preco_max={p['preco_max']}"]
    return scrape_generico("D'Alma Portuguesa", urls, p)

def scrape_vaprealestate(p):
    urls=[f"https://www.vaprealestate.com/properties?max_price={p['preco_max']}&bedrooms={p['quartos_min']}"]
    return scrape_generico("VAP Real Estate", urls, p)

def scrape_tripalgarve(p):
    urls=[f"https://www.tripalgarve.com/properties-for-sale?max_price={p['preco_max']}"]
    return scrape_generico("Tripalgarve", urls, p)

def scrape_algarvedream(p):
    urls=[f"https://www.algarvedreamproperty.com/for-sale?max_price={p['preco_max']}"]
    return scrape_generico("Algarve Dream Property", urls, p)

# ── BARLAVENTO ───────────────────────────────────────────

def scrape_mimosa(p):
    urls=[f"https://www.mimosaproperties.com/properties-for-sale?max_price={p['preco_max']}&bedrooms={p['quartos_min']}"]
    return scrape_generico("Mimosa Properties", urls, p)

def scrape_algarveuniqueproperties(p):
    urls=[f"https://www.algarveuniqueproperties.com/for-sale?max_price={p['preco_max']}"]
    return scrape_generico("Algarve Unique Properties", urls, p)

def scrape_boto(p):
    urls=[f"https://www.botoproperties.com/properties-for-sale?max_price={p['preco_max']}&bedrooms={p['quartos_min']}"]
    return scrape_generico("Boto Properties", urls, p)

def scrape_vernon(p):
    urls=[f"https://www.vernonalgarve.com/for-sale?max_price={p['preco_max']}&bedrooms={p['quartos_min']}"]
    return scrape_generico("Vernon Algarve", urls, p)

def scrape_sunpoint(p):
    urls=[f"https://www.sunpointproperties.com/for-sale?max_price={p['preco_max']}&bedrooms={p['quartos_min']}"]
    return scrape_generico("Sunpoint Properties", urls, p)

def scrape_a1algarve(p):
    urls=[f"https://www.a1-algarve.com/properties?max_price={p['preco_max']}&bedrooms={p['quartos_min']}"]
    return scrape_generico("A1 Algarve", urls, p)

# ── TRIÂNGULO DOURADO ────────────────────────────────────

def scrape_qpsavills(p):
    urls=[f"https://www.quintaproperty.com/property-for-sale?max_price={p['preco_max']}&beds={p['quartos_min']}"]
    return scrape_generico("QP Savills", urls, p)

def scrape_jppproperties(p):
    urls=[f"https://www.jppproperties.com/buy?max_price={p['preco_max']}&bedrooms={p['quartos_min']}"]
    return scrape_generico("JPP Properties", urls, p)

def scrape_yourluxury(p):
    urls=[f"https://www.yourluxuryproperty.pt/imoveis-para-venda?preco_max={p['preco_max']}"]
    return scrape_generico("Your Luxury Property", urls, p)

def scrape_barraprime(p):
    urls=[f"https://www.barraprime.pt/imoveis-para-venda?preco_max={p['preco_max']}"]
    return scrape_generico("Barra Prime", urls, p)

def scrape_insidevillas(p):
    urls=[f"https://www.inside-villas.com/for-sale?max_price={p['preco_max']}&bedrooms={p['quartos_min']}"]
    return scrape_generico("Inside-Villas", urls, p)

def scrape_cluttons(p):
    urls=[f"https://www.cluttons.com/algarve/properties-for-sale?max_price={p['preco_max']}&bedrooms={p['quartos_min']}"]
    return scrape_generico("Cluttons Algarve", urls, p)

def scrape_chestertons(p):
    urls=[f"https://www.chestertons.com/algarve/properties-for-sale?max_price={p['preco_max']}&bedrooms={p['quartos_min']}"]
    return scrape_generico("Chestertons Algarve", urls, p)

# ── SOTAVENTO ────────────────────────────────────────────

def scrape_algarvemanta(p):
    urls=[f"https://casa.sapo.pt/comprar-apartamentos/tavira/?precomax={p['preco_max']}",
          f"https://casa.sapo.pt/comprar-moradias/tavira/?precomax={p['preco_max']}"]
    return scrape_generico("Algarve Manta Properties", urls, p)

SCRAPERS=[
    # Portais agregadores (via ScraperAPI)
    ("Idealista",scrape_idealista),("Imovirtual",scrape_imovirtual),
    ("Casa SAPO",scrape_casasapo),("SuperCasa",scrape_supercasa),
    # Sotavento — imobiliárias locais
    ("Casas do Sotavento",scrape_casasdosotavento),("AlgarVila",scrape_algarvila),
    ("Villas Tavira",scrape_villastavira),("Imocusto",scrape_imocusto),
    ("LNHouse",scrape_lnhouse),("Sortami",scrape_sortami),("Garvetur",scrape_garvetur),
    ("Algarve Manta Properties",scrape_algarvemanta),
    # Redes nacionais/internacionais
    ("Engel & Völkers",scrape_engelvoelkers),("ERA Imobiliária",scrape_era),
    ("RE/MAX",scrape_remax),("KW Portugal",scrape_kwportugal),
    ("Coldwell Banker",scrape_coldwell),("Sotheby's",scrape_sothebys),
    ("IAD Portugal",scrape_iad),("Fine & Country",scrape_fineandcountry),
    ("Century 21",scrape_century21),("Chave Nova",scrape_chavanova),
    ("Arcada Imobiliária",scrape_arcada),
    # Algarve toda a região
    ("Villas Key",scrape_villaskey),("Dils Portugal",scrape_dils),
    ("BuyMe Property",scrape_buyme),("Algarve Property",scrape_algarveproperty),
    ("Nurisimo",scrape_nurisimo),("Golden Properties",scrape_goldenproperties),
    ("Algarve Real Estate",scrape_algarverealestate),
    ("Espaços Algarve",scrape_espacosalgarve),("Rede Real",scrape_redereal),
    ("D'Alma Portuguesa",scrape_dalmaportuguesa),("VAP Real Estate",scrape_vaprealestate),
    ("Tripalgarve",scrape_tripalgarve),("Algarve Dream Property",scrape_algarvedream),
    # Barlavento
    ("Mimosa Properties",scrape_mimosa),
    ("Algarve Unique Properties",scrape_algarveuniqueproperties),
    ("Boto Properties",scrape_boto),("Vernon Algarve",scrape_vernon),
    ("Sunpoint Properties",scrape_sunpoint),("A1 Algarve",scrape_a1algarve),
    # Triângulo Dourado
    ("QP Savills",scrape_qpsavills),("JPP Properties",scrape_jppproperties),
    ("Your Luxury Property",scrape_yourluxury),("Barra Prime",scrape_barraprime),
    ("Inside-Villas",scrape_insidevillas),("Cluttons Algarve",scrape_cluttons),
    ("Chestertons Algarve",scrape_chestertons),
]

# ============================================================
# TELEGRAM
# ============================================================

def enviar_telegram(chat_id, texto):
    if not TELEGRAM_BOT_TOKEN or not chat_id: return
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id":chat_id,"text":texto,"parse_mode":"HTML"},timeout=10)
    except Exception as e: log.warning(f"Telegram: {e}")

# ============================================================
# EMAIL
# ============================================================

def card_email(im, badge="NOVO", cor="#16a34a"):
    img_html=(f'<img src="{im["imagem_url"]}" style="width:100%;height:180px;object-fit:cover;">'
              if im.get("imagem_url") else
              '<div style="height:80px;background:#e5e7eb;text-align:center;line-height:80px;font-size:28px;">🏠</div>')
    extras=[]
    if im.get("area_m2"):  extras.append(f"📐 {im['area_m2']}m²")
    if im.get("quartos"):  extras.append(f"🛏 T{im['quartos']}")
    if im.get("preco_m2"): extras.append(f"💶 {im['preco_m2']:,}€/m²")
    if im.get("ano_construcao"): extras.append(f"🏗 {im['ano_construcao']}")
    score_html=f'<span style="float:right;background:#fef3c7;color:#92400e;padding:1px 6px;border-radius:4px;font-size:10px;">⭐{im.get("score",0)}</span>' if im.get("score") else ""
    preco_ant=(f'<span style="color:#aaa;text-decoration:line-through;font-size:12px;margin-right:4px;">{im["preco_antigo"]}</span>'
               if im.get("preco_antigo") else "")
    return f"""<div style="border:1px solid #e5e7eb;border-radius:8px;overflow:hidden;margin-bottom:14px;">
      <a href="{im['link']}">{img_html}</a>
      <div style="padding:12px;">
        {score_html}
        <span style="background:{cor};color:white;font-size:10px;font-weight:700;padding:2px 7px;border-radius:12px;">{badge}</span>
        <div style="margin-top:7px;"><a href="{im['link']}" style="color:#1e3a5f;font-weight:700;text-decoration:none;">{im['titulo']}</a></div>
        <div style="margin-top:5px;">{preco_ant}<span style="color:#16a34a;font-weight:700;font-size:16px;">{im['preco']}</span></div>
        {f'<div style="margin-top:4px;font-size:12px;color:#6b7280;">{" · ".join(extras)}</div>' if extras else ""}
        <div style="margin-top:4px;font-size:11px;color:#9ca3af;">📍 {im["zona"]} · 🏢 {im["fonte"]}</div>
        {f'<div style="margin-top:6px;font-size:12px;color:#4b5563;border-left:3px solid #e5e7eb;padding-left:8px;">{im["descricao"][:150]}...</div>' if im.get("descricao") else ""}
      </div>
    </div>"""

def enviar_email(perfil, novos, baixas, reativados):
    if not novos and not baixas and not reativados: return
    partes=[]
    if novos: partes.append(f"{len(novos)} novo(s)")
    if baixas: partes.append(f"{len(baixas)} baixa(s)")
    if reativados: partes.append(f"{len(reativados)} reat.")
    assunto=f"🏠 {' · '.join(partes)} — {perfil['nome']}"
    todos=novos+baixas+reativados
    zonas_str=" · ".join(sorted(set(i["zona"] for i in todos))) if todos else ""
    cards_n="".join(card_email(i) for i in sorted(novos,key=lambda x:-x.get("score",0)))
    cards_b="".join(card_email(i,"📉 BAIXA","#dc2626") for i in baixas)
    cards_r="".join(card_email(i,"🔄 REATIVADO","#7c3aed") for i in reativados)
    s_b=f'<h3 style="color:#dc2626;margin-top:24px;">📉 Baixas ({len(baixas)})</h3>{cards_b}' if baixas else ""
    s_r=f'<h3 style="color:#7c3aed;margin-top:24px;">🔄 Reativados ({len(reativados)})</h3>{cards_r}' if reativados else ""
    html=f"""<html><body style="font-family:Arial,sans-serif;max-width:600px;margin:auto;background:#f9fafb;padding:20px;">
      <div style="background:white;border-radius:10px;padding:22px;box-shadow:0 1px 4px rgba(0,0,0,.08);">
        <h2 style="color:#1e3a5f;margin:0 0 12px;">🏠 {perfil['nome']}</h2>
        <p style="background:#f0f4ff;padding:10px;border-radius:6px;color:#555;font-size:13px;">
          🛏 T{perfil['quartos_min']}+ · 💰 Até {perfil['preco_max']:,}€ · 📍 {zonas_str}
        </p>
        <h3 style="color:#1e3a5f;margin-top:20px;">✨ Novos ({len(novos)}) — por relevância</h3>
        {cards_n}{s_b}{s_r}
        <p style="color:#aaa;font-size:11px;margin-top:20px;text-align:center;">
          {datetime.now().strftime('%d/%m/%Y %H:%M')}
        </p>
      </div></body></html>"""
    msg=MIMEMultipart("alternative")
    msg["Subject"]=assunto; msg["From"]=EMAIL_REMETENTE; msg["To"]=perfil["email"]
    msg.attach(MIMEText(html,"html"))
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com",465) as smtp:
            smtp.login(EMAIL_REMETENTE,EMAIL_PASSWORD)
            smtp.sendmail(EMAIL_REMETENTE,perfil["email"],msg.as_string())
        log.info(f"✉  Email → {perfil['email']}")
    except Exception as e: log.error(f"Email: {e}")

def enviar_resumo_semanal():
    for perfil in PERFIS:
        try:
            with get_db() as conn:
                with conn.cursor(row_factory=psycopg_rows.dict_row) as cur:
                    cur.execute("SELECT * FROM imoveis WHERE perfil_nome=%s AND criado_em>NOW()-INTERVAL '7 days' ORDER BY score DESC",(perfil["nome"],))
                    imoveis=[dict(r) for r in cur.fetchall()]
            if not imoveis: continue
            enviar_email(perfil,imoveis,[],[])
        except Exception as e: log.error(f"Resumo: {e}")

# ============================================================
# LOOP PRINCIPAL
# ============================================================

def verificar_perfil(perfil):
    log.info(f"▶ {perfil['nome']}")
    todos_raw=[]; ids_ronda=[]
    for nome, fn in SCRAPERS:
        log.info(f"  → {nome}...")
        erros=""; total=0; novos_s=0; pags=1
        try:
            r=fn(perfil)
            anuncios,pags=r if isinstance(r,tuple) else (r,1)
            anuncios=[a for a in anuncios if validar(a,perfil)]
            total=len(anuncios); todos_raw.extend(anuncios)
            if total==0: log.warning(f"    ⚠️ 0 resultados")
        except Exception as e: erros=str(e); log.error(f"    {e}")
        registar_log_scraper(nome,perfil["nome"],total,novos_s,pags,erros)
        time.sleep(random.uniform(1,3))

    # Enriquece novos itens com detalhes completos (amostra de 10 por ronda para não sobrecarregar)
    todos=deduplicar(todos_raw)
    novos_para_enriquecer=[i for i in todos if imovel_existe(i["id"])[0] is None][:10]
    for item in novos_para_enriquecer:
        item = enriquecer_com_detalhes(item)
        time.sleep(random.uniform(0.5,1.5))

    ids_ronda=[i["id"] for i in todos]
    novos=[]; baixas=[]; reativados=[]

    for item in todos:
        score=calcular_score(item,perfil); item["score"]=score
        p_ant,disp_ant=imovel_existe(item["id"])
        if p_ant is None:
            guardar_imovel(item,perfil["nome"],score); novos.append(item)
        else:
            guardar_imovel(item,perfil["nome"],score)
            pv_n=extrair_preco_valor(item["preco"]); pv_a=extrair_preco_valor(p_ant)
            if pv_n and pv_a and pv_n<pv_a:
                registar_mudanca_preco(item["id"],p_ant,item["preco"])
                item["preco_antigo"]=p_ant; baixas.append(item)
            if disp_ant==False:
                marcar_reativado(item["id"]); reativados.append(item)

    removidos=marcar_removidos(ids_ronda,perfil["nome"])
    atualizar_snapshot_mercado(perfil["nome"])
    log.info(f"  N:{len(novos)} B:{len(baixas)} R:{len(reativados)} Rem:{len(removidos)}")

    if novos or baixas or reativados:
        enviar_email(perfil,novos,baixas,reativados)
        if perfil.get("telegram_chat"):
            msg=f"🏠 <b>{perfil['nome']}</b>\n"
            if novos: msg+=f"{len(novos)} novo(s)\n"
            if baixas: msg+=f"📉 {len(baixas)} baixa(s)\n"
            enviar_telegram(perfil["telegram_chat"],msg)

def verificar_creditos_scraperapi():
    """
    Verifica créditos disponíveis na ScraperAPI.
    Devolve (usados, limite, percentagem) ou None se não conseguir verificar.
    """
    if not SCRAPERAPI_KEY:
        return None
    try:
        r = requests.get(
            f"https://api.scraperapi.com/account?api_key={SCRAPERAPI_KEY}",
            timeout=10)
        data = r.json()
        used  = data.get("requestCount", 0)
        limit = data.get("requestLimit", 1000)
        pct   = int((used / limit) * 100) if limit else 100
        return used, limit, pct
    except Exception as e:
        log.warning(f"Não foi possível verificar créditos ScraperAPI: {e}")
        return None

def verificar():
    log.info("="*55)
    log.info(f"Verificação: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    log.info("="*55)

    # Verifica créditos — só para se ScraperAPI esgotado E sem outros proxies
    creditos = verificar_creditos_scraperapi()
    proxies_disponiveis = sum([bool(SCRAPERAPI_KEY), bool(ZENROWS_KEY), bool(SCRAPINGBEE_KEY)])
    
    if creditos:
        used, limit, pct = creditos
        log.info(f"ScraperAPI: {used}/{limit} créditos usados ({pct}%)")

        if pct >= 100:
            if proxies_disponiveis <= 1:
                # Só tem ScraperAPI e está esgotado — para
                log.warning("⛔ ScraperAPI sem créditos e sem proxies alternativos! A saltar ronda.")
                try:
                    msg = MIMEMultipart("alternative")
                    msg["Subject"] = "⛔ Todos os proxies esgotados — Monitor pausado"
                    msg["From"] = EMAIL_REMETENTE
                    msg["To"]   = EMAIL_DESTINATARIO
                    msg.attach(MIMEText(f"""
                    <html><body style="font-family:Arial,sans-serif;padding:20px">
                    <h2 style="color:#dc2626">⛔ Todos os proxies esgotados!</h2>
                    <p>ScraperAPI: <b>{used}/{limit}</b> ({pct}%)</p>
                    <p>Sem ZenRows nem ScrapingBee configurados.</p>
                    <p>O monitor está <b>pausado</b> até ao reset mensal (dia 1).</p>
                    </body></html>""", "html"))
                    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
                        smtp.login(EMAIL_REMETENTE, EMAIL_PASSWORD)
                        smtp.sendmail(EMAIL_REMETENTE, EMAIL_DESTINATARIO, msg.as_string())
                except Exception as e:
                    log.error(f"Email aviso créditos: {e}")
                return
            else:
                # Tem outros proxies — continua com ZenRows/ScrapingBee
                log.warning(f"⚠️ ScraperAPI esgotado — a usar ZenRows/ScrapingBee ({proxies_disponiveis-1} proxy(s) alternativos)")

        elif pct >= 80:
            log.warning(f"⚠️ ScraperAPI a {pct}% do limite!")
            try:
                msg = MIMEMultipart("alternative")
                msg["Subject"] = f"⚠️ ScraperAPI a {pct}% do limite — Monitor Imóveis"
                msg["From"] = EMAIL_REMETENTE
                msg["To"]   = EMAIL_DESTINATARIO
                msg.attach(MIMEText(f"""
                <html><body style="font-family:Arial,sans-serif;padding:20px">
                <h2 style="color:#f59e0b">⚠️ ScraperAPI quase no limite!</h2>
                <p>Usados: <b>{used}/{limit}</b> ({pct}%)</p>
                <p>A continuar com ZenRows e ScrapingBee como backup.</p>
                </body></html>""", "html"))
                with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
                    smtp.login(EMAIL_REMETENTE, EMAIL_PASSWORD)
                    smtp.sendmail(EMAIL_REMETENTE, EMAIL_DESTINATARIO, msg.as_string())
                log.info("Alerta 80% enviado por email.")
            except Exception as e:
                log.error(f"Email alerta 80%: {e}")

    perfis_ativos = get_perfis_db()
    log.info(f"{len(perfis_ativos)} perfil(is) ativo(s)")
    for p in perfis_ativos: verificar_perfil(p)
    verificar_scrapers_com_falha()
    log.info("Ronda concluída."); quit_driver()

# ============================================================
# AUTENTICAÇÃO
# ============================================================

def login_required(f):
    @functools.wraps(f)
    def decorated(*args,**kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args,**kwargs)
    return decorated

# ============================================================
# IMT / CUSTOS
# ============================================================

def calcular_imt(preco, habitacao_propria=True):
    """Calcula IMT para habitação própria permanente em Portugal."""
    escaloes_hpp = [
        (97064, 0, 0),
        (132774, 0.02, 1941.28),
        (181034, 0.05, 5944.53),
        (301688, 0.07, 9552.23),
        (603289, 0.08, 12568.23),
        (1050400, 0.06, 0),  # taxa única acima de 603k
        (float("inf"), 0.075, 0),
    ]
    escaloes_outros = [
        (97064, 1, 0),
        (132774, 2, 970.64),
        (181034, 5, 4942.22),
        (301688, 7, 8571.86),
        (578598, 8, 11588.50),
        (float("inf"), 6, 0),
    ]
    escaloes = escaloes_hpp if habitacao_propria else escaloes_outros
    for limite, taxa, deducao in escaloes:
        if preco <= limite:
            if taxa == 0: return 0.0
            return round(preco * (taxa/100) - deducao, 2)
    return round(preco * 0.075, 2)

def calcular_custos_totais(preco, habitacao_propria=True):
    imt      = calcular_imt(preco, habitacao_propria)
    is_val   = round(preco * 0.008, 2)      # Imposto de Selo 0.8%
    registo  = round(250 + preco*0.001, 2)  # estimativa registo
    notario  = round(300 + preco*0.001, 2)  # estimativa escritura
    total    = round(imt+is_val+registo+notario, 2)
    return {"preco":preco,"imt":imt,"imposto_selo":is_val,
            "registo":registo,"notario":notario,"total_encargos":total,
            "total_aquisicao":round(preco+total,2)}

# ============================================================
# FLASK APP
# ============================================================

LOGIN_HTML = """<!DOCTYPE html>
<html lang="pt">
<head>
  <meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Monitor Imóveis — Login</title>
  <style>
    *{box-sizing:border-box;margin:0;padding:0}
    body{font-family:Arial,sans-serif;background:linear-gradient(135deg,#0f2942,#1a6b8a);
         min-height:100vh;display:flex;align-items:center;justify-content:center;}
    .box{background:white;border-radius:16px;padding:40px;width:100%;max-width:380px;
         box-shadow:0 20px 60px rgba(0,0,0,.3);}
    .logo{text-align:center;margin-bottom:28px;}
    .logo .icon{font-size:48px;}
    .logo h1{font-size:22px;color:#0f2942;margin-top:8px;}
    .logo p{font-size:13px;color:#9ca3af;margin-top:4px;}
    label{display:block;font-size:13px;font-weight:600;color:#374151;margin-bottom:5px;}
    input{width:100%;padding:11px 14px;border:1.5px solid #e5e7eb;border-radius:8px;
          font-size:14px;margin-bottom:16px;outline:none;}
    input:focus{border-color:#1a6b8a;}
    button{width:100%;padding:12px;background:#0f2942;color:white;border:none;
           border-radius:8px;font-size:15px;font-weight:600;cursor:pointer;}
    button:hover{background:#1a6b8a;}
    .error{background:#fee2e2;color:#991b1b;padding:10px;border-radius:6px;
           font-size:13px;margin-bottom:14px;}
  </style>
</head>
<body>
  <div class="box">
    <div class="logo">
      <div class="icon">🏠</div>
      <h1>Monitor Imóveis</h1>
      <p>Algarve Sotavento</p>
    </div>
    {% if error %}<div class="error">{{ error }}</div>{% endif %}
    <form method="POST">
      <label>Utilizador</label>
      <input name="username" type="text" autocomplete="username" required>
      <label>Password</label>
      <input name="password" type="password" autocomplete="current-password" required>
      <button type="submit">Entrar →</button>
    </form>
  </div>
</body>
</html>"""

DASHBOARD_HTML = open(os.path.join(os.path.dirname(__file__), "dashboard.html")).read() if os.path.exists(
    os.path.join(os.path.dirname(__file__), "dashboard.html")) else "<!-- dashboard.html not found -->"

app = Flask(__name__)
app.secret_key = SECRET_KEY

@app.route("/login", methods=["GET","POST"])
def login():
    error = None
    if request.method == "POST":
        u = request.form.get("username","")
        p = request.form.get("password","")
        if u==DASHBOARD_USERNAME and p==DASHBOARD_PASSWORD:
            session["logged_in"] = True
            return redirect(url_for("dashboard"))
        error = "Utilizador ou password incorretos."
    return render_template_string(LOGIN_HTML, error=error)

@app.route("/logout")
def logout():
    session.clear(); return redirect(url_for("login"))

@app.route("/")
@login_required
def dashboard():
    return render_template_string(DASHBOARD_HTML)

@app.route("/api/imoveis")
@login_required
def api_imoveis():
    try: return jsonify(get_imoveis())
    except Exception as e: return jsonify({"erro":str(e)}),500

@app.route("/api/stats")
@login_required
def api_stats():
    try: return jsonify(get_stats())
    except Exception as e: return jsonify({"erro":str(e)}),500

@app.route("/api/mercado")
@login_required
def api_mercado():
    try:
        dados = get_dados_mercado()
        return jsonify(dados)
    except Exception as e:
        log.error(f"api_mercado: {e}")
        return jsonify({"por_zona":[],"evolucao":[],"distribuicao":{}}), 200

@app.route("/api/imovel/favorito", methods=["POST"])
@login_required
def api_favorito():
    data=request.get_json(); iid=data.get("id")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE imoveis SET favorito=NOT favorito WHERE id=%s RETURNING favorito",(iid,))
            row=cur.fetchone()
        conn.commit()
    return jsonify({"favorito":row[0] if row else False})

@app.route("/api/imovel/estado", methods=["POST"])
@login_required
def api_estado():
    data=request.get_json()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE imoveis SET estado=%s WHERE id=%s",(data.get("estado"),data.get("id")))
        conn.commit()
    return jsonify({"ok":True})

@app.route("/api/imovel/nota", methods=["POST"])
@login_required
def api_nota():
    data=request.get_json()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE imoveis SET nota=%s WHERE id=%s",(data.get("nota",""),data.get("id")))
        conn.commit()
    return jsonify({"ok":True})

@app.route("/api/imovel/<iid>")
@login_required
def api_imovel_detalhe(iid):
    with get_db() as conn:
        with conn.cursor(row_factory=psycopg_rows.dict_row) as cur:
            cur.execute("SELECT * FROM imoveis WHERE id=%s",(iid,))
            row=cur.fetchone()
    if not row: return jsonify({"erro":"não encontrado"}),404
    d=dict(row)
    for k in ["criado_em","atualizado_em","removido_em","reativado_em"]:
        if d.get(k): d[k]=d[k].isoformat()
    return jsonify(d)

@app.route("/api/comparar", methods=["POST"])
@login_required
def api_comparar():
    ids=request.get_json().get("ids",[])
    if len(ids)<2 or len(ids)>3: return jsonify({"erro":"Seleciona 2 ou 3 imóveis"}),400
    imoveis=[]
    with get_db() as conn:
        with conn.cursor(row_factory=psycopg_rows.dict_row) as cur:
            for iid in ids:
                cur.execute("SELECT * FROM imoveis WHERE id=%s",(iid,))
                row=cur.fetchone()
                if row:
                    d=dict(row)
                    for k in ["criado_em","atualizado_em"]:
                        if d.get(k): d[k]=d[k].isoformat()
                    imoveis.append(d)
    custos=[calcular_custos_totais(i["preco_valor"]) for i in imoveis if i.get("preco_valor")]
    return jsonify({"imoveis":imoveis,"custos":custos})

@app.route("/api/custos")
@login_required
def api_custos():
    try:
        preco=int(request.args.get("preco",0))
        hpp=request.args.get("hpp","true").lower()=="true"
        return jsonify(calcular_custos_totais(preco,hpp))
    except Exception as e: return jsonify({"erro":str(e)}),400

@app.route("/api/visitas", methods=["GET","POST"])
@login_required
def api_visitas():
    if request.method=="GET":
        iid=request.args.get("imovel_id")
        return jsonify(get_visitas(iid))
    data=request.get_json()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO visitas(imovel_id,data_visita,nota,avaliacao)
                VALUES(%s,%s,%s,%s)
            """, (data["imovel_id"],data["data_visita"],
                  data.get("nota",""),data.get("avaliacao")))
        conn.commit()
    return jsonify({"ok":True})

@app.route("/api/exportar/excel")
@login_required
def api_exportar_excel():
    """Exporta favoritos para Excel."""
    try:
        import io
        try: import openpyxl
        except ImportError: return jsonify({"erro":"openpyxl não instalado"}),500
        with get_db() as conn:
            with conn.cursor(row_factory=psycopg_rows.dict_row) as cur:
                cur.execute("""
                    SELECT titulo,preco,area_m2,quartos,preco_m2,ano_construcao,
                           zona,fonte,estado,nota,score,link,criado_em
                    FROM imoveis WHERE favorito=TRUE ORDER BY score DESC
                """)
                rows=[dict(r) for r in cur.fetchall()]
        wb=openpyxl.Workbook(); ws=wb.active; ws.title="Favoritos"
        headers=["Título","Preço","Área m²","Quartos","€/m²","Ano","Zona","Fonte","Estado","Notas","Score","Link","Data"]
        ws.append(headers)
        from openpyxl.styles import Font, PatternFill
        for cell in ws[1]:
            cell.font=Font(bold=True,color="FFFFFF")
            cell.fill=PatternFill(fill_type="solid",fgColor="0F2942")
        for r in rows:
            ws.append([r.get("titulo"),r.get("preco"),r.get("area_m2"),r.get("quartos"),
                       r.get("preco_m2"),r.get("ano_construcao"),r.get("zona"),r.get("fonte"),
                       r.get("estado"),r.get("nota"),r.get("score"),r.get("link"),
                       str(r.get("criado_em",""))[:10]])
        for col in ws.columns:
            ws.column_dimensions[col[0].column_letter].width = max(len(str(cell.value or "")) for cell in col)+4
        buf=io.BytesIO(); wb.save(buf); buf.seek(0)
        resp=make_response(buf.read())
        resp.headers["Content-Type"]="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        resp.headers["Content-Disposition"]=f"attachment; filename=favoritos_algarve_{datetime.now().strftime('%Y%m%d')}.xlsx"
        return resp
    except Exception as e: return jsonify({"erro":str(e)}),500

@app.route("/api/mapa")
@login_required
def api_mapa():
    """Imóveis com coordenadas GPS para o mapa."""
    with get_db() as conn:
        with conn.cursor(row_factory=psycopg_rows.dict_row) as cur:
            cur.execute("""
                SELECT id,titulo,preco,preco_valor,zona,fonte,score,
                       lat,lng,imagem_url,estado,favorito
                FROM imoveis WHERE disponivel=TRUE AND lat IS NOT NULL AND lng IS NOT NULL
                ORDER BY score DESC LIMIT 500
            """)
            return jsonify([dict(r) for r in cur.fetchall()])

@app.route("/api/push/subscribe", methods=["POST"])
@login_required
def api_push_subscribe():
    data=request.get_json()
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO push_subscriptions(endpoint,p256dh,auth) VALUES(%s,%s,%s) ON CONFLICT(endpoint) DO NOTHING",
                    (data["endpoint"],data["keys"]["p256dh"],data["keys"]["auth"]))
            conn.commit()
        return jsonify({"ok":True})
    except Exception as e: return jsonify({"erro":str(e)}),500

@app.route("/api/perfis", methods=["GET"])
@login_required
def api_perfis_get():
    try:
        perfis = get_todos_perfis_db()
        for p in perfis:
            for k in ["criado_em","atualizado_em"]:
                if p.get(k): p[k] = str(p[k])
        return jsonify(perfis)
    except Exception as e:
        return jsonify({"erro":str(e)}),500

@app.route("/api/perfis", methods=["POST"])
@login_required
def api_perfis_criar():
    try:
        d = request.get_json()
        pid = criar_perfil_db(
            d["nome"], d["email"],
            int(d.get("preco_max",200000)), int(d.get("quartos_min",2)),
            d.get("tipos",["apartamentos","moradias-e-vivendas"]),
            d.get("zonas",["faro","tavira","olhao","vila-real-de-santo-antonio","castro-marim"])
        )
        return jsonify({"ok":True,"id":pid})
    except Exception as e:
        return jsonify({"erro":str(e)}),500

@app.route("/api/perfis/<int:pid>", methods=["PUT"])
@login_required
def api_perfis_atualizar(pid):
    try:
        d = request.get_json()
        atualizar_perfil_db(
            pid, d["nome"], d["email"],
            int(d.get("preco_max",200000)), int(d.get("quartos_min",2)),
            d.get("tipos",["apartamentos","moradias-e-vivendas"]),
            d.get("zonas",["faro","tavira","olhao"]),
            d.get("ativo",True)
        )
        return jsonify({"ok":True})
    except Exception as e:
        return jsonify({"erro":str(e)}),500

@app.route("/api/perfis/<int:pid>", methods=["DELETE"])
@login_required
def api_perfis_apagar(pid):
    try:
        apagar_perfil_db(pid)
        return jsonify({"ok":True})
    except Exception as e:
        return jsonify({"erro":str(e)}),500

@app.route("/api/perfis/teste-email", methods=["POST"])
@login_required
def api_teste_email():
    try:
        d = request.get_json()
        email_dest = d.get("email", EMAIL_DESTINATARIO)
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "✅ Teste — Monitor Imóveis Algarve"
        msg["From"] = EMAIL_REMETENTE
        msg["To"] = email_dest
        msg.attach(MIMEText(f"""
        <html><body style="font-family:Arial,sans-serif;padding:20px">
        <h2 style="color:#0f2942">✅ Email de teste enviado com sucesso!</h2>
        <p>O Monitor de Imóveis está configurado corretamente.</p>
        <p style="color:#888;font-size:12px">{datetime.now().strftime('%d/%m/%Y %H:%M')}</p>
        </body></html>""", "html"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(EMAIL_REMETENTE, EMAIL_PASSWORD)
            smtp.sendmail(EMAIL_REMETENTE, email_dest, msg.as_string())
        return jsonify({"ok":True})
    except Exception as e:
        return jsonify({"erro":str(e)}),500

def verificar_limite_scraperapi():
    """Verifica uso de todos os proxies e envia alerta se algum >80%."""
    # Log estatísticas de rotação
    stats = get_proxy_stats()
    if stats: log.info(f"Proxy stats: {stats}")
    
    if not SCRAPERAPI_KEY: return
    try:
        r = requests.get(
            f"https://api.scraperapi.com/account?api_key={SCRAPERAPI_KEY}",
            timeout=10)
        data = r.json()
        used    = data.get("requestCount", 0)
        limit   = data.get("requestLimit", 1000)
        pct     = int((used / limit) * 100) if limit else 0
        log.info(f"ScraperAPI: {used}/{limit} pedidos ({pct}%)")
        if pct >= 80:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"⚠️ ScraperAPI a {pct}% do limite ({used}/{limit} pedidos)"
            msg["From"] = EMAIL_REMETENTE
            msg["To"]   = EMAIL_DESTINATARIO
            msg.attach(MIMEText(f"""
            <html><body style="font-family:Arial,sans-serif;padding:20px">
            <h2 style="color:#dc2626">⚠️ ScraperAPI quase no limite!</h2>
            <p>Usados: <b>{used}/{limit}</b> pedidos ({pct}%)</p>
            <p>Considera fazer upgrade em <a href="https://scraperapi.com">scraperapi.com</a></p>
            </body></html>""", "html"))
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
                smtp.login(EMAIL_REMETENTE, EMAIL_PASSWORD)
                smtp.sendmail(EMAIL_REMETENTE, EMAIL_DESTINATARIO, msg.as_string())
            log.warning(f"⚠️ Alerta ScraperAPI enviado ({pct}%)")
        return {"used": used, "limit": limit, "pct": pct}
    except Exception as e:
        log.warning(f"verificar_limite_scraperapi: {e}")
        return {}

@app.route("/api/scraperapi/stats")
@login_required
def api_scraperapi_stats():
    stats = verificar_limite_scraperapi()
    proxy_stats = get_proxy_stats()
    return jsonify({"scraperapi": stats or {}, "rotacao": proxy_stats})

@app.route("/api/historico_precos")
@login_required
def api_historico_precos():
    imovel_id = request.args.get("imovel_id","")
    try:
        with get_db() as conn:
            with conn.cursor(row_factory=psycopg_rows.dict_row) as cur:
                cur.execute("""
                    SELECT preco_antigo, preco_novo, alterado_em::TEXT
                    FROM historico_precos WHERE imovel_id=%s
                    ORDER BY alterado_em DESC
                """, (imovel_id,))
                return jsonify([dict(r) for r in cur.fetchall()])
    except Exception as e:
        return jsonify([])

@app.route("/api/imovel/apagar", methods=["DELETE"])
@login_required
def api_apagar_imovel():
    try:
        data = request.get_json()
        iid = data.get("id")
        if not iid:
            return jsonify({"erro":"ID não fornecido"}), 400
        with get_db() as conn:
            with conn.cursor() as cur:
                # Apaga também histórico de preços e visitas
                cur.execute("DELETE FROM historico_precos WHERE imovel_id=%s", (iid,))
                cur.execute("DELETE FROM visitas WHERE imovel_id=%s", (iid,))
                cur.execute("DELETE FROM imoveis WHERE id=%s", (iid,))
                apagados = cur.rowcount
            conn.commit()
        if apagados:
            log.info(f"Imóvel apagado: {iid[:50]}")
            return jsonify({"ok": True})
        else:
            return jsonify({"erro": "Imóvel não encontrado"}), 404
    except Exception as e:
        log.error(f"api_apagar_imovel: {e}")
        return jsonify({"erro": str(e)}), 500

@app.route("/health")
def health(): return jsonify({"status":"ok","ts":datetime.now().isoformat()})

# ============================================================
# ARRANQUE
# ============================================================

if __name__=="__main__":
    log.info("╔══════════════════════════════════════════════════╗")
    log.info("║   Monitor de Imóveis — Algarve  v4.0             ║")
    log.info("╚══════════════════════════════════════════════════╝")
    if DATABASE_URL:
        init_db()
        sincronizar_perfis_iniciais()
        # Geocodifica imóveis existentes em background
        threading.Thread(target=geocodificar_existentes, daemon=True).start()
    else: log.warning("DATABASE_URL não definida!")
    log.info(f"Login: {DASHBOARD_USERNAME} / {DASHBOARD_PASSWORD}")
    log.info(f"{len(SCRAPERS)} fontes | {len(PERFIS)} perfil(is) | cada {INTERVALO_HORAS}h")
    threading.Thread(target=lambda:app.run(host="0.0.0.0",port=PORT,use_reloader=False),daemon=True).start()
    log.info(f"Dashboard em http://localhost:{PORT}")
    verificar()
    # Corre uma vez por dia às 08:00 — poupa pedidos ScraperAPI
    schedule.every(24).hours.do(verificar)  # uma vez por dia
    schedule.every().monday.at("08:00").do(enviar_resumo_semanal)
    schedule.every().day.at("09:00").do(verificar_scrapers_com_falha)
    schedule.every().day.at("20:00").do(verificar_limite_scraperapi)
    schedule.every(24).hours.do(geocodificar_existentes)
    log.info("A monitorizar. Ctrl+C para parar.\n")
    while True: schedule.run_pending(); time.sleep(60)
"# v4.1" 
"# v4.1" 
