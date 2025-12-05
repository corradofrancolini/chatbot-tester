# Chatbot Tester - Note Progetto

**Mantra: Se si puo fare, deve essere visibile, spiegato, e configurabile.**

## Documentazione

| Guida | Contenuto |
|-------|-----------|
| [README.md](README.md) | Panoramica e quick start |
| [docs/CONFIGURATION.md](docs/CONFIGURATION.md) | Guida completa configurazione |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Docker, GitHub Actions, PyPI |

---

## Comandi Principali

### Eseguire test
```bash
# Nuovo run completo
python run.py -p my-chatbot -m auto --no-interactive --new-run

# Continuare run esistente (solo pending)
python run.py -p my-chatbot -m auto --no-interactive

# Singolo test (sovrascrive)
python run.py -p my-chatbot -m auto --no-interactive -t TEST_050 --tests all

# Solo test falliti
python run.py -p my-chatbot -m auto --no-interactive --tests failed
```

### Health Check
```bash
# Verifica servizi prima di eseguire
python run.py --health-check -p my-chatbot

# Esegui test saltando health check
python run.py -p my-chatbot -m auto --no-interactive --skip-health-check
```

---

## Configurazione run_config.json

| Opzione | Descrizione | Menu |
|---------|-------------|------|
| `env` | Ambiente: DEV, STAGING, PROD | Configura |
| `dry_run` | Simula senza eseguire | Toggle [1] |
| `use_langsmith` | Abilita tracing LangSmith | Toggle [2] |
| `use_rag` | Abilita recupero RAG | Toggle [3] |
| `use_ollama` | Abilita valutazione Ollama | Toggle [4] |
| `single_turn` | Solo domanda iniziale | Toggle [5] |
| `active_run` | Numero run su Google Sheets | Auto |

### Opzioni CLI Complete

```bash
python run.py [OPZIONI]

# Progetto e modalita
-p, --project       Nome progetto
-m, --mode          train | assisted | auto
-t, --test          ID singolo test
--tests             all | pending | failed
--new-run           Forza nuova RUN

# Comportamento
--no-interactive    Senza prompt utente
--dry-run           Simula
--headless          Browser nascosto

# Servizi
--health-check      Verifica servizi e esci
--skip-health-check Salta verifica

# Debug
--debug             Output dettagliato
--lang              it | en
-v, --version       Mostra versione
```

---

## Screenshot

Gli screenshot devono catturare l'INTERA conversazione con TUTTI i prodotti visibili.

**File chiave:** `src/browser.py` metodo `take_conversation_screenshot()`
- Usa CSS injection per nascondere input bar, footer, scroll indicators
- Espande container per mostrare tutto il contenuto
- Cattura `section.llm__thread`

---

## Struttura Report

```
reports/{project}/run_{N}/
├── report.html       # Report HTML interattivo
└── screenshots/      # Screenshot conversazioni
    ├── TEST_001.png
    └── ...
```

---

## Moduli Principali

| Modulo | Descrizione |
|--------|-------------|
| `run.py` | Entry point, CLI, menu interattivo |
| `src/tester.py` | Engine principale test |
| `src/browser.py` | Automazione Playwright |
| `src/health.py` | Health checks, circuit breaker, retry |
| `src/sheets_client.py` | Integrazione Google Sheets |
| `src/langsmith_client.py` | Tracing LangSmith |
| `src/ollama_client.py` | Valutazione AI locale |
| `src/config_loader.py` | Caricamento configurazioni |
| `src/i18n.py` | Traduzioni IT/EN |
| `src/ui.py` | Console UI (Rich) |
| `src/finetuning.py` | Pipeline fine-tuning |
| `wizard/main.py` | Wizard nuovo progetto |

---

## Deployment (v1.1.0)

### Docker
```bash
docker build -t chatbot-tester .
docker run -v ./projects:/app/projects chatbot-tester -p my-chatbot -m auto
```

### GitHub Actions
```bash
# Esegui test nel cloud
gh workflow run chatbot-test.yml -f project=my-chatbot -f mode=auto
```

### PyPI (dopo pubblicazione)
```bash
pip install chatbot-tester
chatbot-tester -p my-chatbot -m auto
```

### Binary standalone
```bash
pip install pyinstaller
pyinstaller chatbot-tester.spec
./dist/chatbot-tester -p my-chatbot -m auto
```

---

## File di Deployment

| File | Scopo |
|------|-------|
| `Dockerfile` | Build immagine Docker |
| `.github/workflows/chatbot-test.yml` | Esecuzione test nel cloud |
| `.github/workflows/build-release.yml` | Build automatici per release |
| `action.yml` | GitHub Action per marketplace |
| `pyproject.toml` | Configurazione PyPI |
| `chatbot-tester.spec` | Configurazione PyInstaller |

---

## Progetti Configurati

- `my-chatbot` → Silicon search chatbot (DEV)
- `example-bot` → EFG chatbot
