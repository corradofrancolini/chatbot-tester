"""
MCP Tools for chatbot-tester.

Defines all tools exposed by the MCP server for interacting with
chatbot-tester functionality.
"""

import os
import sys
import json
import logging
from pathlib import Path
from typing import Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp.server import Server
from mcp.types import Tool, TextContent

logger = logging.getLogger(__name__)

# Projects directory
PROJECTS_DIR = Path(__file__).parent.parent / "projects"


def get_available_projects() -> list[str]:
    """Get list of available project names."""
    if not PROJECTS_DIR.exists():
        return []

    projects = []
    for item in PROJECTS_DIR.iterdir():
        if item.is_dir() and not item.name.startswith('.'):
            # Check if it has a project.yaml
            if (item / "project.yaml").exists():
                projects.append(item.name)

    return sorted(projects)


def get_available_test_sets(project: str) -> dict[str, int]:
    """Get available test sets for a project with their test counts."""
    project_dir = PROJECTS_DIR / project
    test_sets = {}

    if not project_dir.exists():
        return test_sets

    # Look for test files
    for file in project_dir.iterdir():
        if file.name.startswith("tests") and file.name.endswith(".json"):
            try:
                with open(file) as f:
                    data = json.load(f)
                    tests = data if isinstance(data, list) else data.get("tests", [])
                    # Create friendly name
                    if file.name == "tests.json":
                        name = "standard"
                    else:
                        # tests_paraphrase.json -> paraphrase
                        name = file.name.replace("tests_", "").replace(".json", "")
                    test_sets[name] = len(tests)
            except Exception as e:
                logger.error(f"Error reading {file}: {e}")

    return test_sets


def get_project_tests(project: str, test_set: str = "standard") -> list[dict]:
    """Get tests for a project from a specific test set."""
    project_dir = PROJECTS_DIR / project

    # Map test set name to file
    if test_set == "standard":
        tests_file = project_dir / "tests.json"
    else:
        tests_file = project_dir / f"tests_{test_set}.json"

    if not tests_file.exists():
        # Fallback to standard tests.json
        tests_file = project_dir / "tests.json"
        if not tests_file.exists():
            return []

    try:
        with open(tests_file) as f:
            data = json.load(f)
            # Handle both formats: direct array [...] or object {"tests": [...]}
            if isinstance(data, list):
                return data
            return data.get("tests", [])
    except Exception as e:
        logger.error(f"Error reading tests: {e}")
        return []


def get_run_config(project: str) -> dict:
    """Get run_config.json for a project."""
    config_file = PROJECTS_DIR / project / "run_config.json"
    if not config_file.exists():
        return {}
    try:
        with open(config_file) as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error reading run_config: {e}")
        return {}


def should_use_parallel(test_count: int) -> bool:
    """Decide automaticamente se usare parallelismo."""
    return test_count >= 10


def estimate_duration(test_count: int, parallel: bool) -> str:
    """Stima durata esecuzione."""
    # ~1.5 min per test singolo, ~0.5 min con 3 container
    if parallel:
        minutes = (test_count / 3) * 0.5 + 2  # +2 min overhead
    else:
        minutes = test_count * 1.5

    if minutes < 5:
        return "5 minuti"
    elif minutes < 15:
        return "10-15 minuti"
    else:
        return f"{int(minutes)} minuti"


