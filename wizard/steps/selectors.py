"""
Step 4: Selector Detection
Auto-detects or manually learns CSS selectors for chatbot UI elements.
Supports interactive testing with multiple questions to detect all response types.
"""

import asyncio
import time
from typing import Tuple, Optional, Dict, List
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich import box

# Permette asyncio.run() anche dentro un event loop esistente
try:
    import nest_asyncio
    nest_asyncio.apply()
except ImportError:
    pass

from wizard.steps.base import BaseStep
from wizard.utils import get_project_dir
from src.ui import console
from src.i18n import t


class SelectorsStep(BaseStep):
    """Step 4: Detect or learn CSS selectors with interactive testing."""

    step_number = 4
    step_key = "step4"
    is_optional = False
    estimated_time = 5.0  # Increased for interactive testing

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _show_selectors_table(self, selectors: Dict[str, str]) -> None:
        """Display selectors in a table."""
        table = Table(box=box.SIMPLE, show_header=True)
        table.add_column("Elemento", style="cyan")
        table.add_column("Selettore CSS")
        table.add_column("Status")

        elements = [
            ('textarea', 'Textarea input'),
            ('submit_button', 'Bottone invio'),
            ('bot_messages', 'Messaggi bot'),
            ('loading_indicator', 'Loading indicator'),
            ('thread_container', 'Container thread'),
            ('content_inner', 'Content inner'),
        ]

        for key, label in elements:
            value = selectors.get(key, '')
            if value:
                status = "[green]✓[/green]"
            elif key in ['thread_container', 'loading_indicator', 'content_inner']:
                status = "[dim]- Opzionale[/dim]"
            else:
                status = "[red]✗ Mancante[/red]"

            table.add_row(label, value or "-", status)

        console.print()
        console.print(table)
        console.print()

    def run(self) -> Tuple[bool, str]:
        """Execute selector detection with interactive mode."""
        self.show()

        console.print("\n  [bold]Modalità di rilevamento selettori:[/bold]")
        console.print("  [1] Interattivo (consigliato) - Test con domande multiple")
        console.print("  [2] Rapido - Solo auto-detect")
        console.print("  [3] Manuale - Inserisci selettori a mano")

        mode = Prompt.ask("  Scelta", choices=["1", "2", "3"], default="1")

        if mode == "1":
            return self._run_interactive()
        elif mode == "2":
            return self._run_quick()
        else:
            return self._run_manual()

    def _run_interactive(self) -> Tuple[bool, str]:
        """Run interactive selector detection with multiple test questions."""
        try:
            from wizard.steps.selectors_detector import SelectorDetectorStep

            console.print("\n  > Avvio rilevamento interattivo...")
            console.print("  [dim]Potrai testare con più domande per rilevare tutti i tipi di risposta.[/dim]\n")

            # Run async detector
            step = SelectorDetectorStep(self.state.chatbot_url)
            result = asyncio.run(step.run())

            if result:
                # Convert to dict for state
                self.state.selectors = result.to_dict()
                self._show_selectors_table(self.state.selectors)

                self.state.mark_step_complete(self.step_number)
                console.print("\n  [dim]Premi INVIO per continuare...[/dim]")
                input()
                return True, 'next'
            else:
                console.print("\n  [yellow]! Rilevamento annullato[/yellow]")
                retry = Confirm.ask("  Vuoi riprovare?", default=True)
                if retry:
                    return self.run()
                else:
                    return False, 'quit'

        except ImportError as e:
            console.print(f"\n  [red]✗ Modulo non trovato: {e}[/red]")
            console.print("  [dim]Fallback alla modalità rapida...[/dim]")
            return self._run_quick()

        except Exception as e:
            console.print(f"\n  [red]✗ Errore: {e}[/red]")

            choice = self.ui.show_error(
                "Errore durante il rilevamento interattivo",
                str(e),
                solutions=[
                    "Verifica che l'URL sia corretto",
                    "Prova la modalità rapida o manuale",
                    "Controlla la connessione internet"
                ]
            )

            if choice == 'r':
                return self.run()
            elif choice == 's':
                return self._run_quick()
            else:
                return False, 'quit'

    def _run_quick(self) -> Tuple[bool, str]:
        """Run quick auto-detect only."""
        from playwright.sync_api import sync_playwright
        from wizard.utils import (
            TEXTAREA_SELECTORS,
            SUBMIT_SELECTORS,
            BOT_MESSAGE_SELECTORS,
            CONTAINER_SELECTORS,
        )

        # Additional selectors for loading indicator
        LOADING_SELECTORS = [
            ".llm__busyIndicator",
            ".loading",
            ".typing-indicator",
            "[class*='loading']",
            "[class*='typing']",
            "[class*='dots']",
        ]

        browser = None
        playwright_instance = None

        try:
            console.print("\n   Apertura browser...")

            browser_data_dir = get_project_dir(self.state.project_name) / "browser-data"
            browser_data_dir.mkdir(parents=True, exist_ok=True)

            playwright_instance = sync_playwright().start()
            browser = playwright_instance.chromium.launch_persistent_context(
                user_data_dir=str(browser_data_dir),
                headless=False,
                viewport={'width': 1280, 'height': 720}
            )

            page = browser.pages[0] if browser.pages else browser.new_page()

            console.print(f"   Navigazione a {self.state.chatbot_url}...")
            page.goto(self.state.chatbot_url, wait_until='networkidle', timeout=30000)
            time.sleep(1)

            console.print(f"\n  > Auto-detect selettori...\n")

            detected = {}

            # Auto-detect each selector type
            selector_configs = [
                ('textarea', TEXTAREA_SELECTORS, 'Textarea'),
                ('submit_button', SUBMIT_SELECTORS, 'Submit button'),
                ('bot_messages', BOT_MESSAGE_SELECTORS, 'Bot messages'),
                ('loading_indicator', LOADING_SELECTORS, 'Loading indicator'),
                ('thread_container', CONTAINER_SELECTORS, 'Thread container'),
            ]

            for key, selectors, label in selector_configs:
                found = None
                for selector in selectors:
                    try:
                        element = page.query_selector(selector)
                        if element and element.is_visible():
                            found = selector
                            break
                    except:
                        continue

                detected[key] = found or ''
                if found:
                    console.print(f"  [green]✓ {label}: {found}[/green]")
                else:
                    console.print(f"  [yellow]!  {label}: non trovato[/yellow]")

                time.sleep(0.2)

            self._show_selectors_table(detected)

            # Check required
            required = ['textarea', 'submit_button', 'bot_messages']
            missing = [k for k in required if not detected.get(k)]

            if missing:
                console.print(f"  [yellow]! Mancano selettori obbligatori: {', '.join(missing)}[/yellow]")
                console.print("  [bold]Opzioni:[/bold]")
                console.print("  [1] Prova modalità interattiva")
                console.print("  [2] Inserisci manualmente")
                console.print("  [3] Salta (non consigliato)")

                choice = Prompt.ask("  Scelta", choices=["1", "2", "3"], default="1")

                if choice == "1":
                    browser.close()
                    playwright_instance.stop()
                    return self._run_interactive()
                elif choice == "2":
                    console.print("\n  [bold]Inserisci i selettori CSS:[/bold]")
                    for key in missing:
                        value = Prompt.ask(f"  {key}")
                        if value:
                            detected[key] = value
                    self._show_selectors_table(detected)

            if Confirm.ask(f"\n  Confermi questi selettori?", default=True):
                self.state.selectors = detected
                self.state.mark_step_complete(self.step_number)

                console.print("\n  [dim]Premi INVIO per continuare...[/dim]")
                input()
                return True, 'next'
            else:
                return self.run()

        except Exception as e:
            console.print(f"\n  [red]✗ Errore: {e}[/red]")
            return False, 'quit'

        finally:
            if browser:
                try:
                    browser.close()
                except:
                    pass
            if playwright_instance:
                try:
                    playwright_instance.stop()
                except:
                    pass

    def _run_manual(self) -> Tuple[bool, str]:
        """Manual selector entry."""
        console.print("\n  [bold]Inserisci i selettori CSS:[/bold]")
        console.print("  [dim]Lascia vuoto per saltare gli opzionali[/dim]\n")

        selectors = {}

        fields = [
            ('textarea', 'Textarea input', True),
            ('submit_button', 'Bottone invio', True),
            ('bot_messages', 'Messaggi bot', True),
            ('loading_indicator', 'Loading indicator', False),
            ('thread_container', 'Thread container', False),
            ('content_inner', 'Content inner', False),
        ]

        for key, label, required in fields:
            suffix = " [required]" if required else " [opzionale]"
            value = Prompt.ask(f"  {label}{suffix}", default="")

            if required and not value:
                console.print(f"  [red]✗ {label} è obbligatorio[/red]")
                return self._run_manual()

            selectors[key] = value

        self._show_selectors_table(selectors)

        if Confirm.ask(f"\n  Confermi questi selettori?", default=True):
            self.state.selectors = selectors
            self.state.mark_step_complete(self.step_number)

            console.print("\n  [dim]Premi INVIO per continuare...[/dim]")
            input()
            return True, 'next'
        else:
            return self.run()
