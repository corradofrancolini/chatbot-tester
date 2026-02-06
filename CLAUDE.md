# Chatbot Tester - Project Notes

**Mantra: If it can be done, it must be visible, explained, and configurable.**

---

## Quick Reference

| What | Command/Location |
|------|------------------|
| Run tests | `python run.py -p {project} -m auto --no-interactive` |
| Trigger from cloud | MCP tool `trigger_circleci` o CircleCI dashboard |
| Results | Google Sheets `chatbot-tester-results` |
| Traces | LangSmith (progetto configurato in `project.yaml`) |
| MCP Server | `fly.io/chatbot-tester-mcp` |

---

## Environment Variables - Secrets Management

**IMPORTANTE**: Tutte le API keys e credentials sono gestite tramite file `.env` locale. Mai committare secrets o hardcodarli nel codice.

### Variabili Disponibili

| Variabile | Servizio | Uso |
|-----------|----------|-----|
| `LANGSMITH_API_KEY` | LangSmith | Tracing e osservabilità |
| `ANTHROPIC_API_KEY` | Anthropic | Claude API per evaluation |
| `OPENAI_API_KEY` | OpenAI | GPT models (opzionale) |
| `GOOGLE_API_KEY` | Google API | Google Sheets integration |
| `CIRCLECI_TOKEN` | CircleCI | Trigger automatici da MCP |

### Setup Iniziale

```bash
# 1. Copia il template
cp config/.env.template config/.env

# 2. Modifica config/.env con le tue API keys reali
# NOTA: Non committare mai config/.env (è già in .gitignore)

# 3. Le variabili vengono caricate automaticamente da src/config_loader.py
python run.py -p silicon-b --health-check
```

### Aggiungere Nuove API Keys

1. Aggiungi la variabile a `config/.env.template`:
   ```bash
   NEW_SERVICE_KEY=your_new_service_key_here
   ```

2. Aggiungi la stessa variabile al tuo `config/.env` locale con il valore reale

3. Se serve per setup globale, aggiungi anche a `~/.env` (caricato da `~/.zshrc`)

### File e Sicurezza

| File | Status | Scopo |
|------|--------|-------|
| `config/.env.template` | ✅ Committabile | Template con placeholder, safe da condividere |
| `config/.env` | ❌ In .gitignore | Contiene API keys reali, mai committare |

### Verifica Setup

```bash
# Controlla che le variabili siano caricate
echo $ANTHROPIC_API_KEY

# Test con health check
python run.py -p silicon-b --health-check
```

### .env Globale vs Locale

| File | Scope | Caricato da |
|------|-------|-------------|
| `~/.env` | Globale per tutti i progetti | `~/.zshrc` all'avvio della shell |
| `config/.env` | Locale solo per chatbot-tester | `src/config_loader.py` all'avvio del tool |

**Best practice**: Usa `~/.env` per API keys condivise tra progetti, `config/.env` per keys specifiche del chatbot-tester.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         ENTRY POINTS                            │
├─────────────────────────────────────────────────────────────────┤
│  CLI (run.py)          MCP Server (fly.io)         CircleCI     │
│       │                      │                         │        │
│       └──────────────────────┴─────────────────────────┘        │
│                              │                                  │
│                              ▼                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    ORCHESTRATION                         │   │
│  │  tester.py — Orchestrator (Session & State Manager)      │   │
│  │  executor.py — Logic (Deep Module: Execute & Persist)    │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│         ┌────────────────────┼────────────────────┐            │
│         ▼                    ▼                    ▼            │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────┐    │
│  │  BROWSER    │    │  EVALUATION │    │  PERSISTENCE    │    │
│  │  browser.py │    │  ollama.py  │    │  sheets_client  │    │
│  │  Playwright │    │  langsmith  │    │  Google Sheets  │    │
│  └─────────────┘    └─────────────┘    └─────────────────┘    │
│         │                    │                    │            │
│         ▼                    ▼                    ▼            │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────┐    │
│  │  CHATBOT    │    │  LOCAL AI   │    │  CLOUD STORAGE  │    │
│  │  (target)   │    │  (Ollama)   │    │  (GSheets API)  │    │
│  └─────────────┘    └─────────────┘    └─────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **Input**: Test definitions (`tests.json`) + project config (`project.yaml`)
2. **Execution**: Browser automates chatbot interaction, captures responses
3. **Evaluation**: Ollama/LangSmith scores responses against expected answers
4. **Output**: Results written to Google Sheets, screenshots saved locally