def register_tools(server: Server):
    """Register all MCP tools with the server."""

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """List available tools."""
        return [
            Tool(
                name="get_help",
                description="""Mostra la guida su come usare chatbot-tester.

USA QUESTO TOOL quando l'utente chiede:
- "Come funziona?"
- "Aiuto"
- "Cosa posso fare?"
- "Come si usa?"

Se l'utente è nuovo, usa topic='quickstart' per una guida rapida.""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "topic": {
                            "type": "string",
                            "enum": ["overview", "testing", "results", "comparison", "quickstart", "all"],
                            "description": "Argomento specifico (default: 'all'). Usa 'quickstart' per utenti nuovi.",
                            "default": "all"
                        }
                    },
                    "required": []
                }
            ),
            Tool(
                name="list_projects",
                description="""Mostra i progetti disponibili per il testing.

USA QUESTO TOOL quando l'utente chiede:
- "Quali progetti posso testare?"
- "Cosa c'è disponibile?"
- "Lista progetti"
- "Mostrami i progetti"

Per ogni progetto mostra i test set disponibili (es. standard, paraphrase, ggp).""",
                inputSchema={
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            ),
            Tool(
                name="suggest_project",
                description="Analizza i progetti disponibili e suggerisce quale testare, mostrando statistiche e priorità",
                inputSchema={
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            ),
            Tool(
                name="list_test_sets",
                description="Mostra i set di test disponibili per un progetto (es. standard, paraphrase)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project": {
                            "type": "string",
                            "description": "Nome del progetto (es. 'silicon-b')"
                        }
                    },
                    "required": ["project"]
                }
            ),
            Tool(
                name="list_tests",
                description="Elenca i test disponibili per un progetto, con filtro opzionale per ID o keyword",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project": {
                            "type": "string",
                            "description": "Nome del progetto (es. 'silicon-b')"
                        },
                        "test_set": {
                            "type": "string",
                            "description": "Nome del set di test (corrisponde al file tests_{name}.json). Default: 'standard'"
                        },
                        "filter": {
                            "type": "string",
                            "description": "Filtra test per ID o keyword (es. 'PARA', 'TEST_001', 'prodotto')"
                        }
                    },
                    "required": ["project"]
                }
            ),
            Tool(
                name="trigger_circleci",
                description="Avvia una pipeline CircleCI per eseguire i test su un progetto. "
                           "Questo esegue i test nel cloud e scrive i risultati su Google Sheets.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project": {
                            "type": "string",
                            "description": "Nome del progetto (es. 'silicon-b')"
                        },
                        "test_set": {
                            "type": "string",
                            "description": "Set di test da usare. Esempi: 'paraphrase' per test di parafrasi (PARA_*), 'standard' per test normali (TEST_*). Corrisponde al file tests_{name}.json. Default: 'standard'"
                        },
                        "mode": {
                            "type": "string",
                            "enum": ["auto", "assisted", "train"],
                            "description": "Modalita' di test (default: 'auto')",
                            "default": "auto"
                        },
                        "tests": {
                            "type": "string",
                            "enum": ["all", "pending", "failed"],
                            "description": "Quali test eseguire (default: 'pending')",
                            "default": "pending"
                        },
                        "new_run": {
                            "type": "boolean",
                            "description": "Se creare una nuova RUN su Google Sheets (default: false)",
                            "default": False
                        },
                        "test_limit": {
                            "type": "integer",
                            "description": "Limita a N test (0 = nessun limite)",
                            "default": 0
                        },
                        "test_ids": {
                            "type": "string",
                            "description": "Lista di ID test separati da virgola (es. 'TEST_001,TEST_002')"
                        },
                        "prompt_version": {
                            "type": "string",
                            "description": "Versione del prompt (es. 'v12'). Viene registrata su Google Sheets."
                        },
                        "parallel": {
                            "type": "boolean",
                            "description": "Abilita parallelismo per esecuzione veloce. Usa questo se l'utente chiede 'veloce', 'parallelo', 'il prima possibile'.",
                            "default": False
                        },
                        "repeat": {
                            "type": "integer",
                            "description": "Numero di RUN da creare (1-5). Usa questo se l'utente chiede 'lancia 2 run', '3 esecuzioni', etc. Ogni RUN crea un foglio separato su Google Sheets.",
                            "default": 1,
                            "minimum": 1,
                            "maximum": 5
                        }
                    },
                    "required": ["project"]
                }
            ),
            Tool(
                name="get_pipeline_status",
                description="Ottiene lo stato delle pipeline CircleCI recenti",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "Numero massimo di pipeline da mostrare (default: 5)",
                            "default": 5
                        }
                    },
                    "required": []
                }
            ),
            Tool(
                name="get_workflow_status",
                description="Ottiene lo stato dettagliato di un workflow CircleCI",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "pipeline_id": {
                            "type": "string",
                            "description": "ID della pipeline CircleCI"
                        }
                    },
                    "required": ["pipeline_id"]
                }
            ),
            Tool(
                name="list_runs",
                description="Elenca tutte le RUN disponibili su Google Sheets per un progetto",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project": {
                            "type": "string",
                            "description": "Nome del progetto (es. 'silicon-b')"
                        }
                    },
                    "required": ["project"]
                }
            ),
            Tool(
                name="get_run_results",
                description="Ottiene i risultati di una specifica RUN da Google Sheets",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project": {
                            "type": "string",
                            "description": "Nome del progetto (es. 'silicon-b')"
                        },
                        "run_number": {
                            "type": "integer",
                            "description": "Numero della RUN (es. 15). Se non specificato, usa l'ultima."
                        }
                    },
                    "required": ["project"]
                }
            ),
            Tool(
                name="get_failed_tests",
                description="Ottiene solo i test falliti di una RUN",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project": {
                            "type": "string",
                            "description": "Nome del progetto (es. 'silicon-b')"
                        },
                        "run_number": {
                            "type": "integer",
                            "description": "Numero della RUN. Se non specificato, usa l'ultima."
                        }
                    },
                    "required": ["project"]
                }
            ),
            Tool(
                name="compare_runs",
                description="Confronta due RUN per trovare regressioni, miglioramenti e test instabili",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project": {
                            "type": "string",
                            "description": "Nome del progetto (es. 'silicon-b')"
                        },
                        "run_a": {
                            "type": "integer",
                            "description": "Numero della prima RUN (baseline)"
                        },
                        "run_b": {
                            "type": "integer",
                            "description": "Numero della seconda RUN (da confrontare). Se non specificato, usa l'ultima."
                        }
                    },
                    "required": ["project"]
                }
            ),
            # ====== NUOVI TOOL FOOL-PROOF ======
            Tool(
                name="start_test_session",
                description="""Avvia una sessione guidata per testare un progetto.

USA QUESTO TOOL quando l'utente dice:
- "Voglio testare silicon-b"
- "Lancia i test su silicon-b"
- "Esegui i test di parafrasi su silicon-b"
- "Testa il chatbot silicon-b"

IMPORTANTE: L'utente DEVE specificare il nome del progetto.
Se non lo fa, chiedi "Quale progetto vuoi testare?" e usa list_projects.

Il tool mostra:
1. Test set disponibili (es. standard, paraphrase, ggp) con conteggio
2. Stato attuale (test pending, falliti, pass rate ultima RUN)
3. Raccomandazione su cosa testare

DOPO aver mostrato le opzioni, CHIEDI all'utente quale test set vuole usare.""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project": {
                            "type": "string",
                            "description": "Nome del progetto da testare (es. silicon-b, silicon-a)"
                        }
                    },
                    "required": ["project"]
                }
            ),
            Tool(
                name="prepare_test_run",
                description="""Prepara l'esecuzione dei test e mostra un RIEPILOGO DETTAGLIATO per conferma.

USA QUESTO TOOL quando l'utente ha scelto cosa testare:
- "Ok, lancia i test standard"
- "Vai con paraphrase"
- "Esegui i pending"

NON lancia ancora! Mostra il riepilogo e CHIEDI CONFERMA all'utente.
Solo dopo che l'utente conferma (es. "sì", "procedi", "ok"), usa execute_test_run.""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project": {
                            "type": "string",
                            "description": "Nome del progetto"
                        },
                        "test_set": {
                            "type": "string",
                            "description": "Test set (standard, paraphrase, ggp)"
                        },
                        "tests": {
                            "type": "string",
                            "enum": ["pending", "all", "failed"],
                            "description": "Quali test eseguire",
                            "default": "pending"
                        }
                    },
                    "required": ["project", "test_set"]
                }
            ),
            Tool(
                name="execute_test_run",
                description="""Esegue i test DOPO che l'utente ha confermato il riepilogo.

USA QUESTO TOOL SOLO quando l'utente ha visto il riepilogo di prepare_test_run
e ha confermato esplicitamente:
- "sì"
- "procedi"
- "ok vai"
- "confermo"

Se l'utente NON ha confermato o ha detto "no", NON usare questo tool.""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project": {
                            "type": "string",
                            "description": "Nome del progetto"
                        },
                        "test_set": {
                            "type": "string",
                            "description": "Test set (standard, paraphrase, ggp)"
                        },
                        "tests": {
                            "type": "string",
                            "enum": ["pending", "all", "failed"],
                            "description": "Quali test eseguire",
                            "default": "pending"
                        }
                    },
                    "required": ["project", "test_set"]
                }
            ),
            Tool(
                name="check_pipeline_status",
                description="""Controlla lo stato di una pipeline in esecuzione.

USA QUESTO TOOL quando l'utente chiede:
- "Come sta andando?"
- "A che punto siamo?"
- "Sono finiti i test?"
- "Controlla lo stato"

NON fa polling automatico (non possibile in MCP).
Restituisce lo stato attuale + promemoria per ricontrollare.""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "pipeline_id": {
                            "type": "string",
                            "description": "ID pipeline da controllare"
                        }
                    },
                    "required": ["pipeline_id"]
                }
            ),
            Tool(
                name="show_results",
                description="""Mostra i risultati dell'ultima esecuzione in modo chiaro e comprensibile.

USA QUESTO TOOL quando l'utente chiede:
- "Come è andata?"
- "Mostrami i risultati di silicon-b"
- "Quanti test sono passati?"
- "Ci sono errori?"

Mostra:
- Pass rate con indicatore visivo (✅ >90%, ⚠️ 70-90%, ❌ <70%)
- Numero test passati/falliti/pending
- Lista test falliti con breve descrizione
- Suggerimento per prossimi passi""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project": {
                            "type": "string",
                            "description": "Nome del progetto"
                        },
                        "run_number": {
                            "type": "integer",
                            "description": "Numero RUN (se non specificato, usa l'ultima)"
                        }
                    },
                    "required": ["project"]
                }
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        """Handle tool calls."""
        logger.info(f"Tool call: {name} with args: {arguments}")

        try:
            if name == "get_help":
                return await handle_get_help(arguments)
            elif name == "list_projects":
                return await handle_list_projects()
            elif name == "suggest_project":
                return await handle_suggest_project()
            elif name == "list_test_sets":
                return await handle_list_test_sets(arguments)
            elif name == "list_tests":
                return await handle_list_tests(arguments)
            elif name == "trigger_circleci":
                return await handle_trigger_circleci(arguments)
            elif name == "get_pipeline_status":
                return await handle_get_pipeline_status(arguments)
            elif name == "get_workflow_status":
                return await handle_get_workflow_status(arguments)
            elif name == "list_runs":
                return await handle_list_runs(arguments)
            elif name == "get_run_results":
                return await handle_get_run_results(arguments)
            elif name == "get_failed_tests":
                return await handle_get_failed_tests(arguments)
            elif name == "compare_runs":
                return await handle_compare_runs(arguments)
            # ====== NUOVI TOOL FOOL-PROOF ======
            elif name == "start_test_session":
                return await handle_start_test_session(arguments)
            elif name == "prepare_test_run":
                return await handle_prepare_test_run(arguments)
            elif name == "execute_test_run":
                return await handle_execute_test_run(arguments)
            elif name == "check_pipeline_status":
                return await handle_check_pipeline_status(arguments)
            elif name == "show_results":
                return await handle_show_results(arguments)
            else:
                return [TextContent(
                    type="text",
                    text=f"Tool sconosciuto: {name}"
                )]
        except Exception as e:
            logger.error(f"Error in tool {name}: {e}")
            return [TextContent(
                type="text",
                text=f"Errore nell'esecuzione del tool {name}: {str(e)}"
            )]


