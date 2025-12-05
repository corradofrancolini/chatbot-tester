# Guida Completa alla Configurazione

Questa guida documenta **tutte** le opzioni di configurazione disponibili in Chatbot Tester.

**Mantra: Se si puo fare, deve essere visibile, spiegato, e configurabile.**

---

## Indice

1. [Opzioni CLI](#1-opzioni-cli)
2. [File di Configurazione](#2-file-di-configurazione)
   - [settings.yaml](#settingsyaml-configurazione-globale)
   - [project.yaml](#projectyaml-configurazione-progetto)
   - [run_config.json](#run_configjson-stato-run)
3. [Toggle Runtime](#3-toggle-runtime)
4. [Variabili d'Ambiente](#4-variabili-dambiente)

---

## 1. Opzioni CLI

Tutte le opzioni disponibili via `python run.py [OPZIONI]`:

### Selezione Progetto

| Opzione | Descrizione | Esempio |
|---------|-------------|---------|
| `-p, --project` | Nome del progetto | `-p my-chatbot` |
| `--new-project` | Avvia wizard nuovo progetto | `--new-project` |

### Modalita di Test

| Opzione | Descrizione | Valori |
|---------|-------------|--------|
| `-m, --mode` | Modalita di esecuzione | `train`, `assisted`, `auto` |
| `-t, --test` | Esegui singolo test | `-t TEST_001` |
| `--tests` | Quali test eseguire | `all`, `pending` (default), `failed` |
| `--new-run` | Forza nuova RUN | flag |

### Comportamento Browser

| Opzione | Descrizione | Default |
|---------|-------------|---------|
| `--headless` | Browser invisibile | `false` |
| `--no-interactive` | Senza prompt utente | `false` |
| `--dry-run` | Simula senza eseguire | `false` |

### Servizi e Debug

| Opzione | Descrizione | Note |
|---------|-------------|------|
| `--health-check` | Verifica servizi e esci | Esce con codice 0/1 |
| `--skip-health-check` | Salta verifica iniziale | Velocizza avvio |
| `--debug` | Output debug dettagliato | Per troubleshooting |

### Esecuzione Parallela

| Opzione | Descrizione | Default |
|---------|-------------|---------|
| `--parallel` | Esegui test in parallelo | `false` |
| `--workers` | Numero browser paralleli | `3` (max: 5) |

**Come funziona:**
- Ogni worker ha un browser Chromium isolato
- I risultati vengono accumulati in memoria
- Alla fine vengono scritti in batch su Google Sheets
- Thread-safe: nessun rischio di sovrascrittura

**Quando usarlo:**
- Suite di test grandi (50+ test)
- CI/CD dove il tempo e critico
- Hardware con RAM sufficiente (ogni browser ~200MB)

### Analisi Testing

| Opzione | Descrizione | Esempio |
|---------|-------------|---------|
| `--compare` | Confronta run | `--compare 15:16` o `--compare` |
| `--regressions` | Mostra regressioni | `--regressions 16` o `--regressions` |
| `--flaky` | Test flaky | `--flaky 20` (default: 10 run) |

### Lingua e Versione

| Opzione | Descrizione | Default |
|---------|-------------|---------|
| `--lang` | Lingua interfaccia | `it` |
| `-v, --version` | Mostra versione | - |
| `--help` | Mostra aiuto | - |

### Esempi Completi

```bash
# Test automatici con nuovo run, headless
python run.py -p my-chatbot -m auto --no-interactive --new-run --headless

# Debug di un singolo test
python run.py -p my-chatbot -m auto -t TEST_001 --debug

# Health check veloce
python run.py --health-check -p my-chatbot

# Interfaccia in inglese
python run.py --lang en

# Esecuzione parallela con 4 worker
python run.py -p my-chatbot -m auto --parallel --workers 4 --no-interactive

# Confronta ultimi 2 run
python run.py -p my-chatbot --compare

# Regressioni nella run 16
python run.py -p my-chatbot --regressions 16

# Test flaky su 20 run
python run.py -p my-chatbot --flaky 20
```

---

## 2. File di Configurazione

### settings.yaml (Configurazione Globale)

**Percorso:** `config/settings.yaml`

Queste impostazioni si applicano a **tutti** i progetti.

```yaml
# =============================================================================
# CHATBOT TESTER - Settings Globali
# =============================================================================

app:
  version: "1.1.0"
  language: "it"              # Lingua default: it | en

# -----------------------------------------------------------------------------
# Browser
# -----------------------------------------------------------------------------
browser:
  headless: false             # true = browser nascosto
  slow_mo: 0                  # ms di pausa tra azioni (utile per debug)
  viewport:
    width: 1280               # Larghezza finestra
    height: 720               # Altezza finestra
  device_scale_factor: 2      # 2 = retina display (screenshot HD)

# -----------------------------------------------------------------------------
# Test
# -----------------------------------------------------------------------------
test:
  max_turns: 15               # Max turni per conversazione
  screenshot_on_complete: true
  default_wait_after_send: 1000  # ms attesa dopo invio messaggio

# -----------------------------------------------------------------------------
# Report
# -----------------------------------------------------------------------------
reports:
  local:
    enabled: true
    formats:
      - html                  # Report HTML interattivo
      - csv                   # Esportazione dati
    keep_last_n: 50           # Mantieni ultimi N run (0 = tutti)

# -----------------------------------------------------------------------------
# UI Terminal
# -----------------------------------------------------------------------------
ui:
  colors: true                # Colori nel terminale
  progress_bar: true          # Mostra barra progresso
  clear_screen: true          # Pulisce schermo tra step

# -----------------------------------------------------------------------------
# Esecuzione Parallela
# -----------------------------------------------------------------------------
parallel:
  enabled: false            # true = abilita esecuzione parallela
  max_workers: 3            # Numero browser in parallelo (1-5)
  retry_strategy: "exponential"  # none | linear | exponential
  max_retries: 2            # Tentativi per test fallito
  base_delay_ms: 1000       # Delay base tra retry
  rate_limit_per_minute: 60 # Limite richieste al chatbot

# -----------------------------------------------------------------------------
# Cache
# -----------------------------------------------------------------------------
cache:
  enabled: true             # Abilita caching risposte
  memory:
    max_entries: 1000       # Max entry in memoria
    default_ttl_seconds: 300  # TTL default (5 minuti)
  langsmith:
    trace_ttl_seconds: 300  # Cache trace (5 minuti)
    report_ttl_seconds: 600 # Cache report (10 minuti)

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
logging:
  level: "INFO"               # DEBUG | INFO | WARNING | ERROR
  file: "chatbot-tester.log"
  max_size_mb: 10
  backup_count: 3
```

#### Opzioni Dettagliate

| Sezione | Opzione | Descrizione | Impatto |
|---------|---------|-------------|---------|
| `browser.headless` | Browser visibile/nascosto | `true` per CI/cloud, `false` per debug |
| `browser.slow_mo` | Rallenta azioni browser | Utile per vedere cosa succede |
| `browser.device_scale_factor` | Qualita screenshot | `2` = retina, `1` = normale |
| `test.max_turns` | Limite conversazione | Evita loop infiniti |
| `test.screenshot_on_complete` | Cattura automatica | Ogni test salva screenshot |
| `test.default_wait_after_send` | Pausa dopo invio | Aumentare se chatbot e lento |
| `reports.keep_last_n` | Pulizia automatica | `0` = mantieni tutto |
| `ui.colors` | Output colorato | `false` per pipe/log |
| `parallel.enabled` | Esecuzione parallela | `true` per test veloci |
| `parallel.max_workers` | Browser simultanei | 1-5, piu worker = piu RAM |
| `parallel.retry_strategy` | Strategia retry | `exponential` per API lente |
| `cache.enabled` | Caching risposte | Riduce chiamate LangSmith |
| `cache.memory.max_entries` | Limite cache | Bilanciare RAM vs hit rate |
| `logging.level` | Verbosita log | `DEBUG` per troubleshooting |

---

### project.yaml (Configurazione Progetto)

**Percorso:** `projects/<nome>/project.yaml`

Configurazione specifica per ogni chatbot.

```yaml
project:
  name: my-chatbot
  description: Descrizione del chatbot
  created: '2024-12-01'
  language: it                # Lingua principale test

# -----------------------------------------------------------------------------
# Chatbot Target
# -----------------------------------------------------------------------------
chatbot:
  url: https://example.com/chatbot

  # Selettori CSS per elementi UI
  selectors:
    textarea: '#chat-input'           # Campo input messaggio
    submit_button: 'button.send'      # Bottone invio
    bot_messages: '.message.bot'      # Messaggi del bot
    thread_container: '.chat-thread'  # Container conversazione
    loading_indicator: '.typing'      # Indicatore "sta scrivendo"

  # CSS extra per screenshot (nasconde elementi)
  screenshot_css: |
    .unwanted-element { display: none !important; }

  # Timeout in millisecondi
  timeouts:
    page_load: 30000          # Attesa caricamento pagina
    bot_response: 60000       # Attesa risposta bot

# -----------------------------------------------------------------------------
# Test Defaults
# -----------------------------------------------------------------------------
test_defaults:
  email: test@example.com     # Email per test che richiedono auth
  countries:                  # Valori predefiniti per campi select
    - Italy
    - Germany
  confirmations:
    - 'yes'
    - 'no'

# -----------------------------------------------------------------------------
# Google Sheets (opzionale)
# -----------------------------------------------------------------------------
google_sheets:
  enabled: true
  spreadsheet_id: '1abc...'   # ID dallo URL del foglio
  drive_folder_id: '1xyz...'  # ID cartella per screenshot

# -----------------------------------------------------------------------------
# LangSmith (opzionale)
# -----------------------------------------------------------------------------
langsmith:
  enabled: true
  api_key_env: LANGSMITH_API_KEY  # Nome variabile ambiente
  project_id: 'uuid-...'          # ID progetto LangSmith
  org_id: ''                      # Org ID (vuoto = default)
  tool_names: []                  # Tool da tracciare (vuoto = auto)

# -----------------------------------------------------------------------------
# Ollama LLM (opzionale)
# -----------------------------------------------------------------------------
ollama:
  enabled: true
  model: llama3.2:3b              # Modello per valutazione
  url: http://localhost:11434/api/generate
```

#### Selettori CSS - Come Trovarli

1. Apri il chatbot nel browser
2. Premi `F12` per DevTools
3. Usa il selettore elementi (icona freccia)
4. Clicca sull'elemento desiderato
5. Copia il selettore CSS dall'HTML

**Esempi comuni:**
```yaml
# Per ID
textarea: '#message-input'

# Per classe
bot_messages: '.chat-message.assistant'

# Per attributo
submit_button: 'button[type="submit"]'

# Combinato
thread_container: 'div.chat-container > .messages'
```

#### Screenshot CSS - Personalizzazione

Il campo `screenshot_css` inietta CSS prima di catturare lo screenshot:

```yaml
screenshot_css: |
  /* Nascondi footer */
  footer { display: none !important; }

  /* Nascondi barra input */
  .input-bar { display: none !important; }

  /* Espandi container */
  .chat-container {
    max-height: none !important;
    overflow: visible !important;
  }

  /* Nascondi scrollbar */
  ::-webkit-scrollbar { display: none !important; }
```

---

### run_config.json (Stato Run)

**Percorso:** `projects/<nome>/run_config.json`

Stato della sessione di test corrente. Modificabile anche da menu interattivo.

```json
{
  "env": "DEV",
  "prompt_version": "v2.1",
  "model_version": "gpt-4o",
  "active_run": 15,
  "run_start": "2025-12-05T10:00:00",
  "tests_completed": 25,
  "mode": "auto",
  "last_test_id": "TEST_025",
  "dry_run": false,
  "use_langsmith": true,
  "use_rag": false,
  "use_ollama": true,
  "single_turn": false
}
```

#### Opzioni Run

| Opzione | Tipo | Descrizione | Dove Configurare |
|---------|------|-------------|------------------|
| `env` | string | Ambiente: DEV, STAGING, PROD | Menu > Configura |
| `prompt_version` | string | Versione prompt del chatbot | Menu > Configura |
| `model_version` | string | Versione modello LLM chatbot | Auto da LangSmith |
| `active_run` | number | Numero run su Google Sheets | Auto |
| `dry_run` | bool | Simula senza eseguire | Menu > Toggle |
| `use_langsmith` | bool | Abilita tracing LangSmith | Menu > Toggle |
| `use_rag` | bool | Abilita recupero RAG | Menu > Toggle |
| `use_ollama` | bool | Abilita valutazione Ollama | Menu > Toggle |
| `single_turn` | bool | Solo domanda iniziale | Menu > Toggle |

#### Single Turn Mode

Quando `single_turn: true`:
- Esegue **solo** la domanda iniziale di ogni test
- **Non** genera followup con Ollama
- Utile per test rapidi o quando Ollama non e disponibile

---

## 3. Toggle Runtime

Accessibili dal menu interattivo: **Progetto > Toggle Opzioni**

| Toggle | Effetto ON | Effetto OFF |
|--------|------------|-------------|
| **Dry Run** | Simula test senza eseguire | Esecuzione reale |
| **LangSmith** | Recupera traces e sources | Skip LangSmith |
| **RAG** | Abilita ricerca RAG | Disabilita RAG |
| **Ollama** | Valutazione automatica AI | Valutazione manuale |
| **Single Turn** | Solo domanda iniziale | Conversazione completa |

### Da CLI

```bash
# Dry run
python run.py -p my-chatbot -m auto --dry-run

# Senza Ollama (imposta in run_config.json)
# Modifica: "use_ollama": false
python run.py -p my-chatbot -m auto --no-interactive
```

---

## 4. Variabili d'Ambiente

**Percorso:** `config/.env` (non versionato)

```bash
# LangSmith
LANGSMITH_API_KEY=lsv2_sk_...

# Google (opzionale, se non usi file credenziali)
GOOGLE_APPLICATION_CREDENTIALS=/path/to/credentials.json

# OpenAI (per fine-tuning)
OPENAI_API_KEY=sk-...
```

### Priorita Configurazione

1. **CLI** (massima priorita)
2. **Variabili ambiente**
3. **run_config.json**
4. **project.yaml**
5. **settings.yaml** (minima priorita)

---

## Troubleshooting

### Browser non si apre

```bash
# Installa browser
playwright install chromium

# Verifica
playwright --version
```

### Selettori non funzionano

1. Apri browser con `--debug`:
   ```bash
   python run.py -p mio-progetto --debug
   ```
2. Verifica selettori in DevTools
3. Aggiorna `project.yaml`

### Screenshot vuoti

Verifica `screenshot_css` non nasconda elementi necessari.

### Timeout troppo frequenti

Aumenta timeout in `project.yaml`:
```yaml
chatbot:
  timeouts:
    page_load: 60000    # 60 secondi
    bot_response: 120000 # 2 minuti
```

---

## Riferimento Rapido

### File Principali

| File | Scope | Modifica |
|------|-------|----------|
| `config/settings.yaml` | Globale | Manuale |
| `projects/<nome>/project.yaml` | Progetto | Wizard o manuale |
| `projects/<nome>/run_config.json` | Sessione | Menu o manuale |
| `config/.env` | Credenziali | Manuale |

### Comandi Utili

```bash
# Visualizza configurazione
cat projects/my-chatbot/project.yaml
cat projects/my-chatbot/run_config.json

# Reset run
rm projects/my-chatbot/run_config.json

# Reset sessione browser
rm -rf projects/my-chatbot/browser-data/
```
