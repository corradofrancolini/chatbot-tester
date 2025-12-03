#!/usr/bin/env python3
"""
Chatbot Tester - Entry Point Principale

Comando principale per avviare il tool di testing chatbot.

Usage:
    python run.py                          # Menu interattivo
    python run.py --new-project            # Wizard nuovo progetto
    python run.py --project=my-chatbot     # Apri progetto specifico
    python run.py --project=my-chatbot --mode=auto    # Modalità specifica
    python run.py --lang=en                # In inglese
    python run.py --help                   # Aiuto
"""

import asyncio
import argparse
import sys
from pathlib import Path

# Aggiungi src al path
sys.path.insert(0, str(Path(__file__).parent))

from src.config_loader import ConfigLoader, ProjectConfig
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
  python run.py --project efg-intranet       Apri progetto esistente
  python run.py -p efg-intranet -m auto      Modalità auto su progetto
  python run.py -p efg-intranet --test TC001 Esegui singolo test
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
        version='Chatbot Tester v1.0.0'
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
        MenuItem('q', t('menu_exit'), '')
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


async def run_test_session(
    project: ProjectConfig,
    settings,
    mode: TestMode,
    test_filter: str = 'pending',
    single_test: str = None,
    dry_run: bool = False
):
    """Esegue una sessione di test"""
    ui = get_ui()
    
    def on_status(msg):
        ui.print(msg)
    
    def on_progress(current, total):
        ui.print(f"[{current}/{total}]", "dim")
    
    tester = ChatbotTester(project, settings, on_status, on_progress)
    
    try:
        # Inizializza
        ui.section("Inizializzazione")
        if not await tester.initialize():
            ui.error("Inizializzazione fallita")
            return
        
        # Naviga al chatbot
        if not dry_run:
            if not await tester.navigate_to_chatbot():
                ui.error("Impossibile raggiungere il chatbot")
                return
        
        # Carica test cases
        tests = tester.load_test_cases()
        
        if single_test:
            tests = [t for t in tests if t.id == single_test]
            if not tests:
                ui.error(f"Test {single_test} non trovato")
                return
        
        # Filtra
        if test_filter == 'pending':
            tests = tester.filter_pending_tests(tests)
        elif test_filter == 'failed':
            # TODO: implementare filtro failed
            pass
        
        if not tests:
            ui.info("Nessun test da eseguire")
            return
        
        ui.section(f"Esecuzione {len(tests)} test in modalità {mode.value}")
        
        if dry_run:
            ui.info("[DRY RUN] Simulazione senza esecuzione reale")
            for test in tests:
                ui.print(f"  • {test.id}: {test.question[:50]}...")
            return
        
        # Esegui
        if mode == TestMode.TRAIN:
            results = await tester.run_train_session(tests)
        elif mode == TestMode.ASSISTED:
            results = await tester.run_assisted_session(tests)
        else:
            results = await tester.run_auto_session(tests)
        
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
        
        if choice == 'q':
            ui.print(t('goodbye'))
            break
        
        elif choice == '1':
            # Nuovo progetto - avvia wizard
            ui.info("Avvio wizard nuovo progetto...")
            # TODO: implementare wizard completo
            ui.warning("Wizard non ancora implementato. Usa --new-project")
        
        elif choice == '2':
            # Apri progetto
            project_name = show_project_menu(ui, loader)
            if project_name:
                try:
                    project = loader.load_project(project_name)
                    settings = loader.load_global_settings()
                    
                    # Scegli modalità
                    mode_choice = show_mode_menu(ui, project)
                    if mode_choice:
                        mode_map = {'1': TestMode.TRAIN, '2': TestMode.ASSISTED, '3': TestMode.AUTO}
                        mode = mode_map.get(mode_choice, TestMode.TRAIN)
                        
                        await run_test_session(project, settings, mode)
                
                except FileNotFoundError:
                    ui.error(f"Progetto '{project_name}' non trovato")
        
        elif choice == '3':
            # Impostazioni
            ui.info("Impostazioni non ancora implementate")
        
        elif choice == '4':
            # Aiuto
            ui.help_text("""
# Chatbot Tester - Guida Rapida

## Modalità di Test

- **Train**: Interagisci manualmente col chatbot, il sistema impara
- **Assisted**: LLM suggerisce azioni, tu confermi o correggi
- **Auto**: Test completamente automatici (richiede Ollama)

## Comandi Utili

- `python run.py --new-project` - Crea nuovo progetto
- `python run.py -p NOME -m auto` - Test automatici
- `python run.py -p NOME -t TC001` - Singolo test

## File Importanti

- `projects/<nome>/tests.json` - Test cases
- `reports/<nome>/` - Report generati
            """)


async def main_direct(args):
    """Modalità diretta con argomenti CLI"""
    set_language(args.lang)
    ui = get_ui()
    loader = ConfigLoader()
    
    if args.new_project:
        ui.info("Wizard nuovo progetto...")
        # TODO: implementare wizard
        ui.warning("Wizard in sviluppo")
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
            dry_run=args.dry_run
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
