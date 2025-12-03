"""
Step 7: Ollama Configuration
Configures optional Ollama (local LLM) for Assisted and Auto modes.
"""

import subprocess
import time
from typing import Tuple
from rich.prompt import Prompt, Confirm

from wizard.steps.base import BaseStep
from wizard.utils import check_ollama_installed, check_ollama_running, check_ollama_model
from src.ui import console
from src.i18n import t


class OllamaStep(BaseStep):
    """Step 7: Configure Ollama integration."""
    
    step_number = 7
    step_key = "step7"
    is_optional = True
    estimated_time = 5.0
    
    def _install_ollama(self) -> bool:
        """Install Ollama via Homebrew."""
        try:
            console.print("\n  ⏳ Installazione Ollama...")
            
            result = subprocess.run(
                ["brew", "install", "ollama"],
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode == 0:
                console.print("  [green]✅ Ollama installato[/green]")
                return True
            else:
                console.print(f"  [red]❌ Errore installazione: {result.stderr}[/red]")
                return False
                
        except subprocess.TimeoutExpired:
            console.print("  [red]❌ Timeout installazione[/red]")
            return False
        except Exception as e:
            console.print(f"  [red]❌ Errore: {e}[/red]")
            return False
    
    def _start_ollama(self) -> bool:
        """Start Ollama server."""
        try:
            console.print("\n  ⏳ Avvio Ollama...")
            
            # Start ollama serve in background
            subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            
            # Wait for server to be ready
            for _ in range(30):
                time.sleep(1)
                if check_ollama_running():
                    console.print("  [green]✅ Ollama avviato[/green]")
                    return True
            
            console.print("  [yellow]⚠️  Ollama avviato ma non risponde ancora[/yellow]")
            return True
            
        except Exception as e:
            console.print(f"  [red]❌ Errore avvio: {e}[/red]")
            return False
    
    def _pull_model(self, model: str = "mistral") -> bool:
        """Download a model."""
        try:
            console.print(f"\n  ⏳ Download modello {model}... (può richiedere alcuni minuti)")
            
            result = subprocess.run(
                ["ollama", "pull", model],
                capture_output=True,
                text=True,
                timeout=600  # 10 minutes
            )
            
            if result.returncode == 0 or check_ollama_model(model):
                console.print(f"  [green]✅ Modello {model} disponibile[/green]")
                return True
            else:
                console.print(f"  [red]❌ Errore download: {result.stderr}[/red]")
                return False
                
        except subprocess.TimeoutExpired:
            console.print("  [yellow]⚠️  Download in corso in background, verificherò più tardi[/yellow]")
            return False
        except Exception as e:
            console.print(f"  [red]❌ Errore: {e}[/red]")
            return False
    
    def _test_generation(self, model: str = "mistral") -> bool:
        """Test LLM generation."""
        try:
            import requests
            
            console.print(f"\n  ⏳ {t('step7.test_prompt')}")
            
            response = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": model,
                    "prompt": "Say 'Hello!' in one word.",
                    "stream": False
                },
                timeout=60
            )
            
            if response.status_code == 200:
                result = response.json().get("response", "")
                if result:
                    console.print(f"  [green]✅ {t('step7.test_ok')}[/green]")
                    console.print(f"  [dim]Risposta: {result[:50]}...[/dim]")
                    return True
            
            console.print(f"  [red]❌ {t('step7.test_fail')}[/red]")
            return False
            
        except Exception as e:
            console.print(f"  [red]❌ Errore test: {e}[/red]")
            return False
    
    def run(self) -> Tuple[bool, str]:
        """Execute Ollama configuration."""
        self.show()
        
        # Info about Ollama
        console.print(f"\n  [dim]{t('step7.info')}[/dim]")
        
        # Check current status
        console.print(f"\n  ⏳ {t('step7.checking')}")
        
        ollama_installed = check_ollama_installed()
        ollama_running = check_ollama_running() if ollama_installed else False
        mistral_installed = check_ollama_model("mistral") if ollama_running else False
        
        # Status report
        console.print()
        console.print(f"  Ollama installato: {'[green]✅ Sì[/green]' if ollama_installed else '[yellow]❌ No[/yellow]'}")
        
        if ollama_installed:
            console.print(f"  Ollama in esecuzione: {'[green]✅ Sì[/green]' if ollama_running else '[yellow]❌ No[/yellow]'}")
        
        if ollama_running:
            console.print(f"  Modello Mistral: {'[green]✅ Disponibile[/green]' if mistral_installed else '[yellow]❌ Non installato[/yellow]'}")
        
        console.print()
        
        # Options based on status
        if not ollama_installed:
            console.print(f"  [bold]{t('step7.options_title')}[/bold]\n")
            console.print(f"  [1] {t('step7.option_install')}")
            console.print(f"  [2] {t('step7.option_skip')}")
            
            choice = Prompt.ask("\n  Scelta", choices=["1", "2"], default="2")
            
            if choice == "1":
                # Install Ollama
                if self._install_ollama():
                    ollama_installed = True
                    
                    # Start Ollama
                    if self._start_ollama():
                        ollama_running = True
                        
                        # Pull Mistral
                        if Confirm.ask(f"\n  {t('step7.model_install_prompt')}", default=True):
                            if self._pull_model("mistral"):
                                mistral_installed = True
                else:
                    console.print("\n  [yellow]⚠️  Installazione fallita, continuo senza Ollama[/yellow]")
            
        elif not ollama_running:
            if Confirm.ask(f"  {t('step7.start_prompt')}", default=True):
                if self._start_ollama():
                    ollama_running = True
                    
                    # Check for Mistral
                    if not check_ollama_model("mistral"):
                        if Confirm.ask(f"\n  {t('step7.model_install_prompt')}", default=True):
                            self._pull_model("mistral")
                            mistral_installed = check_ollama_model("mistral")
        
        elif not mistral_installed:
            if Confirm.ask(f"  {t('step7.model_install_prompt')}", default=True):
                self._pull_model("mistral")
                mistral_installed = check_ollama_model("mistral")
        
        # Final status
        if ollama_running and mistral_installed:
            # Test generation
            if self._test_generation("mistral"):
                self.state.ollama_enabled = True
                self.state.ollama_model = "mistral"
                console.print("\n  [green]✅ Ollama configurato correttamente![/green]")
            else:
                if Confirm.ask("\n  Test fallito. Abilitare comunque Ollama?", default=False):
                    self.state.ollama_enabled = True
                    self.state.ollama_model = "mistral"
                else:
                    self.state.ollama_enabled = False
        else:
            self.state.ollama_enabled = False
            console.print("\n  [yellow]⚠️  Ollama non configurato. Potrai usare solo la modalità Train.[/yellow]")
        
        # Summary
        console.print()
        console.print("  [cyan]─" * 50 + "[/cyan]")
        console.print(f"  🧠 Ollama: {'Abilitato' if self.state.ollama_enabled else 'Disabilitato'}")
        if self.state.ollama_enabled:
            console.print(f"  🤖 Modello: {self.state.ollama_model}")
            console.print(f"  📍 URL: http://localhost:11434")
        console.print("  [cyan]─" * 50 + "[/cyan]")
        
        if not self.state.ollama_enabled:
            console.print("\n  [dim]Modalità disponibili: Solo Train[/dim]")
            console.print("  [dim]Per Assisted/Auto, configura Ollama in seguito.[/dim]")
        else:
            console.print("\n  [dim]Modalità disponibili: Train, Assisted, Auto[/dim]")
        
        console.print()
        console.print("  [dim]Premi INVIO per continuare, 'b' per tornare indietro...[/dim]")
        nav = input("  ").strip().lower()
        
        if nav == 'b':
            return True, 'back'
        elif nav == 'q':
            return False, 'quit'
        
        self.state.mark_step_complete(self.step_number)
        return True, 'next'
