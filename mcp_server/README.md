# MCP Server per chatbot-tester

Server MCP remoto per esporre le funzionalita' di chatbot-tester a Claude Desktop.

## Architettura

```
┌─────────────────────┐              ┌─────────────────────────────┐
│  Mac del collega    │              │  Cloud (Fly.io)             │
│                     │              │                             │
│  Claude Desktop ────┼───HTTPS──────►  MCP Server (SSE)          │
│  + config MCP       │              │  + chatbot-tester           │
│                     │              │  + API CircleCI             │
└─────────────────────┘              └─────────────────────────────┘
```

## Tools Disponibili

| Tool | Descrizione |
|------|-------------|
| `list_projects` | Elenca progetti disponibili |
| `list_tests` | Elenca test di un progetto |
| `trigger_circleci` | Avvia pipeline CircleCI |
| `get_pipeline_status` | Stato pipeline recenti |
| `get_workflow_status` | Stato dettagliato workflow |

## Setup Locale (Sviluppo)

```bash
# Installa dipendenze
pip install -r mcp_server/requirements.txt

# Genera API key
python mcp_server/auth.py

# Avvia server
export MCP_API_KEY="<api-key-generata>"
export CIRCLECI_TOKEN="<tuo-token-circleci>"
python mcp_server/server.py
```

Il server sara' disponibile su `http://localhost:8080`.

## Deploy su Fly.io

### 1. Installa Fly CLI

```bash
brew install flyctl
fly auth login
```

### 2. Crea l'applicazione

```bash
cd mcp_server
fly launch --name chatbot-tester-mcp --no-deploy
```

### 3. Configura i secrets

```bash
# Genera API key
python auth.py

# Imposta secrets
fly secrets set MCP_API_KEY="<api-key-generata>"
fly secrets set CIRCLECI_TOKEN="<token-circleci>"
```

### 4. Deploy

```bash
# Dal root del progetto
fly deploy --config mcp_server/fly.toml --dockerfile mcp_server/Dockerfile
```

### 5. Verifica

```bash
curl https://chatbot-tester-mcp.fly.dev/health
```

## Configurazione Claude Desktop

Il collega deve aggiungere a `~/Library/Application Support/Claude/claude_desktop_config.json`:

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

Riavviare Claude Desktop dopo la modifica.

## Esempi di Utilizzo

Una volta configurato, il collega puo' chiedere a Claude Desktop:

- "Mostrami i progetti disponibili su chatbot-tester"
- "Elenca i test del progetto silicon-b"
- "Avvia i test pending su silicon-b"
- "Crea una nuova RUN e avvia tutti i test su silicon-b"
- "Qual e' lo stato delle pipeline recenti?"

## Costi Fly.io

| Risorsa | Costo stimato |
|---------|---------------|
| VM shared-cpu-1x (512MB) | ~$5/mese |
| Bandwidth | Incluso (primi 100GB) |
| **Totale** | **~$5/mese** |

## Troubleshooting

### Errore "CircleCI non configurato"

Verificare che `CIRCLECI_TOKEN` sia impostato:
```bash
fly secrets list
```

### Errore 401 Unauthorized

Verificare che l'API key nel config di Claude Desktop corrisponda a quella impostata su Fly.io.

### Connessione rifiutata

Verificare che l'app sia in esecuzione:
```bash
fly status
fly logs
```
