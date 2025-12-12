"""
Step 3: Chatbot URL
Configures the chatbot URL and handles authentication.
"""

import time
from typing import Tuple
from rich.prompt import Prompt, Confirm
from pathlib import Path

from wizard.steps.base import BaseStep
from wizard.utils import validate_url, test_url_reachable, get_project_dir, PROJECT_ROOT
from src.ui import console, with_spinner
from src.i18n import t


class ChatbotUrlStep(BaseStep):
    """Step 3: Configure chatbot URL."""
    
    step_number = 3
    step_key = "step3"
    is_optional = False
    estimated_time = 2.0
    
    def _test_connection(self, url: str) -> Tuple[bool, int]:
        """Test URL reachability."""
        console.print(f"\n   {t('step3.testing_connection')}")
        
        try:
            import requests
            response = requests.get(url, timeout=10, allow_redirects=True)
            return True, response.status_code
        except requests.exceptions.SSLError:
            # Try without SSL verification for internal sites
            try:
                response = requests.get(url, timeout=10, verify=False, allow_redirects=True)
                return True, response.status_code
            except:
                return False, 0
        except:
            return False, 0
    
    def _open_browser_for_login(self, url: str) -> bool:
        """Open browser for manual login and save session."""
        try:
            from playwright.sync_api import sync_playwright
            
            console.print(f"\n  {t('step3.login_prompt')}")
            console.print()
            console.print(t('step3.login_instructions'))
            console.print()
            
            # Create browser data directory
            browser_data_dir = get_project_dir(self.state.project_name) / "browser-data"
            browser_data_dir.mkdir(parents=True, exist_ok=True)
            
            with sync_playwright() as p:
                # Use persistent context to save session
                browser = p.chromium.launch_persistent_context(
                    user_data_dir=str(browser_data_dir),
                    headless=False,
                    viewport={'width': 1280, 'height': 720}
                )
                
                page = browser.pages[0] if browser.pages else browser.new_page()
                page.goto(url, wait_until='domcontentloaded')
                
                console.print("  [yellow] In attesa del login...[/yellow]")
                console.print("  [dim]Premi INVIO qui quando hai completato il login e sei sulla pagina del chatbot[/dim]")
                input()
                
                # Save current URL (might have changed after login)
                final_url = page.url
                
                browser.close()
                
                console.print(f"  [green]✓ {t('step3.login_saved')}[/green]")
                return True, final_url
                
        except Exception as e:
            console.print(f"  [red]✗ Errore browser: {e}[/red]")
            return False, url
    
    def run(self) -> Tuple[bool, str]:
        """Execute URL configuration."""
        self.show()
        
        # URL input
        console.print(f"\n  [bold]{t('step3.url_prompt')}[/bold]")
        console.print(f"  [dim]{t('step3.url_hint')}[/dim]\n")
        
        while True:
            url = Prompt.ask("  URL")
            
            if not url:
                console.print(f"  [red]✗ L'URL è obbligatorio[/red]")
                continue
            
            # Add https:// if missing
            if not url.startswith('http://') and not url.startswith('https://'):
                url = 'https://' + url
            
            is_valid, error = validate_url(url)
            
            if not is_valid:
                console.print(f"  [red]✗ {error}[/red]")
                continue
            
            # Test connection
            reachable, status_code = self._test_connection(url)
            
            if reachable:
                console.print(f"  [green]✓ {t('step3.connection_ok')} (HTTP {status_code})[/green]")
                self.state.chatbot_url = url
                break
            else:
                console.print(f"  [red]✗ {t('step3.connection_fail')}[/red]")
                
                # Options
                console.print("\n  [bold]Opzioni:[/bold]")
                console.print("  [r] Riprova")
                console.print("  [c] Continua comunque (l'URL potrebbe richiedere VPN/auth)")
                console.print("  [n] Inserisci URL diverso")
                
                choice = Prompt.ask("  Scelta", choices=["r", "c", "n"], default="r")
                
                if choice == 'r':
                    reachable, status_code = self._test_connection(url)
                    if reachable:
                        console.print(f"  [green]✓ {t('step3.connection_ok')}[/green]")
                        self.state.chatbot_url = url
                        break
                elif choice == 'c':
                    self.state.chatbot_url = url
                    break
                # else 'n': loop continues
        
        console.print()
        
        # Check if login is needed
        needs_login = Confirm.ask(f"  {t('step3.needs_login')}", default=False)
        self.state.needs_login = needs_login
        
        if needs_login:
            success, final_url = self._open_browser_for_login(self.state.chatbot_url)
            if success and final_url != self.state.chatbot_url:
                console.print(f"  [cyan]>  URL aggiornato: {final_url}[/cyan]")
                self.state.chatbot_url = final_url

        # Performance option: skip screenshots
        console.print()
        skip_screenshot = Confirm.ask(
            "  Disabilita screenshot? (test più veloci)",
            default=False
        )
        self.state.skip_screenshot = skip_screenshot

        # Summary
        console.print()
        console.print("  [cyan]─" * 50 + "[/cyan]")
        console.print(f"  · URL: [bold]{self.state.chatbot_url}[/bold]")
        console.print(f"  · Login richiesto: {'Sì' if self.state.needs_login else 'No'}")
        if self.state.needs_login:
            console.print(f"  · Sessione: Salvata")
        console.print(f"  · Screenshot: {'Disabilitati' if self.state.skip_screenshot else 'Abilitati'}")
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