async def handle_get_help(arguments: dict) -> list[TextContent]:
    """Handle get_help tool."""
    topic = arguments.get("topic", "all")

    help_sections = {
        "overview": """## Chatbot Tester - Panoramica

Chatbot Tester è un sistema per testare automaticamente chatbot conversazionali.

**Progetti disponibili:** Usa `list_projects` per vedere i progetti configurati.

**Flusso tipico:**
1. Scegli un progetto (es. `silicon-b`)
2. Esegui i test con `trigger_circleci`
3. Controlla i risultati con `list_runs` e `get_run_results`
4. Analizza regressioni con `compare_runs`
""",

        "testing": """## Come eseguire i test

### Comando base
> "Esegui i test pending di silicon-b"

### Parametri disponibili per `trigger_circleci`:

| Parametro | Valori | Default | Descrizione |
|-----------|--------|---------|-------------|
| `project` | nome progetto | - | **Obbligatorio** |
| `mode` | auto, assisted, train | auto | Modalità esecuzione |
| `tests` | all, pending, failed | pending | Quali test eseguire |
| `new_run` | true/false | false | Crea nuova RUN su Sheets |
| `test_limit` | numero | 0 (tutti) | Limita numero test |
| `test_ids` | "ID1,ID2,..." | - | Test specifici |

### Esempi:
- *"Esegui tutti i test di silicon-b con nuova RUN"*
- *"Esegui solo i test falliti di silicon-b"*
- *"Esegui TEST_001 e TEST_050 su silicon-b"*
- *"Esegui 5 test di silicon-b"*

### Modalità:
- **auto**: Esecuzione automatica, valutazione AI
- **assisted**: Richiede conferma manuale
- **train**: Per generare dati di training
""",

        "results": """## Come vedere i risultati

### Lista RUN disponibili
> "Mostra le RUN di silicon-b"

### Risultati di una RUN specifica
> "Mostra i risultati della RUN 15 di silicon-b"

### Solo test falliti
> "Mostra i test falliti della RUN 15"

### Stato pipeline CircleCI
> "Mostra lo stato delle pipeline recenti"
> "Dettaglio della pipeline xyz123"

### Informazioni mostrate:
- Pass rate (% test passati)
- Lista test con esito (PASS/FAIL)
- Timestamp esecuzione
- Ambiente (DEV/STAGING/PROD)
""",

        "comparison": """## Come confrontare RUN

### Confronto tra due RUN
> "Confronta le RUN 10 e 15 di silicon-b"

### Cosa mostra il confronto:
- **Regressioni**: Test che erano PASS e ora sono FAIL
- **Miglioramenti**: Test che erano FAIL e ora sono PASS
- **Delta pass rate**: Variazione percentuale

### Quando usarlo:
- Dopo un deploy per verificare regressioni
- Per confrontare performance tra ambienti
- Per tracking qualità nel tempo
""",

        "quickstart": """## 🚀 Guida Rapida

**Se non sai da dove partire, dimmi semplicemente:**
- *"Voglio testare silicon-b"* → Ti guido io passo passo
- *"Mostrami cosa posso fare"* → Lista completa opzioni

### Test Set disponibili per silicon-b:
- **standard**: 50+ test completi
- **paraphrase**: 40+ test con domande riformulate
- **ggp**: 4 test di grounding

### Comandi rapidi:
- *"Lancia i test pending di silicon-b"* → Esegue solo test non ancora fatti
- *"Lancia tutti i test"* → Nuova RUN completa
- *"Come sta andando?"* → Stato pipeline
- *"Mostrami i risultati"* → Ultima RUN

### Flusso tipico:
1. **Scegli progetto**: "Voglio testare silicon-b"
2. **Scegli test set**: "standard" / "paraphrase" / "ggp"
3. **Conferma**: Vedi riepilogo e confermi
4. **Monitora**: "Come sta andando?"
5. **Risultati**: "Mostrami i risultati"
"""
    }

    if topic == "all":
        result = "# Guida Chatbot Tester\n\n"
        result += help_sections["overview"] + "\n---\n\n"
        result += help_sections["testing"] + "\n---\n\n"
        result += help_sections["results"] + "\n---\n\n"
        result += help_sections["comparison"]
    else:
        result = help_sections.get(topic, "Argomento non trovato. Usa: overview, testing, results, comparison, all")

    return [TextContent(type="text", text=result)]


async def handle_list_projects() -> list[TextContent]:
    """Handle list_projects tool."""
    projects = get_available_projects()

    if not projects:
        return [TextContent(
            type="text",
            text="Nessun progetto trovato."
        )]

    result = "Progetti disponibili:\n\n"
    for project in projects:
        test_sets = get_available_test_sets(project)
        total = sum(test_sets.values())
        sets_info = ", ".join([f"{name}: {count}" for name, count in test_sets.items()])
        result += f"- **{project}**: {total} test ({sets_info})\n"

    return [TextContent(type="text", text=result)]


async def handle_list_test_sets(arguments: dict) -> list[TextContent]:
    """Handle list_test_sets tool."""
    project = arguments.get("project")

    if not project:
        return [TextContent(type="text", text="Errore: specificare il nome del progetto")]

    if project not in get_available_projects():
        return [TextContent(
            type="text",
            text=f"Progetto '{project}' non trovato."
        )]

    test_sets = get_available_test_sets(project)

    if not test_sets:
        return [TextContent(type="text", text=f"Nessun set di test trovato per '{project}'.")]

    result = f"## Set di test disponibili per {project}\n\n"

    for name, count in sorted(test_sets.items()):
        result += f"- **{name}**: {count} test\n"

    result += "\n---\n"
    result += "Per usare un set specifico:\n"
    result += f"*\"Esegui i test paraphrase di {project}\"*\n"
    result += f"*\"Mostra i test paraphrase di {project}\"*"

    return [TextContent(type="text", text=result)]


