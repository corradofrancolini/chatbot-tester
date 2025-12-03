"""
Step 2: Project Information
Collects basic project details (name, description).
"""

from typing import Tuple
from rich.prompt import Prompt

from wizard.steps.base import BaseStep
from wizard.utils import validate_project_name
from src.ui import console, ask
from src.i18n import t


class ProjectInfoStep(BaseStep):
    """Step 2: Collect project information."""
    
    step_number = 2
    step_key = "step2"
    is_optional = False
    estimated_time = 1.0
    
    def run(self) -> Tuple[bool, str]:
        """Execute project info collection."""
        self.show()
        
        # Project name
        console.print(f"\n  [bold]{t('step2.name_prompt')}[/bold]")
        console.print(f"  [dim]{t('step2.name_hint')}[/dim]\n")
        
        while True:
            name = Prompt.ask("  Nome progetto")
            
            if not name:
                console.print(f"  [red]❌ Il nome è obbligatorio[/red]")
                continue
            
            # Normalize: lowercase and replace spaces with hyphens
            name = name.lower().strip().replace(' ', '-')
            
            is_valid, error = validate_project_name(name)
            
            if is_valid:
                console.print(f"  [green]✅ {t('step2.name_ok')}[/green]")
                self.state.project_name = name
                break
            else:
                console.print(f"  [red]❌ {error}[/red]")
        
        console.print()
        
        # Project description (optional)
        console.print(f"  [bold]{t('step2.description_prompt')}[/bold]")
        console.print(f"  [dim]{t('step2.description_hint')}[/dim]\n")
        
        description = Prompt.ask("  Descrizione", default="")
        self.state.project_description = description
        
        # Confirm
        console.print()
        console.print("  [cyan]─" * 50 + "[/cyan]")
        console.print(f"  📁 Progetto: [bold]{self.state.project_name}[/bold]")
        if description:
            console.print(f"  📝 Descrizione: {description}")
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
