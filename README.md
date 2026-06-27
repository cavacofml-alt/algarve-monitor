# 🏠 Monitor de Imóveis — Algarve v4.0

## ✨ Novidades v4

| # | Melhoria | Descrição |
|---|---|---|
| 1 | 🔐 Autenticação | Login com username/password — ninguém acede ao teu dashboard sem credenciais |
| 2 | 🔍 Detalhes completos | Entra em cada anúncio e extrai área, ano, descrição, GPS, galeria de fotos |
| 3 | ⚠️ Alertas de falha | Email automático se um scraper falhar 3+ vezes consecutivas |
| 4 | ⚖️ Comparação lado a lado | Seleciona 2-3 imóveis e compara numa tabela com custos incluídos |
| 5 | 📊 Exportar Excel | Exporta todos os favoritos para .xlsx com um clique |
| 6 | 🗺️ Mapa interativo | Visualiza imóveis num mapa (Leaflet + OpenStreetMap, sem custos) |
| 7 | 💶 Custos de aquisição | Calcula IMT, Imposto de Selo, Registo e Escritura automaticamente |
| 8 | 📅 Histórico de visitas | Regista visitas com data, avaliação em estrelas e notas |

---

## 🚀 Deploy no Railway

### 1. Push para GitHub
```bash
git init && git add . && git commit -m "v4.0"
git remote add origin https://github.com/USERNAME/algarve-monitor.git
git push -u origin main
```

### 2. Railway
- [railway.app](https://railway.app) → **New Project → GitHub repo**
- **New → Database → PostgreSQL** (DATABASE_URL automática)

### 3. Variáveis de ambiente

| Variável | Obrigatória | Descrição |
|---|---|---|
| `EMAIL_REMETENTE` | ✅ | Gmail que envia alertas |
| `EMAIL_PASSWORD` | ✅ | App Password Gmail (16 chars) |
| `EMAIL_DESTINATARIO` | ✅ | Email que recebe alertas |
| `DATABASE_URL` | ✅ | Automática — Railway PostgreSQL |
| `DASHBOARD_USERNAME` | ✅ | Username para login (default: admin) |
| `DASHBOARD_PASSWORD` | ✅ | Password para login (default: algarve2024) |
| `SECRET_KEY` | ✅ | Chave de sessão — qualquer string longa aleatória |
| `INTERVALO_HORAS` | — | Default: 6 |
| `SCRAPERAPI_KEY` | — | scraperapi.com — evita bloqueios por IP |
| `TELEGRAM_BOT_TOKEN` | — | Alertas Telegram |
| `PERFIL_1_TELEGRAM_CHAT` | — | Chat ID Telegram |
| `VAPID_PUBLIC_KEY` | — | Push notifications PWA |
| `VAPID_PRIVATE_KEY` | — | Push notifications PWA |
| `PERFIL_1_EMAIL` | — | Email do Perfil 1 |
| `PERFIL_1_PRECO_MAX` | — | Default: 200000 |
| `PERFIL_1_QUARTOS_MIN` | — | Default: 2 |

> ⚠️ **Importante:** Muda `DASHBOARD_PASSWORD` para uma password forte antes do deploy!

---

## 🔐 Autenticação

O dashboard requer login. As credenciais são definidas nas variáveis de ambiente:
- `DASHBOARD_USERNAME` (default: `admin`)
- `DASHBOARD_PASSWORD` (default: `algarve2024` — **muda isto!**)

---

## 🗺️ Mapa

O mapa usa **Leaflet + OpenStreetMap** — completamente gratuito, sem API key.

As coordenadas GPS são extraídas automaticamente dos anúncios quando disponíveis. Imóveis sem coordenadas não aparecem no mapa.

---

## 💶 Cálculo de Custos (IMT)

O cálculo do IMT segue os escalões de **Habitação Própria Permanente** em Portugal (2024):

| Valor | Taxa | Dedução |
|---|---|---|
| Até 97.064€ | 0% | — |
| 97.064€ – 132.774€ | 2% | 1.941€ |
| 132.774€ – 181.034€ | 5% | 5.944€ |
| 181.034€ – 301.688€ | 7% | 9.552€ |
| 301.688€ – 603.289€ | 8% | 12.568€ |

Inclui também: Imposto de Selo (0,8%), estimativa de registo e escritura.

---

## ⚖️ Comparação

Clica no botão **+** em qualquer card para o adicionar à comparação (máx. 3). A barra azul no topo mostra quantos tens selecionados. Clica em **Comparar** para ver a tabela lado a lado com todos os detalhes e custos.

---

## 📊 Exportar Excel

Clica em **📊 Excel** no canto superior direito para descarregar todos os favoritos num ficheiro `.xlsx` formatado, ordenado por score de relevância.

---

## 📅 Histórico de Visitas

No detalhe de cada imóvel (botão 🔍), podes registar visitas com:
- Data da visita
- Avaliação de 1 a 5 estrelas
- Notas pessoais

O separador **Visitas** mostra o histórico completo de todas as visitas.

---

## 📲 PWA (instalável no telemóvel)

Abre o URL do Railway no Chrome (Android) ou Safari (iOS) e instala como app.

### Gerar chaves VAPID para notificações push:
```bash
pip install py-vapid
python -c "from py_vapid import Vapid; v=Vapid(); v.generate_keys(); print('Public:', v.public_key); print('Private:', v.private_key)"
```

---

## 🔧 Personalizar

Em `algarve_monitor.py`:
- `PERFIS` — adiciona/remove perfis de pesquisa
- `MAX_PAGINAS` — número de páginas por scraper (default: 5)
- `ZONA_SCORE` — ponderação de zonas no score de relevância
- Linha `schedule.every().monday.at("08:00")` — hora do resumo semanal
- Linha `schedule.every(12).hours` — frequência de verificação de scrapers com falha

---

## 👥 Segundo perfil

Descomenta o bloco `Perfil 2` em `algarve_monitor.py`, faz push e adiciona no Railway:
`PERFIL_2_EMAIL`, `PERFIL_2_PRECO_MAX`, `PERFIL_2_QUARTOS_MIN`