async def handle_suggest_project() -> list[TextContent]:
    """Handle suggest_project tool - analyzes projects and suggests which to test."""
    projects = get_available_projects()

    if not projects:
        return [TextContent(type="text", text="Nessun progetto trovato.")]

    project_stats = []

    for project in projects:
        tests = get_project_tests(project)
        total_tests = len(tests)

        stats = {
            "name": project,
            "total_tests": total_tests,
            "last_run": None,
            "last_run_date": None,
            "pass_rate": None,
            "pending": 0,
            "failed": 0,
            "priority_score": 0,
            "priority_reason": []
        }

        # Try to get last RUN info
        try:
            client = get_sheets_client(project)
            runs = client.get_all_run_numbers()

            if runs:
                last_run = max(runs)
                stats["last_run"] = last_run

                # Get last run results
                client.active_run = last_run
                results = client.get_all_results()

                if results:
                    passed = sum(1 for r in results if r.get("esito", "").upper() == "PASS")
                    failed = sum(1 for r in results if r.get("esito", "").upper() == "FAIL")
                    pending = total_tests - passed - failed

                    stats["pass_rate"] = (passed / len(results) * 100) if results else 0
                    stats["pending"] = pending
                    stats["failed"] = failed

                    # Get run info for date
                    run_info = client.get_run_info(last_run)
                    if run_info:
                        stats["last_run_date"] = run_info.get("timestamp", "?")

        except Exception as e:
            logger.warning(f"Could not get stats for {project}: {e}")

        # Calculate priority score
        score = 0

        # High priority: has pending tests
        if stats["pending"] > 0:
            score += 30
            stats["priority_reason"].append(f"{stats['pending']} test pending")

        # High priority: has failed tests
        if stats["failed"] > 0:
            score += 20
            stats["priority_reason"].append(f"{stats['failed']} test falliti")

        # Medium priority: low pass rate
        if stats["pass_rate"] is not None and stats["pass_rate"] < 80:
            score += 15
            stats["priority_reason"].append(f"pass rate {stats['pass_rate']:.0f}%")

        # Low priority: never run
        if stats["last_run"] is None:
            score += 10
            stats["priority_reason"].append("mai eseguito")

        # Base score from test count (more tests = slightly higher priority)
        score += min(stats["total_tests"] / 10, 5)

        stats["priority_score"] = score
        project_stats.append(stats)

    # Sort by priority score (descending)
    project_stats.sort(key=lambda x: x["priority_score"], reverse=True)

    # Build result
    result = "## Analisi Progetti\n\n"

    for i, stats in enumerate(project_stats):
        is_suggested = (i == 0)
        prefix = "**>>> " if is_suggested else ""
        suffix = " <<<**" if is_suggested else ""

        result += f"{prefix}{stats['name']}{suffix}\n"
        result += f"- Test totali: {stats['total_tests']}\n"

        if stats["last_run"]:
            result += f"- Ultima RUN: #{stats['last_run']}"
            if stats["last_run_date"]:
                result += f" ({stats['last_run_date']})"
            result += "\n"

            if stats["pass_rate"] is not None:
                result += f"- Pass rate: {stats['pass_rate']:.0f}%\n"
            if stats["pending"] > 0:
                result += f"- Pending: {stats['pending']}\n"
            if stats["failed"] > 0:
                result += f"- Falliti: {stats['failed']}\n"
        else:
            result += "- *Nessuna RUN eseguita*\n"

        result += "\n"

    # Add suggestion
    suggested = project_stats[0]
    result += "---\n\n"
    result += f"## Suggerimento\n\n"
    result += f"**Consiglio di testare `{suggested['name']}`**"

    if suggested["priority_reason"]:
        result += f" perché: {', '.join(suggested['priority_reason'])}"

    result += f"\n\nPer eseguire: *\"Esegui i test pending di {suggested['name']}\"*"

    return [TextContent(type="text", text=result)]


async def handle_list_tests(arguments: dict) -> list[TextContent]:
    """Handle list_tests tool."""
    project = arguments.get("project")
    test_set = arguments.get("test_set", "standard")
    filter_text = arguments.get("filter", "").lower()

    if not project:
        return [TextContent(
            type="text",
            text="Errore: specificare il nome del progetto"
        )]

    if project not in get_available_projects():
        return [TextContent(
            type="text",
            text=f"Progetto '{project}' non trovato. Usa list_projects per vedere i progetti disponibili."
        )]

    tests = get_project_tests(project, test_set)

    if not tests:
        return [TextContent(
            type="text",
            text=f"Nessun test trovato per il progetto '{project}'."
        )]

    # Apply filter if provided
    if filter_text:
        filtered_tests = []
        for test in tests:
            test_id = test.get("id", "").lower()
            description = test.get("description", "").lower()
            question = test.get("question", "").lower()
            category = test.get("category", "").lower()

            if (filter_text in test_id or
                filter_text in description or
                filter_text in question or
                filter_text in category):
                filtered_tests.append(test)

        if not filtered_tests:
            return [TextContent(
                type="text",
                text=f"Nessun test trovato con filtro '{filter_text}' nel progetto '{project}'."
            )]

        result = f"Test per **{project}** filtrati per '{filter_text}' ({len(filtered_tests)} trovati):\n\n"

        # List all filtered tests (no category grouping for filtered results)
        for test in filtered_tests:
            test_id = test.get("id", "?")
            description = test.get("description", test.get("question", ""))[:80]
            result += f"- `{test_id}`: {description}\n"

        # Add hint for running these tests
        if len(filtered_tests) <= 10:
            test_ids = ",".join([t.get("id", "") for t in filtered_tests if t.get("id")])
            result += f"\n---\nPer eseguire questi test:\n"
            result += f"*\"Esegui i test {test_ids} su {project}\"*"

        return [TextContent(type="text", text=result)]

    # No filter - show grouped by category
    result = f"Test per **{project}** ({len(tests)} totali):\n\n"

    # Group by category if available
    by_category = {}
    for test in tests:
        category = test.get("category", "Uncategorized")
        if category not in by_category:
            by_category[category] = []
        by_category[category].append(test)

    for category, cat_tests in sorted(by_category.items()):
        result += f"### {category}\n"
        for test in cat_tests[:10]:  # Limit to first 10 per category
            test_id = test.get("id", "?")
            description = test.get("description", test.get("question", ""))[:60]
            result += f"- `{test_id}`: {description}...\n"
        if len(cat_tests) > 10:
            result += f"  ... e altri {len(cat_tests) - 10} test\n"
        result += "\n"

    return [TextContent(type="text", text=result)]


