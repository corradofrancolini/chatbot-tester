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
        '-v', '--version',
        action='version',
        version='Chatbot Tester v1.0.1'
    )
    
    return parser.parse_args()


def show_main_menu(ui: ConsoleUI, loader: ConfigLoader) -> str:
    """Mostra menu principale e ritorna scelta"""
    projects = loader.list_projects()
    
    ui.header(
        t('app_name'),
        t('welcome')
    )
    
    items = [
        MenuItem('1', t('menu_new_project'), ''),
        MenuItem('2', t('menu_open_project'), f'{len(projects)} progetti disponibili' if projects else 'Nessun progetto'),
        MenuItem('3', t('menu_settings'), ''),
        MenuItem('4', t('menu_help'), ''),
        MenuItem('quit', t('menu_exit'), '')
    ]
    
    return ui.menu(items, t('confirm'))


def show_project_menu(ui: ConsoleUI, loader: ConfigLoader) -> str:
    """Mostra lista progetti e ritorna scelta"""
    projects = loader.list_projects()
    
    if not projects:
        ui.warning("Nessun progetto disponibile. Crea un nuovo progetto.")
        return None
    
    ui.section("Seleziona Progetto")
    
    items = [
        MenuItem(str(i+1), proj, '')
        for i, proj in enumerate(projects)
    ]
    
    choice = ui.menu(items, "Progetto", allow_back=True)
    
    if choice is None:
        return None
    
    idx = int(choice) - 1
    return projects[idx] if 0 <= idx < len(projects) else None


def show_mode_menu(ui: ConsoleUI, project: ProjectConfig) -> str:
    """Mostra menu modalità test"""
    ui.section("Seleziona Modalità")
    
    # Verifica disponibilità Ollama per modalità avanzate
    ollama_available = project.ollama.enabled
    
    items = [
        MenuItem('1', t('mode_train'), t('mode_train_desc')),
        MenuItem('2', t('mode_assisted'), t('mode_assisted_desc'), disabled=not ollama_available),
        MenuItem('3', t('mode_auto'), t('mode_auto_desc'), disabled=not ollama_available),
    ]
    
    if not ollama_available:
        ui.warning("Ollama non configurato - modalità Assisted/Auto non disponibili")
    
    return ui.menu(items, t('confirm'), allow_back=True)


def show_test_selection(ui: ConsoleUI, tests: list) -> list:
    """
    Menu interattivo per selezionare quali test eseguire.
    
    Args:
        ui: Console UI
        tests: Lista completa test cases
        
    Returns:
        Lista filtrata di test da eseguire
    """
    ui.section(f"Selezione Test ({len(tests)} disponibili)")
    
    items = [
        MenuItem('1', 'Tutti', f'Esegui tutti i {len(tests)} test'),
        MenuItem('2', 'Pending', 'Solo test non completati in questa RUN'),
        MenuItem('3', 'Primi N', 'Esegui i primi N test'),
        MenuItem('4', 'Range', 'Esegui test da X a Y'),
        MenuItem('5', 'Specifici', 'Scegli test per ID'),
        MenuItem('6', 'Cerca', 'Filtra per keyword nella domanda'),
        MenuItem('7', 'Lista', 'Mostra tutti i test'),
    ]
    
    while True:
        choice = ui.menu(items, "Scelta", allow_back=True)
        
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
                n = input("  Quanti test? ").strip()
                n = int(n)
                if 1 <= n <= len(tests):
                    ui.success(f"Selezionati primi {n} test")
                    return tests[:n]
                else:
                    ui.warning(f"Inserisci un numero tra 1 e {len(tests)}")
            except ValueError:
                ui.warning("Numero non valido")
        
        elif choice == '4':
            # Range
            try:
                range_input = input("  Range (es. 10-20 o TEST-010-TEST-020): ").strip()
                
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
                    
                    selected = [t for t in tests 
                               if start <= int(t.id.split('-')[1]) <= end]
                    
                    if selected:
                        ui.success(f"Selezionati {len(selected)} test (da {selected[0].id} a {selected[-1].id})")
                        return selected
                    else:
                        ui.warning("Nessun test nel range specificato")
                else:
                    ui.warning("Formato: 10-20 oppure TEST-010-TEST-020")
            except (ValueError, IndexError):
                ui.warning("Range non valido")
        
        elif choice == '5':
            # Specifici
            ids_input = input("  IDs (es. TEST-001,TEST-005,TEST-010): ").strip()
            ids = [x.strip().upper() for x in ids_input.split(',')]
            
            # Normalizza IDs (aggiungi TEST- se manca)
            normalized_ids = []
            for id_ in ids:
                if not id_.startswith('TEST-'):
                    id_ = f"TEST-{id_.zfill(3)}"
                normalized_ids.append(id_)
            
            selected = [t for t in tests if t.id in normalized_ids]
            
            if selected:
                ui.success(f"Selezionati {len(selected)} test: {', '.join(t.id for t in selected)}")
                return selected
            else:
                ui.warning(f"Nessun test trovato per: {', '.join(normalized_ids)}")
        
        elif choice == '6':
            # Cerca per keyword
            keyword = input("  Keyword: ").strip().lower()
            if keyword:
                selected = [t for t in tests 
                           if keyword in t.question.lower() 
                           or keyword in (t.category or '').lower()]
                
                if selected:
                    ui.success(f"Trovati {len(selected)} test con '{keyword}'")
                    for t in selected[:10]:
                        ui.print(f"  [cyan]{t.id}[/cyan]: {t.question[:50]}...")
                    if len(selected) > 10:
                        ui.print(f"  [dim]...e altri {len(selected)-10}[/dim]")
                    
                    confirm = input("  Eseguire questi test? (s/n): ").strip().lower()
                    if confirm == 's':
                        return selected
                else:
                    ui.warning(f"Nessun test trovato con '{keyword}'")
            else:
                ui.warning("Inserisci una keyword")
        
        elif choice == '7':
            # Lista tutti
            ui.section("Lista Test")
            for i, t in enumerate(tests):
                followups = len(t.followups) if t.followups else 0
                fu_info = f" [dim][{followups}fu][/dim]" if followups > 0 else ""
                cat_info = f" [magenta]{t.category}[/magenta]" if t.category else ""
                ui.print(f"  [cyan]{t.id}[/cyan]: {t.question[:45]}...{cat_info}{fu_info}")
                
                # Pausa ogni 20 test
                if (i + 1) % 20 == 0 and i + 1 < len(tests):
                    more = input(f"  [Mostra altri? INVIO=sì, q=menu] ").strip().lower()
                    if more == 'q':
                        break
            
            ui.print("")  # Spazio prima del menu


