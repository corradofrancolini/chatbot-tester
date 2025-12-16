"""
Step 8: Test Cases Import

Import or create test cases for the chatbot with support for:
- Local files (JSON, CSV, Excel)
- Google Sheets
- URL/API endpoints
- Templates and manual creation
"""

import os
import json
from typing import Tuple, List, Dict, Any, Optional
from pathlib import Path
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich import box

from wizard.steps.base import BaseStep
from wizard.utils import (
    validate_file_path, load_tests_from_file,
    get_project_dir, load_existing_tests, extract_spreadsheet_id
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
        self._importer = None
        self._sheets_client = None

    def _get_importer(self):
        """Lazy-load TestImporter."""
        if self._importer is None:
            from src.test_importer import TestImporter, FieldMapper, TestValidator
            self._importer = TestImporter(
                mapper=FieldMapper(),
                validator=TestValidator(),
                sheets_client=self._get_sheets_client()
            )
        return self._importer

    def _get_sheets_client(self):
        """Get Google Sheets client if configured."""
        if self._sheets_client is None and self.state.google_sheets_enabled:
            try:
                from src.sheets_client import GoogleSheetsClient
                credentials_path = self.state.google_credentials_path or "config/oauth_credentials.json"
                self._sheets_client = GoogleSheetsClient(
                    credentials_path=credentials_path,
                    spreadsheet_id=self.state.spreadsheet_id or "",
                    drive_folder_id=self.state.drive_folder_id or ""
                )
                if self._sheets_client.authenticate():
                    return self._sheets_client
                else:
                    self._sheets_client = None
            except Exception:
                self._sheets_client = None
        return self._sheets_client

    def _show_tests_preview(self, tests: List[Dict[str, Any]], max_rows: int = 10):
        """Display preview of test cases."""
        table = Table(box=box.ROUNDED, title="Preview Test Cases")
        table.add_column("ID", style="cyan", width=12)
        table.add_column("Question", max_width=40)
        table.add_column("Category", width=12)
        table.add_column("F/U", justify="center", width=4)

        for i, test in enumerate(tests[:max_rows]):
            test_id = test.get('id', f'TEST-{i+1:03d}')
            question = test.get('question', '')
            if len(question) > 40:
                question = question[:37] + "..."
            category = test.get('category', '-')[:12]
            followups = len(test.get('followups', []))

            table.add_row(test_id, question, category, str(followups) if followups else "-")

        if len(tests) > max_rows:
            table.add_row(
                "...",
                f"[dim]... e altri {len(tests) - max_rows} test[/dim]",
                "",
                ""
            )

        console.print(table)

    def _show_validation_report(self, report) -> bool:
        """Show validation report and ask to continue."""
        console.print(f"\n  [green]✓ {report.valid_count} test validi[/green]")

        if report.error_count > 0:
            console.print(f"  [red]✗ {report.error_count} test con errori:[/red]")
            for row, test, errors in report.invalid_tests[:5]:
                test_id = test.get('id', f'riga {row}')
                console.print(f"    · {test_id}: {', '.join(errors)}")

            if report.error_count > 5:
                console.print(f"    [dim]... e altri {report.error_count - 5} errori[/dim]")

            return Confirm.ask("\n  Continuare con i test validi?", default=True)

        return True

    def _handle_conflicts(self, new_tests: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Handle conflicts with existing tests."""
        existing = load_existing_tests(self.state.project_name)

        if not existing:
            return new_tests

        from src.test_importer import ConflictResolver
        resolver = ConflictResolver(existing)
        conflict_report = resolver.find_conflicts(new_tests)

        if not conflict_report.conflicts:
            return new_tests

        console.print(f"\n  [yellow]! {len(conflict_report.conflicts)} conflitti con test esistenti[/yellow]")
        resolved = resolver.resolve_interactive(conflict_report.conflicts)

        return conflict_report.new_only + resolved

    # =========================================================================
    # Import Methods
    # =========================================================================

    def _import_from_file(self) -> List[Dict[str, Any]]:
        """Import tests from a local file."""
        console.print(f"\n  [bold]Import da file locale[/bold]")
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
            console.print(f"  Formato rilevato: {format_names.get(ext, ext)}")

            try:
                importer = self._get_importer()
                result = importer.import_from_file(path)

                if not self._show_validation_report(result.validation_report):
                    return []

                if not result.tests:
                    console.print("  [yellow]! Nessun test valido trovato[/yellow]")
                    if not Confirm.ask("  Vuoi provare un altro file?", default=True):
                        return []
                    continue

                # Handle conflicts
                final_tests = self._handle_conflicts(result.tests)

                # Show preview
                console.print(f"\n  Preview:\n")
                self._show_tests_preview(final_tests)

                if Confirm.ask(f"\n  Confermare import di {len(final_tests)} test?", default=True):
                    return final_tests
                else:
                    if not Confirm.ask("  Vuoi provare un altro file?", default=True):
                        return []

            except Exception as e:
                console.print(f"  [red]✗ Errore: {str(e)}[/red]")
                if not Confirm.ask("  Vuoi riprovare?", default=True):
                    return []

    def _import_from_google_sheets(self) -> List[Dict[str, Any]]:
        """Import tests from Google Sheets."""
        console.print(f"\n  [bold]Import da Google Sheets[/bold]\n")

        # Check if Google Sheets is configured
        sheets_client = self._get_sheets_client()

        console.print("  [1] Usa spreadsheet del progetto")
        console.print("  [2] Specifica spreadsheet esterno")

        choice = Prompt.ask("  Scelta", choices=["1", "2"], default="1")

        if choice == "1":
            if not sheets_client or not self.state.spreadsheet_id:
                console.print("  [red]! Google Sheets non configurato per questo progetto[/red]")
                console.print("  [dim]Configura Google Sheets nello step precedente o usa uno spreadsheet esterno[/dim]")
                return []
            spreadsheet_id = self.state.spreadsheet_id
        else:
            url_or_id = Prompt.ask("  Spreadsheet ID o URL")
            spreadsheet_id = extract_spreadsheet_id(url_or_id)

            if not sheets_client:
                console.print("  [yellow]! Google Sheets non autenticato[/yellow]")
                console.print("  [dim]Configura le credenziali Google per usare questa funzione[/dim]")
                return []

        # Get sheet name
        sheet_name = Prompt.ask("  Nome foglio (tab)", default="Tests")

        try:
            console.print(f"\n  Caricamento da {spreadsheet_id[:20]}.../{sheet_name}...")

            importer = self._get_importer()
            result = importer.import_from_google_sheets(spreadsheet_id, sheet_name)

            if not self._show_validation_report(result.validation_report):
                return []

            if not result.tests:
                console.print("  [yellow]! Nessun test valido trovato[/yellow]")
                return []

            # Handle conflicts
            final_tests = self._handle_conflicts(result.tests)

            # Show preview
            console.print(f"\n  Preview:\n")
            self._show_tests_preview(final_tests)

            if Confirm.ask(f"\n  Confermare import di {len(final_tests)} test?", default=True):
                return final_tests

            return []

        except Exception as e:
            console.print(f"  [red]✗ Errore: {str(e)}[/red]")
            return []

    def _import_from_url(self) -> List[Dict[str, Any]]:
        """Import tests from URL/API endpoint."""
        console.print(f"\n  [bold]Import da URL/API[/bold]")
        console.print("  [dim]L'endpoint deve restituire JSON con array di test[/dim]\n")

        url = Prompt.ask("  URL endpoint")

        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url

        # Optional headers
        headers = {}
        if Confirm.ask("  Aggiungere headers HTTP?", default=False):
            console.print("  [dim]Inserisci headers (nome vuoto per terminare)[/dim]")
            while True:
                key = Prompt.ask("    Header name", default="")
                if not key:
                    break
                value = Prompt.ask(f"    {key}")
                headers[key] = value

        try:
            console.print(f"\n  Caricamento da {url[:50]}...")

            importer = self._get_importer()
            result = importer.import_from_url(url, headers if headers else None)

            if not self._show_validation_report(result.validation_report):
                return []

            if not result.tests:
                console.print("  [yellow]! Nessun test valido trovato[/yellow]")
                return []

            # Handle conflicts
            final_tests = self._handle_conflicts(result.tests)

            # Show preview
            console.print(f"\n  Preview:\n")
            self._show_tests_preview(final_tests)

            if Confirm.ask(f"\n  Confermare import di {len(final_tests)} test?", default=True):
                return final_tests

            return []

        except Exception as e:
            console.print(f"  [red]✗ Errore: {str(e)}[/red]")
            return []

    def _create_tests_manually(self) -> List[Dict[str, Any]]:
        """Create tests through guided wizard."""
        tests = []
        test_count = 0

        console.print(f"\n  [bold]Creazione manuale test[/bold]")
        console.print("  [dim]Inserisci le domande da testare. Premi INVIO vuoto per finire.[/dim]\n")

        while True:
            test_count += 1
            test_id = f"TEST_{test_count:03d}"

            # Question
            console.print(f"  [cyan]─── Test {test_id} ───[/cyan]")
            question = Prompt.ask(f"  Domanda")

            if not question:
                if test_count == 1:
                    console.print("  [yellow]! Devi inserire almeno una domanda[/yellow]")
                    test_count -= 1
                    continue
                break

            test = {
                'id': test_id,
                'question': question,
                'category': '',
                'followups': []
            }

            # Category (optional)
            category = Prompt.ask("  Categoria (opzionale)", default="")
            if category:
                test['category'] = category

            # Expected topics (optional)
            topics = Prompt.ask("  Argomenti attesi (opzionale, separati da virgola)", default="")
            if topics:
                test['expected_topics'] = [t.strip() for t in topics.split(',') if t.strip()]

            # Followups
            if Confirm.ask("  Aggiungere followup?", default=False):
                followup_num = 0
                while True:
                    followup_num += 1
                    followup = Prompt.ask(
                        f"  Followup {followup_num} (vuoto per finire)",
                        default=""
                    )

                    if not followup:
                        break

                    test['followups'].append(followup)

            tests.append(test)
            console.print(f"  [green]✓ Test {test_id} aggiunto[/green]\n")

            # Ask if continue
            if not Confirm.ask("  Aggiungere altro test?", default=True):
                break

        if tests:
            console.print(f"\n  Creati {len(tests)} test:")
            self._show_tests_preview(tests)

        return tests

    def _create_from_template(self) -> List[Dict[str, Any]]:
        """Create tests from predefined template."""
        templates = {
            'basic': [
                {'id': 'TEST_001', 'question': 'Ciao', 'category': 'greeting', 'followups': []},
                {'id': 'TEST_002', 'question': 'Come posso contattare assistenza?', 'category': 'support', 'followups': ['E via email?']},
                {'id': 'TEST_003', 'question': 'Quali servizi offrite?', 'category': 'info', 'followups': []},
            ],
            'support': [
                {'id': 'TEST_001', 'question': 'Ho un problema', 'category': 'support', 'followups': ['Non funziona nulla']},
                {'id': 'TEST_002', 'question': 'Vorrei parlare con un operatore', 'category': 'escalation', 'followups': []},
                {'id': 'TEST_003', 'question': 'Come posso fare un reclamo?', 'category': 'complaint', 'followups': ['Dove lo invio?']},
                {'id': 'TEST_004', 'question': 'Qual è il vostro numero di telefono?', 'category': 'contact', 'followups': []},
            ],
            'ecommerce': [
                {'id': 'TEST_001', 'question': 'Come posso tracciare il mio ordine?', 'category': 'order', 'followups': []},
                {'id': 'TEST_002', 'question': 'Voglio fare un reso', 'category': 'return', 'followups': ['Quali sono le tempistiche?']},
                {'id': 'TEST_003', 'question': 'Metodi di pagamento disponibili', 'category': 'payment', 'followups': []},
                {'id': 'TEST_004', 'question': 'Costi di spedizione', 'category': 'shipping', 'followups': ["E per l'estero?"]},
            ]
        }

        console.print("\n  [bold]Seleziona un template:[/bold]\n")
        console.print("  [1] Basic - Test generici (3 test)")
        console.print("  [2] Support - Customer support (4 test)")
        console.print("  [3] E-commerce - Shop online (4 test)")

        choice = Prompt.ask("\n  Scelta", choices=["1", "2", "3"], default="1")

        template_map = {"1": "basic", "2": "support", "3": "ecommerce"}
        selected = [dict(t) for t in templates[template_map[choice]]]  # Deep copy

        console.print(f"\n  [green]✓ Template caricato ({len(selected)} test)[/green]\n")
        self._show_tests_preview(selected)

        return selected

    # =========================================================================
    # Main Run
    # =========================================================================

    def run(self) -> Tuple[bool, str]:
        """Execute test import/creation."""
        self.show()

        # Options menu
        console.print(f"\n  [bold]Scegli come importare i test:[/bold]\n")
        console.print(f"  [1] File locale (JSON/CSV/Excel)")
        console.print(f"  [2] Google Sheets")
        console.print(f"  [3] URL/API")
        console.print(f"  [4] Template predefinito")
        console.print(f"  [5] Creazione manuale")
        console.print(f"  [6] Salta (aggiungi test in seguito)")

        choice = Prompt.ask("\n  Scelta", choices=["1", "2", "3", "4", "5", "6"], default="1")

        if choice == "1":
            self.tests = self._import_from_file()

        elif choice == "2":
            self.tests = self._import_from_google_sheets()

        elif choice == "3":
            self.tests = self._import_from_url()

        elif choice == "4":
            self.tests = self._create_from_template()

            # Allow editing template
            if self.tests and Confirm.ask("\n  Vuoi modificare/aggiungere test?", default=False):
                additional = self._create_tests_manually()
                # Renumber additional tests
                start_num = len(self.tests) + 1
                for i, test in enumerate(additional):
                    test['id'] = f"TEST_{start_num + i:03d}"
                self.tests.extend(additional)

        elif choice == "5":
            self.tests = self._create_tests_manually()

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
            categories = set(t.get('category', '') for t in self.tests if t.get('category'))
            console.print(f"  · Followups totali: {total_followups}")
            if categories:
                console.print(f"  · Categorie: {', '.join(sorted(categories))}")
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
