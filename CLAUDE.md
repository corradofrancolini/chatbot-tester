# Chatbot Tester - Note Progetto

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

## Configurazione run_config.json

- `single_turn: true` → Esegue solo domanda iniziale, no followup Ollama
- `use_ollama: false` → Disabilita valutazione automatica (richiede review manuale)
- `active_run` → Numero del run attivo su Google Sheets

## Screenshot

Gli screenshot devono catturare l'INTERA conversazione con TUTTI i prodotti visibili.

**File chiave:** `src/browser.py` metodo `take_conversation_screenshot()`
- Usa CSS injection per nascondere input bar, footer, scroll indicators
- Espande container per mostrare tutto il contenuto
- Cattura `section.llm__thread`

**Riferimento funzionante:** `/Users/corradofrancolini/efg-chatbot-tests/test_smart.py`

## Struttura Report

- Screenshots: `reports/{project}/run_{N}/screenshots/`
- Report HTML: `reports/{project}/run_{N}/report.html`
- Google Sheets: Un foglio per ogni run

## Progetti Configurati

- `my-chatbot` → Silicon search chatbot (DEV)
- `example-bot` → EFG chatbot