async def handle_trigger_circleci(arguments: dict) -> list[TextContent]:
    """Handle trigger_circleci tool."""
    from src.circleci_client import CircleCIClient

    project = arguments.get("project")
    test_set = arguments.get("test_set", "standard")
    mode = arguments.get("mode", "auto")
    tests = arguments.get("tests", "pending")
    new_run = arguments.get("new_run", False)
    test_limit = arguments.get("test_limit", 0)
    test_ids = arguments.get("test_ids", "")
    prompt_version = arguments.get("prompt_version", "")
    parallel = arguments.get("parallel", False)
    repeat = arguments.get("repeat", 1)

    # Se parallel=True, usa 3 container CircleCI per velocizzare
    native_parallelism = 3 if parallel else 0

    # Valida repeat
    repeat = max(1, min(5, repeat))

    if not project:
        return [TextContent(
            type="text",
            text="Errore: specificare il nome del progetto"
        )]

    # Validate project exists
    if project not in get_available_projects():
        return [TextContent(
            type="text",
            text=f"Progetto '{project}' non trovato. Usa list_projects per vedere i progetti disponibili."
        )]

    # If a non-standard test_set is specified, use the tests_file parameter instead of test_ids
    tests_file = "tests.json"
    if test_set != "standard" and not test_ids:
        tests_file = f"tests_{test_set}.json"
        tests = "all"  # Run all tests from the file
        logger.info(f"Using test set file '{tests_file}'")

    # Initialize CircleCI client
    client = CircleCIClient()

    if not client.is_available():
        return [TextContent(
            type="text",
            text="Errore: CircleCI non configurato. Assicurarsi che CIRCLECI_TOKEN sia impostato."
        )]

    # Se repeat > 1, lancia multiple pipeline
    pipelines_launched = []
    for i in range(repeat):
        success, response = client.trigger_pipeline(
            project=project,
            mode=mode,
            tests=tests,
            new_run=new_run,
            test_limit=test_limit,
            test_ids=test_ids,
            tests_file=tests_file,
            prompt_version=prompt_version,
            native_parallelism=native_parallelism
        )
        if success:
            pipelines_launched.append({
                "id": response.get("id", "?"),
                "number": response.get("number", "?")
            })
        else:
            error = response.get("error", "Errore sconosciuto") if response else "Errore sconosciuto"
            if pipelines_launched:
                # Alcune pipeline sono partite, riporta comunque
                break
            else:
                return [TextContent(
                    type="text",
                    text=f"Errore nell'avvio della pipeline: {error}"
                )]

    if len(pipelines_launched) == 1:
        # Singola pipeline
        p = pipelines_launched[0]
        pipeline_url = f"https://app.circleci.com/pipelines/gh/corradofrancolini/chatbot-tester-private/{p['number']}"

        result = f"""Pipeline avviata con successo!

**Dettagli:**
- Pipeline ID: `{p['id']}`
- Numero: #{p['number']}
- Progetto: {project}
- Modalita': {mode}
- Test: {tests}
- Nuova RUN: {'Si' if new_run else 'No'}
{f'- Test set: {test_set}' if test_set != 'standard' else ''}
{f'- Prompt version: {prompt_version}' if prompt_version else ''}
{f'- Parallelismo: {native_parallelism} container' if native_parallelism > 0 else ''}
{f'- Limite test: {test_limit}' if test_limit > 0 else ''}
{f'- Test specifici: {test_ids}' if test_ids else ''}

**Link:** {pipeline_url}

Usa `get_workflow_status` con pipeline_id `{p['id']}` per monitorare lo stato."""
    else:
        # Multiple pipeline
        result = f"""**{len(pipelines_launched)} Pipeline avviate con successo!**

**Configurazione comune:**
- Progetto: {project}
- Modalita': {mode}
- Test: {tests}
- Nuova RUN: Si (una per pipeline)
{f'- Test set: {test_set}' if test_set != 'standard' else ''}
{f'- Prompt version: {prompt_version}' if prompt_version else ''}
{f'- Parallelismo: {native_parallelism} container' if native_parallelism > 0 else ''}

**Pipeline lanciate:**
"""
        for i, p in enumerate(pipelines_launched, 1):
            url = f"https://app.circleci.com/pipelines/gh/corradofrancolini/chatbot-tester-private/{p['number']}"
            result += f"{i}. **#{p['number']}** - {url}\n"

        result += f"\nOgni pipeline creerà una RUN separata su Google Sheets per confronto A/B."

    return [TextContent(type="text", text=result)]


async def handle_get_pipeline_status(arguments: dict) -> list[TextContent]:
    """Handle get_pipeline_status tool."""
    from src.circleci_client import CircleCIClient

    limit = arguments.get("limit", 5)

    client = CircleCIClient()

    if not client.is_available():
        return [TextContent(
            type="text",
            text="Errore: CircleCI non configurato. Assicurarsi che CIRCLECI_TOKEN sia impostato."
        )]

    pipelines = client.list_pipelines(limit=limit)

    if not pipelines:
        return [TextContent(
            type="text",
            text="Nessuna pipeline trovata."
        )]

    result = f"Ultime {len(pipelines)} pipeline:\n\n"

    for p in pipelines:
        created = p.created_at[:19].replace("T", " ") if p.created_at else "?"
        result += f"{p.status_icon} **#{p.number}** [{p.state}] - {created}\n"
        result += f"   ID: `{p.id}`\n"
        result += f"   URL: {p.url}\n\n"

    return [TextContent(type="text", text=result)]


async def handle_get_workflow_status(arguments: dict) -> list[TextContent]:
    """Handle get_workflow_status tool."""
    from src.circleci_client import CircleCIClient

    pipeline_id = arguments.get("pipeline_id")

    if not pipeline_id:
        return [TextContent(
            type="text",
            text="Errore: specificare pipeline_id"
        )]

    client = CircleCIClient()

    if not client.is_available():
        return [TextContent(
            type="text",
            text="Errore: CircleCI non configurato. Assicurarsi che CIRCLECI_TOKEN sia impostato."
        )]

    # Get pipeline info
    pipeline = client.get_pipeline(pipeline_id)
    if not pipeline:
        return [TextContent(
            type="text",
            text=f"Pipeline {pipeline_id} non trovata."
        )]

    # Get workflows
    workflows = client.get_pipeline_workflows(pipeline_id)

    result = f"""**Pipeline #{pipeline.number}** {pipeline.status_icon}

- Stato: {pipeline.state}
- Creata: {pipeline.created_at[:19].replace('T', ' ') if pipeline.created_at else '?'}
- URL: {pipeline.url}

"""

    if workflows:
        result += "**Workflows:**\n\n"
        for w in workflows:
            result += f"{w.status_icon} **{w.name}** [{w.status}]\n"

            # Get jobs for workflow
            jobs = client.get_workflow_jobs(w.id)
            if jobs:
                for job in jobs:
                    job_status = job.get("status", "unknown")
                    job_name = job.get("name", "?")
                    job_icon = {
                        "running": "...",
                        "success": "ok",
                        "failed": "X",
                        "blocked": "-",
                        "canceled": "X",
                        "not_run": "-"
                    }.get(job_status, "?")
                    result += f"   [{job_icon}] {job_name}\n"
            result += "\n"
    else:
        result += "*Nessun workflow ancora avviato*\n"

    return [TextContent(type="text", text=result)]


def get_sheets_client(project: str):
    """Get a GoogleSheetsClient for a project."""
    from src.sheets_client import GoogleSheetsClient
    from src.config_loader import ConfigLoader
    from pathlib import Path

    logger.info(f"get_sheets_client called for project: {project}")

    # Load project configuration
    project_root = Path(__file__).parent.parent
    logger.info(f"Project root: {project_root}")

    loader = ConfigLoader(str(project_root))
    logger.info(f"ConfigLoader created")

    project_config = loader.load_project(project)
    logger.info(f"Project config loaded: {project_config.name}")

    # Get Google Sheets config
    gs_config = project_config.google_sheets
    logger.info(f"Google Sheets enabled: {gs_config.enabled}, spreadsheet_id: {gs_config.spreadsheet_id}")

    if not gs_config.enabled:
        raise Exception(f"Google Sheets not enabled for project {project}")

    # Resolve credentials path relative to project root
    credentials_path = gs_config.credentials_path or "config/oauth_credentials.json"
    full_credentials_path = project_root / credentials_path
    logger.info(f"Credentials path: {full_credentials_path}, exists: {full_credentials_path.exists()}")

    client = GoogleSheetsClient(
        credentials_path=str(full_credentials_path),
        spreadsheet_id=gs_config.spreadsheet_id,
        drive_folder_id=gs_config.drive_folder_id
    )
    logger.info("GoogleSheetsClient created, authenticating...")

    # Authenticate
    if not client.authenticate():
        raise Exception("Failed to authenticate with Google Sheets")

    logger.info("Authentication successful")
    return client