### Key Boundaries

| Layer | Responsibility | Never Does |
|-------|----------------|------------|
| `run.py` | CLI parsing, menu, orchestration | Business logic |
| `tester.py` | Session orchestration, UI/CLI interactions | Deep test execution logic |
| `executor.py` | Core test logic, standalone persistence | Direct Terminal I/O or CLI menus |
| `browser.py` | Playwright automation | Evaluation logic |
| `sheets_client.py` | Google Sheets CRUD | Test logic |
| `ollama_client.py` | AI evaluation | Persistence |

---

## Decision Heuristics

Quando devi scegliere tra alternative, usa queste euristiche:

### 1. Visibilità > Magia
Preferisci codice esplicito a comportamenti impliciti. Se un'operazione ha side effects, deve essere ovvio dal nome o dai parametri.

```python
# ❌ Magico - cosa fa internamente?
process_test(test)

# ✅ Esplicito - chiaro cosa succede
result = execute_test(test)
save_result_to_sheets(result)
update_langsmith_trace(result)
```

### 2. Configurabile > Hardcoded
Ogni threshold, timeout, o comportamento variabile deve essere in `settings.yaml`, mai nel codice.

```python
# ❌ Hardcoded
MAX_RETRIES = 3
TIMEOUT = 30

# ✅ Configurabile
max_retries = config.get("health.max_retries", 3)
timeout = config.get("browser.timeout", 30)
```

### 3. Fail Fast > Fail Silent
Errori chiari con contesto, mai swallowed. L'utente deve sapere cosa è andato storto e perché.

```python
# ❌ Silent failure
try:
    result = risky_operation()
except Exception:
    return None

# ✅ Fail fast with context
try:
    result = risky_operation()
except SpecificError as e:
    logger.error(f"Operazione fallita per {test_id}: {e}")
    raise TestExecutionError(f"Impossibile completare {test_id}") from e
```

### 4. Idempotenza
I comandi devono essere safe da ri-eseguire. Se lancio lo stesso comando due volte, il risultato deve essere coerente.

```python
# ❌ Non idempotente - duplica righe
sheets.append_row(result)

# ✅ Idempotente - sovrascrive o salta
if sheets.row_exists(test_id):
    sheets.update_row(test_id, result)
else:
    sheets.append_row(result)
```

### 5. Composition > Inheritance
Preferisci funzioni componibili a gerarchie di classi. Più facile testare, più facile capire.

```python
# ❌ Inheritance profonda
class ParallelBrowserTester(BrowserTester):
    class ThreadSafeBrowserTester(ParallelBrowserTester):
        ...

# ✅ Composition
def run_parallel_tests(tester, pool, collector):
    for browser in pool:
        result = tester.execute(browser)
        collector.add(result)
```

### 6. Context Objects > Bloated Parameters
Se un componente ha più di 5 dipendenze, raggruppale in un context object. Mantiene i costruttori puliti e facilita l'estensione senza rompere le API.

```python
# ❌ Troppi parametri
def __init__(self, browser, settings, ollama, langsmith, training,
             evaluator, baselines, perf_collector, report, ...):

# ✅ Context object
def __init__(self, context: ExecutionContext):
    self.ctx = context
    self.browser = context.browser  # Alias per comodità
```

Vedi `src/models/execution.py` per l'implementazione di `ExecutionContext`.

---

## Anti-patterns (Don't)

### Mai fare

