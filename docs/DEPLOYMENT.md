# Guida al Deployment

Questa guida spiega come eseguire Chatbot Tester senza avere Chromium in esecuzione sul tuo Mac.

---

## Indice

1. [GitHub Actions (Consigliato)](#1-github-actions-consigliato)
2. [Docker](#2-docker)
3. [PyPI Package](#3-pypi-package)
4. [Binary Standalone](#4-binary-standalone)
5. [GitHub Action Marketplace](#5-github-action-marketplace)

---

## 1. GitHub Actions (Consigliato)

Esegui test direttamente sui server GitHub, senza alcun software locale.

### Setup (una tantum)

#### Step 1: Configura i Secrets

Vai su **GitHub > Settings > Secrets and variables > Actions** e aggiungi:

| Secret | Valore | Obbligatorio |
|--------|--------|--------------|
| `LANGSMITH_API_KEY` | La tua API key LangSmith | No |
| `GOOGLE_CREDENTIALS` | JSON delle credenziali Google | No |

#### Step 2: Pusha il workflow

Il file `.github/workflows/chatbot-test.yml` e gia nel repo.

```bash
git add .github/
git commit -m "Add GitHub Actions workflow"
git push
```

### Utilizzo quotidiano

#### Via interfaccia web

1. Vai su **GitHub > Actions > Chatbot Test Suite**
2. Clicca **Run workflow**
3. Compila i parametri:
   - `project`: nome del progetto (es. `my-chatbot`)
   - `mode`: `auto`, `assisted`, o `train`
   - `tests`: `all`, `pending`, o `failed`
   - `new_run`: spunta per creare nuovo run

#### Via CLI (consigliato)

```bash
# Installa GitHub CLI
brew install gh

# Login
gh auth login

# Lancia test
gh workflow run chatbot-test.yml \
  -f project=my-chatbot \
  -f mode=auto \
  -f tests=pending

# Guarda lo stato
gh run watch

# Scarica report
gh run download <run-id>
```

### Costi

- **Gratis**: 2000 minuti/mese per repo pubblici
- **Privati**: 2000 minuti/mese inclusi, poi $0.008/minuto

---

## 2. Docker

Esegui test in un container isolato, localmente o su un server.

### Setup locale

```bash
# Build immagine
docker build -t chatbot-tester .

# Verifica
docker run chatbot-tester --help
```

### Esecuzione locale

```bash
# Con progetto esistente
docker run \
  -v $(pwd)/projects:/app/projects \
  -v $(pwd)/reports:/app/reports \
  chatbot-tester \
  -p my-chatbot -m auto --no-interactive

# Con variabili d'ambiente
docker run \
  -e LANGSMITH_API_KEY=your_key \
  -v $(pwd)/projects:/app/projects \
  chatbot-tester \
  -p my-chatbot -m auto --no-interactive
```

### Esecuzione su server remoto

```bash
# Step 1: Copia immagine su server
docker save chatbot-tester | ssh user@server docker load

# Step 2: Copia progetti
scp -r projects/ user@server:~/chatbot-tester/

# Step 3: Esegui da remoto
ssh user@server "docker run \
  -v ~/chatbot-tester/projects:/app/projects \
  chatbot-tester \
  -p my-chatbot -m auto --no-interactive"
```

### Docker Compose (opzionale)

Crea `docker-compose.yml`:

```yaml
version: '3.8'
services:
  chatbot-tester:
    build: .
    volumes:
      - ./projects:/app/projects
      - ./reports:/app/reports
      - ./config:/app/config
    environment:
      - LANGSMITH_API_KEY=${LANGSMITH_API_KEY}
    command: ["-p", "my-chatbot", "-m", "auto", "--no-interactive"]
```

Esegui:
```bash
docker-compose run chatbot-tester
```

---

## 3. PyPI Package

Installa come pacchetto Python standard.

### Prerequisiti

- Python 3.10+
- pip

### Installazione (dopo pubblicazione)

```bash
# Installazione base
pip install chatbot-tester

# Con supporto Google Sheets
pip install chatbot-tester[google]

# Completa
pip install chatbot-tester[all]
```

### Utilizzo

```bash
# Comando diretto
chatbot-tester -p my-chatbot -m auto --no-interactive

# Health check
chatbot-tester --health-check -p my-chatbot
```

### Pubblicazione su PyPI (per maintainer)

```bash
# Build
pip install build twine
python -m build

# Upload a TestPyPI (test)
twine upload --repository testpypi dist/*

# Upload a PyPI (produzione)
twine upload dist/*
```

---

## 4. Binary Standalone

Eseguibile singolo senza dipendenze Python.

### Prerequisiti

```bash
pip install pyinstaller
```

### Build

```bash
# Build per la piattaforma corrente
pyinstaller chatbot-tester.spec

# Output in dist/chatbot-tester
```

### Utilizzo

```bash
# Rendi eseguibile (macOS/Linux)
chmod +x dist/chatbot-tester

# Esegui
./dist/chatbot-tester -p my-chatbot -m auto --no-interactive
```

### Note

- Il binary include Python ma **non** include Playwright browsers
- Devi installare Chromium separatamente: `playwright install chromium`
- Per distribuzione completa, usa Docker

---

## 5. GitHub Action Marketplace

Usa Chatbot Tester come action in altri repository.

### Utilizzo in un workflow

```yaml
name: Test Chatbot
on: [push, workflow_dispatch]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Run Chatbot Tests
        uses: corradofrancolini/chatbot-tester@v1
        with:
          project: my-chatbot
          mode: auto
          tests: pending
          langsmith-api-key: ${{ secrets.LANGSMITH_API_KEY }}

      - name: Check results
        run: |
          echo "Passed: ${{ steps.test.outputs.passed }}"
          echo "Failed: ${{ steps.test.outputs.failed }}"
```

### Input disponibili

| Input | Descrizione | Default |
|-------|-------------|---------|
| `project` | Nome progetto | (obbligatorio) |
| `mode` | Modalita test | `auto` |
| `tests` | Quali test | `pending` |
| `new-run` | Crea nuovo run | `false` |
| `single-test` | ID singolo test | - |
| `headless` | Browser headless | `true` |
| `langsmith-api-key` | API key | - |
| `google-credentials` | JSON credentials | - |

### Output disponibili

| Output | Descrizione |
|--------|-------------|
| `report-path` | Path al report HTML |
| `passed` | Numero test passati |
| `failed` | Numero test falliti |
| `total` | Totale test eseguiti |

---

## Confronto opzioni

| Metodo | Setup | Costo | Manutenzione | Chromium locale |
|--------|-------|-------|--------------|-----------------|
| GitHub Actions | Facile | Gratis* | Zero | No |
| Docker locale | Medio | Zero | Bassa | Si (nel container) |
| Docker server | Medio | Server | Media | No |
| PyPI | Facile | Zero | Zero | Si |
| Binary | Medio | Zero | Zero | Si |

*2000 minuti/mese inclusi

---

## Troubleshooting

### GitHub Actions fallisce

1. Verifica i secrets siano configurati
2. Controlla i log in **Actions > Run details**
3. Verifica che il progetto esista in `projects/`

### Docker non trova il progetto

```bash
# Verifica il volume mount
docker run -v $(pwd)/projects:/app/projects chatbot-tester ls /app/projects
```

### Health check fallisce

```bash
# Verifica servizi
python run.py --health-check -p my-chatbot

# Salta health check per forzare
python run.py -p my-chatbot -m auto --skip-health-check
```