async def handle_list_runs(arguments: dict) -> list[TextContent]:
    """Handle list_runs tool."""
    project = arguments.get("project")

    if not project:
        return [TextContent(type="text", text="Errore: specificare il nome del progetto")]

    if project not in get_available_projects():
        return [TextContent(
            type="text",
            text=f"Progetto '{project}' non trovato. Usa list_projects per vedere i progetti disponibili."
        )]

    try:
        client = get_sheets_client(project)
        runs = client.get_all_run_numbers()

        if not runs:
            return [TextContent(type="text", text=f"Nessuna RUN trovata per il progetto '{project}'.")]

        result = f"**RUN disponibili per {project}:**\n\n"

        # Get info for last 10 runs (most recent first)
        for run_num in sorted(runs, reverse=True)[:10]:
            info = client.get_run_info(run_num)
            if info:
                timestamp = info.get("timestamp", "?")
                env = info.get("env", "?")
                mode = info.get("mode", "?")
                total = info.get("total_tests", 0)
                passed = info.get("passed", 0)
                failed = info.get("failed", 0)
                pass_rate = (passed / total * 100) if total > 0 else 0
                result += f"- **RUN {run_num}** ({timestamp}) - {env}/{mode}\n"
                result += f"  {passed}/{total} passed ({pass_rate:.0f}%), {failed} failed\n"
            else:
                result += f"- **RUN {run_num}**\n"

        if len(runs) > 10:
            result += f"\n... e altre {len(runs) - 10} RUN precedenti"

        return [TextContent(type="text", text=result)]
    except Exception as e:
        logger.error(f"Error listing runs: {e}")
        return [TextContent(type="text", text=f"Errore nel recupero delle RUN: {str(e)}")]


async def handle_get_run_results(arguments: dict) -> list[TextContent]:
    """Handle get_run_results tool."""
    project = arguments.get("project")
    run_number = arguments.get("run_number")

    if not project:
        return [TextContent(type="text", text="Errore: specificare il nome del progetto")]

    if project not in get_available_projects():
        return [TextContent(
            type="text",
            text=f"Progetto '{project}' non trovato."
        )]

    try:
        client = get_sheets_client(project)

        # Get latest run if not specified
        if not run_number:
            runs = client.get_all_run_numbers()
            if not runs:
                return [TextContent(type="text", text="Nessuna RUN trovata.")]
            run_number = max(runs)

        # Set active run and get results
        client.active_run = run_number
        results = client.get_all_results()

        if not results:
            return [TextContent(type="text", text=f"Nessun risultato trovato per RUN {run_number}.")]

        # Calculate stats
        total = len(results)
        passed = sum(1 for r in results if r.get("esito", "").upper() == "PASS")
        failed = sum(1 for r in results if r.get("esito", "").upper() == "FAIL")
        pending = total - passed - failed
        pass_rate = (passed / total * 100) if total > 0 else 0

        result = f"""**Risultati RUN {run_number}** per {project}

**Statistiche:**
- Totale: {total} test
- Passati: {passed} ({pass_rate:.1f}%)
- Falliti: {failed}
- Pending: {pending}

**Dettaglio test:**

"""
        # Group by status
        for r in results[:30]:  # Limit to 30 results
            test_id = r.get("test_id", "?")
            esito = r.get("esito", "?").upper()
            icon = "ok" if esito == "PASS" else "X" if esito == "FAIL" else "-"
            result += f"[{icon}] `{test_id}`: {esito}\n"

        if len(results) > 30:
            result += f"\n... e altri {len(results) - 30} test"

        return [TextContent(type="text", text=result)]
    except Exception as e:
        logger.error(f"Error getting run results: {e}")
        return [TextContent(type="text", text=f"Errore nel recupero dei risultati: {str(e)}")]


async def handle_get_failed_tests(arguments: dict) -> list[TextContent]:
    """Handle get_failed_tests tool."""
    project = arguments.get("project")
    run_number = arguments.get("run_number")

    if not project:
        return [TextContent(type="text", text="Errore: specificare il nome del progetto")]

    if project not in get_available_projects():
        return [TextContent(
            type="text",
            text=f"Progetto '{project}' non trovato."
        )]

    try:
        client = get_sheets_client(project)

        # Get latest run if not specified
        if not run_number:
            runs = client.get_all_run_numbers()
            if not runs:
                return [TextContent(type="text", text="Nessuna RUN trovata.")]
            run_number = max(runs)

        # Set active run and get results
        client.active_run = run_number
        results = client.get_all_results()

        # Filter failed tests
        failed_tests = [r for r in results if r.get("esito", "").upper() == "FAIL"]

        if not failed_tests:
            return [TextContent(type="text", text=f"Nessun test fallito nella RUN {run_number}!")]

        result = f"""**Test Falliti - RUN {run_number}** ({len(failed_tests)} fallimenti)

"""
        for r in failed_tests:
            test_id = r.get("test_id", "?")
            question = r.get("question", r.get("domanda", ""))[:80]
            notes = r.get("notes", r.get("note", ""))[:100]
            result += f"**{test_id}**\n"
            if question:
                result += f"  Domanda: {question}...\n"
            if notes:
                result += f"  Note: {notes}...\n"
            result += "\n"

        return [TextContent(type="text", text=result)]
    except Exception as e:
        logger.error(f"Error getting failed tests: {e}")
        return [TextContent(type="text", text=f"Errore nel recupero dei test falliti: {str(e)}")]


async def handle_compare_runs(arguments: dict) -> list[TextContent]:
    """Handle compare_runs tool."""
    from src.comparison import RunComparator

    project = arguments.get("project")
    run_a = arguments.get("run_a")
    run_b = arguments.get("run_b")

    if not project:
        return [TextContent(type="text", text="Errore: specificare il nome del progetto")]

    if project not in get_available_projects():
        return [TextContent(
            type="text",
            text=f"Progetto '{project}' non trovato."
        )]

    try:
        comparator = RunComparator(project)

        # If no runs specified, compare latest two
        if not run_a and not run_b:
            comparison = comparator.compare_latest()
            if not comparison:
                return [TextContent(type="text", text="Servono almeno 2 RUN per il confronto.")]
        elif run_a and run_b:
            comparison = comparator.compare(run_a, run_b)
        else:
            # Get latest run for comparison
            client = get_sheets_client(project)
            runs = client.get_all_run_numbers()
            if not runs:
                return [TextContent(type="text", text="Nessuna RUN trovata.")]
            if run_a:
                run_b = max(runs)
            else:
                run_a = sorted(runs)[-2] if len(runs) > 1 else runs[0]
                run_b = max(runs)
            comparison = comparator.compare(run_a, run_b)

        # Format results
        result = f"""**Confronto RUN {comparison.run_a} vs RUN {comparison.run_b}**

**Riepilogo:**
- RUN {comparison.run_a}: {comparison.passed_a}/{comparison.total_tests_a} passed ({comparison.pass_rate_a:.1f}%)
- RUN {comparison.run_b}: {comparison.passed_b}/{comparison.total_tests_b} passed ({comparison.pass_rate_b:.1f}%)
- Delta: {comparison.pass_rate_delta:+.1f}%

"""
        if comparison.regressions:
            result += f"**Regressioni ({len(comparison.regressions)}):** (erano PASS, ora FAIL)\n"
            for r in comparison.regressions[:10]:
                result += f"- `{r.test_id}`: {r.old_result} -> {r.new_result}\n"
            if len(comparison.regressions) > 10:
                result += f"  ... e altre {len(comparison.regressions) - 10}\n"
            result += "\n"

        if comparison.improvements:
            result += f"**Miglioramenti ({len(comparison.improvements)}):** (erano FAIL, ora PASS)\n"
            for r in comparison.improvements[:10]:
                result += f"- `{r.test_id}`: {r.old_result} -> {r.new_result}\n"
            if len(comparison.improvements) > 10:
                result += f"  ... e altri {len(comparison.improvements) - 10}\n"
            result += "\n"

        if not comparison.regressions and not comparison.improvements:
            result += "*Nessun cambiamento significativo tra le due RUN.*\n"

        return [TextContent(type="text", text=result)]
    except Exception as e:
        logger.error(f"Error comparing runs: {e}")
        return [TextContent(type="text", text=f"Errore nel confronto delle RUN: {str(e)}")]