| Anti-pattern | Perché | Alternativa |
|--------------|--------|-------------|
| `print()` in produzione | Non loggato, non configurabile | `logger.info()` o `self.on_status()` |
| Credenziali hardcoded | Security risk | Environment variables |
| `time.sleep()` in async | Blocca event loop | `await asyncio.sleep()` |
| Catch generico `except Exception` | Nasconde bug | Catch specifico + re-raise |
| Modificare `run_config.json` durante esecuzione | Race conditions | Usa parametri CLI |
| Più pipeline `native-parallel` contemporanee | Scrivono sulla stessa RUN | Usa `multi_testset: true` |

### Smells da evitare

- **File > 500 righe**: Probabilmente fa troppe cose, splitta (post-refactoring siamo in linea)
- **Funzione > 50 righe**: Estrai sottofunzioni
- **Più di 5 parametri**: Usa `ExecutionContext` o dataclass
- **Import circolari**: Ripensa le dipendenze
- **Test che dipendono dall'ordine**: Ogni test deve essere indipendente
- **Stringhe per modalità**: Usa `TestMode` enum per type safety

---

## When to Extend vs. Modify

### Crea un NUOVO modulo quando:
- La funzionalità è ortogonale a quelle esistenti (es. nuovo canale notifiche)
- Può essere disabilitata senza impatto (es. nuovo export format)
- Ha dipendenze esterne proprie (es. nuovo servizio cloud)

### Estendi un modulo ESISTENTE quando:
- È una variante di comportamento esistente (es. nuovo tipo di test)
- Condivide infrastruttura (es. nuovo metodo in `sheets_client.py`)
- È strettamente accoppiato logicamente

### Crea una NUOVA classe quando:
- Ha stato interno che deve persistere
- Implementa un'interfaccia definita (es. `NotificationChannel`)
- Sarà istanziata più volte con config diverse

### Usa una FUNZIONE quando:
- È stateless (input → output)
- È una trasformazione di dati
- È un'utility riutilizzabile

---

## Key Files for Context

Prima di lavorare su una feature, leggi questi file per capire i pattern esistenti:

| Task | Leggi prima |
|------|-------------|
| Modificare logica esecuzione | `src/engine/executor.py` (metodi `execute_auto_test`, `persist`) |
| Gestire dipendenze e config | `src/models/execution.py` (`ExecutionContext`, `TestMode`) |
| Modificare schema report | `src/models/sheet_schema.py` (centralizzazione colonne) |
| Orchestrazione sessione | `src/tester.py` (session manager, train mode) |
| Aggiungere API esterna | `src/sheets_client.py` (pattern retry, auth, error handling) |
| Nuovo tool MCP | `mcp_server/server.py` (struttura tools, async patterns) |
| Modificare browser automation | `src/browser.py` (Playwright patterns, screenshots) |
| Aggiungere configurazione | `config/settings.yaml` + `src/config_loader.py` |
| Nuovo tipo di analisi | `src/comparison.py` (pattern per analisi cross-run) |
| Performance/metriche | `src/performance.py` (collector, reporter, alerter) |

---

## Projects Structure

I progetti testabili si trovano in `projects/`. Ogni progetto ha questa struttura:

```
projects/{project-name}/
├── project.yaml           # Config: URLs, credenziali, LangSmith
├── tests.json             # Test set standard (prefisso TEST_)
├── tests_paraphrase.json  # Parafrasi (prefisso PARA_) — opzionale
├── tests_ggp.json         # GGP (prefissi GRD_/GRL_/PRB_) — opzionale
└── run_config.json        # Stato runtime (active_run, env, flags)
```

### Test Set Types

| Tipo | Prefisso | Scopo |
|------|----------|-------|
| **Standard** | `TEST_` | Funzionalità base del chatbot |
| **Paraphrase** | `PARA_` | Robustezza a riformulazioni semantiche |
| **GGP** | `GRD_/GRL_/PRB_` | Grounding, Guardrail, Probing (limiti e sicurezza) |

### GGP Methodology

Test set per verificare limiti e sicurezza:

