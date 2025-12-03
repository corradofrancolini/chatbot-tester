"""
Step 9: Summary
Shows configuration summary and saves project.
"""

from typing import Tuple
from rich.prompt import Prompt, Confirm
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

from wizard.steps.base import BaseStep
from wizard.utils import (
    save_project_config, save_tests, ensure_project_dirs,
    get_project_dir
)
from src.ui import console, show_key_value
from src.i18n import t


class SummaryStep(BaseStep):
    """Step 9: Show summary and finalize setup."""
    
    step_number = 9
    step_key = "step9"
    is_optional = False
    estimated_time = 0.5
    
    def _create_summary_panel(self, title: str, items: list) -> Panel:
        """Create a formatted summary panel."""
        text = Text()
        for label, value, icon in items:
            text.append(f"  {icon} ", style="cyan")
            text.append(f"{label}: ", style="bold")
            
            if isinstance(value, bool):
                text.append(
                    "✅ Sì" if value else "❌ No",
                    style="green" if value else "red"
                )
            elif value is None or value == "":
                text.append("Non configurato", style="dim")
            else:
                text.append(str(value))
            text.append("\n")
        
        return Panel(text, title=title, box=box.ROUNDED, border_style="cyan")
    
    def _show_complete_summary(self):
        """Display complete configuration summary."""
        
        # Project section
        console.print(f"\n  {t('step9.section_project')}")
        console.print("  " + "─" * 48)
        console.print(f"    Nome:        [bold]{self.state.project_name}[/bold]")
        console.print(f"    Descrizione: {self.state.project_description or '[dim]Non specificata[/dim]'}")
        
        # Chatbot section
        console.print(f"\n  {t('step9.section_chatbot')}")
        console.print("  " + "─" * 48)
        console.print(f"    URL:         [bold]{self.state.chatbot_url}[/bold]")
        console.print(f"    Login:       {'Sì' if self.state.needs_login else 'No'}")
        
        # Selectors section
        console.print(f"\n  {t('step9.section_selectors')}")
        console.print("  " + "─" * 48)
        selectors = self.state.selectors
        for key, name in [
            ('textarea', 'Textarea'),
            ('submit_button', 'Bottone'),
            ('bot_messages', 'Messaggi'),
            ('thread_container', 'Container')
        ]:
            value = selectors.get(key, '')
            status = "✅" if value else "❌"
            display_value = value[:40] + "..." if len(value) > 40 else value
            console.print(f"    {name:12} {status} {display_value or '[dim]Non configurato[/dim]'}")
        
        # Google Sheets section
        console.print(f"\n  {t('step9.section_google')}")
        console.print("  " + "─" * 48)
        if self.state.google_sheets_enabled:
            console.print(f"    Status:      [green]✅ Abilitato[/green]")
            console.print(f"    Spreadsheet: {self.state.spreadsheet_id[:20]}...")
            if self.state.drive_folder_id:
                console.print(f"    Drive:       {self.state.drive_folder_id[:20]}...")
        else:
            console.print(f"    Status:      [dim]❌ Disabilitato (solo report locali)[/dim]")
        
        # LangSmith section
        console.print(f"\n  {t('step9.section_langsmith')}")
        console.print("  " + "─" * 48)
        if self.state.langsmith_enabled:
            console.print(f"    Status:      [green]✅ Abilitato[/green]")
            console.print(f"    Project:     {self.state.langsmith_project_id}")
            if self.state.langsmith_tool_names:
                console.print(f"    Tools:       {', '.join(self.state.langsmith_tool_names)}")
        else:
            console.print(f"    Status:      [dim]❌ Disabilitato[/dim]")
        
        # Ollama section
        console.print(f"\n  {t('step9.section_ollama')}")
        console.print("  " + "─" * 48)
        if self.state.ollama_enabled:
            console.print(f"    Status:      [green]✅ Abilitato[/green]")
            console.print(f"    Modello:     {self.state.ollama_model}")
            console.print(f"    Modalità:    Train, Assisted, Auto")
        else:
            console.print(f"    Status:      [dim]❌ Disabilitato[/dim]")
            console.print(f"    Modalità:    Solo Train")
        
        # Test Cases section
        console.print(f"\n  {t('step9.section_tests')}")
        console.print("  " + "─" * 48)
        test_count = len(self.state.tests)
        if test_count > 0:
            total_followups = sum(len(t.get('followups', [])) for t in self.state.tests)
            console.print(f"    Test cases:  [green]{test_count}[/green]")
            console.print(f"    Followups:   {total_followups}")
        else:
            console.print(f"    Test cases:  [dim]Nessuno (da aggiungere)[/dim]")
    
    def _save_configuration(self) -> bool:
        """Save all configuration files."""
        try:
            console.print(f"\n  {t('step9.saving')}")
            
            # Ensure directories
            ensure_project_dirs(self.state.project_name)
            console.print("    ✅ Cartelle create")
            
            # Save project config
            save_project_config(self.state)
            console.print("    ✅ project.yaml salvato")
            
            # Save tests if any
            if self.state.tests:
                save_tests(self.state.project_name, self.state.tests)
                console.print("    ✅ tests.json salvato")
            
            # Create empty training_data.json
            project_dir = get_project_dir(self.state.project_name)
            training_file = project_dir / "training_data.json"
            if not training_file.exists():
                import json
                with open(training_file, 'w') as f:
                    json.dump([], f)
                console.print("    ✅ training_data.json creato")
            
            console.print(f"\n  [green]✅ {t('step9.saved')}[/green]")
            return True
            
        except Exception as e:
            console.print(f"\n  [red]❌ Errore salvataggio: {e}[/red]")
            return False
    
    def _show_next_steps(self):
        """Display next steps and launch options."""
        next_steps = f"""
    🎉 SETUP COMPLETATO!
    
    Il progetto è stato configurato in:
    [cyan]projects/{self.state.project_name}/[/cyan]
    
    [bold]Prossimi passi:[/bold]
    
    1. Avvia il tool:
       [cyan]python run.py --project={self.state.project_name}[/cyan]
    
    2. Inizia in modalità [bold]Train[/bold] per familiarizzare con il chatbot
       e costruire il training data
    
    3. Passa a modalità [bold]Assisted[/bold] quando hai abbastanza dati
       per avere suggerimenti automatici
    
    4. Usa modalità [bold]Auto[/bold] per regression testing automatico
    
    [dim]Puoi modificare la configurazione in:
    - projects/{self.state.project_name}/project.yaml
    - projects/{self.state.project_name}/tests.json
    - config/.env (credenziali)[/dim]
"""
        console.print(Panel(next_steps, border_style="green", box=box.DOUBLE))
    
    def run(self) -> Tuple[bool, str]:
        """Execute summary step."""
        self.show()
        
        # Show complete summary
        self._show_complete_summary()
        
        console.print()
        
        # Confirm save
        if Confirm.ask(f"  {t('step9.save_prompt')}", default=True):
            if not self._save_configuration():
                if not Confirm.ask("  Vuoi riprovare?", default=True):
                    return False, 'quit'
                return True, 'retry'
        else:
            console.print("\n  [yellow]⚠️ Configurazione non salvata[/yellow]")
            if Confirm.ask("  Vuoi tornare indietro per modificare?", default=True):
                return True, 'back'
        
        # Show next steps
        self._show_next_steps()
        
        # Option to launch
        if Confirm.ask(f"\n  {t('step9.launch_prompt')}", default=False):
            console.print(f"\n  [cyan]Avvio: python run.py --project={self.state.project_name}[/cyan]\n")
            
            import subprocess
            import sys
            from pathlib import Path
            
            run_script = Path(__file__).parent.parent.parent / "run.py"
            if run_script.exists():
                subprocess.run([
                    sys.executable,
                    str(run_script),
                    f"--project={self.state.project_name}"
                ])
        
        self.state.mark_step_complete(self.step_number)
        return True, 'next'
