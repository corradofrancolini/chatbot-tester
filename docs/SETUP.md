# 📦 Guida Setup Dettagliata

Questa guida ti accompagna passo-passo nell'installazione e configurazione di Chatbot Tester.

---

## 📋 Indice

1. [Prerequisiti](#prerequisiti)
2. [Installazione](#installazione)
3. [Configurazione Base](#configurazione-base)
4. [Configurazione Google Sheets](#configurazione-google-sheets)
5. [Configurazione LangSmith](#configurazione-langsmith)
6. [Configurazione Ollama](#configurazione-ollama)
7. [Verifica Installazione](#verifica-installazione)

---

## Prerequisiti

### Sistema Operativo

| Requisito | Minimo | Consigliato |
|-----------|--------|-------------|
| macOS | 12.0 (Monterey) | 14.0+ (Sonoma) |
| Spazio disco | 500 MB | 2 GB |
| RAM | 4 GB | 8 GB+ |

### Software Necessario

#### Python 3.10+

Verifica la versione installata:
```bash
python3 --version
```

Se non presente o versione inferiore:
```bash
# Installa via Homebrew
brew install python@3.12
```

#### Homebrew

Verifica installazione:
```bash
brew --version
```

Se non presente:
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

#### Git

Verifica installazione:
```bash
git --version
```

Se non presente:
```bash
brew install git
```

---

## Installazione

### 1. Scarica il progetto

```bash
# Clona il repository
git clone https://github.com/your-org/chatbot-tester.git

# Entra nella cartella
cd chatbot-tester
```

### 2. Esegui l'installer

```bash
./install.sh
```

L'installer eseguirà automaticamente:

1. ✅ Verifica sistema operativo (macOS 12.0+)
2. ✅ Verifica Homebrew
3. ✅ Verifica Python 3.10+
4. ✅ Verifica Git
5. ✅ Verifica spazio disco (500 MB)
6. ✅ Crea virtual environment Python
7. ✅ Installa dipendenze Python
8. ✅ Installa Playwright + Chromium
9. ✅ Crea struttura cartelle
10. ✅ Crea script di avvio

### 3. Verifica installazione

```bash
./chatbot-tester --help
```

Dovresti vedere l'help del tool.

---

## Configurazione Base

### Settings Globali

Il file `config/settings.yaml` contiene le impostazioni globali:

```yaml
app:
  version: "1.0.0"
  language: "it"  # it | en

browser:
  headless: false      # true per esecuzione senza GUI
  viewport:
    width: 1280
    height: 720
  device_scale_factor: 2  # Per screenshot retina

test:
  max_turns: 15              # Max turni conversazione
  screenshot_on_complete: true

reports:
  local:
    enabled: true
    format: ["html", "csv"]

ui:
  colors: true
  progress_bar: true
```

### Personalizzazioni comuni

#### Esecuzione headless (senza browser visibile)

```yaml
browser:
  headless: true
```

#### Lingua inglese di default

```yaml
app:
  language: "en"
```

#### Timeout più lunghi

Modifica in `project.yaml` del progetto:
```yaml
chatbot:
  timeouts:
    page_load: 60000     # 60 secondi
    bot_response: 120000 # 2 minuti
```

---

## Configurazione Google Sheets

> ⚠️ **Opzionale**: Se non configuri Google Sheets, i report saranno solo locali.

### 1. Crea progetto Google Cloud

1. Vai su [Google Cloud Console](https://console.cloud.google.com)
2. Crea un nuovo progetto o selezionane uno esistente
3. Annota il **Project ID**

### 2. Abilita le API

1. Vai su **API e servizi** → **Libreria**
2. Cerca e abilita:
   - **Google Sheets API**
   - **Google Drive API**

### 3. Crea credenziali OAuth

1. Vai su **API e servizi** → **Credenziali**
2. Clicca **Crea credenziali** → **ID client OAuth**
3. Seleziona **Applicazione desktop**
4. Dai un nome (es. "Chatbot Tester")
5. Clicca **Crea**
6. Scarica il file JSON

### 4. Configura le credenziali

```bash
# Copia il file scaricato
cp ~/Downloads/client_secret_*.json config/oauth_credentials.json
```

### 5. Crea lo Spreadsheet

1. Vai su [Google Sheets](https://sheets.google.com)
2. Crea un nuovo foglio
3. Copia l'ID dall'URL: `https://docs.google.com/spreadsheets/d/QUESTO_È_L_ID/edit`

### 6. Crea cartella Drive per screenshot

1. Vai su [Google Drive](https://drive.google.com)
2. Crea una nuova cartella (es. "Chatbot Tests Screenshots")
3. Copia l'ID dall'URL: `https://drive.google.com/drive/folders/QUESTO_È_L_ID`

### 7. Prima autorizzazione

La prima volta che usi Google Sheets, si aprirà il browser per autorizzare l'accesso. Segui le istruzioni a schermo.

---

## Configurazione LangSmith

> ⚠️ **Opzionale**: LangSmith fornisce debug avanzato delle risposte del chatbot.

### 1. Crea account

1. Vai su [smith.langchain.com](https://smith.langchain.com)
2. Crea un account o accedi

### 2. Genera API Key

1. Vai su **Settings** → **API Keys**
2. Clicca **Create API Key**
3. Copia la chiave (inizia con `lsv2_sk_`)

### 3. Trova Project ID e Org ID

1. **Project ID**: Vai su Projects, clicca sul progetto, l'ID è nell'URL
2. **Org ID**: Vai su Settings → Organization, l'ID è visibile

### 4. Configura

Aggiungi al file `config/.env`:

```bash
LANGSMITH_API_KEY=lsv2_sk_xxxxxxxxxxxxx
```

E nel `project.yaml` del progetto:

```yaml
langsmith:
  enabled: true
  project_id: "your-project-id"
  org_id: "your-org-id"
  tool_names:
    - "retrieval_tool"
    - "calculator"
```

### 5. Auto-detect tool names

Il wizard può rilevare automaticamente i tool names dalle trace LangSmith. Durante la configurazione, esegui un test manuale sul chatbot e il wizard analizzerà la trace per estrarre i nomi dei tool.

---

## Configurazione Ollama

> ⚠️ **Opzionale per Train mode, richiesto per Assisted/Auto**.

### 1. Installa Ollama

```bash
brew install ollama
```

### 2. Avvia il servizio

```bash
ollama serve
```

> 💡 Lascia questo terminale aperto o configura Ollama come servizio di sistema.

### 3. Scarica il modello Mistral

```bash
ollama pull mistral
```

Questo scaricherà ~4GB di dati.

### 4. Verifica funzionamento

```bash
ollama run mistral "Ciao, funzioni?"
```

### 5. Configurazione nel progetto

Nel `project.yaml`:

```yaml
ollama:
  enabled: true
  model: "mistral"
  url: "http://localhost:11434/api/generate"
```

### Modelli alternativi

| Modello | RAM | Velocità | Qualità |
|---------|-----|----------|---------|
| mistral | 4GB | ⭐⭐⭐ | ⭐⭐⭐ |
| llama2 | 4GB | ⭐⭐⭐ | ⭐⭐ |
| mixtral | 8GB | ⭐⭐ | ⭐⭐⭐⭐ |
| codellama | 4GB | ⭐⭐⭐ | ⭐⭐ (per codice) |

---

## Verifica Installazione

### Test completo

```bash
# 1. Verifica CLI
./chatbot-tester --help

# 2. Verifica moduli Python
source .venv/bin/activate
python -c "from src import tester, browser, config_loader; print('✅ Moduli OK')"

# 3. Verifica Playwright
python -c "from playwright.sync_api import sync_playwright; print('✅ Playwright OK')"

# 4. Verifica Ollama (se configurato)
curl -s http://localhost:11434/api/tags | python -c "import sys,json; print('✅ Ollama OK' if json.load(sys.stdin) else '❌')"

# 5. Dry run
./chatbot-tester --project=my-chatbot --dry-run
```

### Checklist finale

- [ ] `./chatbot-tester --help` funziona
- [ ] Virtual environment attivo (`.venv/`)
- [ ] Chromium installato (`.venv/lib/...`)
- [ ] `config/.env` configurato (se usi servizi esterni)
- [ ] Almeno un progetto in `projects/`

---

## Prossimi passi

✅ **Setup completato!**

Ora puoi:
1. [Creare un nuovo progetto](NEW_PROJECT.md)
2. Configurare i test cases
3. Iniziare con la modalità Train

---

## Problemi?

Consulta la [Guida Troubleshooting](TROUBLESHOOTING.md) o apri una issue su GitHub.
