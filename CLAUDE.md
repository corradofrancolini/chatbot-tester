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

# Export
--export            pdf | excel | html | csv | all
--export-run        Numero run da esportare

# Notifiche
--notify            desktop | email | teams | all
--test-notify       Testa configurazione notifiche
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
| `src/scheduler.py` | Scheduled runs, esecuzione distribuita |
| `src/notifications.py` | Notifiche Email, Desktop, Teams |
| `src/export.py` | Export PDF, Excel, HTML, CSV |
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

## Automazione (v1.2.0)

### Scheduled Runs (Locale)

```bash
# Aggiungi schedule giornaliero
python run.py --add-schedule my-chatbot:daily

# Aggiungi schedule settimanale
python run.py --add-schedule my-chatbot:weekly

# Lista schedule configurati
python run.py --list-schedules

# Avvia scheduler locale (cron-like, Ctrl+C per fermare)
python run.py --scheduler
```

### Scheduled Runs (GitHub Actions)

Il workflow `.github/workflows/scheduled-tests.yml` esegue automaticamente:
- **Daily** (6:00 UTC): Test pending su tutti i progetti
- **Weekly** (Lun 2:00 UTC): Full run con nuovo RUN

```yaml
# Per abilitare, i secrets richiesti sono:
# - LANGSMITH_API_KEY
# - GOOGLE_CREDENTIALS_JSON
# - SLACK_WEBHOOK_URL (opzionale, per notifiche)
```

### API Scheduler

```python
from src.scheduler import LocalScheduler, ScheduleConfig, ScheduleType

scheduler = LocalScheduler()

# Aggiungi schedule personalizzato
scheduler.add_schedule(ScheduleConfig(
    name="my-schedule",
    project="my-chatbot",
    schedule_type=ScheduleType.DAILY,  # DAILY, WEEKLY, HOURLY, INTERVAL
    mode="auto",
    tests="pending",
    cron_hour=6,
    cron_minute=0
))

# Avvia (blocca il processo)
scheduler.start()

# Oppure in background
scheduler.start_background()
```

### Esecuzione Distribuita

```python
from src.scheduler import DistributedCoordinator, WorkerConfig

coordinator = DistributedCoordinator()

# Registra worker
coordinator.register_worker(WorkerConfig(
    worker_id="worker-1",
    host="192.168.1.10",
    port=5000,
    projects=["my-chatbot"]
))

# Distribuisci test
distribution = coordinator.distribute_tests(tests, project="my-chatbot")
# {"worker-1": [test1, test3], "worker-2": [test2, test4]}
```

---

## Export Report (v1.2.0)

### CLI

```bash
# Export PDF ultimo run
python run.py -p my-chatbot --export pdf

# Export Excel di una run specifica
python run.py -p my-chatbot --export excel --export-run 15

# Export tutti i formati
python run.py -p my-chatbot --export all

# Formati disponibili: pdf, excel, html, csv, all
```

### Dipendenze opzionali

```bash
# Per PDF
pip install reportlab pillow

# Per Excel
pip install openpyxl
```

### Output

I file esportati vengono salvati in:
```
reports/{project}/run_{N}/exports/
├── project_runN.pdf
├── project_runN.xlsx
├── project_runN.html
└── project_runN.csv
```

### API

```python
from src.export import RunReport, ReportExporter

# Carica report
report = RunReport.from_local_report(Path("reports/my-chatbot/run_15/report.json"))

# Export
exporter = ReportExporter(report)
exporter.to_pdf(Path("output.pdf"))
exporter.to_excel(Path("output.xlsx"))
exporter.to_html(Path("output.html"))
exporter.to_csv(Path("output.csv"))

# Export multiplo
results = exporter.export_all(Path("exports/"))
```

---

## Notifiche (v1.2.0)

### CLI

```bash
# Test configurazione notifiche
python run.py --test-notify

# Invia notifica desktop (ultimo run)
python run.py -p my-chatbot --notify desktop

# Invia email
python run.py -p my-chatbot --notify email

# Invia a Teams
python run.py -p my-chatbot --notify teams

# Invia su tutti i canali configurati
python run.py -p my-chatbot --notify all
```

### Configurazione (settings.yaml)

```yaml
notifications:
  email:
    enabled: true
    smtp_host: "smtp.gmail.com"
    smtp_port: 587
    smtp_user: "your@email.com"
    smtp_password_env: "SMTP_PASSWORD"  # export SMTP_PASSWORD=xxx
    recipients:
      - "team@example.com"

  desktop:
    enabled: true
    sound: true

  teams:
    enabled: true
    webhook_url_env: "TEAMS_WEBHOOK_URL"  # export TEAMS_WEBHOOK_URL=https://...

  triggers:
    on_complete: false    # Ogni run completato
    on_failure: true      # Solo fallimenti
    on_regression: true   # Regressioni rilevate
```

### Teams Webhook

Per configurare Teams:
1. Vai nel canale Teams > Connettori > Incoming Webhook
2. Crea webhook e copia URL
3. `export TEAMS_WEBHOOK_URL="https://..."`

### API

