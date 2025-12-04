"""
Step 8: Test Cases Import
Import or create test cases for the chatbot.
"""

import os
import json
from typing import Tuple, List, Dict, Any
from pathlib import Path
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich import box

from wizard.steps.base import BaseStep
from wizard.utils import (
    validate_file_path, load_tests_from_file,
    get_project_dir
)
from src.ui import console
from src.i18n import t


class TestImportStep(BaseStep):
    """Step 8: Import or create test cases."""
    
    step_number = 8
    step_key = "step8"
    is_optional = True
    estimated_time = 5.0
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tests: List[Dict[str, Any]] = []
    
    def _show_tests_preview(self, tests: List[Dict[str, Any]], max_rows: int = 10):
        """Display preview of test cases."""
        table = Table(box=box.ROUNDED, title="Preview Test Cases")
        table.add_column("ID", style="cyan", width=12)
        table.add_column("Domanda", max_width=45)
        table.add_column("Followups", justify="center", width=10)
        
        for i, test in enumerate(tests[:max_rows]):
            test_id = test.get('id', f'TEST-{i+1:03d}')
            question = test.get('question', '')
            if len(question) > 45:
                question = question[:42] + "..."
            followups = len(test.get('followups', []))
            
            table.add_row(test_id, question, str(followups))
        
        if len(tests) > max_rows:
            table.add_row(
                "...",
                f"[dim]... e altri {len(tests) - max_rows} test[/dim]",
                ""
            )
        
        console.print(table)
    
    def _import_from_file(self) -> List[Dict[str, Any]]:
        """Import tests from a file."""
        console.print(f"\n  [bold]{t('step8.import_path')}[/bold]")
        console.print("  [dim]Formati supportati: JSON, CSV, Excel (.xlsx)[/dim]\n")
        
        while True:
            path = Prompt.ask("  Percorso file")
            path = os.path.expanduser(path)
            
            is_valid, error = validate_file_path(
                path,
                must_exist=True,
                extensions=['.json', '.csv', '.xlsx', '.xls']
            )
            
            if not is_valid:
                console.print(f"  [red]✗ {error}[/red]")
                if not Confirm.ask("  Vuoi riprovare?", default=True):
                    return []
                continue
            
            # Detect format
            ext = Path(path).suffix.lower()
            format_names = {'.json': 'JSON', '.csv': 'CSV', '.xlsx': 'Excel', '.xls': 'Excel'}
            console.print(f"  {t('step8.import_format_detect', format=format_names.get(ext, ext))}")
            
            try:
                tests = load_tests_from_file(path)
                
                if not tests:
                    console.print("  [yellow]! Nessun test trovato nel file[/yellow]")
                    if not Confirm.ask("  Vuoi provare un altro file?", default=True):
                        return []
                    continue
                
                console.print(f"  [green]✓ {t('step8.import_count', count=len(tests))}[/green]\n")
                
                # Show preview
                console.print(f"  {t('step8.import_preview')}:\n")
                self._show_tests_preview(tests)
                
                if Confirm.ask(f"\n  {t('step8.import_confirm')}", default=True):
                    return tests
                else:
                    if not Confirm.ask("  Vuoi provare un altro file?", default=True):
                        return []
                        
            except Exception as e:
                console.print(f"  [red]✗ {t('step8.import_fail', error=str(e))}[/red]")
                if not Confirm.ask("  Vuoi riprovare?", default=True):
                    return []
    
    def _create_tests_manually(self) -> List[Dict[str, Any]]:
        """Create tests through guided wizard."""
        tests = []
        test_count = 0
        
        console.print(f"\n  [bold]{t('step8.create_title')}[/bold]")
        console.print("  [dim]Inserisci le domande da testare. Premi INVIO vuoto per finire.[/dim]\n")
        
        while True:
            test_count += 1
            test_id = f"TEST-{test_count:03d}"
            
            # Question
            console.print(f"  [cyan]─── Test {test_id} ───[/cyan]")
            question = Prompt.ask(f"  {t('step8.create_question')}")
            
            if not question:
                if test_count == 1:
                    console.print("  [yellow]! Devi inserire almeno una domanda[/yellow]")
                    test_count -= 1
                    continue
                break
            
            test = {
                'id': test_id,
                'question': question,
                'followups': []
            }
            
            # Followups
            if Confirm.ask(f"  {t('step8.create_followup_prompt')}", default=False):
                followup_num = 0
                while True:
                    followup_num += 1
                    followup = Prompt.ask(
                        f"  {t('step8.create_followup', n=followup_num)}",
                        default=""
                    )
                    
                    if not followup:
                        break
                    
                    test['followups'].append(followup)
            
            tests.append(test)
            console.print(f"  [green]✓ Test {test_id} aggiunto[/green]\n")
            
            # Ask if continue
            if not Confirm.ask(f"  {t('step8.create_another')}", default=True):
                break
        
        if tests:
            console.print(f"\n  {t('step8.create_saved', count=len(tests))}")
            self._show_tests_preview(tests)
        
        return tests
    
    def _create_from_template(self) -> List[Dict[str, Any]]:
        """Create tests from predefined template."""
        templates = {
            'basic': [
                {'id': 'TEST-001', 'question': 'Ciao', 'followups': []},
                {'id': 'TEST-002', 'question': 'Come posso contattare assistenza?', 'followups': ['E via email?']},
                {'id': 'TEST-003', 'question': 'Quali servizi offrite?', 'followups': []},
            ],
            'support': [
                {'id': 'TEST-001', 'question': 'Ho un problema', 'followups': ['Non funziona nulla']},
                {'id': 'TEST-002', 'question': 'Vorrei parlare con un operatore', 'followups': []},
                {'id': 'TEST-003', 'question': 'Come posso fare un reclamo?', 'followups': ['Dove lo invio?']},
                {'id': 'TEST-004', 'question': 'Qual è il vostro numero di telefono?', 'followups': []},
            ],
            'ecommerce': [
                {'id': 'TEST-001', 'question': 'Come posso tracciare il mio ordine?', 'followups': []},
                {'id': 'TEST-002', 'question': 'Voglio fare un reso', 'followups': ['Quali sono le tempistiche?']},
                {'id': 'TEST-003', 'question': 'Metodi di pagamento disponibili', 'followups': []},
                {'id': 'TEST-004', 'question': 'Costi di spedizione', 'followups': ['E per l\'estero?']},
            ]
        }
        
        console.print("\n  [bold]Seleziona un template:[/bold]\n")
        console.print("  [1] Basic - Test generici (3 test)")
        console.print("  [2] Support - Customer support (4 test)")
        console.print("  [3] E-commerce - Shop online (4 test)")
        
        choice = Prompt.ask("\n  Scelta", choices=["1", "2", "3"], default="1")
        
        template_map = {"1": "basic", "2": "support", "3": "ecommerce"}
        selected = templates[template_map[choice]]
        
        console.print(f"\n  [green]✓ Template caricato ({len(selected)} test)[/green]\n")
        self._show_tests_preview(selected)
        
        return selected
    
    def run(self) -> Tuple[bool, str]:
        """Execute test import/creation."""
        self.show()
        
        # Options
        console.print(f"\n  [bold]{t('step8.options_title')}[/bold]\n")
        console.print(f"  [1] {t('step8.option_import')}")
        console.print(f"  [2] {t('step8.option_create')}")
        console.print("  [3] Usa un template predefinito")
        console.print(f"  [4] {t('step8.option_skip')}")
        
        choice = Prompt.ask("\n  Scelta", choices=["1", "2", "3", "4"], default="1")
        
        if choice == "1":
            # Import from file
            self.tests = self._import_from_file()
            
        elif choice == "2":
            # Create manually
            self.tests = self._create_tests_manually()
            
        elif choice == "3":
            # Use template
            self.tests = self._create_from_template()
            
            # Allow editing
            if Confirm.ask("\n  Vuoi modificare/aggiungere test?", default=False):
                additional = self._create_tests_manually()
                # Renumber additional tests
                start_num = len(self.tests) + 1
                for i, test in enumerate(additional):
                    test['id'] = f"TEST-{start_num + i:03d}"
                self.tests.extend(additional)
        else:
            # Skip
            console.print("\n  [dim]Puoi aggiungere test in seguito in tests.json[/dim]")
            self.tests = []
        
        # Save tests to state
        self.state.tests = self.tests
        
        # Summary
        console.print()
        console.print("  [cyan]─" * 50 + "[/cyan]")
        console.print(f"  · Test cases: {len(self.tests)}")
        if self.tests:
            total_followups = sum(len(t.get('followups', [])) for t in self.tests)
            console.print(f"  · Followups totali: {total_followups}")
        console.print("  [cyan]─" * 50 + "[/cyan]")
        console.print()
        
        console.print("  [dim]Premi INVIO per continuare, 'b' per tornare indietro...[/dim]")
        choice = input("  ").strip().lower()
        
        if choice == 'b':
            return True, 'back'
        elif choice == 'q':
            return False, 'quit'
        
        self.state.mark_step_complete(self.step_number)
        return True, 'next'
