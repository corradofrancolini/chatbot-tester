#!/usr/bin/env python3
"""
Chatbot Tester - Entry Point Principale

Comando principale per avviare il tool di testing chatbot.

Usage:
    python run.py                          # Menu interattivo
    python run.py --new-project            # Wizard nuovo progetto
    python run.py --project=my-chatbot     # Apri progetto specifico
    python run.py --project=my-chatbot --mode=auto    # Modalità specifica
    python run.py --project=my-chatbot --new-run      # Forza nuova RUN
    python run.py --lang=en                # In inglese
    python run.py --help                   # Aiuto
"""

import asyncio
import argparse
import os
import sys
import yaml
from pathlib import Path
from datetime import datetime
from typing import Optional

# Aggiungi src al path
sys.path.insert(0, str(Path(__file__).parent))

from src.config_loader import ConfigLoader, ProjectConfig, RunConfig
from src.tester import ChatbotTester, TestMode
from src.ui import ConsoleUI, MenuItem, get_ui
from src.i18n import get_i18n, set_language, t
from src.health import HealthChecker, ServiceStatus
from src.circleci_client import CircleCIClient
from src.cli_utils import (
    ExitCode, suggest_project, NextSteps,
    confirm_action, ConfirmLevel, handle_keyboard_interrupt,
    print_startup_feedback
)

# ═══════════════════════════════════════════════════════════════════════════════
# HELPER: Project validation with suggestions
# ═══════════════════════════════════════════════════════════════════════════════

def validate_project(project_name: str, ui: ConsoleUI) -> bool:
    """
    Valida progetto con suggerimenti 'did you mean'.

    Returns:
        True se progetto valido, False altrimenti (con messaggio errore)
    """
    projects_dir = Path(__file__).parent / "projects"

    if not projects_dir.exists():
        ui.error("Directory projects/ non trovata")
        return False

    project_dir = projects_dir / project_name
    project_file = project_dir / "project.yaml"

    if project_file.exists():
        return True

    # Progetto non trovato - suggerisci alternativa
    suggestion = suggest_project(project_name, projects_dir)

    if suggestion:
        ui.error(f"Progetto '{project_name}' non trovato. Intendevi '{suggestion}'?")
        ui.muted(f"  Usa: chatbot-tester -p {suggestion}")
    else:
        ui.error(f"Progetto '{project_name}' non trovato")
        available = [
            p.name for p in projects_dir.iterdir()
            if p.is_dir() and (p / "project.yaml").exists()
        ]
        if available:
            ui.muted(f"  Progetti disponibili: {', '.join(available)}")

    return False


