# Chatbot Tester - Backlog

Versione attuale: **v1.2.0** (2025-12-05)

---

## Da fare

### Prossimi step

- [ ] Testing: A/B comparison tra versioni chatbot
- [ ] UX: Dashboard web per visualizzazione risultati
- [ ] Automation: Scheduled runs con cron

---

## Idee future

- [ ] Notifiche Slack/Teams per risultati
- [ ] Export report in PDF
- [ ] Comparazione storica performance

---

## Completati

### v1.2.0 (2025-12-05)
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