| Sezione | Verifica |
|---------|----------|
| **Grounding** | Non inventa dati (codici, prezzi, link non autorizzati) |
| **Guardrail** | Rispetta vincoli operativi definiti nel prompt |
| **Probing** | Resiste a manipolazioni (prompt injection, jailbreak) |

Valutazione GGP: manuale con ESITO (`PASS`/`FAIL`/`PARTIAL`) e RATIONALE obbligatorio.

---

## Documentation

| Guide | Content |
|-------|---------|
| [PRD.md](PRD.md) | Vision, priorities, constraints |
| [DECISIONS.md](DECISIONS.md) | Architectural decision log |
| [README.md](README.md) | Overview and quick start |
| [docs/CONFIGURATION.md](docs/CONFIGURATION.md) | Complete configuration guide |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Docker, GitHub Actions, PyPI |

---

## Main Commands

### Running tests
```bash
# New full run
python run.py -p my-chatbot -m auto --no-interactive --new-run

# Continue existing run (pending only)
python run.py -p my-chatbot -m auto --no-interactive

# Single test (overwrite)
python run.py -p my-chatbot -m auto --no-interactive -t TEST_050 --tests all

# Failed tests only
python run.py -p my-chatbot -m auto --no-interactive --tests failed
```

### Health Check
```bash
# Verify services before execution
python run.py --health-check -p my-chatbot

# Run tests skipping health check
python run.py -p my-chatbot -m auto --no-interactive --skip-health-check
```

---

## run_config.json Configuration

| Option | Description | Menu |
|--------|-------------|------|
| `env` | Environment: DEV, STAGING, PROD | Configure |
| `dry_run` | Simulate without executing | Toggle [1] |
| `use_langsmith` | Enable LangSmith tracing | Toggle [2] |
| `use_rag` | Enable RAG retrieval | Toggle [3] |
| `use_ollama` | Enable Ollama evaluation | Toggle [4] |
| `single_turn` | Initial question only | Toggle [5] |
| `active_run` | Run number on Google Sheets | Auto |

### Complete CLI Options

```bash
python run.py [OPTIONS]

# Project and mode
-p, --project       Project name
-m, --mode          train | assisted | auto
-t, --test          Single test ID
--tests             all | pending | failed
--new-run           Force new RUN

# Behavior
--no-interactive    No user prompts
--dry-run           Simulate
--headless          Hidden browser

# Services
--health-check      Verify services and exit
--skip-health-check Skip verification

# Debug
--debug             Detailed output
--lang              it | en
-v, --version       Show version

# Export
--export            pdf | excel | html | csv | all
--export-run        Run number to export

# Notifications
--notify            desktop | email | teams | all
--test-notify       Test notification configuration

# Performance
--perf-report       Show performance report
--perf-dashboard    Historical performance dashboard
--perf-compare      Compare two runs (e.g., 15:16)
--list-runs         List all runs from all projects
```

---

## Screenshots

Screenshots must capture the ENTIRE conversation with ALL products visible.

**Key file:** `src/browser.py` method `take_conversation_screenshot()`
- Uses CSS injection to hide input bar, footer, scroll indicators
- Expands containers to show all content
- Captures `section.llm__thread`

---

## Report Structure

```
reports/{project}/run_{N}/
├── report.html       # Interactive HTML report
├── screenshots/      # Conversation screenshots
│   ├── TEST_001.png
│   └── ...
└── performance/      # Performance metrics
    └── performance_run_{N}.json
```

---

## Main Modules

| Module | Description |
|--------|-------------|
| `run.py` | Entry point, CLI, interactive menu |
| `src/tester.py` | Main test engine |
| `src/browser.py` | Playwright automation |
| `src/health.py` | Health checks, circuit breaker, retry |
| `src/sheets_client.py` | Google Sheets integration |
| `src/langsmith_client.py` | LangSmith tracing |
| `src/ollama_client.py` | Local AI evaluation |
| `src/config_loader.py` | Configuration loading |
| `src/i18n.py` | IT/EN translations |
| `src/ui.py` | Console UI (Rich) |
| `src/finetuning.py` | Fine-tuning pipeline |
| `src/parallel.py` | Parallel execution, browser pool |
| `src/cache.py` | In-memory and disk caching |
| `src/comparison.py` | A/B comparison, regressions, flaky tests |
| `src/scheduler.py` | Scheduled runs, distributed execution |
| `src/notifications.py` | Email, Desktop, Teams notifications |
| `src/export.py` | Export PDF, Excel, HTML, CSV |
| `src/github_actions.py` | GitHub Actions integration |
| `src/performance.py` | Performance metrics collection |
| `wizard/main.py` | New project wizard |