def show_run_menu(ui: ConsoleUI, project: ProjectConfig, run_config: RunConfig) -> str:
    """Mostra menu gestione RUN"""
    ui.section("Gestione RUN")
    
    # Status toggle
    dry_status = "[yellow]ON[/yellow]" if run_config.dry_run else "[dim]OFF[/dim]"
    ls_status = "[green]ON[/green]" if run_config.use_langsmith else "[dim]OFF[/dim]"
    rag_status = "[green]ON[/green]" if run_config.use_rag else "[dim]OFF[/dim]"
    ui.print(f"\n  Toggle: Dry run: {dry_status} | LangSmith: {ls_status} | RAG: {rag_status}")
    
    # Mostra stato RUN attuale
    if run_config.active_run:
        ui.print(f"\n  RUN attiva: [cyan]Run {run_config.active_run:03d}[/cyan]")
        ui.print(f"  Ambiente: [cyan]{run_config.env}[/cyan]")
        ui.print(f"  Modalità: [cyan]{run_config.mode}[/cyan]")
        ui.print(f"  Test completati: [cyan]{run_config.tests_completed}[/cyan]")
        if run_config.run_start:
            ui.print(f"  Iniziata: [dim]{run_config.run_start[:19]}[/dim]")
        ui.print("")
    else:
        ui.print("\n  [yellow]Nessuna RUN attiva[/yellow]\n")
    
    items = [
        MenuItem('1', 'Continua RUN attiva' if run_config.active_run else 'Inizia nuova RUN', ''),
        MenuItem('2', 'Inizia nuova RUN', 'Crea nuovo foglio per regression test'),
        MenuItem('3', 'Configura RUN', 'Modifica ambiente/versioni'),
        MenuItem('4', 'Toggle opzioni', 'Dry run / LangSmith / RAG'),
    ]
    
    return ui.menu(items, "Scelta", allow_back=True)


