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
import sys
from pathlib import Path
from datetime import datetime

# Aggiungi src al path
sys.path.insert(0, str(Path(__file__).parent))

from src.config_loader import ConfigLoader, ProjectConfig, RunConfig
from src.tester import ChatbotTester, TestMode
from src.ui import ConsoleUI, MenuItem, get_ui
from src.i18n import get_i18n, set_language, t
from src.health import HealthChecker, ServiceStatus
from src.github_actions import GitHubActionsClient


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Chatbot Tester - Tool parametrizzabile per testing chatbot',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Esempi:
  python run.py                              Menu interattivo
  python run.py --new-project                Wizard nuovo progetto  
  python run.py --project example-bot       Apri progetto esistente
  python run.py -p example-bot -m auto      Modalità auto su progetto
  python run.py -p example-bot --test TC001 Esegui singolo test
  python run.py -p example-bot --new-run    Forza nuova RUN
  python run.py --lang en                    Interfaccia in inglese
        """
    )
    
    parser.add_argument(
        '--new-project',
        action='store_true',
        help='Avvia wizard per nuovo progetto'
    )
    
    parser.add_argument(
        '-p', '--project',
        type=str,
        default=None,
        help='Nome del progetto da aprire'
    )
    
    parser.add_argument(
        '-m', '--mode',
        type=str,
        choices=['train', 'assisted', 'auto'],
        default=None,
        help='Modalità di test: train, assisted, auto'
    )
    
    parser.add_argument(
        '-t', '--test',
        type=str,
        default=None,
        help='ID singolo test da eseguire'
    )
    
    parser.add_argument(
        '--tests',
        type=str,
        default='pending',
        choices=['all', 'pending', 'failed'],
        help='Quali test eseguire: all, pending (default), failed'
    )
    
    parser.add_argument(
        '--new-run',
        action='store_true',
        help='Forza creazione di una nuova RUN'
    )
    
    parser.add_argument(
        '--lang',
        type=str,
        default='it',
        choices=['it', 'en'],
        help='Lingua interfaccia: it (default), en'
    )
    
    parser.add_argument(
        '--no-interactive',
        action='store_true',
        help='Modalità non interattiva (per CI/automazione)'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Simula senza eseguire realmente i test'
    )
    
    parser.add_argument(
        '--headless',
        action='store_true',
        help='Esegui browser in modalità headless'
    )
    
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Abilita output di debug'
    )

    parser.add_argument(
        '--health-check',
        action='store_true',
        help='Esegui health check dei servizi e esci'
    )

    parser.add_argument(
        '--skip-health-check',
        action='store_true',
        help='Salta health check pre-esecuzione'
    )

    parser.add_argument(
        '--parallel',
        action='store_true',
        help='Esegui test in parallelo (piu browser)'
    )

    parser.add_argument(
        '--workers',
        type=int,
        default=3,
        help='Numero di browser paralleli (default: 3, max: 5)'
    )

    parser.add_argument(
        '--scheduler',
        action='store_true',
        help='Avvia scheduler locale (cron-like)'
    )

    parser.add_argument(
        '--add-schedule',
        type=str,
        metavar='PROJECT:TYPE',
        help='Aggiungi schedule (es: --add-schedule my-chatbot:daily)'
    )

    parser.add_argument(
        '--list-schedules',
        action='store_true',
        help='Lista tutti gli schedule configurati'
    )

    parser.add_argument(
        '--compare',
        type=str,
        nargs='?',
        const='latest',
        metavar='RUN_A:RUN_B',
        help='Confronta run (es: --compare 15:16 oppure --compare per ultimi 2)'
    )

    parser.add_argument(
        '--regressions',
        type=int,
        nargs='?',
        const=0,
        metavar='RUN',
        help='Mostra regressioni (es: --regressions 16 oppure --regressions per ultima)'
    )

    parser.add_argument(
        '--flaky',
        type=int,
        nargs='?',
        const=10,
        metavar='N_RUNS',
        help='Rileva test flaky sugli ultimi N run (default: 10)'
    )

    # Export
    parser.add_argument(
        '--export',
        type=str,
        choices=['pdf', 'excel', 'html', 'csv', 'all'],
        metavar='FORMAT',
        help='Esporta report (pdf, excel, html, csv, all)'
    )

    parser.add_argument(
        '--export-run',
        type=int,
        metavar='RUN',
        help='Run da esportare (default: ultimo)'
    )

    # Notifiche
    parser.add_argument(
        '--notify',
        type=str,
        choices=['desktop', 'email', 'teams', 'all'],
        metavar='CHANNEL',
        help='Invia notifica test (desktop, email, teams, all)'
    )

    parser.add_argument(
        '--test-notify',
        action='store_true',
        help='Invia notifica di test per verificare configurazione'
    )

    parser.add_argument(
        '-v', '--version',
        action='version',
        version='Chatbot Tester v1.2.0'
    )

    return parser.parse_args()


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

    # Configura checker
    chatbot_url = project.chatbot.url if project else ""
    langsmith_key = ""
    google_creds = ""

    if settings:
        langsmith_key = getattr(settings, 'langsmith_api_key', '') or ''
        google_creds = str(getattr(settings, 'google_credentials_file', '') or '')

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

    # Verifica disponibilita cloud execution
    gh_client = GitHubActionsClient()
    cloud_available = gh_client.is_available()
    cloud_desc = "Lancia test senza browser locale" if cloud_available else "Richiede: brew install gh"

    items = [
        MenuItem('1', t('main_menu.new_project'), t('main_menu.new_project_desc')),
        MenuItem('2', t('main_menu.open_project'), project_desc),
        MenuItem('3', t('main_menu.finetuning'), t('main_menu.finetuning_desc')),
        MenuItem('4', "Esegui nel cloud", cloud_desc, disabled=not cloud_available),
        MenuItem('5', "Analisi Testing", "Confronta run, regressioni, test flaky"),
        MenuItem('6', t('main_menu.settings'), t('main_menu.settings_desc')),
        MenuItem('7', t('main_menu.help'), t('main_menu.help_desc')),
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

    items = [
        MenuItem('1', t('run_menu.continue_run') if run_config.active_run else t('run_menu.start_run'), ''),
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

        if choice == 'b' or choice == '':
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
    """Menu per esecuzione test nel cloud (GitHub Actions)"""
    gh_client = GitHubActionsClient()

    if not gh_client.is_available():
        ui.error("GitHub CLI non disponibile")
        ui.print(gh_client.get_install_instructions())
        input("\n  Premi INVIO per continuare...")
        return

    while True:
        ui.section("Esegui nel Cloud")
        ui.print("\n  [dim]Test eseguiti su server GitHub, senza browser locale[/dim]\n")

        # Mostra run recenti
        runs = gh_client.list_runs(limit=5)
        if runs:
            ui.print("  Run recenti:")
            for run in runs[:3]:
                status_icon = {
                    "completed": "[green]OK[/green]" if run.conclusion == "success" else "[red]FAIL[/red]",
                    "in_progress": "[yellow]...[/yellow]",
                    "queued": "[dim]queue[/dim]"
                }.get(run.status, "[dim]?[/dim]")
                ui.print(f"    {status_icon} {run.name[:40]} ({run.created_at[:10]})")
            ui.print("")

        items = [
            MenuItem('1', "Lancia test", "Avvia nuova esecuzione nel cloud"),
            MenuItem('2', "Stato esecuzioni", "Vedi run in corso e recenti"),
            MenuItem('3', "Scarica risultati", "Download report e screenshot"),
        ]

        choice = ui.menu(items, "Azione", allow_back=True)

        if choice is None:
            return

        elif choice == '1':
            _cloud_launch_test(ui, loader, gh_client)

        elif choice == '2':
            _cloud_show_status(ui, gh_client)

        elif choice == '3':
            _cloud_download_results(ui, gh_client)


def _cloud_launch_test(ui: ConsoleUI, loader: ConfigLoader, gh_client: GitHubActionsClient) -> None:
    """Lancia test nel cloud"""
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

    # Lancia
    ui.print("\n  Avvio workflow...")
    success, message = gh_client.trigger_workflow(project_name, mode, tests, new_run)

    if success:
        ui.success(message)
        ui.print("\n  [dim]Usa 'Stato esecuzioni' per monitorare il progresso[/dim]")
    else:
        ui.error(message)

    input("\n  Premi INVIO per continuare...")


def _cloud_show_status(ui: ConsoleUI, gh_client: GitHubActionsClient) -> None:
    """Mostra stato esecuzioni cloud"""
    ui.section("Stato Esecuzioni Cloud")

    runs = gh_client.list_runs(limit=10)

    if not runs:
        ui.warning("Nessuna esecuzione trovata")
        input("\n  Premi INVIO per continuare...")
        return

    ui.print("\n  Esecuzioni recenti:\n")

    for i, run in enumerate(runs, 1):
        # Icona stato
        if run.status == "completed":
            icon = "[green]PASS[/green]" if run.conclusion == "success" else "[red]FAIL[/red]"
        elif run.status == "in_progress":
            icon = "[yellow]RUNNING[/yellow]"
        elif run.status == "queued":
            icon = "[dim]QUEUED[/dim]"
        else:
            icon = "[dim]?[/dim]"

        ui.print(f"  [{i}] {icon} {run.name[:50]}")
        ui.print(f"      {run.created_at[:19]} | ID: {run.id}")
        ui.print("")

    # Opzioni
    ui.print("  [dim]Inserisci numero per vedere dettagli, 'w' per watch live, INVIO per tornare[/dim]")
    choice = input("\n  > ").strip().lower()

    if choice == 'w':
        ui.print("\n  Avvio watch (Ctrl+C per uscire)...")
        gh_client.watch_run()
    elif choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(runs):
            run = runs[idx]
            ui.print(f"\n  URL: {run.url}")
            input("\n  Premi INVIO per continuare...")


def _cloud_download_results(ui: ConsoleUI, gh_client: GitHubActionsClient) -> None:
    """Scarica risultati da esecuzione cloud"""
    ui.section("Scarica Risultati")

    runs = gh_client.list_runs(limit=10)
    completed_runs = [r for r in runs if r.status == "completed"]

    if not completed_runs:
        ui.warning("Nessuna esecuzione completata trovata")
        input("\n  Premi INVIO per continuare...")
        return

    ui.print("\n  Esecuzioni completate:\n")
    for i, run in enumerate(completed_runs[:5], 1):
        icon = "[green]PASS[/green]" if run.conclusion == "success" else "[red]FAIL[/red]"
        ui.print(f"  [{i}] {icon} {run.name[:50]} ({run.created_at[:10]})")

    choice = input("\n  Numero da scaricare (INVIO per annullare): ").strip()

    if not choice.isdigit():
        return

    idx = int(choice) - 1
    if 0 <= idx < len(completed_runs):
        run = completed_runs[idx]
        dest = f"downloads/run_{run.id}"

        ui.print(f"\n  Download artifacts in {dest}...")
        success, message = gh_client.download_artifacts(run.id, dest)

        if success:
            ui.success(message)
        else:
            ui.error(message)

    input("\n  Premi INVIO per continuare...")


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
    force_new_run: bool = False
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
        single_turn=run_config.single_turn
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
                    
                    # Carica RunConfig
                    run_config = RunConfig.load(project.run_config_file)
                    
                    # Menu gestione RUN
                    run_choice = show_run_menu(ui, project, run_config)
                    
                    force_new_run = False
                    
                    if run_choice is None:
                        continue  # Torna al menu principale
                    
                    elif run_choice == '1':
                        # Continua/Inizia RUN
                        if not run_config.active_run:
                            # Configura nuova RUN se non esiste
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
            # Impostazioni
            ui.info("Impostazioni non ancora implementate")

        elif choice == '7':
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
            
            force_new_run=args.new_run
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
        sys.exit(1)

    from src.export import RunReport, ReportExporter, check_dependencies

    # Verifica dipendenze
    deps = check_dependencies()
    if args.export == 'pdf' and not deps['pdf']:
        ui.error("PDF export richiede: pip install reportlab pillow")
        sys.exit(1)
    if args.export == 'excel' and not deps['excel']:
        ui.error("Excel export richiede: pip install openpyxl")
        sys.exit(1)

    # Trova report locale
    reports_dir = Path(f"reports/{args.project}")
    if not reports_dir.exists():
        ui.error(f"Nessun report trovato per {args.project}")
        sys.exit(1)

    # Determina quale run esportare
    run_dirs = sorted(reports_dir.glob("run_*"), key=lambda p: int(p.name.split('_')[1]))
    if not run_dirs:
        ui.error("Nessun run trovato")
        sys.exit(1)

    if args.export_run:
        # Prova entrambi i formati: run_19 e run_019
        target_dir = reports_dir / f"run_{args.export_run}"
        if not target_dir.exists():
            target_dir = reports_dir / f"run_{args.export_run:03d}"
        if not target_dir.exists():
            ui.error(f"Run {args.export_run} non trovato")
            sys.exit(1)
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
        sys.exit(1)
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


def main():
    """Entry point"""
    args = parse_args()

    # Comandi scheduler da CLI
    if args.scheduler or args.add_schedule or args.list_schedules:
        run_scheduler_commands(args)
        return

    # Comandi export da CLI
    if args.export:
        run_export_commands(args)
        return

    # Comandi notifica da CLI
    if args.notify or args.test_notify:
        run_notify_commands(args)
        return

    # Comandi analisi da CLI
    if args.compare is not None or args.regressions is not None or args.flaky is not None:
        run_cli_analysis(args)
        return

    # Health check standalone
    if args.health_check:
        ui = get_ui()
        loader = ConfigLoader()

        # Se specificato progetto, carica config
        project = None
        settings = None
        if args.project:
            try:
                project = loader.load_project(args.project)
                settings = loader.load_global_settings()
            except FileNotFoundError:
                ui.error(f"Progetto '{args.project}' non trovato")
                sys.exit(1)

        success = run_health_check(project, settings)
        sys.exit(0 if success else 1)

    # Determina modalità
    if args.no_interactive or args.project or args.new_project:
        # Modalità diretta
        asyncio.run(main_direct(args))
    else:
        # Modalità interattiva
        asyncio.run(main_interactive(args))


if __name__ == '__main__':
    main()
