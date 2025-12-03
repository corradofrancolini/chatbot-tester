# 🆕 Creare un Nuovo Progetto

Questa guida ti mostra come configurare un nuovo progetto di test per un chatbot.

---

## 📋 Indice

1. [Wizard Interattivo](#wizard-interattivo)
2. [Configurazione Manuale](#configurazione-manuale)
3. [Rilevamento Selettori](#rilevamento-selettori)
4. [Import Test Cases](#import-test-cases)
5. [Primo Test](#primo-test)

---

## Wizard Interattivo

Il modo più semplice per creare un progetto è usare il wizard:

```bash
./chatbot-tester --new-project
```

### Step del wizard

#### Step 1: Verifica Prerequisiti
Il wizard verifica che tutto sia installato correttamente.

#### Step 2: Informazioni Progetto
```
Nome progetto: mio-chatbot
Descrizione: Chatbot assistenza clienti Example Corp
```

> 💡 Il nome deve contenere solo lettere minuscole, numeri e trattini.

#### Step 3: URL Chatbot
```
URL: https://chat.example.com/assistant
```

Il wizard:
1. Verifica che l'URL sia raggiungibile
2. Apre il browser per il login (se necessario)
3. Salva la sessione per usi futuri

#### Step 4: Rilevamento Selettori

**Auto-detect** (consigliato):
Il wizard cerca automaticamente i selettori CSS comuni.

**Click-to-learn** (fallback):
Se l'auto-detect fallisce, il wizard ti chiede di cliccare:
1. La textarea dove scrivi i messaggi
2. Il bottone di invio
3. Un messaggio del bot

#### Step 5: Google Sheets (opzionale)
```
[1] Solo report locali (HTML/CSV)
[2] Configura Google Sheets
[3] Configuro dopo
```

#### Step 6: LangSmith (opzionale)
```
[1] Non uso LangSmith
[2] Configura LangSmith
[3] Configuro dopo
```

#### Step 7: Ollama (opzionale)
```
[1] Installa Ollama + Mistral
[2] Già installato
[3] Solo modalità Train (skip)
```

#### Step 8: Test Cases
```
[1] Importa da file (JSON/CSV/Excel)
[2] Crea manualmente
[3] Inizio senza test
```

#### Step 9: Riepilogo
Conferma della configurazione e salvataggio.

---

## Configurazione Manuale

Se preferisci configurare manualmente:

### 1. Crea la cartella del progetto

```bash
mkdir -p projects/mio-chatbot
```

### 2. Crea project.yaml

```bash
cat > projects/mio-chatbot/project.yaml << 'EOF'
# Configurazione Progetto Chatbot Tester

project:
  name: "mio-chatbot"
  description: "Chatbot assistenza clienti"
  created: "2025-12-02"
  language: "it"

chatbot:
  url: "https://chat.example.com/assistant"
  
  selectors:
    textarea: "#chat-input"
    submit_button: "button.send-btn"
    bot_messages: ".message.assistant"
    thread_container: ".chat-thread"  # opzionale
  
  # CSS da iniettare per screenshot puliti
  screenshot_css: |
    .header, .footer { display: none !important; }
  
  timeouts:
    page_load: 30000
    bot_response: 60000

# Dati default per i test
test_defaults:
  email: "test@example.com"
  countries: ["Italy", "Germany", "France"]

# Google Sheets (opzionale)
google_sheets:
  enabled: false
  spreadsheet_id: ""
  drive_folder_id: ""

# LangSmith (opzionale)
langsmith:
  enabled: false
  project_id: ""
  org_id: ""
  tool_names: []

# Ollama (opzionale)
ollama:
  enabled: true
  model: "mistral"
  url: "http://localhost:11434/api/generate"
EOF
```

### 3. Crea tests.json

```bash
cat > projects/mio-chatbot/tests.json << 'EOF'
[
  {
    "id": "TC001",
    "question": "Come posso resettare la password?",
    "category": "account",
    "expected_topics": ["password", "reset", "email"]
  },
  {
    "id": "TC002", 
    "question": "Quali sono gli orari di apertura?",
    "category": "info",
    "expected_topics": ["orari", "apertura"]
  }
]
EOF
```

### 4. Crea training_data.json (vuoto)

```bash
echo "[]" > projects/mio-chatbot/training_data.json
```

---

## Rilevamento Selettori

### Selettori comuni già supportati

Il tool cerca automaticamente questi pattern:

**Textarea (input messaggi)**:
```css
#llm-prompt-textarea
[data-testid='chat-input']
textarea[placeholder*='message' i]
textarea[placeholder*='scrivi' i]
.chat-input textarea
```

**Bottone invio**:
```css
button.llm__prompt-submit
button[type='submit']
button[aria-label*='send' i]
button[aria-label*='invia' i]
.send-button
```

**Messaggi bot**:
```css
.llm__message--assistant .llm__text-body
[data-role='assistant']
.message.assistant
.bot-message
.ai-response
```

### Trovare selettori manualmente

Se i selettori automatici non funzionano:

1. Apri il chatbot nel browser
2. Premi `F12` per aprire DevTools
3. Clicca l'icona selettore (↖️) in alto a sinistra
4. Clicca sull'elemento desiderato
5. Nel pannello Elements, tasto destro → Copy → Copy selector

### Click-to-learn

Se usi la modalità click-to-learn:

1. Il tool apre il browser
2. L'elemento da cliccare viene evidenziato in giallo
3. Clicca sull'elemento richiesto
4. Il tool estrae automaticamente il selettore
5. Conferma o modifica manualmente

---

## Import Test Cases

### Da JSON

Formato nativo, supporta tutte le funzionalità:

```json
[
  {
    "id": "TC001",
    "question": "Domanda principale",
    "category": "categoria",
    "expected_topics": ["topic1", "topic2"],
    "followups": [
      {
        "condition": "contains:parola",
        "question": "Domanda followup"
      }
    ]
  }
]
```

### Da CSV

```csv
id,question,category,expected_topics
TC001,"Come resetto la password?",account,"password,reset,email"
TC002,"Orari apertura?",info,"orari,apertura"
```

### Da Excel

Stesso formato del CSV, prima riga come intestazioni.

### Condizioni followup

| Condizione | Esempio | Descrizione |
|------------|---------|-------------|
| `contains:X` | `contains:email` | La risposta contiene "email" |
| `not_contains:X` | `not_contains:errore` | La risposta NON contiene "errore" |
| `length_gt:N` | `length_gt:100` | Risposta più lunga di N caratteri |
| `length_lt:N` | `length_lt:50` | Risposta più corta di N caratteri |
| `always` | `always` | Esegui sempre |

---

## Primo Test

### 1. Avvia in modalità Train

```bash
./chatbot-tester --project=mio-chatbot --mode=train
```

### 2. Esegui un test singolo

```bash
./chatbot-tester --project=mio-chatbot --mode=train --test=TC001
```

### 3. Cosa succede in Train mode

1. Il browser si apre sulla pagina del chatbot
2. La domanda viene inviata automaticamente
3. Attendi la risposta del bot
4. Ti viene chiesto di valutare la risposta:
   - ✅ **Pass**: Risposta corretta
   - ❌ **Fail**: Risposta errata
   - ⚠️ **Warning**: Parzialmente corretta
5. Puoi aggiungere note
6. Il risultato viene salvato

### 4. Verifica i report

```bash
# Report locale
open reports/mio-chatbot/run_001/report.html

# Oppure vedi il CSV
cat reports/mio-chatbot/run_001/report.csv
```

---

## Flusso di lavoro consigliato

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  1. TRAIN MODE (10-20 test)                                │
│     - Esegui i test manualmente                            │
│     - Valuta le risposte                                   │
│     - Il tool impara dai tuoi feedback                     │
│                                                             │
│                          ↓                                  │
│                                                             │
│  2. ASSISTED MODE (validazione)                            │
│     - L'AI suggerisce le valutazioni                       │
│     - Tu confermi o correggi                               │
│     - Affina l'apprendimento                               │
│                                                             │
│                          ↓                                  │
│                                                             │
│  3. AUTO MODE (regression)                                 │
│     - Esecuzione completamente automatica                  │
│     - Ideale per CI/CD                                     │
│     - Report automatici                                    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Checklist nuovo progetto

- [ ] Progetto creato in `projects/<nome>/`
- [ ] `project.yaml` configurato con URL e selettori
- [ ] `tests.json` con almeno alcuni test case
- [ ] Login effettuato (sessione salvata)
- [ ] Primo test eseguito con successo
- [ ] Report generato correttamente

---

## Prossimi passi

1. Aggiungi più test cases
2. Configura i followup per scenari complessi
3. Passa alla modalità Assisted
4. Integra con CI/CD usando modalità Auto

---

## Problemi?

Consulta la [Guida Troubleshooting](TROUBLESHOOTING.md).