def parse_args():
    """Parse command line arguments - clig.dev compliant"""
    import os

    parser = argparse.ArgumentParser(
        prog='chatbot-tester',
        description='Chatbot Tester - Test automatizzati per chatbot',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Esempi:
  %(prog)s                                   Menu interattivo
  %(prog)s -p my-chatbot -m auto             Esegui test in modalita auto
  %(prog)s -p my-chatbot --compare           Confronta ultime 2 run
  %(prog)s -p my-chatbot --export html       Esporta report HTML
  %(prog)s --new-project                     Wizard nuovo progetto

Variabili ambiente:
  NO_COLOR      Disabilita output colorato
  DEBUG         Abilita output di debug (equivale a --debug)

Documentazione: https://github.com/user/chatbot-tester
        """
    )

    # ═══════════════════════════════════════════════════════════════════
    # Progetto
    # ═══════════════════════════════════════════════════════════════════
    project_group = parser.add_argument_group('Progetto')
    project_group.add_argument(
        '-p', '--project',
        type=str,
        metavar='NAME',
        help='Nome progetto (es: -p my-chatbot)'
    )
    project_group.add_argument(
        '--new-project',
        action='store_true',
        help='Avvia wizard creazione progetto'
    )

    # ═══════════════════════════════════════════════════════════════════
    # Test Execution
    # ═══════════════════════════════════════════════════════════════════
    test_group = parser.add_argument_group('Esecuzione Test')
    test_group.add_argument(
        '-m', '--mode',
        type=str,
        choices=['train', 'assisted', 'auto'],
        metavar='MODE',
        help='Modalita: train, assisted, auto'
    )
    test_group.add_argument(
        '-t', '--test',
        type=str,
        metavar='ID',
        help='Esegui singolo test (es: -t TC001)'
    )
    test_group.add_argument(
        '--tests',
        type=str,
        default='pending',
        choices=['all', 'pending', 'failed'],
        help='Filtro test: all, pending (default), failed'
    )
    test_group.add_argument(
        '--new-run',
        action='store_true',
        help='Forza nuova RUN invece di continuare'
    )
    test_group.add_argument(
        '-n', '--dry-run',
        action='store_true',
        help='Simula senza eseguire (mostra cosa farebbe)'
    )
    test_group.add_argument(
        '--single-turn',
        action='store_true',
        help='Esegue solo domanda iniziale (no followup)'
    )
    test_group.add_argument(
        '--cloud',
        action='store_true',
        help='Esegui test su CircleCI invece che localmente'
    )
    test_group.add_argument(
        '--test-limit',
        type=int,
        default=0,
        metavar='N',
        help='Limita a N test (0 = tutti)'
    )
    test_group.add_argument(
        '--test-ids',
        type=str,
        default='',
        metavar='IDS',
        help='Lista test specifici separati da virgola (es: TEST_006,TEST_007)'
    )

    # ═══════════════════════════════════════════════════════════════════
    # Analisi
    # ═══════════════════════════════════════════════════════════════════
    analysis_group = parser.add_argument_group('Analisi')
    analysis_group.add_argument(
        '--compare',
        type=str,
        nargs='?',
        const='latest',
        metavar='A:B',
        help='Confronta run (es: --compare 15:16, --compare per ultime 2)'
    )
    analysis_group.add_argument(
        '--regressions',
        type=int,
        nargs='?',
        const=0,
        metavar='RUN',
        help='Mostra regressioni (es: --regressions 16)'
    )
    analysis_group.add_argument(
        '--flaky',
        type=int,
        nargs='?',
        const=10,
        metavar='N',
        help='Rileva test flaky su ultime N run (default: 10)'
    )
    analysis_group.add_argument(
        '--analyze',
        action='store_true',
        help='Analizza test falliti (genera debug package)'
    )
    analysis_group.add_argument(
        '--provider',
        type=str,
        choices=['manual', 'claude', 'groq'],
        default='manual',
        metavar='PROV',
        help='Provider analisi: manual (clipboard), claude, groq'
    )
    analysis_group.add_argument(
        '--analyze-run',
        type=int,
        metavar='RUN',
        help='Run da analizzare (default: ultima)'
    )
    analysis_group.add_argument(
        '-y', '--yes',
        action='store_true',
        help='Salta conferma costi API'
    )

    # ═══════════════════════════════════════════════════════════════════
    # Prompt Manager
    # ═══════════════════════════════════════════════════════════════════
    prompt_group = parser.add_argument_group('Prompt Manager')
    prompt_group.add_argument(
        '--prompt-list',
        action='store_true',
        help='Lista versioni prompt salvate'
    )
    prompt_group.add_argument(
        '--prompt-show',
        type=int,
        nargs='?',
        const=0,
        metavar='VER',
        help='Mostra prompt (default: corrente, oppure versione)'
    )
    prompt_group.add_argument(
        '--prompt-import',
        type=str,
        metavar='FILE',
        help='Importa prompt da file .md'
    )
    prompt_group.add_argument(
        '--prompt-export',
        type=str,
        nargs='?',
        const='auto',
        metavar='FILE',
        help='Esporta prompt su file'
    )
    prompt_group.add_argument(
        '--prompt-diff',
        type=str,
        metavar='V1:V2',
        help='Diff tra versioni (es: --prompt-diff 1:2)'
    )
    prompt_group.add_argument(
        '--prompt-note',
        type=str,
        default='update',
        metavar='NOTE',
        help='Nota per import prompt (default: "update")'
    )

    # ═══════════════════════════════════════════════════════════════════
    # Visualizer
    # ═══════════════════════════════════════════════════════════════════
    viz_group = parser.add_argument_group('Visualizer')
    viz_group.add_argument(
        '--viz-prompt',
        action='store_true',
        help='Visualizza struttura prompt (flowchart + mindmap)'
    )
    viz_group.add_argument(
        '--viz-test',
        type=str,
        nargs='?',
        const='latest',
        metavar='TEST_ID',
        help='Visualizza test (waterfall + timeline). Default: ultimo test'
    )
    viz_group.add_argument(
        '--viz-run',
        type=int,
        metavar='RUN',
        help='Run da visualizzare (default: ultimo)'
    )
    viz_group.add_argument(
        '--viz-output',
        type=str,
        choices=['html', 'terminal'],
        default='html',
        metavar='OUT',
        help='Output: html (browser) o terminal (ASCII)'
    )

    # ═══════════════════════════════════════════════════════════════════
    # Export & Notifiche
    # ═══════════════════════════════════════════════════════════════════
    export_group = parser.add_argument_group('Export & Notifiche')
    export_group.add_argument(
        '--export',
        type=str,
        choices=['pdf', 'excel', 'html', 'csv', 'all'],
        metavar='FMT',
        help='Esporta report: pdf, excel, html, csv, all'
    )
    export_group.add_argument(
        '--export-run',
        type=int,
        metavar='RUN',
        help='Run da esportare (default: ultimo)'
    )
    export_group.add_argument(
        '--notify',
        type=str,
        choices=['desktop', 'email', 'teams', 'all'],
        metavar='CH',
        help='Invia notifica: desktop, email, teams, all'
    )
    export_group.add_argument(
        '--test-notify',
        action='store_true',
        help='Test notifiche (verifica configurazione)'
    )

    # ═══════════════════════════════════════════════════════════════════
    # Scheduler
    # ═══════════════════════════════════════════════════════════════════
    sched_group = parser.add_argument_group('Scheduler')
    sched_group.add_argument(
        '--scheduler',
        action='store_true',
        help='Avvia scheduler locale (cron-like)'
    )
    sched_group.add_argument(
        '--add-schedule',
        type=str,
        metavar='PROJ:TYPE',
        help='Aggiungi schedule (es: my-chatbot:daily)'
    )
    sched_group.add_argument(
        '--list-schedules',
        action='store_true',
        help='Lista schedule configurati'
    )

    # ═══════════════════════════════════════════════════════════════════
    # Cloud Monitoring
    # ═══════════════════════════════════════════════════════════════════
    cloud_group = parser.add_argument_group('Cloud Monitoring')
    cloud_group.add_argument(
        '--watch-cloud',
        nargs='?',
        const='latest',
        metavar='RUN_ID',
        help='Monitora run cloud con barra di avanzamento (default: ultimo run)'
    )
    cloud_group.add_argument(
        '--cloud-runs',
        action='store_true',
        help='Lista ultimi run cloud'
    )

    # ═══════════════════════════════════════════════════════════════════
    # Output
    # ═══════════════════════════════════════════════════════════════════
    output_group = parser.add_argument_group('Output')
    output_group.add_argument(
        '-q', '--quiet',
        action='store_true',
        help='Output minimo (solo errori)'
    )
    output_group.add_argument(
        '--json',
        action='store_true',
        help='Output JSON (machine-readable)'
    )
    output_group.add_argument(
        '--no-color',
        action='store_true',
        help='Disabilita colori (oppure: NO_COLOR=1)'
    )
    output_group.add_argument(
        '--debug',
        action='store_true',
        default=os.environ.get('DEBUG', '').lower() in ('1', 'true'),
        help='Output di debug verbose'
    )

    # ═══════════════════════════════════════════════════════════════════
    # Runtime
    # ═══════════════════════════════════════════════════════════════════
    runtime_group = parser.add_argument_group('Runtime')
    runtime_group.add_argument(
        '--headless',
        action='store_true',
        help='Browser in background (senza finestra)'
    )
    runtime_group.add_argument(
        '--parallel',
        action='store_true',
        help='Esecuzione parallela (multi-browser)'
    )
    runtime_group.add_argument(
        '--workers',
        type=int,
        default=3,
        metavar='N',
        help='Numero browser paralleli (default: 3, max: 5)'
    )
    runtime_group.add_argument(
        '--no-interactive',
        action='store_true',
        help='Disabilita prompt (per CI/script)'
    )
    runtime_group.add_argument(
        '--lang',
        type=str,
        default='it',
        choices=['it', 'en'],
        help='Lingua UI: it (default), en'
    )

    # ═══════════════════════════════════════════════════════════════════
    # Diagnostic Engine (failure analysis)
    # ═══════════════════════════════════════════════════════════════════
    diagnostic_group = parser.add_argument_group('Diagnostic Engine')
    diagnostic_group.add_argument(
        '--diagnose',
        action='store_true',
        help='Esegue diagnosi intelligente sui test falliti'
    )
    diagnostic_group.add_argument(
        '--diagnose-test',
        type=str,
        metavar='TEST_ID',
        help='Diagnosi su test specifico (es: --diagnose-test TEST_001)'
    )
    diagnostic_group.add_argument(
        '--diagnose-run',
        type=int,
        metavar='RUN',
        help='Run da diagnosticare (default: ultimo)'
    )
    diagnostic_group.add_argument(
        '--diagnose-interactive',
        action='store_true',
        help='Modalita interattiva (conferma ipotesi)'
    )
    diagnostic_group.add_argument(
        '--diagnose-model',
        type=str,
        default='generic',
        choices=['generic', 'openai', 'claude', 'gemini'],
        help='Modello target per fix (default: generic)'
    )

    # ═══════════════════════════════════════════════════════════════════
    # Performance Metrics
    # ═══════════════════════════════════════════════════════════════════
    perf_group = parser.add_argument_group('Performance Metrics')
    perf_group.add_argument(
        '--perf-report',
        type=int,
        nargs='?',
        const=0,
        metavar='RUN',
        help='Mostra report performance (default: ultimo run)'
    )
    perf_group.add_argument(
        '--perf-dashboard',
        type=int,
        nargs='?',
        const=10,
        metavar='N',
        help='Dashboard storica performance (ultimi N run, default: 10)'
    )
    perf_group.add_argument(
        '--perf-compare',
        type=str,
        metavar='LOCAL:CLOUD',
        help='Confronta performance local vs cloud (es: --perf-compare 15:16)'
    )
    perf_group.add_argument(
        '--perf-export',
        type=str,
        choices=['json', 'html'],
        metavar='FMT',
        help='Esporta metriche performance: json, html'
    )
    perf_group.add_argument(
        '--list-runs',
        type=int,
        nargs='?',
        const=10,
        metavar='N',
        help='Lista ultimi N run di TUTTI i progetti (default: 10)'
    )

    # ═══════════════════════════════════════════════════════════════════
    # Health Check
    # ═══════════════════════════════════════════════════════════════════
    diag_group = parser.add_argument_group('Health Check')
    diag_group.add_argument(
        '--health-check',
        action='store_true',
        help='Verifica servizi e esci'
    )
    diag_group.add_argument(
        '--skip-health-check',
        action='store_true',
        help='Salta verifica servizi all\'avvio'
    )
    diag_group.add_argument(
        '-v', '--version',
        action='version',
        version='%(prog)s v1.6.0'
    )

    # ═══════════════════════════════════════════════════════════════════
    # Natural Language Interface
    # ═══════════════════════════════════════════════════════════════════
    nl_group = parser.add_argument_group('Natural Language')
    nl_group.add_argument(
        '--ask',
        type=str,
        metavar='COMMAND',
        help='Esegui comando in linguaggio naturale (es: --ask "lancia test silicon-b")'
    )
    nl_group.add_argument(
        '--chat',
        action='store_true',
        help='Avvia sessione chat interattiva'
    )
    nl_group.add_argument(
        '--agent',
        action='store_true',
        help='Avvia agente conversazionale avanzato (memoria, multi-step, conferma)'
    )

    args = parser.parse_args()

    # Supporto NO_COLOR env var (clig.dev standard)
    if os.environ.get('NO_COLOR'):
        args.no_color = True

    return args


def run_health_check(project: ProjectConfig = None, settings = None) -> bool:
    """
    Esegue health check di tutti i servizi.

    Args:
        project: Configurazione progetto (opzionale)
        settings: Settings globali (opzionale)

    Returns:
        True se tutti i servizi critici sono OK
    """
    ui = get_ui()
    ui.section("Health Check")

    # Carica .env per avere le variabili d'ambiente
    from dotenv import load_dotenv
    env_path = Path(__file__).parent / "config" / ".env"
    if env_path.exists():
        load_dotenv(env_path)

    # Configura checker
    chatbot_url = project.chatbot.url if project else ""
    langsmith_key = ""
    google_creds = ""

    if settings:
        langsmith_key = getattr(settings, 'langsmith_api_key', '') or ''

    # Fallback a variabile d'ambiente se non in settings
    if not langsmith_key:
        langsmith_key = os.environ.get('LANGSMITH_API_KEY', '')

    # Leggi credentials path da google_sheets config o da project config
    if settings and hasattr(settings, 'google_sheets') and hasattr(settings.google_sheets, 'credentials_path'):
        google_creds = str(settings.google_sheets.credentials_path or '')
    elif project and hasattr(project, 'google_sheets') and hasattr(project.google_sheets, 'credentials_path'):
        google_creds = str(project.google_sheets.credentials_path or '')

    checker = HealthChecker(
        chatbot_url=chatbot_url,
        langsmith_api_key=langsmith_key,
        google_credentials_path=google_creds
    )

    # Esegui check
    health = checker.check_all(force=True)

    # Mostra risultati
    status_icons = {
        ServiceStatus.HEALTHY: "[green]OK[/green]",
        ServiceStatus.DEGRADED: "[yellow]WARN[/yellow]",
        ServiceStatus.UNHEALTHY: "[red]FAIL[/red]",
        ServiceStatus.DISABLED: "[dim]OFF[/dim]",
        ServiceStatus.UNKNOWN: "[dim]?[/dim]"
    }

    for name, result in health.checks.items():
        icon = status_icons.get(result.status, "?")
        # Evita duplicazione latency se già presente nel messaggio
        latency = ""
        if result.latency_ms > 0 and "ms)" not in result.message:
            latency = f" ({result.latency_ms}ms)"
        ui.print(f"  {icon} {name}: {result.message}{latency}")

    # Riepilogo
    ui.print("")
    if health.all_healthy:
        ui.success("Tutti i servizi sono operativi")
    elif health.can_run:
        if health.warnings:
            ui.warning(f"Avvertimenti: {len(health.warnings)}")
            for w in health.warnings:
                ui.print(f"  ! {w}", "yellow")
        ui.info("I servizi critici sono OK - puoi procedere")
    else:
        ui.error("Servizi critici non disponibili:")
        for issue in health.blocking_issues:
            ui.print(f"  x {issue}", "red")
        return False

    return True


def show_main_menu(ui: ConsoleUI, loader: ConfigLoader) -> str:
    """Mostra menu principale e ritorna scelta"""
    projects = loader.list_projects()

    ui.header(
        t('main_menu.app_name'),
        t('main_menu.welcome')
    )

    project_desc = t('main_menu.open_project_desc').format(count=len(projects)) if projects else t('main_menu.open_project_empty')

    # Verifica disponibilita cloud execution (CircleCI)
    ci_client = CircleCIClient()
    cloud_available = ci_client.is_available()
    cloud_desc = "Lancia test senza browser locale" if cloud_available else "Richiede: export CIRCLECI_TOKEN=..."

    items = [
        MenuItem('1', t('main_menu.new_project'), t('main_menu.new_project_desc')),
        MenuItem('2', t('main_menu.open_project'), project_desc),
        MenuItem('3', t('main_menu.finetuning'), t('main_menu.finetuning_desc')),
        MenuItem('4', "Esegui nel cloud", cloud_desc, disabled=not cloud_available),
        MenuItem('5', "Analisi Testing", "Confronta run, regressioni, test flaky"),
        MenuItem('6', "Lista Run", "Tutti i run recenti di tutti i progetti"),
        MenuItem('7', t('main_menu.settings'), t('main_menu.settings_desc')),
        MenuItem('8', t('main_menu.help'), t('main_menu.help_desc')),
        MenuItem('quit', t('main_menu.exit'), '')
    ]

    return ui.menu(items, t('common.next'))


def show_project_menu(ui: ConsoleUI, loader: ConfigLoader) -> str:
    """Mostra lista progetti e ritorna scelta"""
    projects = loader.list_projects()

    if not projects:
        ui.warning(t('main_menu.no_projects'))
        return None

    ui.section(t('main_menu.select_project'))

    items = [
        MenuItem(str(i+1), proj, '')
        for i, proj in enumerate(projects)
    ]

    choice = ui.menu(items, t('common.next'), allow_back=True)

    if choice is None:
        return None

    idx = int(choice) - 1
    return projects[idx] if 0 <= idx < len(projects) else None


def show_mode_menu(ui: ConsoleUI, project: ProjectConfig, run_config: RunConfig) -> str:
    """Mostra menu modalità test"""
    ui.section(t('mode_menu.title'))

    # Verifica disponibilità Ollama per modalità avanzate
    # Ollama disponibile se: configurato nel progetto E abilitato nel run_config
    ollama_available = project.ollama.enabled and run_config.use_ollama

    items = [
        MenuItem('1', t('mode_menu.train'), t('mode_menu.train_desc')),
        MenuItem('2', t('mode_menu.assisted'), t('mode_menu.assisted_desc'), disabled=not ollama_available),
        MenuItem('3', t('mode_menu.auto'), t('mode_menu.auto_desc'), disabled=not ollama_available),
    ]

    if not project.ollama.enabled:
        ui.warning(t('mode_menu.ollama_not_configured'))
    elif not run_config.use_ollama:
        ui.warning(t('mode_menu.ollama_disabled'))

    return ui.menu(items, t('common.next'), allow_back=True)


def show_test_selection(ui: ConsoleUI, tests: list) -> list:
    """
    Menu interattivo per selezionare quali test eseguire.

    Args:
        ui: Console UI
        tests: Lista completa test cases

    Returns:
        Lista filtrata di test da eseguire
    """
    ui.section(t('test_selection.title') + f" ({t('test_selection.available').format(count=len(tests))})")

    items = [
        MenuItem('1', t('test_selection.all'), t('test_selection.all_desc').format(count=len(tests))),
        MenuItem('2', t('test_selection.pending'), t('test_selection.pending_desc')),
        MenuItem('3', t('test_selection.first_n'), t('test_selection.first_n_desc')),
        MenuItem('4', t('test_selection.range'), t('test_selection.range_desc')),
        MenuItem('5', t('test_selection.specific'), t('test_selection.specific_desc')),
        MenuItem('6', t('test_selection.search'), t('test_selection.search_desc')),
        MenuItem('7', t('test_selection.list'), t('test_selection.list_desc')),
    ]

    while True:
        choice = ui.menu(items, t('common.next'), allow_back=True)

        if choice is None or choice == 'back':
            return []

        elif choice == '1':
            # Tutti
            return tests

        elif choice == '2':
            # Pending - viene gestito dopo nel flusso
            return tests  # Il filtro pending viene applicato dopo

        elif choice == '3':
            # Primi N
            try:
                n = input(f"  {t('test_selection.how_many')} ").strip()
                n = int(n)
                if 1 <= n <= len(tests):
                    ui.success(t('test_selection.selected').format(count=n))
                    return tests[:n]
                else:
                    ui.warning(t('test_selection.how_many_hint').format(max=len(tests)))
            except ValueError:
                ui.warning(t('test_selection.invalid_number'))

        elif choice == '4':
            # Range
            try:
                range_input = input(f"  {t('test_selection.range_input')} ({t('test_selection.range_hint')}): ").strip()

                if '-' in range_input:
                    parts = range_input.split('-')

                    # Gestisce sia "10-20" che "TEST-010-TEST-020"
                    if len(parts) == 2:
                        start, end = int(parts[0]), int(parts[1])
                    elif len(parts) == 4:  # TEST-010-TEST-020
                        start = int(parts[1])
                        end = int(parts[3])
                    else:
                        raise ValueError("Formato non valido")

                    selected = [tc for tc in tests
                               if start <= int(tc.id.split('-')[1]) <= end]

                    if selected:
                        ui.success(t('test_selection.selected').format(count=len(selected)) + f" ({selected[0].id} - {selected[-1].id})")
                        return selected
                    else:
                        ui.warning(t('test_selection.none_found'))
                else:
                    ui.warning(t('test_selection.range_hint'))
            except (ValueError, IndexError):
                ui.warning(t('test_selection.invalid_range'))

        elif choice == '5':
            # Specifici
            ids_input = input(f"  {t('test_selection.ids_input')} ({t('test_selection.ids_hint')}): ").strip()
            ids = [x.strip().upper() for x in ids_input.split(',')]

            # Normalizza IDs (aggiungi TEST- se manca)
            normalized_ids = []
            for id_ in ids:
                if not id_.startswith('TEST-'):
                    id_ = f"TEST-{id_.zfill(3)}"
                normalized_ids.append(id_)

            selected = [tc for tc in tests if tc.id in normalized_ids]

            if selected:
                ui.success(t('test_selection.selected').format(count=len(selected)) + f": {', '.join(tc.id for tc in selected)}")
                return selected
            else:
                ui.warning(t('test_selection.none_found') + f": {', '.join(normalized_ids)}")

        elif choice == '6':
            # Cerca per keyword
            keyword = input(f"  {t('test_selection.keyword_input')}: ").strip().lower()
            if keyword:
                selected = [tc for tc in tests
                           if keyword in tc.question.lower()
                           or keyword in (tc.category or '').lower()]

                if selected:
                    ui.success(t('test_selection.selected').format(count=len(selected)) + f" ('{keyword}')")
                    for tc in selected[:10]:
                        ui.print(f"  [cyan]{tc.id}[/cyan]: {tc.question[:50]}...")
                    if len(selected) > 10:
                        ui.print(f"  [dim]...+{len(selected)-10}[/dim]")

                    confirm = input(f"  {t('test_selection.confirm_selection').format(count=len(selected))} (s/n): ").strip().lower()
                    if confirm == 's':
                        return selected
                else:
                    ui.warning(t('test_selection.none_found') + f" ('{keyword}')")
            else:
                ui.warning(t('test_selection.keyword_input'))

        elif choice == '7':
            # Lista tutti
            ui.section(t('test_selection.list'))
            for i, tc in enumerate(tests):
                followups = len(tc.followups) if tc.followups else 0
                fu_info = f" [dim][{followups}fu][/dim]" if followups > 0 else ""
                cat_info = f" [magenta]{tc.category}[/magenta]" if tc.category else ""
                ui.print(f"  [cyan]{tc.id}[/cyan]: {tc.question[:45]}...{cat_info}{fu_info}")

                # Pausa ogni 20 test
                if (i + 1) % 20 == 0 and i + 1 < len(tests):
                    more = input(f"  {t('test_selection.show_more')} ").strip().lower()
                    if more == 'q':
                        break

            ui.print("")  # Spazio prima del menu


def show_run_menu(ui: ConsoleUI, project: ProjectConfig, run_config: RunConfig) -> str:
    """Mostra menu gestione RUN"""
    ui.section(t('run_menu.title'))

    # Status toggle
    dry_status = "[yellow]ON[/yellow]" if run_config.dry_run else "[dim]OFF[/dim]"
    ls_status = "[green]ON[/green]" if run_config.use_langsmith else "[dim]OFF[/dim]"
    rag_status = "[green]ON[/green]" if run_config.use_rag else "[dim]OFF[/dim]"
    ollama_status = "[green]ON[/green]" if run_config.use_ollama else "[dim]OFF[/dim]"
    ui.print(f"\n  {t('run_menu.toggle_status')}: Dry run: {dry_status} | LangSmith: {ls_status} | RAG: {rag_status} | Ollama: {ollama_status}")

    # Mostra stato RUN attuale
    if run_config.active_run:
        ui.print(f"\n  {t('run_menu.active_run').format(number=run_config.active_run)}")
        ui.print(f"  {t('run_menu.env')}: [cyan]{run_config.env}[/cyan]")
        ui.print(f"  {t('run_menu.mode')}: [cyan]{run_config.mode}[/cyan]")
        ui.print(f"  {t('run_menu.tests_completed')}: [cyan]{run_config.tests_completed}[/cyan]")
        if run_config.run_start:
            ui.print(f"  {t('run_menu.started_at')}: [dim]{run_config.run_start[:19]}[/dim]")
        ui.print("")
    else:
        ui.print(f"\n  [yellow]{t('run_menu.no_active_run')}[/yellow]\n")

    if run_config.active_run:
        items = [
            MenuItem('1', t('run_menu.continue_run'), t('run_menu.continue_run_desc')),
            MenuItem('2', t('run_menu.new_run'), t('run_menu.new_run_desc')),
            MenuItem('3', t('run_menu.configure'), t('run_menu.configure_desc')),
            MenuItem('4', t('run_menu.toggle'), t('run_menu.toggle_desc')),
        ]
    else:
        items = [
            MenuItem('1', t('run_menu.start_run'), t('run_menu.start_run_desc')),
            MenuItem('2', t('run_menu.new_run'), t('run_menu.new_run_desc')),
            MenuItem('3', t('run_menu.configure'), t('run_menu.configure_desc')),
            MenuItem('4', t('run_menu.toggle'), t('run_menu.toggle_desc')),
        ]

    return ui.menu(items, t('common.next'), allow_back=True)


def configure_run_interactive(ui: ConsoleUI, run_config: RunConfig) -> bool:
    """
    Configura i parametri della RUN interattivamente.

    Returns:
        True se configurazione completata, False se annullata
    """
    ui.section(t('run_menu.config_title'))

    # Mostra valori attuali
    ui.print(f"\n  {t('run_menu.config_current')}")
    ui.print(f"  {t('run_menu.config_env')}: [cyan]{run_config.env}[/cyan]")
    ui.print(f"  {t('run_menu.config_prompt_version')}: [cyan]{run_config.prompt_version or '(-)'}[/cyan]")
    ui.print(f"  {t('run_menu.config_model_version')}: [cyan]{run_config.model_version or '(-)'}[/cyan]")
    ui.print(f"\n  [dim]{t('run_menu.config_keep_hint')}[/dim]\n")

    # Ambiente
    env_input = input(f"  {t('run_menu.config_env')} [{run_config.env}]: ").strip().upper()
    if env_input:
        if env_input in ['DEV', 'STAGING', 'PROD']:
            run_config.env = env_input
        else:
            ui.warning(t('run_menu.config_env_invalid'))

    # Versione prompt
    pv_input = input(f"  {t('run_menu.config_prompt_version')} [{run_config.prompt_version or '-'}]: ").strip()
    if pv_input:
        run_config.prompt_version = pv_input

    # Versione modello
    mv_input = input(f"  {t('run_menu.config_model_version')} [{run_config.model_version or '-'}]: ").strip()
    if mv_input:
        run_config.model_version = mv_input

    ui.success(t('run_menu.config_updated'))
    return True


def toggle_options_interactive(ui: ConsoleUI, run_config: RunConfig) -> bool:
    """
    Menu toggle opzioni runtime.

    Returns:
        True se modificato qualcosa
    """
    while True:
        ui.section(t('run_menu.toggle_title'))

        # Status attuale
        dry_status = "[yellow]ON[/yellow]" if run_config.dry_run else "[dim]OFF[/dim]"
        ls_status = "[green]ON[/green]" if run_config.use_langsmith else "[dim]OFF[/dim]"
        rag_status = "[green]ON[/green]" if run_config.use_rag else "[dim]OFF[/dim]"
        ollama_status = "[green]ON[/green]" if run_config.use_ollama else "[dim]OFF[/dim]"
        single_turn_status = "[cyan]ON[/cyan]" if run_config.single_turn else "[dim]OFF[/dim]"

        ui.print(f"\n  {t('run_menu.toggle_status')}:")
        dry_note = f"  ({t('run_menu.toggle_dry_run_on')})" if run_config.dry_run else ""
        ui.print(f"  [1] {t('run_menu.toggle_dry_run')}:    {dry_status}{dry_note}")
        ui.print(f"  [2] {t('run_menu.toggle_langsmith')}:  {ls_status}")
        ui.print(f"  [3] {t('run_menu.toggle_rag')}:        {rag_status}")
        ollama_note = f"  ({t('run_menu.toggle_ollama_on')})" if run_config.use_ollama else f"  ({t('run_menu.toggle_ollama_off')})"
        ui.print(f"  [4] {t('run_menu.toggle_ollama')}:     {ollama_status}{ollama_note}")
        single_turn_note = "  (solo domanda iniziale)" if run_config.single_turn else "  (conversazione completa)"
        ui.print(f"  [5] Single Turn:    {single_turn_status}{single_turn_note}")
        ui.print("")

        items = [
            MenuItem('1', f"{t('run_menu.toggle_dry_run')}: {'OFF->ON' if not run_config.dry_run else 'ON->OFF'}",
                     t('run_menu.toggle_dry_run_on') if not run_config.dry_run else t('run_menu.toggle_dry_run_off')),
            MenuItem('2', f"{t('run_menu.toggle_langsmith')}: {'OFF->ON' if not run_config.use_langsmith else 'ON->OFF'}",
                     t('run_menu.toggle_langsmith_on') if not run_config.use_langsmith else t('run_menu.toggle_langsmith_off')),
            MenuItem('3', f"{t('run_menu.toggle_rag')}: {'OFF->ON' if not run_config.use_rag else 'ON->OFF'}",
                     t('run_menu.toggle_rag_on') if not run_config.use_rag else t('run_menu.toggle_rag_off')),
            MenuItem('4', f"{t('run_menu.toggle_ollama')}: {'OFF->ON' if not run_config.use_ollama else 'ON->OFF'}",
                     t('run_menu.toggle_ollama_on') if not run_config.use_ollama else t('run_menu.toggle_ollama_off')),
            MenuItem('5', f"Single Turn: {'OFF->ON' if not run_config.single_turn else 'ON->OFF'}",
                     "Esegue solo domanda iniziale" if not run_config.single_turn else "Esegue conversazione completa"),
        ]

        choice = ui.menu(items, t('common.next'), allow_back=True)

        if choice is None:
            return True
        elif choice == '1':
            run_config.dry_run = not run_config.dry_run
            status = t('run_menu.dry_run_on') if run_config.dry_run else t('run_menu.dry_run_off')
            ui.success(f"{t('run_menu.toggle_dry_run')}: {status}")
        elif choice == '2':
            run_config.use_langsmith = not run_config.use_langsmith
            status = t('run_menu.langsmith_on') if run_config.use_langsmith else t('run_menu.langsmith_off')
            ui.success(f"{t('run_menu.toggle_langsmith')}: {status}")
        elif choice == '3':
            run_config.use_rag = not run_config.use_rag
            status = t('run_menu.rag_on') if run_config.use_rag else t('run_menu.rag_off')
            ui.success(f"{t('run_menu.toggle_rag')}: {status}")
        elif choice == '4':
            run_config.use_ollama = not run_config.use_ollama
            status = t('run_menu.ollama_on') if run_config.use_ollama else t('run_menu.ollama_off')
            ui.success(f"{t('run_menu.toggle_ollama')}: {status}")
        elif choice == '5':
            run_config.single_turn = not run_config.single_turn
            status = "ON (solo domanda iniziale)" if run_config.single_turn else "OFF (conversazione completa)"
            ui.success(f"Single Turn: {status}")


def show_cloud_menu(ui: ConsoleUI, loader: ConfigLoader) -> None:
    """Menu per esecuzione test nel cloud (CircleCI)"""
    ci_client = CircleCIClient()

    if not ci_client.is_available():
        ui.error("CircleCI non configurato")
        ui.print(ci_client.get_install_instructions())
        input("\n  Premi INVIO per continuare...")
        return

    while True:
        ui.section("Esegui nel Cloud")
        ui.print("\n  [dim]Test eseguiti su CircleCI, senza browser locale[/dim]\n")

        # Mostra pipeline recenti
        pipelines = ci_client.list_pipelines(limit=5)
        if pipelines:
            ui.print("  Pipeline recenti:")
            for pipeline in pipelines[:3]:
                ui.print(f"    {pipeline.status_icon} #{pipeline.number} [{pipeline.state}] ({pipeline.created_at[:10]})")
            ui.print("")

        # Verifica se c'è una pipeline attiva
        active_pipelines = [p for p in pipelines if p.is_active]
        has_active = len(active_pipelines) > 0

        items = [
            MenuItem('1', "Lancia test", "Avvia nuova esecuzione nel cloud"),
            MenuItem('2', "Monitora run", "Segui avanzamento in tempo reale", disabled=not has_active),
            MenuItem('3', "Stato esecuzioni", "Vedi pipeline in corso e recenti"),
            MenuItem('4', "Cancella run", "Interrompi esecuzione in corso", disabled=not has_active),
        ]

        choice = ui.menu(items, "Azione", allow_back=True)

        if choice is None:
            return

        elif choice == '1':
            _cloud_launch_test(ui, loader, ci_client)

        elif choice == '2':
            _cloud_monitor_run(ui, ci_client, pipelines)

        elif choice == '3':
            _cloud_show_status(ui, ci_client)

        elif choice == '4':
            _cloud_cancel_run(ui, ci_client, pipelines)


def _cloud_monitor_run(ui: ConsoleUI, ci_client: CircleCIClient, pipelines: list) -> None:
    """Monitora run cloud con polling status"""
    from src.circleci_client import watch_cloud_run

    # Filtra pipeline attive o recenti
    active_pipelines = [p for p in pipelines if p.is_active]
    recent_pipelines = pipelines[:5]

    if not active_pipelines and not recent_pipelines:
        ui.warning("Nessuna pipeline da monitorare")
        input("\n  Premi INVIO per continuare...")
        return

    ui.section("Monitora Run Cloud")

    # Mostra opzioni
    ui.print("\n  Pipeline disponibili:\n")

    display_pipelines = active_pipelines if active_pipelines else recent_pipelines[:3]
    for i, pipeline in enumerate(display_pipelines, 1):
        ui.print(f"  [{i}] {pipeline.status_icon} #{pipeline.number} [{pipeline.state}]")
        ui.print(f"      {pipeline.created_at[:16].replace('T', ' ')}")
        ui.print("")

    # Selezione
    if len(display_pipelines) == 1:
        ui.print("  [dim]Premi INVIO per monitorare, 'q' per tornare[/dim]")
        choice = input("\n  > ").strip().lower()
        if choice == 'q':
            return
        selected = display_pipelines[0]
    else:
        choice = input("\n  Numero pipeline da monitorare (INVIO per l'ultima): ").strip()
        if choice == '':
            selected = display_pipelines[0]
        elif choice.isdigit() and 1 <= int(choice) <= len(display_pipelines):
            selected = display_pipelines[int(choice) - 1]
        else:
            return

    # Avvia monitoraggio
    ui.print(f"\n  [cyan]Monitoraggio pipeline #{selected.number}[/cyan]")
    ui.print(f"  URL: {selected.url}")
    ui.print("  [dim]Premi Ctrl+C per interrompere[/dim]\n")

    try:
        progress = watch_cloud_run(ci_client, selected.id)

        # Riepilogo finale
        ui.print("")
        if progress.status == "success":
            ui.success("Pipeline completata con successo!")
        elif progress.status in ("failed", "error"):
            ui.error(f"Pipeline fallita: {progress.error_message or 'errore sconosciuto'}")
        elif progress.status == "canceled":
            ui.warning("Pipeline cancellata")

    except KeyboardInterrupt:
        ui.print("\n\n  [dim]Monitoraggio interrotto[/dim]")

    input("\n  Premi INVIO per continuare...")


def _cloud_launch_test(ui: ConsoleUI, loader: ConfigLoader, ci_client: CircleCIClient) -> None:
    """Lancia test nel cloud via CircleCI"""
    # Seleziona progetto
    project_name = show_project_menu(ui, loader)
    if not project_name:
        return

    ui.section(f"Lancia test: {project_name}")

    # Modalita
    ui.print("\n  Modalita:")
    mode_items = [
        MenuItem('1', 'auto', 'Test completamente automatici'),
        MenuItem('2', 'train', 'Solo esecuzione, no valutazione'),
    ]
    mode_choice = ui.menu(mode_items, "Modalita", allow_back=True)
    if mode_choice is None:
        return
    mode = 'auto' if mode_choice == '1' else 'train'

    # Test da eseguire
    ui.print("\n  Quali test:")
    test_items = [
        MenuItem('1', 'pending', 'Solo test non completati'),
        MenuItem('2', 'all', 'Tutti i test'),
        MenuItem('3', 'failed', 'Solo test falliti'),
    ]
    test_choice = ui.menu(test_items, "Test", allow_back=True)
    if test_choice is None:
        return
    tests = {'1': 'pending', '2': 'all', '3': 'failed'}.get(test_choice, 'pending')

    # Nuovo run?
    new_run = input("\n  Creare nuovo run su Google Sheets? (s/n): ").strip().lower() == 's'

    # Conferma
    ui.print(f"\n  [cyan]Riepilogo:[/cyan]")
    ui.print(f"    Progetto: {project_name}")
    ui.print(f"    Modalita: {mode}")
    ui.print(f"    Test: {tests}")
    ui.print(f"    Nuovo run: {'Si' if new_run else 'No'}")

    confirm = input("\n  Avviare? (s/n): ").strip().lower()
    if confirm != 's':
        ui.info("Annullato")
        return

    # Lancia pipeline
    ui.print("\n  Avvio pipeline CircleCI...")
    success, data = ci_client.trigger_pipeline(project_name, mode, tests, new_run)

    if success:
        pipeline_number = data.get('number', '?')
        pipeline_id = data.get('id', '')
        ui.success(f"Pipeline #{pipeline_number} avviata!")
        ui.print(f"\n  URL: https://app.circleci.com/pipelines/gh/corradofrancolini/chatbot-tester-private/{pipeline_number}")

        # Chiedi se monitorare
        monitor = input("\n  Vuoi monitorare l'esecuzione? (s/n): ").strip().lower()
        if monitor == 's':
            ui.print("\n  [dim]Attendo avvio pipeline...[/dim]")
            import time
            time.sleep(5)  # Attendi che la pipeline si avvii

            from src.circleci_client import watch_cloud_run
            try:
                progress = watch_cloud_run(ci_client, pipeline_id)

                if progress.status == "success":
                    ui.success("\nPipeline completata con successo!")
                elif progress.status in ("failed", "error"):
                    ui.error(f"\nPipeline fallita: {progress.error_message or 'errore'}")

            except KeyboardInterrupt:
                ui.print("\n\n  [dim]Monitoraggio interrotto[/dim]")
    else:
        error_msg = data.get('error', 'Errore sconosciuto') if data else 'Errore sconosciuto'
        ui.error(f"Errore: {error_msg}")

    input("\n  Premi INVIO per continuare...")


def _cloud_show_status(ui: ConsoleUI, ci_client: CircleCIClient) -> None:
    """Mostra stato esecuzioni cloud"""
    ui.section("Stato Pipeline CircleCI")

    pipelines = ci_client.list_pipelines(limit=10)

    if not pipelines:
        ui.warning("Nessuna pipeline trovata")
        input("\n  Premi INVIO per continuare...")
        return

    ui.print("\n  Pipeline recenti:\n")

    for i, pipeline in enumerate(pipelines, 1):
        ui.print(f"  [{i}] {pipeline.status_icon} #{pipeline.number} [{pipeline.state}]")
        ui.print(f"      {pipeline.created_at[:19].replace('T', ' ')}")
        ui.print("")

    # Opzioni
    ui.print("  [dim]Inserisci numero per vedere dettagli, INVIO per tornare[/dim]")
    choice = input("\n  > ").strip().lower()

    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(pipelines):
            pipeline = pipelines[idx]
            ui.print(f"\n  URL: {pipeline.url}")

            # Mostra workflow della pipeline
            workflows = ci_client.get_pipeline_workflows(pipeline.id)
            if workflows:
                ui.print("\n  Workflow:")
                for wf in workflows:
                    ui.print(f"    {wf.status_icon} {wf.name}: {wf.status}")

            input("\n  Premi INVIO per continuare...")


def _cloud_cancel_run(ui: ConsoleUI, ci_client: CircleCIClient, pipelines: list) -> None:
    """Cancella un run in corso"""
    active_pipelines = [p for p in pipelines if p.is_active]

    if not active_pipelines:
        ui.warning("Nessuna pipeline attiva da cancellare")
        input("\n  Premi INVIO per continuare...")
        return

    ui.section("Cancella Pipeline")
    ui.print("\n  Pipeline attive:\n")

    for i, pipeline in enumerate(active_pipelines, 1):
        ui.print(f"  [{i}] {pipeline.status_icon} #{pipeline.number} [{pipeline.state}]")

    choice = input("\n  Numero da cancellare (INVIO per annullare): ").strip()

    if not choice.isdigit():
        return

    idx = int(choice) - 1
    if 0 <= idx < len(active_pipelines):
        pipeline = active_pipelines[idx]

        # Ottieni workflow attivi
        workflows = ci_client.get_pipeline_workflows(pipeline.id)
        active_workflows = [w for w in workflows if w.is_active]

        if not active_workflows:
            ui.warning("Nessun workflow attivo trovato")
            input("\n  Premi INVIO per continuare...")
            return

        # Cancella i workflow attivi
        for wf in active_workflows:
            ui.print(f"\n  Cancellazione workflow {wf.name}...")
            if ci_client.cancel_workflow(wf.id):
                ui.success(f"Workflow {wf.name} cancellato")
            else:
                ui.error(f"Errore nella cancellazione di {wf.name}")

    input("\n  Premi INVIO per continuare...")


# =============================================================================
# SETTINGS MENU
# =============================================================================

def show_settings_menu(ui: ConsoleUI, loader: ConfigLoader) -> None:
    """Menu impostazioni globali"""
    settings_path = Path("config/settings.yaml")

    while True:
        # Legge direttamente dal YAML per avere accesso a tutte le sezioni
        with open(settings_path, 'r', encoding='utf-8') as f:
            yaml_data = yaml.safe_load(f) or {}

        app = yaml_data.get('app', {})
        browser = yaml_data.get('browser', {})
        notifications = yaml_data.get('notifications', {})
        logging_cfg = yaml_data.get('logging', {})

        language = app.get('language', 'it')
        headless = browser.get('headless', False)
        desktop_enabled = notifications.get('desktop', {}).get('enabled', False)
        email_enabled = notifications.get('email', {}).get('enabled', False)
        teams_enabled = notifications.get('teams', {}).get('enabled', False)
        log_level = logging_cfg.get('level', 'INFO')

        ui.section("Impostazioni")

        # Mostra stato corrente
        ui.print("")
        ui.print(f"  Lingua:      {language.upper()}")
        ui.print(f"  Headless:    {'ON' if headless else 'OFF'}")
        ui.print(f"  Notifiche:   Desktop={'ON' if desktop_enabled else 'OFF'}, "
                f"Email={'ON' if email_enabled else 'OFF'}, "
                f"Teams={'ON' if teams_enabled else 'OFF'}")
        ui.print(f"  Log Level:   {log_level}")
        ui.print("")

        items = [
            MenuItem('1', 'Lingua', f"Attuale: {language.upper()}"),
            MenuItem('2', 'Notifiche', 'Configura Desktop, Email, Teams'),
            MenuItem('3', 'Browser', 'Headless, viewport, screenshot'),
            MenuItem('4', 'Logging', f"Livello: {log_level}"),
            MenuItem('5', 'Test Notifiche', 'Invia notifica di test'),
        ]

        choice = ui.menu(items, ">", allow_back=True)

        if choice is None:
            return

        elif choice == '1':
            _settings_language(ui, loader, settings_path)

        elif choice == '2':
            _settings_notifications(ui, loader, settings_path)

        elif choice == '3':
            _settings_browser(ui, loader, settings_path)

        elif choice == '4':
            _settings_logging(ui, loader, settings_path)

        elif choice == '5':
            _settings_test_notify(ui, loader)


def _load_settings_yaml(settings_path: Path) -> dict:
    """Helper per caricare settings.yaml come dizionario"""
    with open(settings_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


def _settings_language(ui: ConsoleUI, loader: ConfigLoader, settings_path: Path) -> None:
    """Cambia lingua"""
    ui.section("Lingua Interfaccia")

    items = [
        MenuItem('1', 'Italiano', 'Interfaccia in italiano'),
        MenuItem('2', 'English', 'English interface'),
    ]

    choice = ui.menu(items, ">", allow_back=True)

    if choice is None:
        return

    new_lang = 'it' if choice == '1' else 'en'

    _update_settings_yaml(settings_path, ['app', 'language'], new_lang)
    set_language(new_lang)
    ui.success(f"Lingua cambiata in {'Italiano' if new_lang == 'it' else 'English'}")


def _settings_notifications(ui: ConsoleUI, loader: ConfigLoader, settings_path: Path) -> None:
    """Menu configurazione notifiche"""
    while True:
        data = _load_settings_yaml(settings_path)
        notifications = data.get('notifications', {})

        ui.section("Notifiche")

        desktop_status = "ON" if notifications.get('desktop', {}).get('enabled', False) else "OFF"
        email_status = "ON" if notifications.get('email', {}).get('enabled', False) else "OFF"
        teams_status = "ON" if notifications.get('teams', {}).get('enabled', False) else "OFF"

        items = [
            MenuItem('1', f'Desktop: {desktop_status}', 'Notifiche macOS native'),
            MenuItem('2', f'Email: {email_status}', 'Notifiche via SMTP'),
            MenuItem('3', f'Teams: {teams_status}', 'Notifiche Microsoft Teams'),
            MenuItem('4', 'Trigger', 'Quando inviare notifiche'),
        ]

        choice = ui.menu(items, ">", allow_back=True)

        if choice is None:
            return

        elif choice == '1':
            # Toggle Desktop
            current = notifications.get('desktop', {}).get('enabled', False)
            new_val = not current
            _update_settings_yaml(settings_path, ['notifications', 'desktop', 'enabled'], new_val)
            ui.success(f"Desktop notifications {'abilitate' if new_val else 'disabilitate'}")

        elif choice == '2':
            # Email config
            _settings_email(ui, loader, settings_path)

        elif choice == '3':
            # Toggle Teams
            current = notifications.get('teams', {}).get('enabled', False)
            new_val = not current
            _update_settings_yaml(settings_path, ['notifications', 'teams', 'enabled'], new_val)
            ui.success(f"Teams notifications {'abilitate' if new_val else 'disabilitate'}")
            if new_val:
                ui.info("Assicurati di impostare TEAMS_WEBHOOK_URL")

        elif choice == '4':
            # Trigger config
            _settings_triggers(ui, loader, settings_path)


def _settings_email(ui: ConsoleUI, loader: ConfigLoader, settings_path: Path) -> None:
    """Configurazione email"""
    data = _load_settings_yaml(settings_path)
    email = data.get('notifications', {}).get('email', {})

    ui.section("Configurazione Email")

    enabled = email.get('enabled', False)
    smtp_host = email.get('smtp_host', 'smtp.gmail.com')
    smtp_port = email.get('smtp_port', 587)
    smtp_user = email.get('smtp_user', '')
    recipients = email.get('recipients', [])

    items = [
        MenuItem('1', f"Abilita: {'ON' if enabled else 'OFF'}", 'Toggle abilitazione'),
        MenuItem('2', 'SMTP Host', f"Attuale: {smtp_host}"),
        MenuItem('3', 'SMTP Port', f"Attuale: {smtp_port}"),
        MenuItem('4', 'Username', f"Attuale: {smtp_user or '-'}"),
        MenuItem('5', 'Destinatari', f"Attuale: {', '.join(recipients) or '-'}"),
    ]

    choice = ui.menu(items, ">", allow_back=True)

    if choice is None:
        return

    elif choice == '1':
        new_val = not enabled
        _update_settings_yaml(settings_path, ['notifications', 'email', 'enabled'], new_val)
        ui.success(f"Email notifications {'abilitate' if new_val else 'disabilitate'}")

    elif choice == '2':
        host = ui.input("SMTP Host", smtp_host)
        _update_settings_yaml(settings_path, ['notifications', 'email', 'smtp_host'], host)
        ui.success(f"SMTP Host impostato: {host}")

    elif choice == '3':
        port = ui.input("SMTP Port", str(smtp_port))
        _update_settings_yaml(settings_path, ['notifications', 'email', 'smtp_port'], int(port))
        ui.success(f"SMTP Port impostato: {port}")

    elif choice == '4':
        user = ui.input("SMTP Username (email)", smtp_user)
        _update_settings_yaml(settings_path, ['notifications', 'email', 'smtp_user'], user)
        ui.success(f"SMTP User impostato: {user}")

    elif choice == '5':
        recipients_input = ui.input("Destinatari (separati da virgola)", ', '.join(recipients))
        recipients_list = [r.strip() for r in recipients_input.split(',') if r.strip()]
        _update_settings_yaml(settings_path, ['notifications', 'email', 'recipients'], recipients_list)
        ui.success(f"Destinatari impostati: {recipients_list}")


def _settings_triggers(ui: ConsoleUI, loader: ConfigLoader, settings_path: Path) -> None:
    """Configurazione trigger notifiche"""
    data = _load_settings_yaml(settings_path)
    triggers = data.get('notifications', {}).get('triggers', {})

    ui.section("Trigger Notifiche")
    ui.print("\n  Quando inviare notifiche:\n")

    on_complete = triggers.get('on_complete', False)
    on_failure = triggers.get('on_failure', True)
    on_regression = triggers.get('on_regression', True)
    on_flaky = triggers.get('on_flaky', False)

    items = [
        MenuItem('1', f"On Complete: {'ON' if on_complete else 'OFF'}", 'Ogni run completato'),
        MenuItem('2', f"On Failure: {'ON' if on_failure else 'OFF'}", 'Solo se fallimenti'),
        MenuItem('3', f"On Regression: {'ON' if on_regression else 'OFF'}", 'Se rilevate regressioni'),
        MenuItem('4', f"On Flaky: {'ON' if on_flaky else 'OFF'}", 'Se test flaky rilevati'),
    ]

    choice = ui.menu(items, ">", allow_back=True)

    if choice is None:
        return

    trigger_map = {
        '1': ('on_complete', on_complete),
        '2': ('on_failure', on_failure),
        '3': ('on_regression', on_regression),
        '4': ('on_flaky', on_flaky),
    }

    if choice in trigger_map:
        key, current = trigger_map[choice]
        new_val = not current
        _update_settings_yaml(settings_path, ['notifications', 'triggers', key], new_val)
        ui.success(f"{key} {'abilitato' if new_val else 'disabilitato'}")


def _settings_browser(ui: ConsoleUI, loader: ConfigLoader, settings_path: Path) -> None:
    """Configurazione browser"""
    data = _load_settings_yaml(settings_path)
    browser = data.get('browser', {})
    viewport = browser.get('viewport', {})

    headless = browser.get('headless', False)
    vp_width = viewport.get('width', 1280)
    vp_height = viewport.get('height', 720)
    slow_mo = browser.get('slow_mo', 0)

    ui.section("Configurazione Browser")

    items = [
        MenuItem('1', f"Headless: {'ON' if headless else 'OFF'}", 'Browser nascosto'),
        MenuItem('2', f"Viewport: {vp_width}x{vp_height}", 'Dimensioni finestra'),
        MenuItem('3', f"Slow Mo: {slow_mo}ms", 'Rallenta azioni (debug)'),
    ]

    choice = ui.menu(items, ">", allow_back=True)

    if choice is None:
        return

    elif choice == '1':
        new_val = not headless
        _update_settings_yaml(settings_path, ['browser', 'headless'], new_val)
        ui.success(f"Headless {'abilitato' if new_val else 'disabilitato'}")

    elif choice == '2':
        width = ui.input("Larghezza", str(vp_width))
        height = ui.input("Altezza", str(vp_height))
        _update_settings_yaml(settings_path, ['browser', 'viewport', 'width'], int(width))
        _update_settings_yaml(settings_path, ['browser', 'viewport', 'height'], int(height))
        ui.success(f"Viewport impostato: {width}x{height}")

    elif choice == '3':
        slow = ui.input("Slow Mo (ms)", str(slow_mo))
        _update_settings_yaml(settings_path, ['browser', 'slow_mo'], int(slow))
        ui.success(f"Slow Mo impostato: {slow}ms")


def _settings_logging(ui: ConsoleUI, loader: ConfigLoader, settings_path: Path) -> None:
    """Configurazione logging"""
    ui.section("Configurazione Logging")

    items = [
        MenuItem('1', 'DEBUG', 'Tutto, molto verboso'),
        MenuItem('2', 'INFO', 'Informazioni standard'),
        MenuItem('3', 'WARNING', 'Solo avvertimenti e errori'),
        MenuItem('4', 'ERROR', 'Solo errori'),
    ]

    choice = ui.menu(items, ">", allow_back=True)

    if choice is None:
        return

    level_map = {'1': 'DEBUG', '2': 'INFO', '3': 'WARNING', '4': 'ERROR'}

    if choice in level_map:
        new_level = level_map[choice]
        _update_settings_yaml(settings_path, ['logging', 'level'], new_level)
        ui.success(f"Log level impostato: {new_level}")


def _settings_test_notify(ui: ConsoleUI, loader: ConfigLoader) -> None:
    """Testa le notifiche configurate"""
    from src.notifications import NotificationManager, NotificationConfig, TestRunSummary

    settings_path = Path("config/settings.yaml")
    data = _load_settings_yaml(settings_path)
    notifications = data.get('notifications', {})

    ui.section("Test Notifiche")

    # Crea summary di test (pass_rate è calcolato automaticamente come property)
    summary = TestRunSummary(
        project="test-project",
        run_number=999,
        total_tests=10,
        passed=8,
        failed=2
    )

    # Crea NotificationConfig dai dati YAML
    config = NotificationConfig(
        desktop_enabled=notifications.get('desktop', {}).get('enabled', False),
        email_enabled=notifications.get('email', {}).get('enabled', False),
        teams_enabled=notifications.get('teams', {}).get('enabled', False),
    )
    manager = NotificationManager(config)

    ui.info("Invio notifiche di test...")
    results = manager.notify_run_complete(summary)

    for channel, success in results.items():
        if success:
            ui.success(f"{channel}: inviata")
        else:
            ui.warning(f"{channel}: fallita o disabilitata")

    input("\n  Premi INVIO per continuare...")


def _update_settings_yaml(path: Path, keys: list, value) -> None:
    """Aggiorna un valore nel file settings.yaml preservando la struttura"""
    with open(path, 'r') as f:
        data = yaml.safe_load(f)

    # Naviga fino alla chiave da modificare
    current = data
    for key in keys[:-1]:
        current = current[key]

    current[keys[-1]] = value

    with open(path, 'w') as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def show_analysis_menu(ui: ConsoleUI, loader: ConfigLoader) -> None:
    """Menu per analisi testing (comparison, regression, flaky)"""
    from src.comparison import (
        RunComparator, RegressionDetector, CoverageAnalyzer,
        FlakyTestDetector, format_comparison_report
    )
    from src.sheets_client import GoogleSheetsClient

    # Seleziona progetto
    project_name = show_project_menu(ui, loader)
    if not project_name:
        return

    try:
        project = loader.load_project(project_name)
    except FileNotFoundError:
        ui.error(f"Progetto '{project_name}' non trovato")
        return

    # Inizializza sheets client
    sheets_client = None
    local_reports_path = Path(f"reports/{project_name}")

    if project.google_sheets.enabled:
        try:
            credentials_path = str(Path("config/credentials.json"))
            sheets_client = GoogleSheetsClient(
                credentials_path=credentials_path,
                spreadsheet_id=project.google_sheets.spreadsheet_id,
                drive_folder_id=project.google_sheets.drive_folder_id
            )
            ui.info(f"Connesso a Google Sheets")
        except Exception as e:
            ui.warning(f"Google Sheets non disponibile: {e}")

    # Inizializza comparator con parametri corretti
    comparator = RunComparator(
        sheets_client=sheets_client,
        local_reports_path=local_reports_path
    )
    regression_detector = RegressionDetector(comparator)
    flaky_detector = FlakyTestDetector(comparator)

    while True:
        ui.section(f"Analisi Testing: {project_name}")

        items = [
            MenuItem('1', 'Confronta RUN', 'A/B comparison tra due run'),
            MenuItem('2', 'Rileva Regressioni', 'Test che passavano e ora falliscono'),
            MenuItem('3', 'Test Flaky', 'Test con risultati inconsistenti'),
            MenuItem('4', 'Coverage', 'Analisi copertura test'),
            MenuItem('5', 'Report Stabilita', 'Overview stabilita test suite'),
            MenuItem('6', 'Performance', 'Metriche e trend di performance'),
        ]

        choice = ui.menu(items, "Azione", allow_back=True)

        if choice is None:
            return

        elif choice == '1':
            _analysis_compare_runs(ui, comparator)

        elif choice == '2':
            _analysis_regressions(ui, regression_detector)

        elif choice == '3':
            _analysis_flaky(ui, flaky_detector)

        elif choice == '4':
            _analysis_coverage(ui, project, comparator)

        elif choice == '5':
            _analysis_stability(ui, flaky_detector)

        elif choice == '6':
            _analysis_performance(ui, project_name, loader)


def _analysis_compare_runs(ui: ConsoleUI, comparator) -> None:
    """Sottomenu confronto RUN"""
    from src.comparison import format_comparison_report

    ui.section("Confronta RUN")

    # Chiedi quale confronto
    ui.print("\n  Opzioni:")
    ui.print("  [1] Ultimi 2 run")
    ui.print("  [2] Specifica run")

    choice = input("\n  > ").strip()

    if choice == '1':
        result = comparator.compare_latest()
        if result:
            ui.print(format_comparison_report(result))
        else:
            ui.warning("Servono almeno 2 run per confrontare")

    elif choice == '2':
        try:
            run_a = int(input("  RUN A (baseline): ").strip())
            run_b = int(input("  RUN B (nuova): ").strip())
            result = comparator.compare(run_a, run_b)
            ui.print(format_comparison_report(result))
        except ValueError:
            ui.warning("Inserisci numeri validi")
        except Exception as e:
            ui.error(f"Errore: {e}")

    ui.print("\n  [dim]Premi INVIO per continuare...[/dim]")
    input()


def _analysis_regressions(ui: ConsoleUI, detector) -> None:
    """Sottomenu regressioni"""
    ui.section("Rileva Regressioni")

    ui.print("\n  Quale run analizzare?")
    ui.print("  [1] Ultima run (confronta con precedente)")
    ui.print("  [2] Run specifica")

    choice = input("\n  > ").strip()

    try:
        if choice == '1':
            regressions = detector.check_for_regressions(0)  # 0 = ultima
        else:
            run_num = int(input("  Numero RUN: ").strip())
            regressions = detector.check_for_regressions(run_num)

        if not regressions:
            ui.success("Nessuna regressione rilevata")
        else:
            # Filtra solo regressioni (PASS->FAIL)
            real_regressions = [r for r in regressions if r.change_type == 'regression']
            improvements = [r for r in regressions if r.change_type == 'improvement']

            if real_regressions:
                ui.print(f"\n  [red]REGRESSIONI ({len(real_regressions)}):[/red]")
                for r in real_regressions:
                    ui.print(f"    - {r.test_id}: PASS -> FAIL")

            if improvements:
                ui.print(f"\n  [green]MIGLIORAMENTI ({len(improvements)}):[/green]")
                for r in improvements:
                    ui.print(f"    + {r.test_id}: FAIL -> PASS")

    except Exception as e:
        ui.error(f"Errore: {e}")

    ui.print("\n  [dim]Premi INVIO per continuare...[/dim]")
    input()


def _analysis_flaky(ui: ConsoleUI, detector) -> None:
    """Sottomenu test flaky"""
    ui.section("Test Flaky")

    n_runs = input("  Analizza ultimi N run (default 10): ").strip()
    n_runs = int(n_runs) if n_runs.isdigit() else 10

    threshold = input("  Soglia flaky 0-1 (default 0.3): ").strip()
    try:
        threshold = float(threshold) if threshold else 0.3
    except ValueError:
        threshold = 0.3

    ui.print(f"\n  Analisi test flaky su ultimi {n_runs} run (soglia: {threshold})...")

    try:
        flaky_tests = detector.detect_flaky_tests(n_runs, threshold)

        if not flaky_tests:
            ui.success("Nessun test flaky rilevato")
        else:
            ui.print(f"\n  [yellow]TEST FLAKY ({len(flaky_tests)}):[/yellow]")
            for ft in flaky_tests[:20]:  # Mostra max 20
                score_bar = "#" * int(ft.flaky_score * 10)
                ui.print(f"    {ft.test_id}: score={ft.flaky_score:.2f} [{score_bar}]")
                ui.print(f"      PASS: {ft.pass_count}, FAIL: {ft.fail_count}, SKIP: {ft.skip_count}")

            if len(flaky_tests) > 20:
                ui.print(f"    [dim]... +{len(flaky_tests)-20} altri[/dim]")

    except Exception as e:
        ui.error(f"Errore: {e}")

    ui.print("\n  [dim]Premi INVIO per continuare...[/dim]")
    input()


def _analysis_coverage(ui: ConsoleUI, project, comparator) -> None:
    """Sottomenu coverage"""
    from src.comparison import CoverageAnalyzer

    ui.section("Analisi Coverage")

    try:
        analyzer = CoverageAnalyzer(comparator)
        # Carica test da file
        test_file = project.project_dir / "tests.csv"
        if not test_file.exists():
            ui.warning("File tests.csv non trovato")
            input()
            return

        import csv
        tests = []
        with open(test_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                tests.append(row)

        report = analyzer.analyze(tests)

        ui.print(f"\n  Totale test: [cyan]{report.total_tests}[/cyan]")
        ui.print(f"  Categorie coperte: [cyan]{report.categories_covered}[/cyan]")

        if report.category_distribution:
            ui.print("\n  Distribuzione per categoria:")
            for cat, count in sorted(report.category_distribution.items(), key=lambda x: -x[1]):
                pct = count / report.total_tests * 100
                bar = "#" * int(pct / 5)
                ui.print(f"    {cat}: {count} ({pct:.0f}%) [{bar}]")

        if report.gaps:
            ui.print("\n  [yellow]Gap identificati:[/yellow]")
            for gap in report.gaps:
                ui.print(f"    - {gap}")

    except Exception as e:
        ui.error(f"Errore: {e}")

    ui.print("\n  [dim]Premi INVIO per continuare...[/dim]")
    input()


def _analysis_stability(ui: ConsoleUI, detector) -> None:
    """Sottomenu report stabilita"""
    ui.section("Report Stabilita")

    n_runs = input("  Analizza ultimi N run (default 10): ").strip()
    n_runs = int(n_runs) if n_runs.isdigit() else 10

    try:
        report = detector.get_stability_report(n_runs)

        ui.print(f"\n  [bold]Stabilita Test Suite[/bold] (ultimi {n_runs} run)\n")

        ui.print(f"  Test totali analizzati: {report['total_tests']}")
        ui.print(f"  Run analizzati: {report['runs_analyzed']}")

        stable_pct = report['stable_tests'] / report['total_tests'] * 100 if report['total_tests'] > 0 else 0
        ui.print(f"\n  Test stabili: [green]{report['stable_tests']}[/green] ({stable_pct:.0f}%)")
        ui.print(f"  Test flaky: [yellow]{report['flaky_tests']}[/yellow]")
        ui.print(f"  Test sempre falliti: [red]{report['always_failing']}[/red]")

        ui.print(f"\n  Score medio stabilita: [cyan]{report['average_stability']:.2f}[/cyan] / 1.0")

        # Visualizza barra stabilita
        bar_filled = int(report['average_stability'] * 20)
        bar = "[" + "#" * bar_filled + "-" * (20 - bar_filled) + "]"
        ui.print(f"  {bar}")

    except Exception as e:
        ui.error(f"Errore: {e}")

    ui.print("\n  [dim]Premi INVIO per continuare...[/dim]")
    input()


def _analysis_performance(ui: ConsoleUI, project_name: str, loader: ConfigLoader) -> None:
    """Sottomenu metriche di performance"""
    from src.performance import (
        PerformanceHistory, PerformanceReporter, PerformanceAlerter,
        compare_environments, format_comparison_report
    )

    ui.section("Performance Metrics")

    # Carica storico
    history = PerformanceHistory(project_name, Path("reports"))

    while True:
        items = [
            MenuItem('1', 'Report ultimo run', 'Mostra metriche dell\'ultimo run'),
            MenuItem('2', 'Dashboard storica', 'Trend ultimi N run'),
            MenuItem('3', 'Confronta run', 'Compara due run specifici'),
            MenuItem('4', 'Esporta HTML', 'Genera report HTML interattivo'),
        ]

        choice = ui.menu(items, "Performance", allow_back=True)

        if choice is None:
            return

        elif choice == '1':
            # Report ultimo run
            metrics_list = history.load_history(last_n=1)
            if not metrics_list:
                ui.warning("Nessuna metrica trovata")
                ui.print("Esegui test per generare metriche")
                continue

            reporter = PerformanceReporter(metrics_list[0])
            ui.print(reporter.generate_summary())

            # Check alerting
            alerter = PerformanceAlerter()
            alerts = alerter.check(metrics_list[0])
            if alerts:
                ui.print(alerter.format_alerts())

        elif choice == '2':
            # Dashboard storica
            n_runs = input("  Ultimi N run (default 10): ").strip()
            n_runs = int(n_runs) if n_runs.isdigit() else 10

            trends = history.get_trends(n_runs)

            if "message" in trends:
                ui.warning(trends["message"])
                continue

            ui.print(f"\n{'='*60}")
            ui.print(f"  PERFORMANCE DASHBOARD - {project_name}")
            ui.print(f"  Ultimi {n_runs} run")
            ui.print(f"{'='*60}\n")

            for metric_name, trend_data in trends.items():
                trend_icon = "📈" if trend_data["trend"] == "increasing" else "📉" if trend_data["trend"] == "decreasing" else "➡️"
                change_sign = "+" if trend_data["change_percent"] > 0 else ""

                good_decreasing = metric_name in ["duration", "error_rate", "chatbot_latency", "sheets_latency"]
                if good_decreasing:
                    color = "green" if trend_data["trend"] == "decreasing" else "red" if trend_data["trend"] == "increasing" else "dim"
                else:
                    color = "green" if trend_data["trend"] == "increasing" else "red" if trend_data["trend"] == "decreasing" else "dim"

                ui.print(f"  {trend_icon} {metric_name.replace('_', ' ').title()}")
                ui.print(f"     Attuale: {trend_data['current']}")
                ui.print(f"     Media: {trend_data['average']}")
                ui.print(f"     Trend: [{color}]{change_sign}{trend_data['change_percent']:.1f}%[/{color}]")
                ui.print("")

        elif choice == '3':
            # Confronta run
            try:
                run_a = input("  RUN A (baseline): ").strip()
                run_b = input("  RUN B (nuova): ").strip()

                metrics_list = history.load_history(last_n=50)

                metrics_a = None
                metrics_b = None
                for m in metrics_list:
                    if str(m.run_id) == run_a:
                        metrics_a = m
                    if str(m.run_id) == run_b:
                        metrics_b = m

                if not metrics_a:
                    ui.error(f"Run {run_a} non trovato")
                    continue
                if not metrics_b:
                    ui.error(f"Run {run_b} non trovato")
                    continue

                comparison = compare_environments(metrics_a, metrics_b)
                ui.print(format_comparison_report(comparison))

            except ValueError as e:
                ui.error(f"Errore: {e}")

        elif choice == '4':
            # Esporta HTML
            metrics_list = history.load_history(last_n=1)
            if not metrics_list:
                ui.warning("Nessuna metrica trovata")
                continue

            metrics = metrics_list[0]
            report_dir = loader.get_report_dir(project_name)
            export_dir = report_dir / "exports"
            export_dir.mkdir(parents=True, exist_ok=True)

            output_file = export_dir / f"performance_{metrics.run_id}.html"

            reporter = PerformanceReporter(metrics)
            html = reporter.generate_html_report()

            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(html)

            ui.success(f"Esportato: {output_file}")

            # Apri nel browser
            import webbrowser
            webbrowser.open(f"file://{output_file}")

        ui.print("\n  [dim]Premi INVIO per continuare...[/dim]")
        input()


# ═══════════════════════════════════════════════════════════════════════════════
# Interactive Menu: Prompt Manager
# ═══════════════════════════════════════════════════════════════════════════════

def show_project_actions_menu(ui: ConsoleUI, project_name: str) -> Optional[str]:
    """
    Menu azioni progetto (dopo selezione progetto).

    Returns:
        Scelta utente: 'run', 'prompt', 'visualizer', 'diagnose', None per back
    """
    ui.section(f"Progetto: {project_name}")

    items = [
        MenuItem('1', 'Gestione RUN', 'Esegui test, configura run'),
        MenuItem('2', 'Prompt Manager', 'Versioni, import, export prompt'),
        MenuItem('3', 'Visualizer', 'Visualizza prompt e test'),
        MenuItem('4', 'Diagnosi', 'Analizza fallimenti test'),
    ]

    choice = ui.menu(items, ">", allow_back=True)

    if choice is None:
        return None

    return {'1': 'run', '2': 'prompt', '3': 'visualizer', '4': 'diagnose'}.get(choice)


def show_prompt_manager_menu(ui: ConsoleUI, project_name: str, base_dir: Path) -> None:
    """Menu interattivo per gestione prompt"""
    from src.prompt_manager import PromptManager

    manager = PromptManager(project_name, base_dir)

    while True:
        versions = manager.list_versions()
        current = manager.get_current_version()  # PromptVersion, non contenuto

        ui.section(f"Prompt Manager: {project_name}")

        if current:
            version_id = f"v{current.version:03d}"
            if current.tag:
                version_id += f"_{current.tag}"
            ui.print(f"  Versione corrente: [cyan]{version_id}[/cyan]")
            ui.print(f"  Data: [dim]{current.date}[/dim]")
            ui.print("")
        else:
            ui.warning("Nessun prompt versionato")
            ui.print("")

        items = [
            MenuItem('1', 'Lista versioni', f'{len(versions)} versioni disponibili'),
            MenuItem('2', 'Mostra corrente', 'Visualizza prompt attuale'),
            MenuItem('3', 'Importa prompt', 'Da file esterno'),
            MenuItem('4', 'Esporta prompt', 'Salva versione su file'),
            MenuItem('5', 'Diff versioni', 'Confronta due versioni'),
        ]

        choice = ui.menu(items, ">", allow_back=True)

        if choice is None:
            break

        elif choice == '1':
            # Lista versioni
            _prompt_list_interactive(ui, manager)

        elif choice == '2':
            # Mostra corrente
            _prompt_show_interactive(ui, manager)

        elif choice == '3':
            # Importa prompt
            _prompt_import_interactive(ui, manager)

        elif choice == '4':
            # Esporta prompt
            _prompt_export_interactive(ui, manager)

        elif choice == '5':
            # Diff versioni
            _prompt_diff_interactive(ui, manager)


def _prompt_list_interactive(ui: ConsoleUI, manager) -> None:
    """Lista versioni prompt"""
    versions = manager.list_versions()

    if not versions:
        ui.warning("Nessuna versione salvata")
        input("\n  Premi INVIO per continuare...")
        return

    ui.section(f"Versioni ({len(versions)})")

    # Header
    ui.print(f"  {'Ver':<8} {'Data':<12} {'Tag':<15} {'Note':<30}")
    ui.print("  " + "-" * 70)

    for v in versions[-10:]:  # Ultime 10
        version_id = f"v{v.version:03d}"
        tag = v.tag[:15] if v.tag else "-"
        note = (v.note[:28] + "..") if len(v.note) > 30 else v.note
        ui.print(f"  {version_id:<8} {v.date[:10]:<12} {tag:<15} {note:<30}")

    if len(versions) > 10:
        ui.muted(f"\n  ... e altre {len(versions) - 10} versioni")

    input("\n  Premi INVIO per continuare...")


def _prompt_show_interactive(ui: ConsoleUI, manager) -> None:
    """Mostra prompt corrente"""
    current = manager.get_current_version()

    if not current:
        ui.warning("Nessun prompt salvato")
        input("\n  Premi INVIO per continuare...")
        return

    content = manager.get_version(current.version)
    if not content:
        ui.error("File prompt non trovato")
        input("\n  Premi INVIO per continuare...")
        return

    ui.section(f"Prompt v{current.version:03d}")
    ui.print(f"  Data: {current.date}")
    ui.print(f"  Note: {current.note}")
    if current.tag:
        ui.print(f"  Tag: {current.tag}")
    ui.print("")

    # Mostra prime 30 righe
    lines = content.split('\n')[:30]
    for line in lines:
        ui.print(f"  {line[:100]}")

    if len(content.split('\n')) > 30:
        ui.muted(f"\n  ... ({len(content.split(chr(10)))} righe totali)")

    input("\n  Premi INVIO per continuare...")


def _prompt_import_interactive(ui: ConsoleUI, manager) -> None:
    """Importa prompt da file"""
    ui.section("Importa Prompt")

    filepath = ui.input("Percorso file prompt", default="")
    if not filepath:
        return

    path = Path(filepath).expanduser()
    if not path.exists():
        ui.error(f"File non trovato: {path}")
        input("\n  Premi INVIO per continuare...")
        return

    # Leggi preview
    content = path.read_text()
    lines = content.split('\n')

    ui.print(f"\n  Preview ({len(lines)} righe):")
    for line in lines[:5]:
        ui.print(f"    {line[:80]}")
    if len(lines) > 5:
        ui.muted(f"    ... e altre {len(lines) - 5} righe")

    # Chiedi tag
    tag = ui.input("Tag versione (opzionale)", default="")
    note = ui.input("Note", default="imported from file")

    if ui.confirm("Importare come nuova versione?", default=True):
        try:
            # Usa save() direttamente per supportare tag
            version = manager.save(content, note=note, tag=tag, source="import")
            if version:
                ui.success(f"Importato come v{version.version:03d}")
            else:
                ui.warning("Contenuto identico alla versione precedente")
        except Exception as e:
            ui.error(f"Errore: {e}")

    input("\n  Premi INVIO per continuare...")


def _prompt_export_interactive(ui: ConsoleUI, manager) -> None:
    """Esporta prompt su file"""
    current = manager.get_current_version()

    if not current:
        ui.warning("Nessun prompt da esportare")
        input("\n  Premi INVIO per continuare...")
        return

    ui.section("Esporta Prompt")

    # Chiedi versione
    version_str = ui.input("Versione da esportare", default=str(current.version))
    try:
        version_num = int(version_str)
    except ValueError:
        ui.error("Versione non valida")
        input("\n  Premi INVIO per continuare...")
        return

    # Chiedi destinazione
    default_path = f"./prompt_v{version_num:03d}.txt"
    filepath = ui.input("Percorso destinazione", default=default_path)

    path = Path(filepath).expanduser()

    try:
        content = manager.get_version(version_num)
        if not content:
            ui.error(f"Versione {version_num} non trovata")
        else:
            path.write_text(content)
            ui.success(f"Esportato: {path}")
    except Exception as e:
        ui.error(f"Errore: {e}")

    input("\n  Premi INVIO per continuare...")


def _prompt_diff_interactive(ui: ConsoleUI, manager) -> None:
    """Confronta due versioni"""
    versions = manager.list_versions()

    if len(versions) < 2:
        ui.warning("Servono almeno 2 versioni per il confronto")
        input("\n  Premi INVIO per continuare...")
        return

    ui.section("Diff Versioni")

    # Lista versioni disponibili
    ui.print("  Versioni disponibili:")
    for v in versions[-5:]:
        ui.print(f"    v{v.version:03d} - {v.date[:10]} - {v.note[:40]}")

    # Chiedi versioni
    v1_str = ui.input("Prima versione", default=str(versions[-2].version))
    v2_str = ui.input("Seconda versione", default=str(versions[-1].version))

    try:
        v1 = int(v1_str)
        v2 = int(v2_str)
    except ValueError:
        ui.error("Versione non valida")
        input("\n  Premi INVIO per continuare...")
        return

    try:
        diff = manager.diff(v1, v2)

        ui.section(f"Diff v{v1:03d} -> v{v2:03d}")

        # Mostra diff (prime 50 righe)
        lines = diff.split('\n')[:50]
        for line in lines:
            if line.startswith('+'):
                ui.print(f"  [green]{line[:100]}[/green]")
            elif line.startswith('-'):
                ui.print(f"  [red]{line[:100]}[/red]")
            elif line.startswith('@'):
                ui.print(f"  [cyan]{line[:100]}[/cyan]")
            else:
                ui.print(f"  {line[:100]}")

        if len(diff.split('\n')) > 50:
            ui.muted(f"\n  ... e altre {len(diff.split(chr(10))) - 50} righe")

    except Exception as e:
        ui.error(f"Errore: {e}")

    input("\n  Premi INVIO per continuare...")


def show_finetuning_menu(ui: ConsoleUI, loader: ConfigLoader) -> None:
    """Menu per fine-tuning del modello valutatore"""
    from src.finetuning import FineTuningPipeline, DatasetStats

    # Seleziona progetto
    project_name = show_project_menu(ui, loader)
    if not project_name:
        return

    try:
        project = loader.load_project(project_name)
    except FileNotFoundError:
        ui.error(f"Progetto '{project_name}' non trovato")
        return

    pipeline = FineTuningPipeline(project.project_dir)

    while True:
        ui.section(t('finetuning_menu.title').format(project=project_name))

        # Mostra statistiche dataset corrente
        stats = pipeline.validate_dataset()
        ui.print(f"\n  {t('finetuning_menu.dataset_current')}: [cyan]{t('finetuning_menu.examples').format(count=stats.total_examples)}[/cyan]")
        ui.print(f"  {t('finetuning_menu.pass_count')}: [green]{stats.pass_count}[/green] | {t('finetuning_menu.fail_count')}: [red]{stats.fail_count}[/red] | {t('finetuning_menu.skip_count')}: [dim]{stats.skip_count}[/dim]")

        if stats.is_valid:
            ui.print(f"  Status: [green]{t('finetuning_menu.ready')}[/green]")
        else:
            ui.print(f"  Status: [yellow]{t('finetuning_menu.insufficient')}[/yellow]")

        ui.print("")

        items = [
            MenuItem('1', t('finetuning_menu.stats'), t('finetuning_menu.stats_desc')),
            MenuItem('2', t('finetuning_menu.export'), t('finetuning_menu.export_desc')),
            MenuItem('3', t('finetuning_menu.finetune_ollama'), t('finetuning_menu.finetune_ollama_desc'), disabled=not stats.is_valid),
            MenuItem('4', t('finetuning_menu.finetune_openai'), t('finetuning_menu.finetune_openai_desc'), disabled=not stats.is_valid),
            MenuItem('5', t('finetuning_menu.test_model'), t('finetuning_menu.test_model_desc')),
            MenuItem('6', t('finetuning_menu.available_models'), t('finetuning_menu.available_models_desc')),
        ]

        choice = ui.menu(items, t('common.next'), allow_back=True)

        if choice is None:
            return

        elif choice == '1':
            # Statistiche dettagliate
            _show_dataset_stats(ui, stats)

        elif choice == '2':
            # Esporta dataset
            _export_dataset_menu(ui, pipeline)

        elif choice == '3':
            # Fine-tune Ollama
            _finetune_ollama_menu(ui, pipeline)

        elif choice == '4':
            # Fine-tune OpenAI
            _finetune_openai_menu(ui, pipeline)

        elif choice == '5':
            # Testa modello
            _test_model_menu(ui, pipeline)

        elif choice == '6':
            # Lista modelli
            _show_available_models(ui, pipeline)


def _show_dataset_stats(ui: ConsoleUI, stats) -> None:
    """Mostra statistiche dettagliate del dataset"""
    ui.section("Statistiche Dataset")

    ui.print(f"\n  Totale esempi: [cyan]{stats.total_examples}[/cyan]")
    ui.print(f"  PASS: [green]{stats.pass_count}[/green] ({stats.pass_count/stats.total_examples*100:.1f}%)" if stats.total_examples > 0 else "")
    ui.print(f"  FAIL: [red]{stats.fail_count}[/red] ({stats.fail_count/stats.total_examples*100:.1f}%)" if stats.total_examples > 0 else "")
    ui.print(f"  SKIP: [dim]{stats.skip_count}[/dim] ({stats.skip_count/stats.total_examples*100:.1f}%)" if stats.total_examples > 0 else "")

    ui.print(f"\n  Lunghezza media domanda: {stats.avg_question_length} caratteri")
    ui.print(f"  Lunghezza media risposta: {stats.avg_response_length} caratteri")

    if stats.categories:
        ui.print("\n  Categorie:")
        for cat, count in sorted(stats.categories.items(), key=lambda x: -x[1]):
            ui.print(f"    {cat}: {count}")

    if stats.issues:
        ui.print("\n  [yellow]Problemi rilevati:[/yellow]")
        for issue in stats.issues:
            ui.print(f"    - {issue}")

    ui.print(f"\n  Validità: {'[green]OK[/green]' if stats.is_valid else '[red]NON VALIDO[/red]'}")
    ui.print("\n  [dim]Requisiti minimi: 50+ esempi, 10+ PASS, 10+ FAIL[/dim]")

    ui.print("\n  [dim]Premi INVIO per continuare...[/dim]")
    input()


def _export_dataset_menu(ui: ConsoleUI, pipeline) -> None:
    """Menu esportazione dataset"""
    ui.section("Esporta Dataset")

    items = [
        MenuItem('1', 'JSONL (OpenAI)', 'Formato standard per fine-tuning'),
        MenuItem('2', 'Modelfile (Ollama)', 'Per ollama create'),
    ]

    choice = ui.menu(items, "Formato", allow_back=True)

    if choice == '1':
        try:
            path = pipeline.export_training_data(output_format="jsonl")
            ui.success(f"Dataset esportato: {path}")
        except Exception as e:
            ui.error(f"Errore: {e}")

    elif choice == '2':
        try:
            path = pipeline.export_training_data(output_format="ollama")
            ui.success(f"Modelfile creato: {path}")
        except Exception as e:
            ui.error(f"Errore: {e}")

    ui.print("\n  [dim]Premi INVIO per continuare...[/dim]")
    input()


def _finetune_ollama_menu(ui: ConsoleUI, pipeline) -> None:
    """Menu fine-tuning Ollama"""
    ui.section("Fine-tune con Ollama")

    # Lista modelli disponibili
    models = pipeline.get_available_models()
    ollama_models = models.get("ollama", [])

    if not ollama_models:
        ui.warning("Nessun modello Ollama trovato. Installa con: ollama pull llama3.2:3b")
        ui.print("\n  [dim]Premi INVIO per continuare...[/dim]")
        input()
        return

    ui.print("\n  Modelli Ollama disponibili:")
    for i, model in enumerate(ollama_models[:10], 1):
        ui.print(f"    [{i}] {model}")

    base_model = input("\n  Modello base (default: llama3.2:3b): ").strip() or "llama3.2:3b"
    output_name = input("  Nome modello output (default: chatbot-evaluator): ").strip() or "chatbot-evaluator"

    ui.print(f"\n  Creazione modello '{output_name}' da '{base_model}'...")

    success, message = pipeline.finetune_ollama(base_model, output_name)

    if success:
        ui.success(message)
        ui.print(f"\n  Usa il modello con: ollama run {output_name}")
    else:
        ui.error(message)

    ui.print("\n  [dim]Premi INVIO per continuare...[/dim]")
    input()


def _finetune_openai_menu(ui: ConsoleUI, pipeline) -> None:
    """Menu fine-tuning OpenAI"""
    import os

    ui.section("Fine-tune con OpenAI")

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        ui.warning("OPENAI_API_KEY non trovata nelle variabili d'ambiente")
        api_key = input("  Inserisci API key: ").strip()
        if not api_key:
            return

    # Esporta dataset
    ui.print("\n  Esportazione dataset JSONL...")
    try:
        jsonl_path = pipeline.export_training_data(output_format="jsonl")
    except Exception as e:
        ui.error(f"Errore esportazione: {e}")
        return

    ui.print(f"  Dataset: {jsonl_path}")

    base_model = input("\n  Modello base (default: gpt-4o-mini-2024-07-18): ").strip() or "gpt-4o-mini-2024-07-18"
    suffix = input("  Suffisso modello (default: chatbot-evaluator): ").strip() or "chatbot-evaluator"

    ui.warning("\n  ATTENZIONE: Il fine-tuning OpenAI ha un costo!")
    confirm = input("  Confermi? (s/n): ").strip().lower()

    if confirm != 's':
        ui.info("Operazione annullata")
        return

    ui.print("\n  Avvio job fine-tuning...")

    success, message = pipeline.finetune_openai(api_key, jsonl_path, base_model, suffix)

    if success:
        ui.success(message)
        ui.print("\n  Controlla lo stato su: https://platform.openai.com/finetune")
    else:
        ui.error(message)

    ui.print("\n  [dim]Premi INVIO per continuare...[/dim]")
    input()


def _test_model_menu(ui: ConsoleUI, pipeline) -> None:
    """Menu test modello"""
    ui.section("Testa Modello")

    model_name = input("  Nome modello da testare: ").strip()
    if not model_name:
        return

    provider = input("  Provider (ollama/openai, default: ollama): ").strip() or "ollama"

    # Split dataset
    ui.print("\n  Divisione dataset in train/test (80/20)...")
    train_set, test_set = pipeline.split_dataset(test_ratio=0.2)

    ui.print(f"  Test set: {len(test_set)} esempi")

    if len(test_set) < 5:
        ui.warning("Test set troppo piccolo")
        ui.print("\n  [dim]Premi INVIO per continuare...[/dim]")
        input()
        return

    ui.print(f"\n  Valutazione modello '{model_name}'...")

    results = pipeline.evaluate_model(model_name, test_set, provider)

    # Mostra risultati
    ui.section("Risultati")

    ui.print(f"\n  Accuracy: [cyan]{results['accuracy']*100:.1f}%[/cyan]")
    ui.print(f"  Corretti: [green]{results['correct']}[/green] / {results['total']}")

    ui.print(f"\n  FAIL Precision: {results['fail_precision']*100:.1f}%")
    ui.print(f"  FAIL Recall: {results['fail_recall']*100:.1f}%")

    ui.print("\n  Confusion Matrix:")
    cm = results['confusion_matrix']
    ui.print("            Predetto")
    ui.print("            PASS  FAIL  SKIP")
    ui.print(f"  Vero PASS   {cm['PASS']['PASS']:3d}   {cm['PASS']['FAIL']:3d}   {cm['PASS']['SKIP']:3d}")
    ui.print(f"       FAIL   {cm['FAIL']['PASS']:3d}   {cm['FAIL']['FAIL']:3d}   {cm['FAIL']['SKIP']:3d}")
    ui.print(f"       SKIP   {cm['SKIP']['PASS']:3d}   {cm['SKIP']['FAIL']:3d}   {cm['SKIP']['SKIP']:3d}")

    ui.print("\n  [dim]Premi INVIO per continuare...[/dim]")
    input()


def _show_available_models(ui: ConsoleUI, pipeline) -> None:
    """Mostra modelli disponibili"""
    ui.section("Modelli Disponibili")

    models = pipeline.get_available_models()

    ui.print("\n  [bold]Ollama (locale):[/bold]")
    if models['ollama']:
        for model in models['ollama']:
            ui.print(f"    - {model}")
    else:
        ui.print("    [dim]Nessun modello installato[/dim]")
        ui.print("    [dim]Installa con: ollama pull llama3.2:3b[/dim]")

    ui.print("\n  [bold]OpenAI (API):[/bold]")
    for model in models['openai']:
        ui.print(f"    - {model}")

    ui.print("\n  [dim]Premi INVIO per continuare...[/dim]")
    input()


def start_new_run_interactive(ui: ConsoleUI, run_config: RunConfig) -> bool:
    """
    Inizia una nuova RUN interattivamente.

    Returns:
        True se nuova RUN confermata, False se annullata
    """
    if run_config.active_run:
        ui.print(f"\n  [yellow]{t('run_menu.active_run').format(number=run_config.active_run)}[/yellow] ({run_config.tests_completed} {t('run_menu.tests_completed').lower()})")
        confirm = input(f"  {t('run_menu.confirm_new_run').format(count=run_config.tests_completed)} (s/n): ").strip().lower()
        if confirm != 's':
            ui.info(t('run_menu.cancelled'))
            return False

    # Reset RUN
    run_config.reset()

    # Configura nuova RUN
    configure_run_interactive(ui, run_config)

    ui.success(t('run_menu.new_run_ready'))
    return True


async def run_test_session(
    project: ProjectConfig,
    settings,
    mode: TestMode,
    test_filter: str = 'pending',
    single_test: str = None,
    force_new_run: bool = False,
    no_interactive: bool = False,
    single_turn: bool = False,
    test_limit: int = 0,
    test_ids: str = ''
):
    """Esegue una sessione di test"""
    ui = get_ui()

    def on_status(msg):
        ui.print(msg)

    def on_progress(current, total):
        ui.print(f"[{current}/{total}]", "dim")

    # Carica RunConfig
    run_config = RunConfig.load(project.run_config_file)
    run_config.mode = mode.value

    # Override single_turn from CLI flag
    if single_turn:
        run_config.single_turn = True

    # Se forza nuova RUN o non c'è RUN attiva
    if force_new_run:
        run_config.reset()

    # Passa toggle al tester
    tester = ChatbotTester(
        project,
        settings,
        on_status,
        on_progress,
        dry_run=run_config.dry_run,
        use_langsmith=run_config.use_langsmith,
        single_turn=run_config.single_turn,
        run_config=run_config
    )

    try:
        # Inizializza
        ui.section(t('test_execution.initializing'))
        if not await tester.initialize():
            ui.error(t('test_execution.init_failed'))
            return

        # Mostra stato toggle
        if run_config.dry_run:
            ui.warning(t('test_execution.dry_run_warning'))
        if not run_config.use_langsmith:
            ui.info(t('test_execution.langsmith_disabled'))

        # Setup foglio RUN su Google Sheets (solo se non dry_run)
        if tester.sheets and not run_config.dry_run:
            if not tester.sheets.setup_run_sheet(run_config, force_new=force_new_run):
                ui.warning(t('test_execution.sheets_error'))
            else:
                # Aggiorna run_config con il numero RUN assegnato
                run_config.active_run = tester.sheets.current_run
                run_config.save(project.run_config_file)
                ui.success(t('test_execution.sheets_connected').format(number=run_config.active_run))
                completed_count = len(tester.sheets.get_completed_tests())
                ui.print(f"   {t('test_execution.sheets_completed').format(count=completed_count)}")

        # Naviga al chatbot
        if not await tester.navigate_to_chatbot():
            ui.error(t('test_execution.chatbot_unreachable'))
            return

        # Carica test cases
        all_tests = tester.load_test_cases()

        if single_test:
            # Test singolo da CLI
            tests = [tc for tc in all_tests if tc.id == single_test]
            if not tests:
                ui.error(t('test_execution.test_not_found').format(id=single_test))
                return
        elif test_ids:
            # Lista test specifici da CLI (es: TEST_006,TEST_007,TEST_008)
            test_id_list = [tid.strip() for tid in test_ids.split(',')]
            tests = [tc for tc in all_tests if tc.id in test_id_list]
            if not tests:
                ui.error(f"Nessun test trovato per gli ID specificati: {test_ids}")
                return
            ui.info(f"Esecuzione di {len(tests)} test specifici")
        elif test_filter == 'select':
            # Selezione interattiva
            tests = show_test_selection(ui, all_tests)
            if not tests:
                ui.info(t('test_execution.no_tests'))
                return
        else:
            tests = all_tests

        # Filtra pending se richiesto
        if test_filter == 'pending' and tester.sheets:
            # Filtra solo test non completati in questa RUN
            completed = tester.sheets.get_completed_tests()
            tests = [tc for tc in tests if tc.id not in completed]
        elif test_filter == 'failed':
            # TODO: implementare filtro failed
            pass
        # Se test_filter == 'all', non filtriamo

        # Applica limite se specificato
        if test_limit > 0 and len(tests) > test_limit:
            ui.info(f"Limitato a {test_limit} test (di {len(tests)} disponibili)")
            tests = tests[:test_limit]

        if not tests:
            ui.info(t('test_execution.no_tests'))
            return

        ui.section(t('test_execution.running').format(count=len(tests), mode=mode.value))

        # Esegui
        if mode == TestMode.TRAIN:
            results = await tester.run_train_session(tests, skip_completed=False)
        elif mode == TestMode.ASSISTED:
            results = await tester.run_assisted_session(tests, skip_completed=False)
        else:
            results = await tester.run_auto_session(tests, skip_completed=False)

        # Aggiorna run_config
        run_config.tests_completed += len(results)
        if results:
            run_config.last_test_id = results[-1].test_case.id
        run_config.save(project.run_config_file)

        # Riepilogo
        ui.section(t('test_execution.summary'))
        passed = sum(1 for r in results if r.esito == 'PASS')
        failed = sum(1 for r in results if r.esito == 'FAIL')
        ui.stats_row({
            t('test_execution.total'): len(results),
            t('test_execution.passed'): passed,
            t('test_execution.failed'): failed,
            t('test_execution.pass_rate'): f"{(passed/len(results)*100):.1f}%" if results else "N/A"
        })

        # Next steps suggerimenti
        if results and not no_interactive:
            steps = NextSteps.after_test_run(
                project=project.name,
                run_number=run_config.active_run or 0,
                passed=passed,
                failed=failed
            )
            ui.muted(NextSteps.format(steps))

        # Auto-diagnosi se ci sono fallimenti
        if failed > 0 and not no_interactive:
            ui.print("")
            if ui.confirm("Eseguire diagnosi sui test falliti?", default=True):
                ui.print("")
                # Simula args per diagnose
                class DiagnoseArgs:
                    project = project.name
                    diagnose = True
                    diagnose_test = None
                    diagnose_run = run_config.active_run
                    diagnose_interactive = False
                    diagnose_model = 'generic'
                run_diagnose_command(DiagnoseArgs())

    finally:
        await tester.shutdown()


async def main_interactive(args):
    """Modalità interattiva con menu"""
    set_language(args.lang)
    ui = get_ui()
    loader = ConfigLoader()

    while True:
        choice = show_main_menu(ui, loader)

        if choice == 'quit':
            ui.print(t('main_menu.goodbye'))
            break

        elif choice == '1':
            # Nuovo progetto - avvia wizard
            from wizard.main import run_wizard
            success = run_wizard(language="it")
            if success:
                ui.success("Progetto creato! Selezionalo dal menu.")

        elif choice == '2':
            # Apri progetto
            project_name = show_project_menu(ui, loader)
            if project_name:
                try:
                    project = loader.load_project(project_name)
                    settings = loader.load_global_settings()

                    # Menu azioni progetto (nuovo livello)
                    while True:
                        action = show_project_actions_menu(ui, project_name)

                        if action is None:
                            break  # Torna al menu principale

                        elif action == 'prompt':
                            # Prompt Manager
                            show_prompt_manager_menu(ui, project_name, loader.base_dir)

                        elif action == 'visualizer':
                            # Visualizer (TODO: implementare menu)
                            ui.warning("Visualizer: usa CLI --viz-prompt o --viz-test")
                            input("\n  Premi INVIO per continuare...")

                        elif action == 'diagnose':
                            # Diagnosi
                            class DiagnoseArgs:
                                project = project_name
                                diagnose = True
                                diagnose_test = None
                                diagnose_run = None
                                diagnose_interactive = True
                                diagnose_model = 'generic'
                            run_diagnose_command(DiagnoseArgs())
                            input("\n  Premi INVIO per continuare...")

                        elif action == 'run':
                            # Gestione RUN (flusso esistente)
                            run_config = RunConfig.load(project.run_config_file)

                            run_choice = show_run_menu(ui, project, run_config)

                            force_new_run = False

                            if run_choice is None:
                                continue  # Torna al menu azioni progetto

                            elif run_choice == '1':
                                # Continua/Inizia RUN
                                if not run_config.active_run:
                                    configure_run_interactive(ui, run_config)
                                    run_config.save(project.run_config_file)

                            elif run_choice == '2':
                                # Forza nuova RUN
                                if start_new_run_interactive(ui, run_config):
                                    force_new_run = True
                                    run_config.save(project.run_config_file)
                                else:
                                    continue

                            elif run_choice == '3':
                                # Solo configura, non esegui
                                configure_run_interactive(ui, run_config)
                                run_config.save(project.run_config_file)
                                continue

                            elif run_choice == '4':
                                # Toggle opzioni
                                toggle_options_interactive(ui, run_config)
                                run_config.save(project.run_config_file)
                                continue

                            # Scegli modalità
                            mode_choice = show_mode_menu(ui, project, run_config)
                            if mode_choice:
                                mode_map = {'1': TestMode.TRAIN, '2': TestMode.ASSISTED, '3': TestMode.AUTO}
                                mode = mode_map.get(mode_choice, TestMode.TRAIN)

                                # Chiedi se vuole selezionare test specifici
                                select_items = [
                                    MenuItem('1', t('test_selection.pending'), t('test_selection.pending_desc')),
                                    MenuItem('2', t('test_selection.all'), t('test_selection.all_desc').format(count='')),
                                    MenuItem('3', t('test_selection.specific'), t('test_selection.specific_desc')),
                                ]
                                ui.section(t('test_selection.title'))
                                select_choice = ui.menu(select_items, t('common.next'), allow_back=True)

                                if select_choice is None:
                                    continue

                                test_filter_map = {'1': 'pending', '2': 'all', '3': 'select'}
                                test_filter = test_filter_map.get(select_choice, 'pending')

                                await run_test_session(
                                    project,
                                    settings,
                                    mode,
                                    test_filter=test_filter,
                                    force_new_run=force_new_run
                                )

                except FileNotFoundError:
                    ui.error(f"Progetto '{project_name}' non trovato")

        elif choice == '3':
            # Fine-tuning
            show_finetuning_menu(ui, loader)

        elif choice == '4':
            # Esegui nel cloud
            show_cloud_menu(ui, loader)

        elif choice == '5':
            # Analisi Testing
            show_analysis_menu(ui, loader)

        elif choice == '6':
            # Lista Run (tutti i progetti)
            list_all_runs(ui, loader, last_n=15)
            input("\n  Premi INVIO per continuare...")

        elif choice == '7':
            # Impostazioni
            show_settings_menu(ui, loader)

        elif choice == '8':
            # Aiuto
            ui.help_text(t('help_guide'))


async def main_direct(args):
    """Modalità diretta con argomenti CLI"""
    set_language(args.lang)
    ui = get_ui()
    loader = ConfigLoader()

    if args.new_project:
        from wizard.main import run_wizard
        success = run_wizard(language=args.lang)
        if success:
            ui.success("Progetto creato con successo!")
        return

    if not args.project:
        ui.error("Specifica un progetto con --project=NOME")
        return

    # --cloud: esegui su CircleCI invece che localmente
    if args.cloud:
        ci_client = CircleCIClient()
        if not ci_client.is_available():
            ui.error("CircleCI non configurato. Imposta CIRCLECI_TOKEN.")
            ui.print(ci_client.get_install_instructions())
            return

        mode = args.mode or 'auto'
        tests = args.tests or 'pending'
        new_run = args.new_run
        test_limit = args.test_limit or 0
        test_ids = args.test_ids or ''

        ui.print(f"\n  Avvio test su CircleCI...")
        ui.print(f"    Progetto: {args.project}")
        ui.print(f"    Modalita: {mode}")
        ui.print(f"    Test: {tests}")
        if test_ids:
            test_count = len(test_ids.split(','))
            ui.print(f"    Test specifici: {test_count} test")
        if test_limit > 0:
            ui.print(f"    Limite: {test_limit} test")
        ui.print(f"    Nuovo run: {'Si' if new_run else 'No'}\n")

        success, data = ci_client.trigger_pipeline(args.project, mode, tests, new_run, test_limit, test_ids)

        if success:
            pipeline_number = data.get('number', '?')
            ui.success(f"Pipeline #{pipeline_number} avviata!")
            ui.print(f"\n  URL: https://app.circleci.com/pipelines/gh/corradofrancolini/chatbot-tester-private/{pipeline_number}")
        else:
            error_msg = data.get('error', 'Errore sconosciuto') if data else 'Errore sconosciuto'
            ui.error(f"Errore: {error_msg}")
        return

    try:
        project = loader.load_project(args.project)
        settings = loader.load_global_settings()

        # Health check pre-esecuzione (skip con --skip-health-check)
        if not args.skip_health_check:
            if not run_health_check(project, settings):
                ui.error("Health check fallito. Usa --skip-health-check per forzare.")
                return

        # Override headless se specificato
        if args.headless:
            settings.browser.headless = True

        # Determina modalità
        mode_map = {'train': TestMode.TRAIN, 'assisted': TestMode.ASSISTED, 'auto': TestMode.AUTO}
        mode = mode_map.get(args.mode, TestMode.TRAIN)

        await run_test_session(
            project,
            settings,
            mode,
            test_filter=args.tests,
            single_test=args.test,
            force_new_run=args.new_run,
            no_interactive=args.no_interactive,
            single_turn=args.single_turn,
            test_limit=args.test_limit or 0,
            test_ids=args.test_ids or ''
        )

    except FileNotFoundError:
        ui.error(f"Progetto '{args.project}' non trovato")
    except Exception as e:
        ui.error(f"Errore: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()


def run_scheduler_commands(args):
    """Gestisce comandi scheduler da CLI"""
    from src.scheduler import LocalScheduler, ScheduleConfig, ScheduleType

    ui = get_ui()
    scheduler = LocalScheduler()

    # --list-schedules
    if args.list_schedules:
        schedules = scheduler.list_schedules()

        if not schedules:
            ui.print("\nNessuno schedule configurato")
            ui.print("Usa --add-schedule PROJECT:TYPE per aggiungere")
            return

        ui.print("\n[bold]Schedule Configurati[/bold]\n")
        for s in schedules:
            status = "[green]ON[/green]" if s.enabled else "[dim]OFF[/dim]"
            next_run = s.next_run[:16] if s.next_run else "N/A"
            ui.print(f"  {status} {s.name}")
            ui.print(f"      Progetto: {s.project} | Tipo: {s.schedule_type.value}")
            ui.print(f"      Prossimo: {next_run}")
            ui.print("")
        return

    # --add-schedule
    if args.add_schedule:
        try:
            parts = args.add_schedule.split(':')
            if len(parts) != 2:
                ui.error("Formato: --add-schedule PROJECT:TYPE (es: my-chatbot:daily)")
                return

            project, schedule_type = parts

            type_map = {
                'daily': ScheduleType.DAILY,
                'weekly': ScheduleType.WEEKLY,
                'hourly': ScheduleType.HOURLY
            }

            if schedule_type not in type_map:
                ui.error(f"Tipo non valido. Usa: {', '.join(type_map.keys())}")
                return

            config = ScheduleConfig(
                name=f"{project}-{schedule_type}",
                project=project,
                schedule_type=type_map[schedule_type],
                mode="auto",
                tests="pending"
            )

            scheduler.add_schedule(config)
            ui.success(f"Schedule '{config.name}' aggiunto")
            ui.print(f"  Prossimo run: {config.next_run[:16] if config.next_run else 'N/A'}")

        except Exception as e:
            ui.error(f"Errore: {e}")
        return

    # --scheduler (avvia)
    if args.scheduler:
        schedules = scheduler.list_schedules()

        if not schedules:
            ui.warning("Nessuno schedule configurato")
            ui.print("Usa --add-schedule PROJECT:TYPE per aggiungere")
            return

        ui.print(f"\n[bold]Avvio Scheduler[/bold]")
        ui.print(f"  Schedule attivi: {len([s for s in schedules if s.enabled])}")
        ui.print("  Premi Ctrl+C per fermare\n")

        try:
            scheduler.start()
        except KeyboardInterrupt:
            ui.print("\nScheduler fermato")
        return


def run_cli_cloud_monitor(args):
    """
    Gestisce comandi di monitoraggio cloud.

    Opzioni:
    - --watch-cloud [RUN_ID]: Monitora run con barra di avanzamento
    - --cloud-runs: Lista ultimi run cloud
    """
    from src.github_actions import (
        GitHubActionsClient, watch_cloud_run, CloudRunProgress
    )

    ui = get_ui()
    client = GitHubActionsClient()

    if not client.is_available():
        ui.error("gh CLI non disponibile")
        ui.print(client.get_install_instructions())
        return

    # --cloud-runs: lista run recenti
    if args.cloud_runs:
        runs = client.list_runs(limit=10)

        if not runs:
            ui.print("\nNessun run cloud trovato")
            return

        ui.print("\n[bold]Ultimi Run Cloud[/bold]\n")
        ui.print("  ID           Stato       Conclusione  Data")
        ui.print("  " + "─" * 55)

        for run in runs:
            # Format status with color
            status_color = {
                "completed": "green" if run.conclusion == "success" else "red",
                "in_progress": "yellow",
                "queued": "dim"
            }.get(run.status, "white")

            conclusion = run.conclusion or "-"
            conclusion_color = "green" if conclusion == "success" else "red" if conclusion == "failure" else "dim"

            date = run.created_at[:16].replace("T", " ") if run.created_at else "-"

            ui.print(
                f"  {run.id}  [{status_color}]{run.status:<12}[/{status_color}]"
                f"[{conclusion_color}]{conclusion:<11}[/{conclusion_color}] {date}"
            )

        ui.print("")
        ui.print("  Usa --watch-cloud RUN_ID per monitorare un run specifico")
        return

    # --watch-cloud: monitora run
    if args.watch_cloud:
        run_id = None
        if args.watch_cloud != 'latest':
            try:
                run_id = int(args.watch_cloud)
            except ValueError:
                ui.error(f"ID run non valido: {args.watch_cloud}")
                return

        ui.print("\n[bold]Cloud Run Monitor[/bold]\n")

        progress = watch_cloud_run(run_id)

        # Mostra riepilogo finale con più dettagli
        ui.print("")
        if progress.conclusion == "success":
            ui.success("Run completato con successo!")
        elif progress.conclusion == "failure":
            ui.error(f"Run fallito: {progress.error_message or 'errore sconosciuto'}")
        elif progress.conclusion == "cancelled":
            ui.warning("Run cancellato")

        if progress.total_tests > 0:
            ui.print(f"\n  Test eseguiti: {progress.total_tests}")
            ui.print(f"  Passati: [green]{progress.passed_tests}[/green]")
            ui.print(f"  Falliti: [red]{progress.failed_tests}[/red]")

        if progress.sheets_run:
            ui.print(f"\n  📊 Google Sheets: RUN {progress.sheets_run}")

        return


def run_cli_performance(args):
    """
    Gestisce comandi di performance metrics.

    Opzioni:
    - --perf-report [RUN]: Mostra report performance
    - --perf-dashboard [N]: Dashboard storica (ultimi N run)
    - --perf-compare A:B: Confronta due run
    - --perf-export FMT: Esporta metriche
    """
    from src.performance import (
        PerformanceHistory, PerformanceReporter, RunMetrics,
        compare_environments, format_comparison_report, PerformanceAlerter
    )
    import json as json_module

    ui = get_ui()
    loader = ConfigLoader()

    if not args.project:
        ui.error("Specifica un progetto con --project=NOME")
        return

    try:
        project = loader.load_project(args.project)
    except FileNotFoundError:
        ui.error(f"Progetto '{args.project}' non trovato")
        return

    # Carica storico performance
    history = PerformanceHistory(args.project, Path("reports"))

    # --perf-report: mostra report performance
    if args.perf_report is not None:
        run_number = args.perf_report if args.perf_report > 0 else None

        # Carica metriche
        metrics_list = history.load_history(last_n=20)

        if not metrics_list:
            ui.warning("Nessuna metrica di performance trovata")
            ui.print("Esegui test con 'python run.py -p PROJECT -m auto' per generare metriche")
            return

        # Se specificato run, cerca quello
        metrics = None
        if run_number:
            for m in metrics_list:
                if str(m.run_id) == str(run_number):
                    metrics = m
                    break
            if not metrics:
                ui.error(f"Run {run_number} non trovato")
                return
        else:
            # Ultimo run
            metrics = metrics_list[0]

        # Genera e mostra report
        reporter = PerformanceReporter(metrics)
        ui.print(reporter.generate_summary())

        # Check alerting
        alerter = PerformanceAlerter()
        alerts = alerter.check(metrics)
        if alerts:
            ui.print(alerter.format_alerts())

        return

    # --perf-dashboard: dashboard storica
    if args.perf_dashboard is not None:
        last_n = args.perf_dashboard if args.perf_dashboard > 0 else 10

        # Calcola trend
        trends = history.get_trends(last_n)

        if "message" in trends:
            ui.warning(trends["message"])
            return

        ui.print(f"\n{'='*60}")
        ui.print(f"  PERFORMANCE DASHBOARD - {args.project}")
        ui.print(f"  Ultimi {last_n} run")
        ui.print(f"{'='*60}\n")

        # Mostra trend per ogni metrica
        for metric_name, trend_data in trends.items():
            trend_icon = "📈" if trend_data["trend"] == "increasing" else "📉" if trend_data["trend"] == "decreasing" else "➡️"
            change_sign = "+" if trend_data["change_percent"] > 0 else ""

            # Colore in base alla metrica (per alcune, decreasing è buono)
            good_decreasing = metric_name in ["duration", "error_rate", "chatbot_latency", "sheets_latency"]
            if good_decreasing:
                color = "green" if trend_data["trend"] == "decreasing" else "red" if trend_data["trend"] == "increasing" else "dim"
            else:
                color = "green" if trend_data["trend"] == "increasing" else "red" if trend_data["trend"] == "decreasing" else "dim"

            ui.print(f"  {trend_icon} {metric_name.replace('_', ' ').title()}")
            ui.print(f"     Attuale: {trend_data['current']}")
            ui.print(f"     Media: {trend_data['average']}")
            ui.print(f"     Trend: [{color}]{change_sign}{trend_data['change_percent']:.1f}%[/{color}]")
            ui.print("")

        ui.print(f"{'='*60}")
        return

    # --perf-compare: confronta due run
    if args.perf_compare:
        try:
            parts = args.perf_compare.split(":")
            if len(parts) != 2:
                raise ValueError("Formato: A:B")
            run_a, run_b = parts[0], parts[1]
        except ValueError as e:
            ui.error(f"Formato non valido: {e}")
            ui.print("Usa: --perf-compare 15:16")
            return

        # Carica metriche
        metrics_list = history.load_history(last_n=50)

        metrics_a = None
        metrics_b = None
        for m in metrics_list:
            if str(m.run_id) == run_a:
                metrics_a = m
            if str(m.run_id) == run_b:
                metrics_b = m

        if not metrics_a:
            ui.error(f"Run {run_a} non trovato")
            return
        if not metrics_b:
            ui.error(f"Run {run_b} non trovato")
            return

        # Confronta
        comparison = compare_environments(metrics_a, metrics_b)
        ui.print(format_comparison_report(comparison))
        return

    # --perf-export: esporta metriche
    if args.perf_export:
        metrics_list = history.load_history(last_n=1)

        if not metrics_list:
            ui.warning("Nessuna metrica di performance trovata")
            return

        metrics = metrics_list[0]
        report_dir = loader.get_report_dir(args.project)
        export_dir = report_dir / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)

        if args.perf_export == "json":
            output_file = export_dir / f"performance_{metrics.run_id}.json"

            # Converti a dict
            data = {
                "run_id": metrics.run_id,
                "project": metrics.project,
                "environment": metrics.environment,
                "start_time": metrics.start_time.isoformat() if metrics.start_time else None,
                "end_time": metrics.end_time.isoformat() if metrics.end_time else None,
                "total_tests": metrics.total_tests,
                "passed_tests": metrics.passed_tests,
                "failed_tests": metrics.failed_tests,
                "total_duration_ms": metrics.total_duration_ms,
                "avg_test_duration_ms": metrics.avg_test_duration_ms,
                "tests_per_minute": metrics.tests_per_minute,
                "error_rate": metrics.error_rate,
                "chatbot_avg_latency_ms": metrics.chatbot_avg_latency_ms,
                "sheets_avg_latency_ms": metrics.sheets_avg_latency_ms,
                "langsmith_avg_latency_ms": metrics.langsmith_avg_latency_ms
            }

            with open(output_file, 'w', encoding='utf-8') as f:
                json_module.dump(data, f, indent=2, ensure_ascii=False)

            ui.success(f"Esportato: {output_file}")

        elif args.perf_export == "html":
            output_file = export_dir / f"performance_{metrics.run_id}.html"

            reporter = PerformanceReporter(metrics)
            html = reporter.generate_html_report()

            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(html)

            ui.success(f"Esportato: {output_file}")

            # Apri nel browser
            import webbrowser
            webbrowser.open(f"file://{output_file}")

        return

    # --list-runs: lista run di tutti i progetti
    if args.list_runs is not None:
        last_n = args.list_runs if args.list_runs > 0 else 10
        list_all_runs(ui, loader, last_n)
        return


def list_all_runs(ui: ConsoleUI, loader: ConfigLoader, last_n: int = 10):
    """
    Lista ultimi run di TUTTI i progetti.

    Mostra una tabella aggregata con:
    - Progetto, Run ID, Data, Test, Pass Rate, Durata
    """
    from src.performance import PerformanceHistory

    projects_dir = Path("projects")
    if not projects_dir.exists():
        ui.error("Directory projects/ non trovata")
        return

    # Raccogli run da tutti i progetti
    all_runs = []

    for project_dir in projects_dir.iterdir():
        if not project_dir.is_dir():
            continue
        if not (project_dir / "project.yaml").exists():
            continue

        project_name = project_dir.name
        history = PerformanceHistory(project_name, Path("reports"))
        metrics_list = history.load_history(last_n=last_n)

        for metrics in metrics_list:
            pass_rate = (metrics.passed_tests / metrics.total_tests * 100) if metrics.total_tests > 0 else 0

            # Formatta durata
            duration_ms = metrics.total_duration_ms
            if duration_ms < 60000:
                duration_str = f"{duration_ms/1000:.0f}s"
            else:
                minutes = int(duration_ms / 60000)
                seconds = (duration_ms % 60000) / 1000
                duration_str = f"{minutes}m {seconds:.0f}s"

            all_runs.append({
                "project": project_name,
                "run_id": metrics.run_id,
                "date": metrics.start_time,
                "total_tests": metrics.total_tests,
                "pass_rate": pass_rate,
                "duration": duration_str,
                "environment": metrics.environment
            })

    if not all_runs:
        ui.warning("Nessun run trovato")
        ui.print("Esegui test con 'python run.py -p PROJECT -m auto' per generare dati")
        return

    # Ordina per data (più recenti prima)
    all_runs.sort(key=lambda x: x["date"] or "", reverse=True)

    # Limita a last_n
    all_runs = all_runs[:last_n]

    # Stampa tabella
    ui.print(f"\n[bold]Ultimi Run (tutti i progetti)[/bold]\n")
    ui.print(f"  {'Progetto':<15} {'Run':<8} {'Data':<18} {'Test':<6} {'Pass':<7} {'Durata':<10} {'Env':<6}")
    ui.print("  " + "─" * 75)

    for run in all_runs:
        date_str = run["date"].strftime("%Y-%m-%d %H:%M") if run["date"] else "-"

        # Colore pass rate
        if run["pass_rate"] >= 90:
            pass_color = "green"
        elif run["pass_rate"] >= 70:
            pass_color = "yellow"
        else:
            pass_color = "red"

        ui.print(
            f"  {run['project']:<15} "
            f"{run['run_id']:<8} "
            f"{date_str:<18} "
            f"{run['total_tests']:<6} "
            f"[{pass_color}]{run['pass_rate']:.0f}%[/{pass_color}]    "
            f"{run['duration']:<10} "
            f"{run['environment']:<6}"
        )

    ui.print("")
    ui.print(f"  Totale: {len(all_runs)} run")
    ui.print("  Usa --perf-report -p PROJECT per dettagli")


def run_cli_analysis(args):
    """Esegue analisi da CLI (--compare, --regressions, --flaky)"""
    from src.comparison import (
        RunComparator, RegressionDetector, FlakyTestDetector,
        format_comparison_report
    )
    from src.sheets_client import GoogleSheetsClient

    ui = get_ui()
    loader = ConfigLoader()

    if not args.project:
        ui.error("Specifica un progetto con --project=NOME")
        return

    try:
        project = loader.load_project(args.project)
    except FileNotFoundError:
        ui.error(f"Progetto '{args.project}' non trovato")
        return

    # Inizializza sheets client
    sheets_client = None
    local_reports_path = Path(f"reports/{args.project}")

    if project.google_sheets.enabled:
        try:
            credentials_path = str(Path("config/credentials.json"))
            sheets_client = GoogleSheetsClient(
                credentials_path=credentials_path,
                spreadsheet_id=project.google_sheets.spreadsheet_id,
                drive_folder_id=project.google_sheets.drive_folder_id
            )
        except Exception:
            pass  # Usa report locali

    # Crea comparator
    comparator = RunComparator(
        sheets_client=sheets_client,
        local_reports_path=local_reports_path
    )

    # --compare
    if args.compare is not None:

        if args.compare == 'latest':
            result = comparator.compare_latest()
            if result:
                print(format_comparison_report(result))
            else:
                ui.warning("Servono almeno 2 run per confrontare")
        else:
            try:
                parts = args.compare.split(':')
                if len(parts) == 2:
                    run_a, run_b = int(parts[0]), int(parts[1])
                    result = comparator.compare(run_a, run_b)
                    print(format_comparison_report(result))
                else:
                    ui.error("Formato: --compare RUN_A:RUN_B (es: --compare 15:16)")
            except ValueError:
                ui.error("Formato: --compare RUN_A:RUN_B (es: --compare 15:16)")
        return

    # --regressions
    if args.regressions is not None:
        detector = RegressionDetector(comparator)
        run_num = args.regressions if args.regressions > 0 else None

        regressions = detector.check_for_regressions(run_num or 0)

        if not regressions:
            ui.success("Nessuna regressione rilevata")
        else:
            real_regressions = [r for r in regressions if r.change_type == 'regression']
            improvements = [r for r in regressions if r.change_type == 'improvement']

            if real_regressions:
                ui.print(f"\n[red]REGRESSIONI ({len(real_regressions)}):[/red]")
                for r in real_regressions:
                    ui.print(f"  - {r.test_id}: PASS -> FAIL")

            if improvements:
                ui.print(f"\n[green]MIGLIORAMENTI ({len(improvements)}):[/green]")
                for r in improvements:
                    ui.print(f"  + {r.test_id}: FAIL -> PASS")
        return

    # --flaky
    if args.flaky is not None:
        detector = FlakyTestDetector(comparator)
        n_runs = args.flaky

        flaky_tests = detector.detect_flaky_tests(n_runs, 0.3)

        if not flaky_tests:
            ui.success(f"Nessun test flaky rilevato su ultimi {n_runs} run")
        else:
            ui.print(f"\n[yellow]TEST FLAKY ({len(flaky_tests)}) su ultimi {n_runs} run:[/yellow]")
            for ft in flaky_tests:
                ui.print(f"  {ft.test_id}: score={ft.flaky_score:.2f} (PASS:{ft.pass_count} FAIL:{ft.fail_count})")
        return


def run_export_commands(args):
    """Gestisce comandi export da CLI"""
    ui = get_ui()

    if not args.project:
        ui.error("Specifica un progetto con -p PROJECT")
        sys.exit(ExitCode.USAGE_ERROR)

    from src.export import RunReport, ReportExporter, check_dependencies

    # Verifica dipendenze
    deps = check_dependencies()
    if args.export == 'pdf' and not deps['pdf']:
        ui.error("PDF export richiede: pip install reportlab pillow")
        sys.exit(ExitCode.CONFIG)
    if args.export == 'excel' and not deps['excel']:
        ui.error("Excel export richiede: pip install openpyxl")
        sys.exit(ExitCode.CONFIG)

    # Trova report locale
    reports_dir = Path(f"reports/{args.project}")
    if not reports_dir.exists():
        ui.error(f"Nessun report trovato per {args.project}")
        sys.exit(ExitCode.NO_INPUT)

    # Determina quale run esportare
    run_dirs = sorted(reports_dir.glob("run_*"), key=lambda p: int(p.name.split('_')[1]))
    if not run_dirs:
        ui.error("Nessun run trovato")
        sys.exit(ExitCode.NO_INPUT)

    if args.export_run:
        # Prova entrambi i formati: run_19 e run_019
        target_dir = reports_dir / f"run_{args.export_run}"
        if not target_dir.exists():
            target_dir = reports_dir / f"run_{args.export_run:03d}"
        if not target_dir.exists():
            ui.error(f"Run {args.export_run} non trovato")
            sys.exit(ExitCode.NO_INPUT)
    else:
        target_dir = run_dirs[-1]

    # Cerca report JSON (supporta sia report.json che summary.json + report.csv)
    report_json = target_dir / "report.json"
    summary_json = target_dir / "summary.json"
    report_csv = target_dir / "report.csv"

    ui.section(f"Export Report - {target_dir.name}")

    if report_json.exists():
        # Formato nuovo: report.json completo
        report = RunReport.from_local_report(report_json)
    elif summary_json.exists():
        # Formato esistente: summary.json + report.csv
        report = RunReport.from_summary_and_csv(summary_json, report_csv if report_csv.exists() else None)
    else:
        ui.error(f"Nessun report trovato in {target_dir}")
        sys.exit(ExitCode.NO_INPUT)
    exporter = ReportExporter(report)

    # Export
    output_dir = target_dir / "exports"
    output_dir.mkdir(exist_ok=True)

    base_name = f"{report.project}_run{report.run_number}"

    if args.export == 'all':
        results = exporter.export_all(output_dir)
        for fmt, path in results.items():
            ui.success(f"{fmt.upper()}: {path}")
    elif args.export == 'pdf':
        path = exporter.to_pdf(output_dir / f"{base_name}.pdf")
        ui.success(f"PDF: {path}")
    elif args.export == 'excel':
        path = exporter.to_excel(output_dir / f"{base_name}.xlsx")
        ui.success(f"Excel: {path}")
    elif args.export == 'html':
        path = exporter.to_html(output_dir / f"{base_name}.html")
        ui.success(f"HTML: {path}")
    elif args.export == 'csv':
        path = exporter.to_csv(output_dir / f"{base_name}.csv")
        ui.success(f"CSV: {path}")

    # Next steps suggerimenti
    if args.export != 'all':
        output_path = output_dir / f"{base_name}.{args.export}"
        steps = NextSteps.after_export(output_path)
        ui.muted(NextSteps.format(steps))


def run_notify_commands(args):
    """Gestisce comandi notifica da CLI"""
    ui = get_ui()

    from src.notifications import NotificationConfig, NotificationManager, TestRunSummary

    # Carica config notifiche da settings
    loader = ConfigLoader()
    try:
        settings = loader.load_global_settings()
        notify_config_data = getattr(settings, 'notifications', {}) or {}
        config = NotificationConfig.from_dict(notify_config_data)
    except Exception:
        # Default config
        config = NotificationConfig(desktop_enabled=True)

    manager = NotificationManager(config)

    # Test notifica
    if args.test_notify:
        ui.section("Test Notifiche")

        # Test desktop
        ui.print("Testing desktop notification...")
        if manager.send_desktop("Chatbot Tester", "Test notification", "Configurazione OK"):
            ui.success("Desktop: OK")
        else:
            ui.warning("Desktop: Non disponibile")

        # Test email (solo se configurata)
        if config.email_enabled:
            ui.print("Testing email...")
            if manager.send_email("[TEST] Chatbot Tester", "Test email configuration"):
                ui.success("Email: OK")
            else:
                ui.warning("Email: Configurazione non valida")

        # Test Teams (solo se configurato)
        if config.teams_enabled:
            ui.print("Testing Teams...")
            if manager.send_teams("Chatbot Tester Test", "Test Teams webhook"):
                ui.success("Teams: OK")
            else:
                ui.warning("Teams: Webhook non configurato")

        return

    # Notifica manuale con dati di test
    if args.notify:
        ui.section("Invio Notifica")

        # Crea summary di esempio (o carica da ultimo run)
        summary = TestRunSummary(
            project=args.project or "test-project",
            run_number=1,
            total_tests=10,
            passed=8,
            failed=2,
            pass_rate=80.0
        )

        # Se abbiamo un progetto, cerca ultimo run
        if args.project:
            reports_dir = Path(f"reports/{args.project}")
            if reports_dir.exists():
                run_dirs = sorted(reports_dir.glob("run_*"), key=lambda p: int(p.name.split('_')[1]))
                if run_dirs:
                    report_json = run_dirs[-1] / "report.json"
                    if report_json.exists():
                        import json
                        with open(report_json) as f:
                            data = json.load(f)
                        summary = TestRunSummary(
                            project=data.get('project', args.project),
                            run_number=data.get('run_number', 0),
                            total_tests=data.get('total_tests', 0),
                            passed=data.get('passed', 0),
                            failed=data.get('failed', 0),
                            pass_rate=data.get('pass_rate', 0)
                        )

        # Invia notifica
        if args.notify == 'desktop':
            if manager.desktop.send_run_summary(summary):
                ui.success("Notifica desktop inviata")
        elif args.notify == 'email':
            if manager.email.send_run_summary(summary):
                ui.success("Email inviata")
            else:
                ui.error("Invio email fallito - controlla configurazione")
        elif args.notify == 'teams':
            if manager.teams.send_run_summary(summary):
                ui.success("Notifica Teams inviata")
            else:
                ui.error("Invio Teams fallito - controlla webhook")
        elif args.notify == 'all':
            results = manager.notify_run_complete(summary)
            for channel, success in results.items():
                if success:
                    ui.success(f"{channel}: OK")
                else:
                    ui.warning(f"{channel}: fallito")


# ═══════════════════════════════════════════════════════════════════════════════
# CLI: Analyze Commands
# ═══════════════════════════════════════════════════════════════════════════════

def run_analyze_command(args):
    """
    Esegue comando --analyze.

    Genera debug package dai test falliti e opzionalmente
    li analizza con un LLM (manual/claude/groq).
    """
    from src.analyzer import run_analysis

    ui = get_ui()

    result = run_analysis(
        project_name=args.project,
        provider=args.provider,
        run_number=args.analyze_run,
        skip_confirm=args.yes
    )

    if result is None:
        return

    # Mostra risultato
    ui.section("Risultato Analisi")

    if result.suggestions:
        ui.print("\nSuggerimenti:")
        for i, suggestion in enumerate(result.suggestions, 1):
            ui.print(f"  {i}. {suggestion}")

    if result.prompt_fixes:
        ui.print("\nFix prompt suggeriti:")
        for fix in result.prompt_fixes:
            ui.print(f"  - {fix}")

    # Next steps
    ui.muted("\nProssimi passi:")
    ui.muted(f"  - Modifica il prompt in projects/{args.project}/prompts/")
    ui.muted(f"  - Esegui nuovi test: chatbot-tester -p {args.project} -m auto")


# ═══════════════════════════════════════════════════════════════════════════════
# CLI: Diagnostic Engine Commands
# ═══════════════════════════════════════════════════════════════════════════════

def run_diagnose_command(args):
    """
    Esegue comando --diagnose.

    Analizza test falliti con DiagnosticEngine, genera ipotesi
    e suggerisce fix basati su knowledge base.
    """
    from src.diagnostic import DiagnosticEngine, InteractiveDiagnostic, TestFailure
    from src.prompt_manager import PromptManager
    import json

    ui = get_ui()

    # Carica prompt corrente
    pm = PromptManager(args.project)
    prompt = pm.get_current()
    if not prompt:
        ui.error(f"Nessun prompt trovato per {args.project}")
        ui.muted("  Importa un prompt con: --prompt-import FILE")
        return

    # Trova run da analizzare
    reports_dir = Path(f"reports/{args.project}")
    if not reports_dir.exists():
        ui.error(f"Nessun report trovato per {args.project}")
        return

    run_number = args.diagnose_run
    if run_number is None:
        # Trova ultima run
        runs = sorted([d for d in reports_dir.iterdir() if d.is_dir() and d.name.startswith('run_')])
        if not runs:
            ui.error("Nessuna run trovata")
            return
        run_dir = runs[-1]
        run_number = int(run_dir.name.split('_')[1])
    else:
        run_dir = reports_dir / f"run_{run_number:03d}"

    if not run_dir.exists():
        ui.error(f"Run {run_number} non trovata")
        return

    # Carica report (supporta sia JSON che CSV)
    report_json = run_dir / "report.json"
    report_csv = run_dir / "report.csv"

    failed_tests = []

    if report_json.exists():
        with open(report_json) as f:
            report = json.load(f)
        failed_tests = [t for t in report.get('tests', []) if t.get('status') == 'FAIL']
    elif report_csv.exists():
        import csv
        with open(report_csv, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('esito') == 'FAIL':
                    # Estrai risposta dal campo conversation
                    conversation = row.get('conversation', '')
                    response = ''
                    if 'BOT:' in conversation:
                        response = conversation.split('BOT:')[-1].strip()

                    failed_tests.append({
                        'test_id': row.get('test_id'),
                        'query': row.get('question'),
                        'response': response,
                        'notes': row.get('notes'),
                        'expected': None
                    })
    else:
        ui.error(f"Report non trovato in {run_dir}")
        return

    if args.diagnose_test:
        # Filtra per test specifico
        failed_tests = [t for t in failed_tests if t.get('test_id') == args.diagnose_test]
        if not failed_tests:
            ui.warning(f"Test {args.diagnose_test} non trovato o non fallito")
            return

    if not failed_tests:
        ui.success(f"Nessun test fallito nella run {run_number}")
        return

    ui.header(f"Diagnostic Engine - {args.project}")
    ui.info(f"Run: {run_number} | Test falliti: {len(failed_tests)}")
    ui.info(f"Modello target: {args.diagnose_model}")
    ui.print("")

    # Crea engine
    if args.diagnose_interactive:
        session = InteractiveDiagnostic(ui)
    else:
        engine = DiagnosticEngine()

    # Diagnostica ogni test fallito
    diagnoses = []
    for test in failed_tests:
        failure = TestFailure(
            test_id=test.get('test_id', 'UNKNOWN'),
            question=test.get('query', ''),
            expected=test.get('expected', ''),
            actual=test.get('response', '')[:500],
            error_type=test.get('error_type'),
            notes=test.get('notes')
        )

        if args.diagnose_interactive:
            diagnosis = session.run(
                prompt=prompt,
                failure=failure,
                model=args.diagnose_model
            )
        else:
            diagnosis = engine.diagnose(
                prompt=prompt,
                failure=failure,
                model=args.diagnose_model
            )

        diagnoses.append((failure, diagnosis))

        # Mostra diagnosi (non-interactive mode)
        if not args.diagnose_interactive:
            ui.section(f"Test: {failure.test_id}")
            ui.print(diagnosis.summary())
            ui.print("")

    # Riepilogo finale
    ui.divider()
    ui.section("Riepilogo Diagnosi")

    total_verified = sum(len(d.verified_hypotheses) for _, d in diagnoses)
    total_fixes = sum(len(d.suggested_fixes) for _, d in diagnoses)

    ui.stats_row({
        "Test analizzati": len(diagnoses),
        "Ipotesi verificate": total_verified,
        "Fix suggeriti": total_fixes
    })

    # Top fix suggeriti
    all_fixes = []
    for failure, diagnosis in diagnoses:
        for fix in diagnosis.suggested_fixes:
            all_fixes.append((failure.test_id, fix))

    if all_fixes:
        ui.section("Top Fix Suggeriti")
        seen_fixes = set()
        for test_id, fix in sorted(all_fixes, key=lambda x: x[1].confidence, reverse=True)[:5]:
            if fix.description not in seen_fixes:
                seen_fixes.add(fix.description)
                ui.print(f"  [{fix.confidence:.0%}] {fix.description}")
                ui.muted(f"       {fix.template[:100]}...")

    # Next steps
    ui.print("")
    ui.muted("Prossimi passi:")
    ui.muted(f"  - Applica i fix suggeriti al prompt")
    ui.muted(f"  - Salva nuova versione: --prompt-import FILE --prompt-note 'fix: ...'")
    ui.muted(f"  - Ri-esegui test: -p {args.project} -m auto --new-run")


# ═══════════════════════════════════════════════════════════════════════════════
# CLI: Prompt Manager Commands
# ═══════════════════════════════════════════════════════════════════════════════

def run_prompt_commands(args):
    """
    Esegue comandi --prompt-*.

    Gestione versionata dei prompt di progetto.
    """
    from src.prompt_manager import prompt_manager_cli, PromptManager

    ui = get_ui()

    # List versions
    if args.prompt_list:
        prompt_manager_cli(args.project, 'list')
        return

    # Show prompt
    if args.prompt_show is not None:
        version = args.prompt_show if args.prompt_show > 0 else None
        prompt_manager_cli(args.project, 'show', version=version)
        return

    # Import prompt
    if args.prompt_import:
        prompt_manager_cli(
            args.project, 'import',
            filepath=args.prompt_import,
            note=args.prompt_note
        )
        # Next steps
        ui.muted("\nProssimi passi:")
        ui.muted(f"  - Verifica: chatbot-tester -p {args.project} --prompt-show")
        ui.muted(f"  - Lista versioni: chatbot-tester -p {args.project} --prompt-list")
        return

    # Export prompt
    if args.prompt_export:
        output = args.prompt_export if args.prompt_export != 'auto' else None
        prompt_manager_cli(
            args.project, 'export',
            output=output
        )
        return

    # Diff versions
    if args.prompt_diff:
        try:
            parts = args.prompt_diff.split(':')
            v1, v2 = int(parts[0]), int(parts[1])
            prompt_manager_cli(
                args.project, 'diff',
                version_a=v1,
                version_b=v2
            )
        except (ValueError, IndexError):
            ui.error("Formato diff non valido. Usa: --prompt-diff V1:V2 (es: --prompt-diff 1:2)")
        return


# ═══════════════════════════════════════════════════════════════════════════════
# CLI: Visualizer Commands
# ═══════════════════════════════════════════════════════════════════════════════

def run_visualize_commands(args):
    """
    Esegue comandi --viz-*.

    Visualizzazione grafica di prompt e test.
    """
    from src.visualizer import PromptVisualizer, TestVisualizer

    ui = get_ui()
    output = args.viz_output

    # Visualizza prompt
    if args.viz_prompt:
        viz = PromptVisualizer(args.project)
        if output == 'html':
            path = viz.render_html()
            if path:
                ui.success(f"Visualizzazione prompt aperta: {path}")
            else:
                ui.error("Nessun prompt disponibile per questo progetto")
                ui.muted("  Importa un prompt con: --prompt-import FILE")
        else:
            result = viz.render_terminal()
            print(result)
        return

    # Visualizza test
    if args.viz_test:
        test_id = args.viz_test if args.viz_test != 'latest' else None
        run_number = args.viz_run

        viz = TestVisualizer(args.project, run_number, test_id)

        if output == 'html':
            path = viz.render_html()
            if path:
                ui.success(f"Visualizzazione test aperta: {path}")
            else:
                ui.error("Nessun test trovato")
        else:
            result = viz.render_terminal()
            print(result)
        return


# ═══════════════════════════════════════════════════════════════════════════════
# Natural Language Interface
# ═══════════════════════════════════════════════════════════════════════════════

async def run_nl_ask(command: str):
    """Execute single natural language command"""
    from src.nl_chat import run_single_command
    await run_single_command(command)


async def run_nl_chat():
    """Start interactive chat session"""
    from src.nl_chat import run_chat_mode
    await run_chat_mode()


async def run_nl_agent():
    """Start conversational agent session"""
    from src.nl_agent import run_agent_mode
    await run_agent_mode()


def main():
    """Entry point - clig.dev compliant"""
    import signal

    # Ctrl+C handler pulito
    signal.signal(signal.SIGINT, lambda s, f: handle_keyboard_interrupt())

    args = parse_args()

    # Inizializza UI con opzioni da args
    use_colors = not getattr(args, 'no_color', False)
    quiet = getattr(args, 'quiet', False)

    # Feedback immediato (<100ms) - clig.dev compliant
    if not quiet:
        print_startup_feedback()

    ui = get_ui(use_colors=use_colors, quiet=quiet)

    # Validazione progetto con suggerimenti (se specificato)
    if args.project and not args.new_project:
        if not validate_project(args.project, ui):
            sys.exit(ExitCode.PROJECT_NOT_FOUND)

    # ═══════════════════════════════════════════════════════════════════
    # Natural Language Commands
    # ═══════════════════════════════════════════════════════════════════
    if args.ask:
        asyncio.run(run_nl_ask(args.ask))
        sys.exit(ExitCode.SUCCESS)

    if args.chat:
        asyncio.run(run_nl_chat())
        sys.exit(ExitCode.SUCCESS)

    if args.agent:
        asyncio.run(run_nl_agent())
        sys.exit(ExitCode.SUCCESS)

    # Comandi scheduler da CLI
    if args.scheduler or args.add_schedule or args.list_schedules:
        run_scheduler_commands(args)
        sys.exit(ExitCode.SUCCESS)

    # Comandi cloud monitoring da CLI
    if args.watch_cloud or args.cloud_runs:
        run_cli_cloud_monitor(args)
        sys.exit(ExitCode.SUCCESS)

    # Comandi performance metrics da CLI
    if any([args.perf_report is not None, args.perf_dashboard is not None,
            args.perf_compare, args.perf_export, args.list_runs is not None]):
        run_cli_performance(args)
        sys.exit(ExitCode.SUCCESS)

    # Comandi export da CLI
    if args.export:
        run_export_commands(args)
        sys.exit(ExitCode.SUCCESS)

    # Comandi notifica da CLI
    if args.notify or args.test_notify:
        run_notify_commands(args)
        sys.exit(ExitCode.SUCCESS)

    # Comandi analisi da CLI
    if args.compare is not None or args.regressions is not None or args.flaky is not None:
        run_cli_analysis(args)
        sys.exit(ExitCode.SUCCESS)

    # Comandi analyze (debug package + LLM)
    if args.analyze:
        if not args.project:
            ui.error("Specifica un progetto con -p PROJECT")
            sys.exit(ExitCode.USAGE_ERROR)
        run_analyze_command(args)
        sys.exit(ExitCode.SUCCESS)

    # Comandi diagnostic engine
    if args.diagnose or args.diagnose_test:
        if not args.project:
            ui.error("Specifica un progetto con -p PROJECT")
            sys.exit(ExitCode.USAGE_ERROR)
        run_diagnose_command(args)
        sys.exit(ExitCode.SUCCESS)

    # Comandi prompt manager
    if any([args.prompt_list, args.prompt_show is not None,
            args.prompt_import, args.prompt_export, args.prompt_diff]):
        if not args.project:
            ui.error("Specifica un progetto con -p PROJECT")
            sys.exit(ExitCode.USAGE_ERROR)
        run_prompt_commands(args)
        sys.exit(ExitCode.SUCCESS)

    # Comandi visualizer
    if args.viz_prompt or args.viz_test:
        if not args.project:
            ui.error("Specifica un progetto con -p PROJECT")
            sys.exit(ExitCode.USAGE_ERROR)
        run_visualize_commands(args)
        sys.exit(ExitCode.SUCCESS)

    # Health check standalone
    if args.health_check:
        loader = ConfigLoader()

        # Se specificato progetto, carica config
        project = None
        settings = None
        if args.project:
            try:
                project = loader.load_project(args.project)
                settings = loader.load_global_settings()
            except FileNotFoundError:
                # validate_project gia chiamato sopra
                sys.exit(ExitCode.PROJECT_NOT_FOUND)

        success = run_health_check(project, settings)
        sys.exit(ExitCode.SUCCESS if success else ExitCode.HEALTH_CHECK_FAILED)

    # Determina modalita
    try:
        if args.no_interactive or args.project or args.new_project:
            # Modalita diretta
            asyncio.run(main_direct(args))
        else:
            # Modalita interattiva
            asyncio.run(main_interactive(args))
        sys.exit(ExitCode.SUCCESS)
    except KeyboardInterrupt:
        handle_keyboard_interrupt()
    except Exception as e:
        ui.error(f"Errore: {e}")
        if getattr(args, 'debug', False):
            import traceback
            traceback.print_exc()
        sys.exit(ExitCode.ERROR)


if __name__ == '__main__':
    main()
