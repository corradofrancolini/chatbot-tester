# 🤖 Chatbot Tester

> Tool automatizzato per testare chatbot web con supporto multi-progetto, AI locale e reporting avanzato.

[![macOS](https://img.shields.io/badge/macOS-12.0+-blue.svg)](https://www.apple.com/macos/)
[![Python](https://img.shields.io/badge/Python-3.10+-green.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## ✨ Caratteristiche

- **Multi-progetto**: Testa diversi chatbot dalla stessa installazione
- **3 Modalità**: Train, Assisted, Auto per ogni fase del testing
- **AI Locale**: Ollama + Mistral per analisi privacy-first
- **Report Flessibili**: HTML locale + Google Sheets opzionale
- **Wizard Interattivo**: Setup guidato passo-passo
- **LangSmith Integration**: Debug avanzato delle risposte chatbot
- **Bilingue**: Italiano e Inglese

---

## 🚀 Quick Start

### 1. Installazione

#### Opzione A: Da archivio (consigliato per distribuzione interna)

```bash
# Estrai l'archivio
tar xzf chatbot-tester-v1.0.0.tar.gz
cd chatbot-tester

# Esegui l'installazione
./install.sh
```

#### Opzione B: Da Git repository

```bash
# Clona il repository
git clone https://github.com/your-org/chatbot-tester.git
cd chatbot-tester

# Esegui l'installazione
./install.sh
```

L'installer verificherà automaticamente:
- macOS 12.0+
- Python 3.10+
- Homebrew (opzionale ma consigliato)

### 2. Crea il tuo primo progetto

```bash
./chatbot-tester --new-project
```

Il wizard ti guiderà attraverso:
1. Nome progetto
2. URL del chatbot
3. Rilevamento selettori CSS (automatico)
4. Configurazione report (opzionale)
5. Import test cases

### 3. Avvia i test

```bash
# Modalità Train (apprendimento)
./chatbot-tester --project=mio-chatbot --mode=train

# Modalità Auto (regressione)
./chatbot-tester --project=mio-chatbot --mode=auto
```

---

## 📖 Modalità di Test

| Modalità | Descrizione | Quando usarla |
|----------|-------------|---------------|
| **Train** | Esegui test manualmente, il tool impara | Prima configurazione, nuovi scenari |
| **Assisted** | AI suggerisce, tu confermi | Validazione, correzioni |
| **Auto** | Completamente automatico | Regression testing, CI/CD |

### Flusso consigliato

```
Train (10-20 test) → Assisted (validazione) → Auto (regression)
```

---

## 📁 Struttura Progetto

```
chatbot-tester/
├── chatbot-tester          # Script di avvio
├── install.sh              # Installazione
├── update.sh               # Aggiornamento
├── uninstall.sh            # Disinstallazione
├── run.py                  # Entry point Python
│
├── config/
│   ├── .env                # Credenziali (gitignored)
│   ├── .env.example        # Template credenziali
│   └── settings.yaml       # Settings globali
│
├── projects/               # I tuoi progetti
│   └── <nome-progetto>/
│       ├── project.yaml    # Configurazione
│       ├── tests.json      # Test cases
│       ├── training_data.json
│       └── browser-data/   # Sessione browser
│
├── reports/                # Report locali
│   └── <nome-progetto>/
│       └── run_001/
│           ├── report.html
│           ├── report.csv
│           └── screenshots/
│
├── src/                    # Codice sorgente
├── adapters/               # Rilevamento selettori
├── wizard/                 # Setup guidato
├── templates/              # Template file
├── locales/                # Traduzioni IT/EN
└── docs/                   # Documentazione
```

---

## ⚙️ Configurazione

### File di progetto (`projects/<nome>/project.yaml`)

```yaml
project:
  name: "mio-chatbot"
  description: "Chatbot assistenza clienti"

chatbot:
  url: "https://chat.example.com"
  selectors:
    textarea: "#chat-input"
    submit_button: "button.send"
    bot_messages: ".message.assistant"

google_sheets:
  enabled: false
  spreadsheet_id: ""

langsmith:
  enabled: false
  project_id: ""

ollama:
  enabled: true
  model: "mistral"
```

### Variabili d'ambiente (`config/.env`)

```bash
# LangSmith (opzionale)
LANGSMITH_API_KEY=lsv2_sk_xxxxx

# Google OAuth (opzionale)
GOOGLE_OAUTH_CREDENTIALS=./config/oauth_credentials.json
```

---

## 🧪 Test Cases

### Formato JSON

```json
[
  {
    "id": "TC001",
    "question": "Come posso resettare la password?",
    "category": "account",
    "expected_topics": ["password", "reset", "email"],
    "followups": [
      {
        "condition": "contains:email",
        "question": "Non ho accesso alla mia email"
      }
    ]
  }
]
```

### Import da file

Il wizard supporta import da:
- **JSON**: Formato nativo
- **CSV**: Colonne `id`, `question`, `category`, `expected_topics`
- **Excel**: Stesso formato CSV

---

## 📊 Report

### Report Locale (sempre attivo)

Generato in `reports/<progetto>/run_<N>/`:
- `report.html` - Report interattivo navigabile
- `report.csv` - Export per analisi
- `summary.json` - Metadati run
- `screenshots/` - Screenshot per ogni test

### Google Sheets (opzionale)

Colonne nel report:
| Colonna | Descrizione |
|---------|-------------|
| TEST ID | Identificativo test |
| DATE | Data/ora UTC |
| MODE | Train/Assisted/Auto |
| QUESTION | Domanda inviata |
| CONVERSATION | Storico multi-turn |
| SCREENSHOT | Link Google Drive |
| ESITO | ✅ Pass / ❌ Fail / ⚠️ Warning |
| NOTES | Note automatiche o manuali |

---

## 🔧 Comandi CLI

```bash
# Wizard nuovo progetto
./chatbot-tester --new-project

# Avvia con progetto specifico
./chatbot-tester --project=nome

# Specifica modalità
./chatbot-tester --project=nome --mode=train|assisted|auto

# Esegui singolo test
./chatbot-tester --project=nome --test=TC001

# Dry run (no esecuzione reale)
./chatbot-tester --project=nome --dry-run

# Lingua inglese
./chatbot-tester --lang=en

# Mostra aiuto
./chatbot-tester --help
```

---

## 🔌 Integrazioni

### Ollama (AI Locale)

```bash
# Installa Ollama (se non presente)
brew install ollama

# Avvia servizio
ollama serve

# Scarica modello Mistral
ollama pull mistral
```

### LangSmith (Debug Avanzato)

1. Crea account su [smith.langchain.com](https://smith.langchain.com)
2. Genera API Key in Settings
3. Configura nel wizard o in `project.yaml`

### Google Sheets

1. Crea progetto su [Google Cloud Console](https://console.cloud.google.com)
2. Abilita Google Sheets API e Google Drive API
3. Crea credenziali OAuth 2.0
4. Scarica JSON e configura nel wizard

---

## 📚 Documentazione

- [Guida Setup Dettagliata](docs/SETUP.md)
- [Creare Nuovo Progetto](docs/NEW_PROJECT.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)

---

## 🆘 Supporto

### Problemi comuni

**Il browser non si apre**
```bash
# Reinstalla Playwright
source .venv/bin/activate
playwright install chromium
```

**Errore "Module not found"**
```bash
# Reinstalla dipendenze
source .venv/bin/activate
pip install -r requirements.txt
```

**Sessione scaduta**
```bash
# Elimina dati browser e rifai login
rm -rf projects/<nome>/browser-data/
./chatbot-tester --project=<nome>
```

---

## 📄 Licenza

MIT License - vedi [LICENSE](LICENSE) per dettagli.

---

## 🤝 Contribuire

1. Fork del repository
2. Crea branch feature (`git checkout -b feature/nuova-funzione`)
3. Commit (`git commit -m 'Aggiunge nuova funzione'`)
4. Push (`git push origin feature/nuova-funzione`)
5. Apri Pull Request

---

<p align="center">
  Made with ❤️ for QA teams
</p>
