"""
Step 4: Selector Detection
Auto-detects or manually learns CSS selectors for chatbot UI elements.
"""

import time
from typing import Tuple, Optional, Dict, List
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich import box

from wizard.steps.base import BaseStep
from wizard.utils import (
    get_project_dir,
    TEXTAREA_SELECTORS,
    SUBMIT_SELECTORS,
    BOT_MESSAGE_SELECTORS,
    CONTAINER_SELECTORS,
)
from src.ui import console
from src.i18n import t


class SelectorsStep(BaseStep):
    """Step 4: Detect or learn CSS selectors."""
    
    step_number = 4
    step_key = "step4"
    is_optional = False
    estimated_time = 3.0
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.browser = None
        self.page = None
    
    def _get_browser_context(self):
        """Get Playwright browser with saved session."""
        from playwright.sync_api import sync_playwright
        
        browser_data_dir = get_project_dir(self.state.project_name) / "browser-data"
        browser_data_dir.mkdir(parents=True, exist_ok=True)
        
        self._playwright = sync_playwright().start()
        self.browser = self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(browser_data_dir),
            headless=False,
            viewport={'width': 1280, 'height': 720}
        )
        
        self.page = self.browser.pages[0] if self.browser.pages else self.browser.new_page()
        return self.page
    
    def _close_browser(self):
        """Close browser if open."""
        if self.browser:
            try:
                self.browser.close()
            except:
                pass
        if hasattr(self, '_playwright') and self._playwright:
            try:
                self._playwright.stop()
            except:
                pass
    
    def _auto_detect_selector(self, selectors: List[str], element_name: str) -> Optional[str]:
        """Try to auto-detect a selector from a list of candidates."""
        for selector in selectors:
            try:
                element = self.page.query_selector(selector)
                if element and element.is_visible():
                    console.print(f"  [green]✅ {element_name}: {selector}[/green]")
                    return selector
            except:
                continue
        
        console.print(f"  [yellow]⚠️  {element_name}: Non trovato automaticamente[/yellow]")
        return None
    
    def _auto_detect_all(self) -> Dict[str, str]:
        """Run automatic detection for all selectors."""
        console.print(f"\n  ⏳ {t('step4.auto_detect')}\n")
        
        detected = {}
        
        # Textarea
        detected['textarea'] = self._auto_detect_selector(
            TEXTAREA_SELECTORS, 
            t('step4.found_textarea')
        )
        time.sleep(0.3)
        
        # Submit button
        detected['submit_button'] = self._auto_detect_selector(
            SUBMIT_SELECTORS,
            t('step4.found_button')
        )
        time.sleep(0.3)
        
        # Bot messages
        detected['bot_messages'] = self._auto_detect_selector(
            BOT_MESSAGE_SELECTORS,
            t('step4.found_messages')
        )
        time.sleep(0.3)
        
        # Thread container (optional)
        detected['thread_container'] = self._auto_detect_selector(
            CONTAINER_SELECTORS,
            t('step4.found_container')
        )
        
        return detected
    
    def _manual_click_learn(self) -> Dict[str, str]:
        """Guide user to click on elements to learn selectors."""
        console.print(f"\n  [bold]{t('step4.manual_mode')}[/bold]\n")
        console.print(t('step4.manual_instructions'))
        
        detected = {}
        
        # Inject click capture script
        capture_script = """
        window.__capturedSelector = null;
        window.__clickHandler = function(e) {
            e.preventDefault();
            e.stopPropagation();
            
            let element = e.target;
            let selector = '';
            
            // Try ID first
            if (element.id) {
                selector = '#' + element.id;
            }
            // Try unique class
            else if (element.className && typeof element.className === 'string') {
                const classes = element.className.split(' ').filter(c => c);
                if (classes.length > 0) {
                    selector = '.' + classes.join('.');
                }
            }
            // Try data attributes
            else if (element.dataset) {
                for (const [key, value] of Object.entries(element.dataset)) {
                    selector = `[data-${key}="${value}"]`;
                    break;
                }
            }
            // Fallback to tag + nth-child
            if (!selector) {
                selector = element.tagName.toLowerCase();
                if (element.parentElement) {
                    const siblings = Array.from(element.parentElement.children);
                    const index = siblings.indexOf(element) + 1;
                    selector += `:nth-child(${index})`;
                }
            }
            
            window.__capturedSelector = selector;
            element.style.outline = '3px solid #00ff00';
            setTimeout(() => element.style.outline = '', 1000);
        };
        document.addEventListener('click', window.__clickHandler, true);
        """
        
        self.page.evaluate(capture_script)
        
        # Helper to capture click
        def wait_for_click(prompt: str, optional: bool = False) -> Optional[str]:
            console.print(f"\n  [cyan]👆 {prompt}[/cyan]")
            
            if optional:
                console.print("  [dim](Premi INVIO senza cliccare per saltare)[/dim]")
            
            # Clear previous capture
            self.page.evaluate("window.__capturedSelector = null")
            
            # Wait for click or Enter
            input("  ")
            
            selector = self.page.evaluate("window.__capturedSelector")
            
            if selector:
                console.print(f"  [green]✅ Catturato: {selector}[/green]")
                return selector
            elif optional:
                console.print("  [dim]Saltato[/dim]")
                return None
            else:
                console.print("  [yellow]⚠️  Nessun click rilevato, riprova[/yellow]")
                return wait_for_click(prompt, optional)
        
        # Capture each element
        detected['textarea'] = wait_for_click(t('step4.click_textarea'))
        detected['submit_button'] = wait_for_click(t('step4.click_button'))
        
        # Send a test message to reveal bot response
        console.print("\n  [cyan]Ora invia un messaggio di test (scrivi 'ciao' o simile)[/cyan]")
        console.print("  [dim]Premi INVIO qui quando il bot ha risposto[/dim]")
        input("  ")
        
        detected['bot_messages'] = wait_for_click(t('step4.click_message'))
        detected['thread_container'] = wait_for_click(t('step4.click_container'), optional=True)
        
        # Remove click handler
        self.page.evaluate("""
            document.removeEventListener('click', window.__clickHandler, true);
        """)
        
        return detected
    
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
            ('thread_container', 'Container thread')
        ]
        
        for key, label in elements:
            value = selectors.get(key, '')
            if value:
                status = "[green]✅[/green]"
            elif key == 'thread_container':
                status = "[dim]⏭️ Opzionale[/dim]"
            else:
                status = "[red]❌ Mancante[/red]"
            
            table.add_row(label, value or "-", status)
        
        console.print()
        console.print(table)
        console.print()
    
    def _test_selectors(self, selectors: Dict[str, str]) -> bool:
        """Test selectors by sending a test message."""
        console.print(f"\n  ⏳ Test selettori in corso...")
        
        try:
            # Type in textarea
            textarea = self.page.query_selector(selectors['textarea'])
            if not textarea:
                console.print("  [red]❌ Textarea non trovata[/red]")
                return False
            
            textarea.fill("Test automatico - per favore ignora")
            time.sleep(0.3)
            
            # Click submit
            button = self.page.query_selector(selectors['submit_button'])
            if not button:
                console.print("  [red]❌ Bottone non trovato[/red]")
                return False
            
            button.click()
            
            # Wait for bot response
            console.print("  ⏳ Attendo risposta del bot...")
            
            try:
                self.page.wait_for_selector(
                    selectors['bot_messages'],
                    timeout=30000,
                    state='visible'
                )
                console.print(f"  [green]✅ {t('step4.test_success')}[/green]")
                return True
            except:
                console.print(f"  [red]❌ {t('step4.test_fail')}[/red]")
                return False
                
        except Exception as e:
            console.print(f"  [red]❌ Errore: {e}[/red]")
            return False
    
    def run(self) -> Tuple[bool, str]:
        """Execute selector detection."""
        self.show()
        
        try:
            # Open browser
            console.print("\n  ⏳ Apertura browser...")
            page = self._get_browser_context()
            
            # Navigate to chatbot URL
            console.print(f"  ⏳ Navigazione a {self.state.chatbot_url}...")
            page.goto(self.state.chatbot_url, wait_until='networkidle', timeout=30000)
            time.sleep(1)
            
            # Try auto-detection first
            detected = self._auto_detect_all()
            
            # Check what we found
            required = ['textarea', 'submit_button', 'bot_messages']
            missing = [k for k in required if not detected.get(k)]
            
            if not missing:
                console.print(f"\n  [green]✅ {t('step4.auto_success')}[/green]")
            elif len(missing) < len(required):
                console.print(f"\n  [yellow]⚠️  {t('step4.auto_partial')}[/yellow]")
            else:
                console.print(f"\n  [red]❌ {t('step4.auto_fail')}[/red]")
            
            self._show_selectors_table(detected)
            
            # Options
            if missing:
                console.print("  [bold]Opzioni:[/bold]")
                console.print("  [1] Apprendimento manuale (clicca sugli elementi)")
                console.print("  [2] Inserisci selettori manualmente")
                console.print("  [3] Riprova auto-detect")
                
                choice = Prompt.ask("  Scelta", choices=["1", "2", "3"], default="1")
                
                if choice == "1":
                    manual = self._manual_click_learn()
                    # Merge: manual overrides auto for missing
                    for key in missing:
                        if manual.get(key):
                            detected[key] = manual[key]
                    self._show_selectors_table(detected)
                    
                elif choice == "2":
                    console.print("\n  [bold]Inserisci i selettori CSS:[/bold]")
                    for key in missing:
                        labels = {
                            'textarea': 'Textarea',
                            'submit_button': 'Bottone invio',
                            'bot_messages': 'Messaggi bot'
                        }
                        value = Prompt.ask(f"  {labels.get(key, key)}")
                        if value:
                            detected[key] = value
                    self._show_selectors_table(detected)
                    
                elif choice == "3":
                    detected = self._auto_detect_all()
                    self._show_selectors_table(detected)
            
            # Confirm selectors
            if Confirm.ask(f"\n  {t('step4.confirm_selectors')}", default=True):
                self.state.selectors = detected
                
                # Optional: test selectors
                if Confirm.ask(f"  {t('step4.test_selectors')}", default=False):
                    self._test_selectors(detected)
                
                self._close_browser()
                self.state.mark_step_complete(self.step_number)
                
                console.print("\n  [dim]Premi INVIO per continuare...[/dim]")
                input()
                return True, 'next'
            else:
                # Let user retry
                return self.run()
                
        except Exception as e:
            console.print(f"\n  [red]❌ Errore: {e}[/red]")
            self._close_browser()
            
            choice = self.ui.show_error(
                "Errore durante il rilevamento",
                str(e),
                solutions=[
                    "Verifica che l'URL sia corretto",
                    "Assicurati che la pagina sia caricata completamente",
                    "Prova a effettuare il login manualmente"
                ]
            )
            
            if choice == 'r':
                return self.run()
            elif choice == 's':
                self.state.mark_step_complete(self.step_number)
                return True, 'next'
            else:
                return False, 'quit'
        
        finally:
            self._close_browser()
