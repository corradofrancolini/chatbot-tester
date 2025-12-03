# 🔧 Troubleshooting

Guida alla risoluzione dei problemi comuni.

---

## 📋 Indice

1. [Problemi di Installazione](#problemi-di-installazione)
2. [Problemi con il Browser](#problemi-con-il-browser)
3. [Problemi di Connessione](#problemi-di-connessione)
4. [Problemi con i Selettori](#problemi-con-i-selettori)
5. [Problemi con Ollama](#problemi-con-ollama)
6. [Problemi con Google Sheets](#problemi-con-google-sheets)
7. [Problemi con LangSmith](#problemi-con-langsmith)
8. [Errori Comuni](#errori-comuni)
9. [Reset Completo](#reset-completo)

---

## Problemi di Installazione

### "Command not found: ./install.sh"

**Causa**: Il file non ha permessi di esecuzione.

**Soluzione**:
```bash
chmod +x install.sh update.sh uninstall.sh
./install.sh
```

### "Python 3.10+ non trovato"

**Soluzione**:
```bash
# Installa Python 3.12 via Homebrew
brew install python@3.12

# Verifica
python3.12 --version
```

### "Homebrew non trovato"

**Soluzione**:
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Per Apple Silicon, aggiungi al PATH
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
eval "$(/opt/homebrew/bin/brew shellenv)"
```

### "pip install fallisce"

**Possibili cause e soluzioni**:

```bash
# 1. Aggiorna pip
source .venv/bin/activate
pip install --upgrade pip

# 2. Installa dipendenze di sistema
xcode-select --install

# 3. Prova installazione singola
pip install playwright
pip install rich
# ... etc
```

### "Spazio disco insufficiente"

**Soluzione**:
```bash
# Verifica spazio disponibile
df -h .

# Libera spazio
# - Svuota cestino
# - Rimuovi vecchi backup
# - Usa Disk Utility per ottimizzare
```

---

## Problemi con il Browser

### "Il browser non si apre"

**Soluzioni**:

```bash
# 1. Reinstalla Chromium
source .venv/bin/activate
playwright install chromium --force

# 2. Verifica installazione
playwright install --help

# 3. Se su Apple Silicon
playwright install chromium --with-deps
```

### "Browser si apre ma pagina bianca"

**Causa**: Problema di connessione o URL errato.

**Soluzioni**:
1. Verifica che l'URL sia corretto nel `project.yaml`
2. Prova l'URL manualmente in un browser
3. Verifica connessione internet

### "Screenshot non vengono salvati"

**Soluzioni**:

```bash
# 1. Verifica permessi cartella
ls -la reports/

# 2. Crea manualmente se non esiste
mkdir -p reports/<progetto>/screenshots

# 3. Verifica spazio disco
df -h .
```

### "Browser si chiude improvvisamente"

**Possibili cause**:
- Timeout troppo breve
- Errore JavaScript nella pagina
- Problema di memoria

**Soluzioni**:

```yaml
# In project.yaml, aumenta timeout
chatbot:
  timeouts:
    page_load: 60000
    bot_response: 120000
```

---

## Problemi di Connessione

### "URL non raggiungibile"

**Verifica**:
```bash
# Test connessione
curl -I https://chat.example.com

# Verifica DNS
nslookup chat.example.com

# Verifica se sei dietro proxy/VPN
```

### "Errore SSL/TLS"

**Soluzioni**:
```bash
# 1. Verifica data/ora del sistema
date

# 2. Se certificato self-signed, potrebbe essere necessario
# modificare la configurazione (non consigliato per produzione)
```

### "Timeout durante la risposta del bot"

**Soluzioni**:

```yaml
# In project.yaml
chatbot:
  timeouts:
    bot_response: 120000  # Aumenta a 2 minuti
```

```bash
# Verifica latenza
ping chat.example.com
```

---

## Problemi con i Selettori

### "Selettore non trovato"

**Diagnosi**:
1. Apri il chatbot in Chrome
2. Premi F12 → Console
3. Esegui:
```javascript
document.querySelector('#tuo-selettore')
```

**Se ritorna `null`**, il selettore è errato.

**Soluzioni**:
1. Usa il Click-to-learn:
```bash
./chatbot-tester --new-project
# Al passo 4, scegli "Click-to-learn"
```

2. Trova manualmente con DevTools:
   - F12 → Elements
   - Click sull'icona selettore (↖️)
   - Clicca sull'elemento
   - Tasto destro → Copy → Copy selector

### "Selettore trova più elementi"

Il selettore deve essere univoco. 

**Soluzioni**:
```css
/* Troppo generico */
.message

/* Più specifico */
.message.assistant:last-child

/* Con ID parent */
#chat-container .message.assistant
```

### "Il bot risponde ma non viene rilevato"

**Cause possibili**:
- Selettore messaggi errato
- Risposta caricata dinamicamente
- Iframe nascosto

**Soluzioni**:
```yaml
# In project.yaml, prova diversi selettori
chatbot:
  selectors:
    bot_messages: ".ai-response, .bot-message, [data-role='assistant']"
```

---

## Problemi con Ollama

### "Ollama non risponde"

**Verifica**:
```bash
# Ollama è in esecuzione?
curl http://localhost:11434/api/tags

# Se errore, avvia Ollama
ollama serve
```

### "Modello Mistral non trovato"

```bash
# Scarica il modello
ollama pull mistral

# Verifica modelli disponibili
ollama list
```

### "Risposte Ollama lente"

**Soluzioni**:
1. Verifica RAM disponibile (Activity Monitor)
2. Chiudi altre applicazioni
3. Usa modello più leggero:
```yaml
ollama:
  model: "llama2"  # Più veloce di mistral
```

### "Errore 'out of memory'"

```bash
# Verifica memoria usata
ollama ps

# Riavvia Ollama
pkill ollama
ollama serve
```

---

## Problemi con Google Sheets

### "Errore OAuth / Authentication"

**Soluzioni**:

```bash
# 1. Rimuovi token salvati
rm -f config/token.json

# 2. Verifica credenziali
cat config/oauth_credentials.json | python -m json.tool

# 3. Riesegui autorizzazione
./chatbot-tester --project=<nome>
# Segui il flusso OAuth nel browser
```

### "Spreadsheet non trovato"

**Verifica**:
1. L'ID è corretto? (dall'URL di Sheets)
2. Hai condiviso il foglio con l'account OAuth?
3. API Sheets abilitata?

```bash
# Testa accesso
curl -s "https://sheets.googleapis.com/v4/spreadsheets/YOUR_ID" \
  -H "Authorization: Bearer $(cat config/token.json | jq -r .access_token)"
```

### "Quota API superata"

Google Sheets ha limiti:
- 100 richieste / 100 secondi / utente
- 500 richieste / 100 secondi / progetto

**Soluzioni**:
1. Riduci frequenza test
2. Usa batch updates
3. Abilita più quota in Google Cloud Console

### "Screenshot non caricati su Drive"

**Verifica**:
1. API Drive abilitata?
2. Cartella Drive condivisa?
3. Drive Folder ID corretto?

---

## Problemi con LangSmith

### "API Key non valida"

**Verifica**:
```bash
# Testa chiave
curl -s "https://api.smith.langchain.com/projects" \
  -H "x-api-key: YOUR_KEY"
```

**Se errore 401**:
1. Rigenera la chiave in LangSmith
2. Aggiorna `config/.env`

### "Trace non trovate"

**Possibili cause**:
1. Project ID errato
2. Org ID errato
3. Nessuna trace recente

**Verifica**:
1. Vai su smith.langchain.com
2. Verifica che ci siano trace nel progetto
3. Confronta Project ID e Org ID

### "Tool names non rilevati"

**Soluzioni**:
1. Esegui un test manuale sul chatbot
2. Aspetta che la trace appaia in LangSmith
3. Riesegui il wizard per auto-detect

---

## Errori Comuni

### "ModuleNotFoundError"

```bash
# Assicurati di usare il venv
source .venv/bin/activate

# Reinstalla dipendenze
pip install -r requirements.txt
```

### "FileNotFoundError: project.yaml"

```bash
# Verifica che il progetto esista
ls projects/

# Se mancante, ricrea
./chatbot-tester --new-project
```

### "JSONDecodeError in tests.json"

```bash
# Valida JSON
cat projects/<nome>/tests.json | python -m json.tool

# Errori comuni:
# - Virgola finale: [{"a": 1},]  ← ERRATO
# - Quote singole: {'a': 1}      ← ERRATO
# - Commenti: /* comment */      ← ERRATO
```

### "PermissionError"

```bash
# Fix permessi
chmod -R u+rw projects/ reports/ config/
```

### "TimeoutError"

**Soluzioni**:
1. Aumenta timeout in `project.yaml`
2. Verifica connessione
3. Il chatbot potrebbe essere lento

---

## Reset Completo

Se nulla funziona, reset completo:

### Reset singolo progetto

```bash
# Rimuovi dati browser e training
rm -rf projects/<nome>/browser-data/
rm -f projects/<nome>/training_data.json
echo "[]" > projects/<nome>/training_data.json

# Rimuovi report
rm -rf reports/<nome>/
```

### Reset installazione

```bash
# Disinstalla
./uninstall.sh

# Rimuovi residui
rm -rf .venv/
rm -rf projects/*/browser-data/

# Reinstalla
./install.sh
```

### Reset completo (ATTENZIONE: perdi tutto!)

```bash
# Backup prima!
cp -r projects/ ~/backup-chatbot-tester-projects/
cp config/.env ~/backup-env

# Reset
./uninstall.sh --remove-all

# Reinstalla
./install.sh
```

---

## Log e Debug

### Abilita log verbose

```bash
./chatbot-tester --project=<nome> --verbose
```

### Log Playwright

```bash
DEBUG=pw:api ./chatbot-tester --project=<nome>
```

### Log Python

```python
# In run.py, temporaneamente aggiungi:
import logging
logging.basicConfig(level=logging.DEBUG)
```

---

## Supporto

Se il problema persiste:

1. **Raccogli informazioni**:
```bash
# Versioni
python --version
./chatbot-tester --version
ollama --version 2>/dev/null

# Sistema
sw_vers
uname -m
```

2. **Crea issue su GitHub** con:
   - Descrizione del problema
   - Passaggi per riprodurre
   - Log di errore
   - Versioni software

---

## FAQ

**Q: Posso usare Firefox invece di Chromium?**
A: No, attualmente solo Chromium è supportato per garantire consistenza.

**Q: Funziona su Windows/Linux?**
A: No, solo macOS è ufficialmente supportato.

**Q: Posso testare più chatbot contemporaneamente?**
A: Sì, crea progetti separati ed eseguili in terminali diversi.

**Q: I dati del browser sono condivisi tra progetti?**
A: No, ogni progetto ha la sua sessione browser isolata.

**Q: Come faccio backup dei dati?**
A: Copia le cartelle `projects/` e `config/.env`.