def configure_run_interactive(ui: ConsoleUI, run_config: RunConfig) -> bool:
    """
    Configura i parametri della RUN interattivamente.
    
    Returns:
        True se configurazione completata, False se annullata
    """
    ui.section("Configurazione RUN")
    
    # Mostra valori attuali
    ui.print(f"\n  Valori attuali:")
    ui.print(f"  Ambiente: [cyan]{run_config.env}[/cyan]")
    ui.print(f"  Versione prompt: [cyan]{run_config.prompt_version or '(non impostata)'}[/cyan]")
    ui.print(f"  Versione modello: [cyan]{run_config.model_version or '(non impostata)'}[/cyan]")
    ui.print(f"\n  [dim]Premi INVIO per mantenere il valore attuale[/dim]\n")
    
    # Ambiente
    env_input = input(f"  Ambiente [{run_config.env}]: ").strip().upper()
    if env_input:
        if env_input in ['DEV', 'STAGING', 'PROD']:
            run_config.env = env_input
        else:
            ui.warning(f"Ambiente '{env_input}' non valido. Mantengo '{run_config.env}'")
    
    # Versione prompt
    pv_input = input(f"  Versione prompt [{run_config.prompt_version}]: ").strip()
    if pv_input:
        run_config.prompt_version = pv_input
    
    # Versione modello
    mv_input = input(f"  Versione modello [{run_config.model_version}]: ").strip()
    if mv_input:
        run_config.model_version = mv_input
    
    ui.success("Configurazione aggiornata")
    return True


def toggle_options_interactive(ui: ConsoleUI, run_config: RunConfig) -> bool:
    """
    Menu toggle opzioni runtime.
    
    Returns:
        True se modificato qualcosa
    """
    while True:
        ui.section("Toggle Opzioni")
        
        # Status attuale
        dry_status = "[yellow]ON[/yellow]" if run_config.dry_run else "[dim]OFF[/dim]"
        ls_status = "[green]ON[/green]" if run_config.use_langsmith else "[dim]OFF[/dim]"
        rag_status = "[green]ON[/green]" if run_config.use_rag else "[dim]OFF[/dim]"
        
        ui.print(f"\n  Stato attuale:")
        ui.print(f"  [1] Dry run:    {dry_status}  {'(non salva su Sheets)' if run_config.dry_run else ''}")
        ui.print(f"  [2] LangSmith:  {ls_status}")
        ui.print(f"  [3] RAG locale: {rag_status}")
        ui.print("")
        
        items = [
            MenuItem('1', f"Dry run: {'OFF→ON' if not run_config.dry_run else 'ON→OFF'}", 
                     'Disabilita salvataggio su Sheets' if not run_config.dry_run else 'Riabilita salvataggio'),
            MenuItem('2', f"LangSmith: {'OFF→ON' if not run_config.use_langsmith else 'ON→OFF'}",
                     'Abilita tracking' if not run_config.use_langsmith else 'Disabilita tracking'),
            MenuItem('3', f"RAG: {'OFF→ON' if not run_config.use_rag else 'ON→OFF'}",
                     'Abilita RAG locale' if not run_config.use_rag else 'Disabilita RAG'),
        ]
        
        choice = ui.menu(items, "Toggle", allow_back=True)
        
        if choice == 'b' or choice == '':
            return True
        elif choice == '1':
            run_config.dry_run = not run_config.dry_run
            status = "ON - non salverà su Sheets" if run_config.dry_run else "OFF"
            ui.success(f"Dry run: {status}")
        elif choice == '2':
            run_config.use_langsmith = not run_config.use_langsmith
            status = "ON" if run_config.use_langsmith else "OFF"
            ui.success(f"LangSmith: {status}")
        elif choice == '3':
            run_config.use_rag = not run_config.use_rag
            status = "ON" if run_config.use_rag else "OFF"
            ui.success(f"RAG locale: {status}")