---

## Parallel Execution (v1.2.0)

### CLI
```bash
# 3 browsers in parallel
python run.py -p my-chatbot -m auto --parallel --no-interactive

# 5 browsers
python run.py -p my-chatbot -m auto --parallel --workers 5 --no-interactive
```

### How it works
1. `BrowserPool` creates N isolated Chromium browsers
2. Tests are distributed to workers
3. Each worker accumulates results in `ThreadSafeSheetsClient`
4. At the end, `flush()` writes everything in batch to Google Sheets

### Developer API
```python
from src.sheets_client import ThreadSafeSheetsClient, ParallelResultsCollector

# Thread-safe wrapper for Sheets
safe_client = ThreadSafeSheetsClient(sheets_client)
safe_client.queue_result(result)    # Thread-safe
safe_client.queue_screenshot(path, test_id)
safe_client.flush()                 # Write batch

# Or: in-memory collector
collector = ParallelResultsCollector()
collector.add(result)
all_results = collector.get_all()
```

### Configuration (settings.yaml)
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

## Testing Analysis (v1.2.0)

### CLI
```bash
# Compare last 2 runs
python run.py -p my-chatbot --compare

# Compare specific runs
python run.py -p my-chatbot --compare 15:16

# Show regressions in last run
python run.py -p my-chatbot --regressions

# Regressions in specific run
python run.py -p my-chatbot --regressions 16

# Flaky tests over last 10 runs
python run.py -p my-chatbot --flaky

# Flaky tests over last 20 runs
python run.py -p my-chatbot --flaky 20
```

### Interactive Menu
From `python run.py` > **[5] Testing Analysis**:
- **Compare RUN** - A/B comparison between two runs
- **Detect Regressions** - PASS->FAIL tests
- **Flaky Tests** - Inconsistent results
- **Coverage** - Test distribution by category
- **Stability Report** - Test suite quality overview
- **Performance** - Metrics and trends

### Modules (`src/comparison.py`)

```python
from src.comparison import (
    RunComparator, RegressionDetector,
    CoverageAnalyzer, FlakyTestDetector
)

# A/B comparison
comparator = RunComparator(project)
result = comparator.compare(15, 16)  # RUN 15 vs 16
result = comparator.compare_latest() # Last 2

# Regressions
detector = RegressionDetector(project)
regressions = detector.check_for_regressions(16)
# TestChange(test_id, old_status, new_status, change_type)

# Flaky tests
flaky = FlakyTestDetector(project)
flaky_tests = flaky.analyze(last_n_runs=10)

# Coverage
coverage = CoverageAnalyzer(project)
gaps = coverage.find_gaps()
```

---

## MCP Server

Il server MCP (`mcp_server/server.py`) espone i tool per Claude Desktop.

**URL:** `https://chatbot-tester-mcp.fly.dev`
**Versione:** 1.4.0

### Tool Disponibili (30 totali)

#### Discovery & Help

| Tool | Funzione | Esempio |
|------|----------|---------|
| `get_help` | Guida interattiva | "Come funziona?", "Aiuto" |
| `list_projects` | Mostra progetti | "Quali progetti?", "Lista progetti" |
| `suggest_project` | Suggerisce progetto da testare | "Cosa dovrei testare?" |
| `list_test_sets` | Mostra test set disponibili | "Quali test set ha silicon-b?" |
| `list_tests` | Mostra test con filtro | "Mostra i test", "Quanti test ci sono?" |
| `list_runs` | Elenca RUN su Sheets | "Quali RUN esistono?" |
| `novita` | Mostra changelog versioni | "Novità?", "Cosa c'è di nuovo?" |