```python
from src.notifications import NotificationManager, NotificationConfig, TestRunSummary

# Config
config = NotificationConfig(
    desktop_enabled=True,
    email_enabled=True,
    teams_enabled=True
)

manager = NotificationManager(config)

# Summary risultati
summary = TestRunSummary(
    project="my-chatbot",
    run_number=15,
    total_tests=50,
    passed=45,
    failed=5,
    pass_rate=90.0
)

# Notifica su tutti i canali
manager.notify_run_complete(summary)

# Notifica singolo canale
manager.send_desktop("Titolo", "Messaggio")
manager.send_email("Subject", "Body")
manager.send_teams("Titolo", "Messaggio")
```

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

---

## TODO / Backlog

### UX
- [ ] **Progress bar migliorata**: ETA stimato, velocita test/minuto, indicatore dettagliato
- [ ] **Dashboard web locale**: Server Flask, vista real-time, storico run con grafici

### Automazione
- [ ] **Notifiche remote**: Aggiungere notifiche (Email/Teams) al workflow GitHub Actions usando secrets
- [ ] **Esecuzione parallela**: Implementare multi-browser (config in settings.yaml esiste)

### Internazionalizzazione
- [ ] **i18n completo**: Integrare src/i18n.py in tutti i moduli

---

## Menu Settings (v1.2.0)

Dal menu principale: **[6] Impostazioni**

### Sottomenu disponibili

| Voce | Descrizione |
|------|-------------|
| **Lingua** | Cambia IT/EN |
| **Notifiche** | Configura Desktop, Email, Teams + Trigger |
| **Browser** | Headless, viewport, slow_mo |
| **Logging** | Livello log (DEBUG/INFO/WARNING/ERROR) |
| **Test Notifiche** | Invia notifica di test |

### Notifiche - Sottomenu

```
[1] Desktop: ON/OFF     — Notifiche macOS native
[2] Email: ON/OFF       — Notifiche via SMTP
[3] Teams: ON/OFF       — Notifiche Microsoft Teams
[4] Trigger             — Quando inviare notifiche
```

### Trigger Notifiche

```
[1] On Complete: ON/OFF  — Ogni run completato
[2] On Failure: ON/OFF   — Solo se fallimenti
[3] On Regression: ON/OFF — Se rilevate regressioni
[4] On Flaky: ON/OFF     — Se test flaky rilevati
```

Le modifiche vengono salvate direttamente in `config/settings.yaml`.

---

## Performance Metrics (v1.6.0)

Sistema di metriche di performance per monitorare l'esecuzione dei test.

### CLI

```bash
# Report performance ultimo run
python run.py -p my-chatbot --perf-report

# Report di un run specifico
python run.py -p my-chatbot --perf-report 18

# Dashboard storica (trend ultimi N run)
python run.py -p my-chatbot --perf-dashboard
python run.py -p my-chatbot --perf-dashboard 20  # ultimi 20 run

# Confronta due run (es. local vs cloud)
python run.py -p my-chatbot --perf-compare 15:16

# Esporta report
python run.py -p my-chatbot --perf-export json
python run.py -p my-chatbot --perf-export html  # apre nel browser
```

### Menu Interattivo

Da `python run.py` > **[5] Analisi Testing** > **[6] Performance**:
- **Report ultimo run** - Metriche dettagliate
- **Dashboard storica** - Trend su ultimi N run
- **Confronta run** - A/B comparison
- **Esporta HTML** - Report interattivo nel browser

### Metriche Raccolte

| Categoria | Metriche |
|-----------|----------|
| **Timing** | Durata totale, media per test, min/max, breakdown per fase |
| **Throughput** | Test/minuto, confronto con run precedenti |
| **Affidabilità** | Retry, timeout, error rate, flakiness |
| **Servizi Esterni** | Latenza chatbot, Google Sheets, LangSmith |

### Report Post-Run

Al termine di ogni run in modalità AUTO, viene generato automaticamente:
1. **Summary testuale** - Riepilogo metriche principali
2. **Alerting** - Warning se metriche fuori soglia
3. **File JSON** - Dati completi in `reports/{project}/performance/`

### Alerting

Soglie configurabili per warning automatici:

| Soglia | Default |
|--------|---------|
| Aumento durata | >20% vs baseline |
| Calo throughput | >15% |
| Error rate | >10% |
| Pass rate | <80% |
| Latenza chatbot | >30s |
| Latenza Sheets | >5s |

### API

```python
from src.performance import (
    PerformanceCollector, PerformanceReporter, PerformanceHistory,
    PerformanceAlerter, compare_environments, format_comparison_report
)

# Raccolta metriche (automatica in tester.py)
collector = PerformanceCollector("run_18", "my-chatbot", "local")
collector.start_test("TEST_001")
collector.start_phase("send_question")
# ... esecuzione ...
collector.end_phase()
collector.record_service_call("chatbot", "response", 1500.0)
collector.end_test("PASS")
run_metrics = collector.finalize()

# Report
reporter = PerformanceReporter(run_metrics)
print(reporter.generate_summary())
html = reporter.generate_html_report()

# Storico e trend
history = PerformanceHistory("my-chatbot", Path("reports"))
history.save_run(run_metrics)
trends = history.get_trends(last_n=10)

# Alerting
alerter = PerformanceAlerter()
alerts = alerter.check(run_metrics)
print(alerter.format_alerts())

# Confronto local vs cloud
comparison = compare_environments(local_metrics, cloud_metrics)
print(format_comparison_report(comparison))
```