# ====== NUOVI HANDLER FOOL-PROOF ======

async def handle_start_test_session(arguments: dict) -> list[TextContent]:
    """Handle start_test_session tool - wizard guidato per testare un progetto."""
    project = arguments.get("project")

    if not project:
        return [TextContent(type="text", text="Errore: specificare il nome del progetto")]

    if project not in get_available_projects():
        projects = get_available_projects()
        return [TextContent(
            type="text",
            text=f"Progetto '{project}' non trovato.\n\nProgetti disponibili: {', '.join(projects)}"
        )]

    # Get test sets with counts
    test_sets = get_available_test_sets(project)
    run_config = get_run_config(project)

    # Try to get current run info from Google Sheets
    current_run = run_config.get("active_run", 0)
    env = run_config.get("env", "DEV")
    prompt_version = run_config.get("prompt_version", "N/A")

    result = f"Ecco la situazione per **{project}**:\n\n"

    # For each test set, show details
    for name, total_count in sorted(test_sets.items()):
        result += f"📋 **{name}** ({total_count} test)\n"

        # Try to get executed count from Sheets
        try:
            if current_run > 0:
                client = get_sheets_client(project)
                client.active_run = current_run
                results = client.get_all_results()

                # Filter results for this test set
                prefix = "PARA_" if name == "paraphrase" else "GRD_" if name == "ggp" else "TEST_"
                set_results = [r for r in results if r.get("test_id", "").startswith(prefix)]

                if set_results:
                    passed = sum(1 for r in set_results if r.get("esito", "").upper() == "PASS")
                    failed = sum(1 for r in set_results if r.get("esito", "").upper() == "FAIL")
                    pending = total_count - len(set_results)
                    pass_rate = (passed / len(set_results) * 100) if set_results else 0
                    result += f"   - {pending} pending, {failed} falliti, pass rate {pass_rate:.0f}%\n"
                else:
                    result += f"   - Tutti pending\n"
            else:
                result += f"   - Tutti pending (nessuna RUN attiva)\n"
        except Exception as e:
            logger.warning(f"Could not get stats for {project}/{name}: {e}")
            result += f"   - Stato non disponibile\n"

        result += "\n"

    # Add run info
    if current_run > 0:
        result += f"📈 **RUN attiva:** #{current_run}\n"
        result += f"📝 **Prompt:** {prompt_version}\n"
        result += f"🌍 **Ambiente:** {env}\n\n"

    # Add suggestion
    result += "---\n\n"
    if test_sets.get("standard", 0) > 0:
        result += "💡 **Consiglio:** eseguire i test pending del set **standard**.\n\n"
    result += "**Quale test set vuoi usare?** (standard, paraphrase, ggp)"

    return [TextContent(type="text", text=result)]


async def handle_prepare_test_run(arguments: dict) -> list[TextContent]:
    """Handle prepare_test_run tool - prepara e mostra riepilogo per conferma."""
    project = arguments.get("project")
    test_set = arguments.get("test_set", "standard")
    tests_filter = arguments.get("tests", "pending")

    if not project:
        return [TextContent(type="text", text="Errore: specificare il nome del progetto")]

    if project not in get_available_projects():
        return [TextContent(type="text", text=f"Progetto '{project}' non trovato.")]

    # Load configs
    run_config = get_run_config(project)
    all_tests = get_project_tests(project, test_set)

    if not all_tests:
        return [TextContent(type="text", text=f"Nessun test trovato per il set '{test_set}'.")]

    # Count tests to run
    test_count = len(all_tests)
    executed_ids = set()
    failed_ids = set()

    try:
        current_run = run_config.get("active_run", 0)
        if current_run > 0:
            client = get_sheets_client(project)
            client.active_run = current_run
            results = client.get_all_results()
            executed_ids = {r.get("test_id") for r in results if r.get("test_id")}
            failed_ids = {r.get("test_id") for r in results
                         if r.get("esito", "").upper() == "FAIL"}
    except Exception as e:
        logger.warning(f"Could not get executed tests: {e}")

    # Filter tests based on mode
    if tests_filter == "pending":
        tests_to_run = [t for t in all_tests if t.get("id") not in executed_ids]
        test_count = len(tests_to_run)
    elif tests_filter == "failed":
        tests_to_run = [t for t in all_tests if t.get("id") in failed_ids]
        test_count = len(tests_to_run)
    else:  # all
        test_count = len(all_tests)

    if test_count == 0:
        return [TextContent(
            type="text",
            text=f"Nessun test da eseguire con filtro '{tests_filter}' per il set '{test_set}'."
        )]

    # Determine if new RUN
    current_run = run_config.get("active_run", 0)
    new_run = (tests_filter == "all") or (current_run == 0)
    next_run = current_run + 1 if new_run else current_run

    # Auto-determine parallelism
    use_parallel = should_use_parallel(test_count)
    estimated_time = estimate_duration(test_count, use_parallel)

    # Sheet name
    sheet_name = f"RUN_{next_run}"

    # Build summary
    env = run_config.get("env", "DEV")
    prompt_version = run_config.get("prompt_version", "N/A")

    result = f"""📋 **RIEPILOGO ESECUZIONE**

🎯 **Progetto:** {project}
🌍 **Ambiente:** {env}
📝 **Prompt version:** {prompt_version}

📊 **Test Set:** {test_set}
   - {test_count} test da eseguire ({tests_filter})
   - Modalità: auto

📈 **RUN:** #{next_run} {'(NUOVA)' if new_run else '(ESISTENTE)'}
📄 **Google Sheets:** Foglio "{sheet_name}"

⚡ **Parallelismo:** {'SÌ (3 container)' if use_parallel else 'NO (singolo container)'}
⏱️ **Tempo stimato:** ~{estimated_time}

---
**Procedo con l'esecuzione?** (sì/no)"""

    return [TextContent(type="text", text=result)]