#### Execution & Control

| Tool | Funzione | Esempio |
|------|----------|---------|
| `trigger_circleci` | Avvia pipeline CircleCI | "Lancia i test", "Esegui silicon-b" |
| `start_test_session` | Avvia sessione guidata | "Inizia sessione test" |
| `prepare_test_run` | Riepilogo pre-esecuzione | "Prepara run per silicon-b" |
| `execute_test_run` | Esegue dopo conferma | "Esegui la run preparata" |
| `add_test` | Aggiunge nuovo test | "Aggiungi un test" |

#### Pipeline Status

| Tool | Funzione | Esempio |
|------|----------|---------|
| `get_pipeline_status` | Stato pipeline recenti | "Stato pipeline?" |
| `get_workflow_status` | Dettaglio workflow | "Dettaglio workflow X" |
| `check_pipeline_status` | Controlla pipeline in corso | "La pipeline sta ancora girando?" |

#### Results & Analysis

| Tool | Funzione | Esempio |
|------|----------|---------|
| `get_run_results` | Risultati da Sheets | "Come è andata?", "Risultati run 38" |
| `show_results` | Visualizza formattato | "Mostra risultati run 45" |
| `get_failed_tests` | Test falliti | "Quali sono falliti?", "Errori?" |
| `compare_runs` | Confronta due RUN | "Confronta 37 con 38" |
| `get_regressions` | Regressioni PASS→FAIL | "Cosa si è rotto?" |
| `detect_flaky_tests` | Test instabili | "Test flaky", "Instabili?" |

#### Analytics & Diagnostics (v1.4.0)

| Tool | Funzione | Esempio |
|------|----------|---------|
| `get_performance_report` | Report performance | "Performance run 45?" |
| `get_performance_alerts` | Alert su soglie | "Ci sono alert?" |
| `analyze_coverage` | Copertura per categoria | "Copertura test silicon-b" |
| `get_stability_report` | Stabilità suite | "Quanto è stabile la suite?" |
| `diagnose_prompt` | Diagnosi errori | "Perché TEST_001 fallisce?" |
| `calibrate_thresholds` | Suggerisce soglie | "Calibra le soglie" |
| `export_report` | Export Excel/HTML/CSV | "Esporta run 45 in Excel" |
| `debug_trace` | Analisi trace LangSmith | "Analizza trace abc-123" |

#### Utilities

| Tool | Funzione | Esempio |
|------|----------|---------|
| `notify_corrado` | Invia messaggio Telegram | "Avvisa Corrado che..." |

### Configurazione Claude Desktop

File: `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "chatbot-tester": {
      "url": "https://chatbot-tester-mcp.fly.dev/sse",
      "headers": {
        "Authorization": "Bearer <API_KEY>"
      }
    }
  }
}
```

### Aggiungere un Tool

1. Aggiungi `Tool()` nella lista in `list_tools()` in `mcp_server/tools.py`
2. Aggiungi handler in `handle_tool()`
3. Deploy: `cd mcp_server && fly deploy`
4. Riavvia Claude Desktop

---

## CircleCI (Cloud Execution)

### Workflows

| Workflow | Trigger | Uso |
|----------|---------|-----|
| `manual-test` | `manual_trigger=true` | Singolo test set |
| `native-parallel-test` | `native_parallelism>0` | Test distribuiti su N container |
| `multi-testset` | `multi_testset=true` | 3 test set in parallelo (standard, paraphrase, GGP) |

### Parametri Pipeline

```yaml
parameters:
  project: "my-chatbot"
  mode: "auto"              # auto | assisted | train
  tests: "pending"          # all | pending | failed
  new_run: false            # Crea nuova RUN su Sheets
  test_limit: 0             # 0 = tutti
  test_ids: ""              # "TEST_001,TEST_002"
  single_turn: false        # Solo domanda iniziale
  tests_file: "tests.json"  # File test set
  native_parallelism: 3     # Container paralleli (0 = disabilitato)
  multi_testset: false      # Esegui tutti e 3 i test set
```

