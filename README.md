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
- **Screenshot Completi**: Cattura l'intera conversazione con tutti i prodotti
- **Single-Turn Mode**: Esegui solo la domanda iniziale senza followup
- **LangSmith Integration**: Debug avanzato delle risposte chatbot
- **Bilingue**: Italiano e Inglese

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

### Opzioni

| Opzione | Descrizione |
|---------|-------------|
| `-p, --project` | Nome del progetto |
| `-m, --mode` | Modalita: train, assisted, auto |
| `-t, --test` | ID singolo test da eseguire |
| `--tests` | Quali test: all, pending, failed |
| `--new-run` | Crea nuovo run su Google Sheets |
| `--no-interactive` | Esecuzione non interattiva |
| `--dry-run` | Simula senza eseguire |

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

| Opzione | Descrizione |
|---------|-------------|
| `single_turn` | `true` = Solo domanda iniziale, no followup Ollama |
| `use_ollama` | `false` = Disabilita valutazione automatica |
| `active_run` | Numero del run attivo su Google Sheets |

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
    └── config_loader.py    # Gestione configurazione
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
