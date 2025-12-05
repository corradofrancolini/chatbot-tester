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
| `src/parallel.py` | Esecuzione parallela, browser pool |
| `src/cache.py` | Caching in-memory e disk |
| `src/comparison.py` | A/B comparison, regressioni, flaky tests |
| `src/github_actions.py` | Integrazione GitHub Actions |
| `wizard/main.py` | Wizard nuovo progetto |

---

## Esecuzione Parallela (v1.2.0)

### CLI
```bash
# 3 browser in parallelo
python run.py -p my-chatbot -m auto --parallel --no-interactive

# 5 browser
python run.py -p my-chatbot -m auto --parallel --workers 5 --no-interactive
```

### Come funziona
1. `BrowserPool` crea N browser Chromium isolati
2. I test vengono distribuiti ai worker
3. Ogni worker accumula risultati in `ThreadSafeSheetsClient`
4. Alla fine, `flush()` scrive tutto in batch su Google Sheets

### API per sviluppatori
```python
from src.sheets_client import ThreadSafeSheetsClient, ParallelResultsCollector

# Wrapper thread-safe per Sheets
safe_client = ThreadSafeSheetsClient(sheets_client)
safe_client.queue_result(result)    # Thread-safe
safe_client.queue_screenshot(path, test_id)
safe_client.flush()                 # Scrivi batch

# Oppure: collector in memoria
collector = ParallelResultsCollector()
collector.add(result)
all_results = collector.get_all()
```

### Configurazione (settings.yaml)
```yaml
parallel:
  enabled: false
  max_workers: 3
  retry_strategy: exponential  # none | linear | exponential
  max_retries: 2
  rate_limit_per_minute: 60

cache:
  enabled: true
  memory:
    max_entries: 1000
    default_ttl_seconds: 300
```

---

## Analisi Testing (v1.2.0)

### CLI
```bash
# Confronta ultimi 2 run
python run.py -p my-chatbot --compare

# Confronta run specifici
python run.py -p my-chatbot --compare 15:16

# Mostra regressioni nell'ultima run
python run.py -p my-chatbot --regressions

# Regressioni in una run specifica
python run.py -p my-chatbot --regressions 16

# Test flaky su ultimi 10 run
python run.py -p my-chatbot --flaky

# Test flaky su ultimi 20 run
python run.py -p my-chatbot --flaky 20
```

### Menu Interattivo
Da `python run.py` > **[5] Analisi Testing**:
- **Confronta RUN** - A/B comparison tra due run
- **Rileva Regressioni** - Test PASS->FAIL
- **Test Flaky** - Risultati inconsistenti
- **Coverage** - Distribuzione test per categoria
- **Report Stabilita** - Overview qualita test suite

### Moduli (`src/comparison.py`)

```python
from src.comparison import (
    RunComparator, RegressionDetector,
    CoverageAnalyzer, FlakyTestDetector
)

# Confronto A/B
comparator = RunComparator(project)
result = comparator.compare(15, 16)  # RUN 15 vs 16
result = comparator.compare_latest() # Ultimi 2

# Regressioni
detector = RegressionDetector(project)
regressions = detector.check_for_regressions(16)
# TestChange(test_id, old_status, new_status, change_type)

# Test flaky
flaky = FlakyTestDetector(project)
flaky_tests = flaky.detect_flaky_tests(last_n_runs=10, threshold=0.3)
# FlakyTestReport(test_id, flaky_score, pass_count, fail_count)

# Coverage
coverage = CoverageAnalyzer(project)
report = coverage.analyze(tests)
# CoverageReport(total_tests, categories_covered, gaps)
```

### Concetti chiave

| Termine | Definizione |
|---------|-------------|
| **Regressione** | Test che passava e ora fallisce (PASS->FAIL) |
| **Miglioramento** | Test che falliva e ora passa (FAIL->PASS) |
| **Flaky Score** | 0 = stabile, 1 = risultati casuali |
| **Coverage Gap** | Categorie con pochi test |

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