### Race Condition Warning

**NON lanciare più pipeline `native-parallel-test` contemporaneamente!**
I container 1+ cercano la RUN "più recente" e scrivono tutti sullo stesso foglio.

Usa invece `multi_testset: true` per eseguire più test set in sicurezza.

---

## Debug & Troubleshooting

### LangSmith Trace Analysis

```bash
# CLI (installato)
langsmith-fetch trace <TRACE_ID>
langsmith-fetch trace <ID> | claude -p "analizza errori"

# Da Claude Desktop
"Analizza il trace abc-123-def-456"
```

### Google Sheets Cleanup

```bash
# Rimuovi righe con prefisso sbagliato
python scripts/cleanup_run.py -p my-chatbot -r 38 --keep-prefix TEST_

# Rimuovi duplicati (tiene prima occorrenza)
python scripts/deduplicate_run.py -p my-chatbot -r 38

# Dry run (mostra senza modificare)
python scripts/cleanup_run.py -p my-chatbot -r 38 --dry-run
```

### Errori Comuni

| Errore | Causa | Soluzione |
|--------|-------|-----------|
| `429 Too Many Requests` | Rate limit LangSmith/Sheets | Retry automatico con backoff |
| `Trace non trovato` | ID errato o progetto sbagliato | Verifica URL completo in Sheets |
| `RUN non trovata` | Foglio non esiste | Controlla numero run in Sheets |
| `BASELINE column not found` | Template Sheets vecchio | Aggiungi colonna BASELINE |

### Log Levels

```bash
# Debug dettagliato
python run.py -p my-chatbot -m auto --debug

# Solo errori
LOG_LEVEL=ERROR python run.py ...
```

---

## Code Conventions

### Python Style

- **Python 3.11+** richiesto
- **Type hints** su tutte le funzioni pubbliche
- **Docstrings** in italiano (progetto interno)
- **f-strings** per formatting
- **Niente print()** in produzione - usa `logger` o `self.on_status()`

### Naming

| Tipo | Convenzione | Esempio |
|------|-------------|---------|
| Classi | PascalCase | `GoogleSheetsClient` |
| Funzioni | snake_case | `get_run_results()` |
| Costanti | UPPER_SNAKE | `MAX_RETRIES` |
| File | snake_case | `sheets_client.py` |

### Error Handling

```python
# Pattern standard
try:
    result = risky_operation()
except SpecificError as e:
    logger.error(f"Operazione fallita: {e}")
    return None  # o raise con contesto
```

### Async

- MCP tools sono tutti `async def`
- Usa `await` per I/O (API calls, file)
- Non bloccare con `time.sleep()` - usa `asyncio.sleep()`

### Decision Log

Aggiorna [DECISIONS.md](DECISIONS.md) quando fai scelte architetturali significative:
- Nuovi pattern o refactoring
- Scelta tra alternative (con motivazione)
- Decisioni "ON HOLD" con rationale

---

## TODO / Backlog

### Priority: HIGH 🔴

| Task | Rationale | Effort |
|------|-----------|--------|
| Complete i18n integration | UX consistency across languages | Medium |
| Add retry logic to MCP tools | Resilience against transient failures | Low |

### Priority: MEDIUM 🟡

| Task | Rationale | Effort |
|------|-----------|--------|
| Dashboard web per risultati | Alternativa a Google Sheets | High |
| Slack integration | Notifiche team più ampie | Medium |
| Test coverage report | Capire gap nella suite | Medium |

### Priority: LOW 🟢

| Task | Rationale | Effort |
|------|-----------|--------|
| Dark mode per HTML reports | Nice to have | Low |
| Export to Notion | Integrazione documentazione | Medium |

### Completed ✅

- [x] Improved progress bar: ETA, tests/minute, phase indicator (v1.7.0)
- [x] Remote notifications: GitHub Actions workflows with Email/Teams (v1.7.0)
- [x] Parallel execution: Multi-browser via --parallel --workers N (v1.7.0)

