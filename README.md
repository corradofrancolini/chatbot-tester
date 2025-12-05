# Chatbot Tester

Tool automatizzato per testare chatbot web con supporto multi-progetto, AI locale e reporting avanzato.

[![macOS](https://img.shields.io/badge/macOS-12.0+-blue.svg)](https://www.apple.com/macos/)
[![Python](https://img.shields.io/badge/Python-3.10+-green.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Caratteristiche

- **Multi-progetto**: Testa diversi chatbot dalla stessa installazione
- **3 Modalita**: Train, Assisted, Auto per ogni fase del testing
- **AI Locale**: Ollama per analisi privacy-first
- **Report Flessibili**: HTML locale + Google Sheets opzionale
- **Export Report**: PDF, Excel, HTML, CSV
- **Notifiche**: Desktop (macOS), Email, Microsoft Teams
- **Screenshot Completi**: Cattura l'intera conversazione con tutti i prodotti
- **Single-Turn Mode**: Esegui solo la domanda iniziale senza followup
- **LangSmith Integration**: Debug avanzato delle risposte chatbot
- **Analisi Testing**: Confronto A/B, regressioni, test flaky
- **Esecuzione Parallela**: Multi-browser per test veloci
- **Scheduled Runs**: Cron locale e GitHub Actions
- **Bilingue**: Italiano e Inglese
- **Health Check**: Verifica servizi prima dell'esecuzione
- **Cloud Execution**: Esegui test su GitHub Actions senza Chromium locale
- **Docker Ready**: Container pronto all'uso

---

## Quick Start

### 1. Installazione

```bash
# Clona il repository
git clone https://github.com/corradofrancolini/chatbot-tester.git
cd chatbot-tester

# Crea ambiente virtuale
python3 -m venv .venv
source .venv/bin/activate

# Installa dipendenze
pip install -r requirements.txt
playwright install chromium
```

### 2. Avvia i test

```bash
# Modalità Auto - nuovo run
python run.py -p my-chatbot -m auto --no-interactive --new-run

# Modalità Auto - continua run esistente
python run.py -p my-chatbot -m auto --no-interactive

# Modalità Train (apprendimento)
python run.py -p my-chatbot -m train
```

---

## Comandi CLI

### Esecuzione Test

```bash
# Nuovo run completo (crea nuovo foglio Google Sheets)
python run.py -p <progetto> -m auto --no-interactive --new-run

# Continua run esistente (solo test pending)
python run.py -p <progetto> -m auto --no-interactive

# Esegui singolo test
python run.py -p <progetto> -m auto --no-interactive -t TEST_050

# Ri-esegui singolo test (sovrascrive)
python run.py -p <progetto> -m auto --no-interactive -t TEST_050 --tests all

# Ri-esegui tutti i test falliti
python run.py -p <progetto> -m auto --no-interactive --tests failed

# Ri-esegui tutti i test (sovrascrive)
python run.py -p <progetto> -m auto --no-interactive --tests all
```

### Export Report

```bash
# Esporta ultimo run in HTML
python run.py -p <progetto> --export html

# Esporta run specifico in PDF
python run.py -p <progetto> --export pdf --export-run 15

# Esporta in tutti i formati
python run.py -p <progetto> --export all
```

### Notifiche

```bash
# Testa notifica desktop
python run.py -p <progetto> --test-notify

# Invia notifica dopo run
python run.py -p <progetto> -m auto --no-interactive --notify desktop
```

### Opzioni

| Opzione | Descrizione | Default |
|---------|-------------|---------|
| `-p, --project` | Nome del progetto | - |
| `-m, --mode` | Modalita: train, assisted, auto | train |
| `-t, --test` | ID singolo test da eseguire | - |
| `--tests` | Quali test: all, pending, failed | pending |
| `--new-run` | Crea nuovo run su Google Sheets | false |
| `--no-interactive` | Esecuzione non interattiva | false |
| `--dry-run` | Simula senza eseguire | false |
| `--health-check` | Verifica servizi e esci | false |
| `--skip-health-check` | Salta verifica servizi | false |
| `--headless` | Browser in modalita headless | false |
| `--lang` | Lingua interfaccia: it, en | it |
| `--debug` | Output debug dettagliato | false |
| `--export` | Esporta report: pdf, excel, html, csv, all | - |
| `--export-run` | Numero run da esportare | ultimo |
| `--notify` | Invia notifica: desktop, email, teams, all | - |
| `--test-notify` | Testa configurazione notifiche | false |
| `-v, --version` | Mostra versione | - |

Per la guida completa a tutte le opzioni di configurazione, vedi [docs/CONFIGURATION.md](docs/CONFIGURATION.md).

---

## Modalita di Test

| Modalita | Descrizione | Quando usarla |
|----------|-------------|---------------|
| **Train** | Esegui test manualmente, il tool impara | Prima configurazione |
| **Assisted** | AI suggerisce, tu confermi | Validazione, correzioni |
| **Auto** | Completamente automatico | Regression testing |

---

## Configurazione

### run_config.json

Ogni progetto ha un file `projects/<nome>/run_config.json`:

```json
{
  "env": "DEV",
  "active_run": 15,
  "mode": "auto",
  "use_langsmith": true,
  "use_ollama": true,
  "single_turn": true
}
```

| Opzione | Descrizione | Accessibile da |
|---------|-------------|----------------|
| `env` | Ambiente: DEV, STAGING, PROD | Menu > Configura |
| `active_run` | Numero del run attivo su Google Sheets | Automatico |
| `dry_run` | Simula senza eseguire | Menu > Toggle |
| `use_langsmith` | Abilita tracing LangSmith | Menu > Toggle |
| `use_rag` | Abilita recupero RAG | Menu > Toggle |
| `use_ollama` | Abilita valutazione Ollama | Menu > Toggle |
| `single_turn` | Solo domanda iniziale, no followup | Menu > Toggle |

### Toggle Runtime

Dal menu interattivo: **Progetto > Toggle Opzioni**

```
[1] Dry Run:      OFF  (simula senza eseguire)
[2] LangSmith:    ON   (tracing attivo)
[3] RAG:          OFF  (disabilitato)
[4] Ollama:       ON   (valutazione AI)
[5] Single Turn:  ON   (solo domanda iniziale)
```

---

## Screenshot

Gli screenshot catturano l'**intera conversazione** con tutti i prodotti visibili.

- Nasconde automaticamente: input bar, footer, scroll indicators
- Espande i container per mostrare tutto il contenuto
- Salva in: `reports/<progetto>/run_<N>/screenshots/`

---

## Struttura Progetto

```
chatbot-tester/
├── run.py                  # Entry point
├── CLAUDE.md               # Note progetto per Claude Code
│
├── config/
│   ├── .env                # Credenziali (gitignored)
│   └── settings.yaml       # Settings globali
│
├── projects/               # Progetti configurati
│   └── <nome-progetto>/
│       ├── project.yaml    # Configurazione chatbot
│       ├── tests.json      # Test cases
│       ├── run_config.json # Stato run corrente
│       └── browser-data/   # Sessione browser
│
├── reports/                # Report locali
│   └── <nome-progetto>/
│       └── run_<N>/
│           ├── report.html
│           └── screenshots/
│
└── src/                    # Codice sorgente
    ├── browser.py          # Automazione Playwright
    ├── tester.py           # Logica test
    ├── config_loader.py    # Gestione configurazione
    ├── export.py           # Export PDF, Excel, HTML, CSV
    └── notifications.py    # Notifiche Desktop, Email, Teams
```

---

## Integrazioni

### Ollama (AI Locale)

```bash
# Installa Ollama
brew install ollama

# Avvia servizio
ollama serve

# Scarica modello
ollama pull llama3.2:3b
```

### Google Sheets

1. Crea progetto su [Google Cloud Console](https://console.cloud.google.com)
2. Abilita Google Sheets API e Google Drive API
3. Crea credenziali OAuth 2.0
4. Configura in `config/.env`

### LangSmith

1. Crea account su [smith.langchain.com](https://smith.langchain.com)
2. Genera API Key
3. Configura in `config/.env`

### Notifiche

Configura in `config/settings.yaml`:

```yaml
notifications:
  desktop:
    enabled: true      # macOS native
    sound: true
  email:
    enabled: false
    smtp_host: "smtp.gmail.com"
    smtp_port: 587
    smtp_user: "tuo@email.com"
    recipients: ["team@email.com"]
  teams:
    enabled: false
    webhook_url_env: "TEAMS_WEBHOOK_URL"  # Variabile ambiente
```

**Microsoft Teams**: Crea un Incoming Webhook nel canale Teams e imposta la variabile ambiente:
```bash
export TEAMS_WEBHOOK_URL="https://outlook.office.com/webhook/..."
```

---

## Deployment

Esegui test senza avere Chromium locale. Vedi [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) per la guida completa.

### GitHub Actions (consigliato)

```bash
# Installa GitHub CLI
brew install gh

# Lancia test nel cloud
gh workflow run chatbot-test.yml -f project=my-chatbot -f mode=auto
```

### Docker

```bash
# Build
docker build -t chatbot-tester .

# Esegui
docker run -v ./projects:/app/projects chatbot-tester -p my-chatbot -m auto
```

### Health Check

```bash
# Verifica servizi prima di eseguire
python run.py --health-check -p my-chatbot
```

---

## Documentazione

| Guida | Descrizione |
|-------|-------------|
| [CONFIGURATION.md](docs/CONFIGURATION.md) | Guida completa a tutte le opzioni |
| [DEPLOYMENT.md](docs/DEPLOYMENT.md) | Deploy su Docker, GitHub Actions, PyPI |
| [CLAUDE.md](CLAUDE.md) | Note per sviluppo con Claude Code |

---

## Troubleshooting

**Il browser non si apre**
```bash
source .venv/bin/activate
playwright install chromium
```

**Errore "Module not found"**
```bash
source .venv/bin/activate
pip install -r requirements.txt
```

**Sessione scaduta**
```bash
rm -rf projects/<nome>/browser-data/
python run.py -p <nome>
```

---

## Licenza

MIT License - vedi [LICENSE](LICENSE) per dettagli.