def start_new_run_interactive(ui: ConsoleUI, run_config: RunConfig) -> bool:
    """
    Inizia una nuova RUN interattivamente.
    
    Returns:
        True se nuova RUN confermata, False se annullata
    """
    if run_config.active_run:
        ui.print(f"\n  [yellow]RUN {run_config.active_run:03d} attiva[/yellow] ({run_config.tests_completed} test completati)")
        confirm = input("  Chiudere e iniziare nuova RUN? (s/n): ").strip().lower()
        if confirm != 's':
            ui.info("Operazione annullata")
            return False
    
    # Reset RUN
    run_config.reset()
    
    # Configura nuova RUN
    configure_run_interactive(ui, run_config)
    
    ui.success("Pronto per nuova RUN. Seleziona una modalità per iniziare.")
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
        use_langsmith=run_config.use_langsmith
    )
    
    try:
        # Inizializza
        ui.section("Inizializzazione")
        if not await tester.initialize():
            ui.error("Inizializzazione fallita")
            return
        
        # Mostra stato toggle
        if run_config.dry_run:
            ui.warning("DRY RUN attivo - non salverà su Google Sheets")
        if not run_config.use_langsmith:
            ui.info("LangSmith disabilitato")
        
        # Setup foglio RUN su Google Sheets (solo se non dry_run)
        if tester.sheets and not run_config.dry_run:
            if not tester.sheets.setup_run_sheet(run_config, force_new=force_new_run):
                ui.warning("Impossibile configurare foglio RUN su Google Sheets")
            else:
                # Aggiorna run_config con il numero RUN assegnato
                run_config.active_run = tester.sheets.current_run
                run_config.save(project.run_config_file)
                ui.print(f"✅ Google Sheets connesso - Run {run_config.active_run:03d}")
                completed_count = len(tester.sheets.get_completed_tests())
                ui.print(f"   {completed_count} test già completati in questa RUN")
        
        # Naviga al chatbot
        if not await tester.navigate_to_chatbot():
            ui.error("Impossibile raggiungere il chatbot")
            return
        
        # Carica test cases
        all_tests = tester.load_test_cases()
        
        if single_test:
            # Test singolo da CLI
            tests = [t for t in all_tests if t.id == single_test]
            if not tests:
                ui.error(f"Test {single_test} non trovato")
                return
        elif test_filter == 'select':
            # Selezione interattiva
            tests = show_test_selection(ui, all_tests)
            if not tests:
                ui.info("Nessun test selezionato")
                return
        else:
            tests = all_tests
        
        # Filtra pending se richiesto
        if test_filter == 'pending' and tester.sheets:
            # Filtra solo test non completati in questa RUN
            completed = tester.sheets.get_completed_tests()
            tests = [t for t in tests if t.id not in completed]
        elif test_filter == 'failed':
            # TODO: implementare filtro failed
            pass
        # Se test_filter == 'all', non filtriamo
        
        if not tests:
            ui.info("Nessun test da eseguire")
            return
        
        ui.section(f"Esecuzione {len(tests)} test in modalità {mode.value}")
        
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
        ui.section("Riepilogo")
        passed = sum(1 for r in results if r.esito == 'PASS')
        failed = sum(1 for r in results if r.esito == 'FAIL')
        ui.stats_row({
            'Totale': len(results),
            'Passati': passed,
            'Falliti': failed,
            'Pass Rate': f"{(passed/len(results)*100):.1f}%" if results else "N/A"
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
            ui.print(t('goodbye'))
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
                    mode_choice = show_mode_menu(ui, project)
                    if mode_choice:
                        mode_map = {'1': TestMode.TRAIN, '2': TestMode.ASSISTED, '3': TestMode.AUTO}
                        mode = mode_map.get(mode_choice, TestMode.TRAIN)
                        
                        # Chiedi se vuole selezionare test specifici
                        select_items = [
                            MenuItem('1', 'Pending', 'Solo test non completati'),
                            MenuItem('2', 'Tutti', 'Tutti i test'),
                            MenuItem('3', 'Seleziona...', 'Filtra/scegli test specifici'),
                        ]
                        ui.section("Test da eseguire")
                        select_choice = ui.menu(select_items, "Scelta", allow_back=True)
                        
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
            # Impostazioni
            ui.info("Impostazioni non ancora implementate")
        
        elif choice == '4':
            # Aiuto
            ui.help_text("""
# Chatbot Tester - Guida Rapida

## Gestione RUN

Una **RUN** è una sessione di test che raggruppa i risultati in un foglio dedicato
su Google Sheets. Puoi:

- **Continuare** una RUN esistente (aggiunge test allo stesso foglio)
- **Iniziare nuova RUN** (crea nuovo foglio per regression test)
- **Configurare** ambiente, versione prompt/modello

## Modalità di Test

- **Train**: Interagisci manualmente col chatbot, il sistema impara
- **Assisted**: LLM suggerisce azioni, tu confermi o correggi
- **Auto**: Test completamente automatici (richiede Ollama)

## Comandi Utili

- `python run.py --new-project` - Crea nuovo progetto
- `python run.py -p NOME -m auto` - Test automatici
- `python run.py -p NOME -t TC001` - Singolo test
- `python run.py -p NOME --new-run` - Forza nuova RUN

## File Importanti

- `projects/<nome>/run_config.json` - Stato RUN attiva
- `projects/<nome>/tests.json` - Test cases
- `reports/<nome>/` - Report locali
            """)


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


def main():
    """Entry point"""
    args = parse_args()
    
    # Determina modalità
    if args.no_interactive or args.project or args.new_project:
        # Modalità diretta
        asyncio.run(main_direct(args))
    else:
        # Modalità interattiva
        asyncio.run(main_interactive(args))


if __name__ == '__main__':
    main()