---

## Settings Menu (v1.2.0)

From main menu: **[7] Settings**

### Available submenus

| Item | Description |
|------|-------------|
| **Language** | Switch IT/EN |
| **Notifications** | Configure Desktop, Email, Teams + Triggers |
| **Browser** | Headless, viewport, slow_mo |
| **Logging** | Log level (DEBUG/INFO/WARNING/ERROR) |
| **Test Notifications** | Send test notification |

### Notifications - Submenu

```
[1] Desktop: ON/OFF     — macOS native notifications
[2] Email: ON/OFF       — SMTP notifications
[3] Teams: ON/OFF       — Microsoft Teams notifications
[4] Triggers            — When to send notifications
```

### Notification Triggers

```
[1] On Complete: ON/OFF  — Every completed run
[2] On Failure: ON/OFF   — Failures only
[3] On Regression: ON/OFF — If regressions detected
[4] On Flaky: ON/OFF     — If flaky tests detected
```

Changes are saved directly to `config/settings.yaml`.

---

## Performance Metrics (v1.6.0)

Performance metrics system for monitoring test execution.

### CLI

```bash
# Performance report for last run
python run.py -p my-chatbot --perf-report

# Report for specific run
python run.py -p my-chatbot --perf-report 18

# Historical dashboard (last N runs trend)
python run.py -p my-chatbot --perf-dashboard
python run.py -p my-chatbot --perf-dashboard 20  # last 20 runs

# Compare two runs (e.g., local vs cloud)
python run.py -p my-chatbot --perf-compare 15:16

# Export report
python run.py -p my-chatbot --perf-export json
python run.py -p my-chatbot --perf-export html  # opens in browser

# List all runs from all projects
python run.py --list-runs
```

### Interactive Menu

From `python run.py` > **[5] Testing Analysis** > **[6] Performance**:
- **Last run report** - Detailed metrics
- **Historical dashboard** - Trends over last N runs
- **Compare runs** - A/B comparison
- **Export HTML** - Interactive browser report

### Collected Metrics

| Category | Metrics |
|----------|---------|
| **Timing** | Total duration, average per test, min/max, per-phase breakdown |
| **Throughput** | Tests/minute, comparison with previous runs |
| **Reliability** | Retries, timeouts, error rate, flakiness |
| **External Services** | Chatbot latency, Google Sheets, LangSmith |

### Post-Run Report

At the end of each AUTO mode run, automatically generated:
1. **Text summary** - Main metrics recap
2. **Alerting** - Warnings if metrics out of threshold
3. **JSON file** - Complete data in `reports/{project}/performance/`

### Alerting

Configurable thresholds for automatic warnings:

| Threshold | Default |
|-----------|---------|
| Duration increase | >20% vs baseline |
| Throughput decrease | >15% |
| Error rate | >10% |
| Pass rate | <80% |
| Chatbot latency | >30s |
| Sheets latency | >5s |

### API

```python
from src.performance import (
    PerformanceCollector, PerformanceReporter, PerformanceHistory,
    PerformanceAlerter, compare_environments, format_comparison_report
)

# Metrics collection (automatic in tester.py)
collector = PerformanceCollector("run_18", "my-chatbot", "local")
collector.start_test("TEST_001")
collector.start_phase("send_question")
# ... execution ...
collector.end_phase()
collector.record_service_call("chatbot", "response", 1500.0)
collector.end_test("PASS")
run_metrics = collector.finalize()

# Report
reporter = PerformanceReporter(run_metrics)
print(reporter.generate_summary())
html = reporter.generate_html_report()

# History and trends
history = PerformanceHistory("my-chatbot", Path("reports"))
history.save_run(run_metrics)
trends = history.get_trends(last_n=10)

# Alerting
alerter = PerformanceAlerter()
alerts = alerter.check(run_metrics)
print(alerter.format_alerts())

# Local vs cloud comparison
comparison = compare_environments(local_metrics, cloud_metrics)
print(format_comparison_report(comparison))
```