async def handle_execute_test_run(arguments: dict) -> list[TextContent]:
    """Handle execute_test_run tool - esegue dopo conferma."""
    from src.circleci_client import CircleCIClient

    project = arguments.get("project")
    test_set = arguments.get("test_set", "standard")
    tests_filter = arguments.get("tests", "pending")

    if not project:
        return [TextContent(type="text", text="Errore: specificare il nome del progetto")]

    if project not in get_available_projects():
        return [TextContent(type="text", text=f"Progetto '{project}' non trovato.")]

    # Load configs
    run_config = get_run_config(project)
    all_tests = get_project_tests(project, test_set)

    # Count tests to determine parallelism
    test_count = len(all_tests)

    try:
        current_run = run_config.get("active_run", 0)
        if current_run > 0 and tests_filter in ["pending", "failed"]:
            client = get_sheets_client(project)
            client.active_run = current_run
            results = client.get_all_results()
            executed_ids = {r.get("test_id") for r in results if r.get("test_id")}
            failed_ids = {r.get("test_id") for r in results
                         if r.get("esito", "").upper() == "FAIL"}

            if tests_filter == "pending":
                test_count = len([t for t in all_tests if t.get("id") not in executed_ids])
            elif tests_filter == "failed":
                test_count = len([t for t in all_tests if t.get("id") in failed_ids])
    except Exception as e:
        logger.warning(f"Could not count tests: {e}")

    # Auto-determine parallelism
    use_parallel = should_use_parallel(test_count)
    native_parallelism = 3 if use_parallel else 0

    # Determine new_run
    new_run = (tests_filter == "all")

    # Build tests_file
    tests_file = "tests.json" if test_set == "standard" else f"tests_{test_set}.json"

    # Trigger CircleCI
    circleci = CircleCIClient()

    if not circleci.is_available():
        return [TextContent(
            type="text",
            text="❌ Errore: CircleCI non configurato. Assicurarsi che CIRCLECI_TOKEN sia impostato."
        )]

    success, response = circleci.trigger_pipeline(
        project=project,
        mode="auto",
        tests=tests_filter,
        new_run=new_run,
        tests_file=tests_file,
        native_parallelism=native_parallelism
    )

    if not success:
        error = response.get("error", "Errore sconosciuto") if response else "Errore sconosciuto"
        return [TextContent(type="text", text=f"❌ Errore nell'avvio della pipeline: {error}")]

    pipeline_id = response.get("id", "?")
    pipeline_number = response.get("number", "?")
    pipeline_url = f"https://app.circleci.com/pipelines/gh/corradofrancolini/chatbot-tester-private/{pipeline_number}"

    result = f"""✅ **Pipeline avviata!**

🔗 **URL:** {pipeline_url}
🆔 **ID:** `{pipeline_id}`

{'⚡ Parallelismo attivo (3 container)' if use_parallel else ''}

⏰ **Chiedimi "come sta andando?" tra 5-10 minuti** per un aggiornamento."""

    return [TextContent(type="text", text=result)]


async def handle_check_pipeline_status(arguments: dict) -> list[TextContent]:
    """Handle check_pipeline_status tool - controlla stato pipeline."""
    from src.circleci_client import CircleCIClient

    pipeline_id = arguments.get("pipeline_id")

    if not pipeline_id:
        return [TextContent(type="text", text="Errore: specificare pipeline_id")]

    client = CircleCIClient()

    if not client.is_available():
        return [TextContent(
            type="text",
            text="❌ Errore: CircleCI non configurato."
        )]

    # Get pipeline info
    pipeline = client.get_pipeline(pipeline_id)
    if not pipeline:
        return [TextContent(type="text", text=f"Pipeline `{pipeline_id}` non trovata.")]

    # Get workflows
    workflows = client.get_pipeline_workflows(pipeline_id)

    # Check if all done
    all_done = all(w.status in ["success", "failed", "canceled"]
                   for w in workflows) if workflows else False

    if all_done:
        success = all(w.status == "success" for w in workflows)
        icon = "✅" if success else "❌"
        status = "SUCCESS" if success else "FAILED"

        return [TextContent(
            type="text",
            text=f"""{icon} **Pipeline completata!**

Stato: **{status}**
URL: {pipeline.url}

Vuoi vedere i risultati dei test? Chiedimi "mostrami i risultati di [progetto]"."""
        )]

    # Still running
    jobs_info = ""
    if workflows:
        try:
            jobs = client.get_workflow_jobs(workflows[0].id)
            running = [j for j in jobs if j.get("status") == "running"]
            if running:
                jobs_info = f"\nJob in esecuzione: **{running[0].get('name', '?')}**"
        except Exception:
            pass

    return [TextContent(
        type="text",
        text=f"""⏳ **Pipeline in esecuzione...**

Stato: **{workflows[0].status if workflows else 'starting'}**{jobs_info}
URL: {pipeline.url}

⏰ **Chiedimi di nuovo tra 3-5 minuti** per un aggiornamento."""
    )]


async def handle_show_results(arguments: dict) -> list[TextContent]:
    """Handle show_results tool - mostra risultati user-friendly."""
    project = arguments.get("project")
    run_number = arguments.get("run_number")

    if not project:
        return [TextContent(type="text", text="Errore: specificare il nome del progetto")]

    if project not in get_available_projects():
        return [TextContent(type="text", text=f"Progetto '{project}' non trovato.")]

    try:
        client = get_sheets_client(project)

        # Get latest run if not specified
        if not run_number:
            runs = client.get_all_run_numbers()
            if not runs:
                return [TextContent(type="text", text="Nessuna RUN trovata.")]
            run_number = max(runs)

        # Set active run and get results
        client.active_run = run_number
        results = client.get_all_results()

        if not results:
            return [TextContent(type="text", text=f"Nessun risultato trovato per RUN {run_number}.")]

        # Calculate stats
        total = len(results)
        passed = sum(1 for r in results if r.get("esito", "").upper() == "PASS")
        failed = sum(1 for r in results if r.get("esito", "").upper() == "FAIL")
        pass_rate = (passed / total * 100) if total > 0 else 0

        # Choose icon based on pass rate
        if pass_rate >= 90:
            icon = "✅"
        elif pass_rate >= 70:
            icon = "⚠️"
        else:
            icon = "❌"

        result = f"""{icon} **Risultati RUN #{run_number} - {project}**

**Pass rate: {pass_rate:.0f}%** ({passed}/{total})

"""
        # Show failed tests
        failed_tests = [r for r in results if r.get("esito", "").upper() == "FAIL"]

        if failed_tests:
            result += f"❌ **{len(failed_tests)} test falliti:**\n"
            for r in failed_tests[:10]:
                test_id = r.get("test_id", "?")
                question = r.get("question", r.get("domanda", ""))[:50]
                result += f"- `{test_id}`: {question}...\n"
            if len(failed_tests) > 10:
                result += f"  ... e altri {len(failed_tests) - 10}\n"
            result += "\n"

        # Add suggestions
        result += "---\n"
        if failed_tests:
            result += f"💡 Vuoi ri-eseguire solo i {len(failed_tests)} test falliti? Dimmelo!"
        else:
            result += "🎉 Tutti i test sono passati!"

        return [TextContent(type="text", text=result)]

    except Exception as e:
        logger.error(f"Error showing results: {e}")
        return [TextContent(type="text", text=f"Errore nel recupero dei risultati: {str(e)}")]
