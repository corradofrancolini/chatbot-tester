# Chatbot Tester - Backlog

Versione attuale: **v1.5.0** (2025-12-06)

---

## Da fare

### Prossimi step

- [ ] UX: Dashboard web per visualizzazione risultati
- [ ] Auto-diagnosi dopo run fallita
- [ ] Integrazione diagnosi con --analyze

---

## Idee future

- [ ] Notifiche Slack (oltre a Teams)
- [ ] Notifiche remote in GitHub Actions
- [ ] LLM-powered hypothesis verification
- [ ] Custom knowledge base per progetto

---

## Completati

### v1.5.0 (2025-12-06)
- [x] **Diagnostic Engine** (`src/diagnostic.py`)
  - Classificazione intelligente dei fallimenti (7 tipi)
  - Generazione ipotesi basata su knowledge base
  - Verifica automatica con pattern matching
  - Suggerimento fix model-specific (generic, openai, claude, gemini)
  - Modalita interattiva con conferma ipotesi
  - CLI: `--diagnose`, `--diagnose-test`, `--diagnose-run`, `--diagnose-interactive`
- [x] **Knowledge Base** (`knowledge/failure_patterns.yaml`)
  - Failure patterns da OpenAI, Claude, Gemini, IBM best practices
  - Verification strategies automatizzate
  - Fix templates per modello
  - Symptom mapping per lookup rapido
- [x] **Prompt Versioning Enhanced** (`src/prompt_manager.py`)
  - Schema `v{NNN}_{tag}` (es. `v003_fix-priority`)
  - Tracciabilita: parent_version, source, test_run
  - Conferma interattiva prima del salvataggio
  - Metodi get_by_tag(), get_by_version_id(), get_version_chain()

### v1.4.0 (2025-12-06)
- [x] **Visualizer** (`src/visualizer.py`)
  - Prompt Visualizer: flowchart regole + mindmap capabilities
  - Test Visualizer: waterfall trace + timeline + confronto
  - CLI: `--viz-prompt`, `--viz-test`, `--viz-output html|terminal`
  - Output HTML interattivo con tabs
  - Output terminale ASCII colorato
- [x] **Smoke Tests** aggiornati (23 test)

### v1.3.0 (2025-12-06)
- [x] **Prompt Manager** (`src/prompt_manager.py`)
  - Versioning automatico dei prompt
  - CLI: `--prompt-list`, `--prompt-show`, `--prompt-import`, `--prompt-export`
  - Diff tra versioni: `--prompt-diff 1:2`
  - Storage in `projects/{project}/prompts/` con metadata.json
- [x] **Debug Package Analyzer** (`src/analyzer.py`)
  - Generazione debug package da test falliti
  - CLI: `--analyze`, `--provider`, `--analyze-run`
  - Provider manual (clipboard), Claude API, Groq API
  - Stima costi prima dell'analisi
  - Suggerimenti per fix prompt
- [x] **Smoke Tests** aggiornati (22 test)

### v1.2.1 (2025-12-06)
- [x] **Test Suite Automatizzata** (`tests/`)
  - Smoke tests (20 test, ~2 sec)
  - Unit tests export
  - Integration tests
  - End-to-end tests con dry-run
  - Pre-commit hook per smoke tests
- [x] **CLI UX Improvements** (clig.dev compliant)
  - "Did you mean" suggerimenti per progetti/comandi errati
  - Feedback immediato (<100ms) con versione
  - Next steps dopo operazioni (export, test run)
  - Exit codes significativi (sysexits.h compatibili)
  - TTY detection per auto-disable colori
  - Supporto NO_COLOR environment variable
  - Flag `-q`/`--quiet`, `--no-color`, `--json`
  - Help organizzato in gruppi tematici

### v1.2.0 (2025-12-05)
- [x] **A/B Comparison** (`src/comparison.py`)
  - CLI: `--compare latest` o `--compare 15:16`
  - Menu Analisi con confronto, regressioni, trend, flaky, coverage
- [x] **Esecuzione Parallela** (`src/parallel.py`)
  - BrowserPool con worker riutilizzabili
  - ParallelTestRunner per esecuzione concorrente
  - CLI flags: `--parallel`, `--workers N`
- [x] **Smart Retry** con backoff esponenziale
  - Strategia configurabile: none, linear, exponential
  - Max retries e delay configurabili
- [x] **Cache Module** (`src/cache.py`)
  - MemoryCache con TTL e LRU eviction
  - DiskCache per persistenza
  - LangSmithCache specializzato
- [x] **Performance Metrics** (MetricsCollector)
  - Timing dettagliato per ogni fase
  - Export CSV per analisi
- [x] **Rate Limiting** per evitare sovraccarico
- [x] **Cloud Execution** via GitHub Actions menu
- [x] **Scheduled Runs** (`src/scheduler.py`)
  - LocalScheduler per esecuzione programmata
  - ScheduleConfig configurabile
- [x] **Export PDF** (`src/export.py`)
  - PDFExporter per report in PDF
- [x] **Notifiche Teams** (`src/notifications.py`)
  - TeamsNotifier con webhook
- [x] **Comparazione Run** (`src/comparison.py`)
  - RunComparator per confronto storico
  - RegressionDetector per rilevare regressioni
- [x] **Documentazione** aggiornata (CONFIGURATION.md)

### v1.1.0 (2025-12-04)
- [x] **LangSmith Report avanzato**
  - Sources/fonti consultate con preview contenuto
  - Waterfall tree completo (tutti gli step con timing)
  - Query estratta dal trace
  - First Token Time (TTFT)
  - Token breakdown (input/output)
  - Model version auto-extract
- [x] **Fine-tuning pipeline** (`src/finetuning.py`)
- [x] **Training module** (`src/training.py`)
- [x] **Ollama toggle** - on/off dinamico
- [x] **UI migliorata** (`src/ui.py`)
  - Selezione test interattiva
  - Menu quit/back
  - WizardUI class

### v1.0.1 (2025-12-02)
- [x] Setup Git privato
- [x] Initial commit con struttura base

### v1.0.0 (2025-12-02)
- [x] Release iniziale
- [x] Core tester (Train/Assisted/Auto modes)
- [x] Google Sheets integration
- [x] Playwright browser automation
- [x] Wizard setup progetti
