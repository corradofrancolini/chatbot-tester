"""
Step 6: LangSmith Configuration
Configures optional LangSmith integration for advanced debugging.
"""

from typing import Tuple, Optional, List
from rich.prompt import Prompt, Confirm

from wizard.steps.base import BaseStep
from wizard.utils import validate_langsmith_key, PROJECT_ROOT
from src.ui import console
from src.i18n import t


class LangSmithStep(BaseStep):
    """Step 6: Configure LangSmith integration."""
    
    step_number = 6
    step_key = "step6"
    is_optional = True
    estimated_time = 3.0
    
    def _test_langsmith_connection(self, api_key: str, project_id: str = "", org_id: str = "") -> Tuple[bool, str]:
        """Test LangSmith API connection."""
        try:
            import requests
            
            headers = {
                "x-api-key": api_key,
                "Content-Type": "application/json"
            }
            
            # Test API with a simple request
            url = "https://api.smith.langchain.com/sessions"
            params = {"limit": 1}
            
            if org_id:
                params["tenant_id"] = org_id
            
            response = requests.get(url, headers=headers, params=params, timeout=10)
            
            if response.status_code == 200:
                return True, ""
            elif response.status_code == 401:
                return False, "API Key non valida"
            elif response.status_code == 403:
                return False, "Accesso negato (verifica org_id)"
            else:
                return False, f"Errore HTTP {response.status_code}"
                
        except requests.exceptions.Timeout:
            return False, "Timeout connessione"
        except Exception as e:
            return False, str(e)
    
    def _detect_tool_names(self, api_key: str, project_id: str = "", org_id: str = "") -> List[str]:
        """Auto-detect tool names from recent LangSmith traces."""
        try:
            import requests
            
            headers = {
                "x-api-key": api_key,
                "Content-Type": "application/json"
            }
            
            # Get recent runs
            url = "https://api.smith.langchain.com/runs/query"
            
            payload = {
                "limit": 10,
                "filter": {
                    "run_type": "tool"
                }
            }
            
            if project_id:
                payload["project_id"] = project_id
            
            params = {}
            if org_id:
                params["tenant_id"] = org_id
            
            response = requests.post(url, headers=headers, json=payload, params=params, timeout=15)
            
            if response.status_code != 200:
                return []
            
            runs = response.json().get("runs", [])
            
            # Extract unique tool names
            tool_names = set()
            for run in runs:
                name = run.get("name", "")
                if name:
                    tool_names.add(name)
            
            return sorted(list(tool_names))
            
        except Exception:
            return []
    
    def _save_api_key(self, api_key: str) -> None:
        """Save API key to .env file."""
        env_file = PROJECT_ROOT / "config" / ".env"
        env_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Read existing content
        existing = ""
        if env_file.exists():
            with open(env_file, 'r') as f:
                existing = f.read()
        
        # Update or add LANGSMITH_API_KEY
        lines = existing.split('\n')
        found = False
        
        for i, line in enumerate(lines):
            if line.startswith('LANGSMITH_API_KEY='):
                lines[i] = f'LANGSMITH_API_KEY={api_key}'
                found = True
                break
        
        if not found:
            lines.append(f'LANGSMITH_API_KEY={api_key}')
        
        with open(env_file, 'w') as f:
            f.write('\n'.join(lines))
    
    def run(self) -> Tuple[bool, str]:
        """Execute LangSmith configuration."""
        self.show()
        
        # Options
        console.print(f"\n  [bold]{t('step6.options_title')}[/bold]\n")
        console.print(f"  [1] {t('step6.option_no')}")
        console.print(f"  [2] {t('step6.option_yes')}")
        console.print(f"  [3] {t('step6.option_later')}")
        
        choice = Prompt.ask("\n  Scelta", choices=["1", "2", "3"], default="1")
        
        if choice == "1" or choice == "3":
            # Skip LangSmith
            self.state.langsmith_enabled = False
            
            if choice == "3":
                console.print("\n  [cyan]ℹ️  Potrai configurare LangSmith in seguito modificando project.yaml e .env[/cyan]")
            else:
                console.print("\n  [dim]LangSmith non configurato[/dim]")
                
        else:
            # Configure LangSmith
            
            # API Key
            console.print(f"\n  [bold]{t('step6.api_key_prompt')}[/bold]")
            console.print(f"  [dim]{t('step6.api_key_hint')}[/dim]")
            
            while True:
                api_key = Prompt.ask("\n  API Key")
                
                if not api_key:
                    console.print("  [red]❌ API Key obbligatoria[/red]")
                    continue
                
                if not validate_langsmith_key(api_key):
                    console.print(f"  [red]❌ {t('step6.api_key_invalid')}[/red]")
                    continue
                
                console.print(f"  [green]✅ Formato API Key valido[/green]")
                break
            
            # Project ID (optional)
            console.print(f"\n  [bold]{t('step6.project_prompt')}[/bold]")
            console.print("  [dim](opzionale, per filtrare le trace)[/dim]")
            project_id = Prompt.ask("\n  Project ID", default="")
            
            # Org ID (optional)
            console.print(f"\n  [bold]{t('step6.org_prompt')}[/bold]")
            console.print("  [dim](opzionale, necessario per org multiple)[/dim]")
            org_id = Prompt.ask("\n  Organization ID", default="")
            
            # Test connection
            console.print(f"\n  ⏳ {t('step6.testing')}")
            
            success, error = self._test_langsmith_connection(api_key, project_id, org_id)
            
            if success:
                console.print(f"  [green]✅ {t('step6.test_ok')}[/green]")
                
                # Auto-detect tool names
                console.print(f"\n  ⏳ {t('step6.detect_tools')}")
                
                tools = self._detect_tool_names(api_key, project_id, org_id)
                
                if tools:
                    console.print(f"  [green]✅ {t('step6.tools_found', tools=', '.join(tools))}[/green]")
                    
                    if Confirm.ask(f"\n  {t('step6.tools_confirm')}", default=True):
                        self.state.langsmith_tool_names = tools
                    else:
                        # Manual input
                        console.print(f"\n  {t('step6.tools_manual')}")
                        manual_tools = Prompt.ask("  Tool names")
                        self.state.langsmith_tool_names = [t.strip() for t in manual_tools.split(',') if t.strip()]
                else:
                    console.print(f"  [yellow]⚠️  {t('step6.tools_not_found')}[/yellow]")
                    
                    # Manual input
                    console.print(f"\n  {t('step6.tools_manual')}")
                    console.print("  [dim](es. search_kb,get_user_info,create_ticket)[/dim]")
                    manual_tools = Prompt.ask("\n  Tool names", default="")
                    
                    if manual_tools:
                        self.state.langsmith_tool_names = [t.strip() for t in manual_tools.split(',') if t.strip()]
                
                # Save configuration
                self.state.langsmith_enabled = True
                self.state.langsmith_api_key = api_key
                self.state.langsmith_project_id = project_id
                self.state.langsmith_org_id = org_id
                
                # Save API key to .env
                self._save_api_key(api_key)
                
            else:
                console.print(f"  [red]❌ {t('step6.test_fail')}: {error}[/red]")
                
                if Confirm.ask("\n  Vuoi riprovare?", default=True):
                    return self.run()
                else:
                    self.state.langsmith_enabled = False
                    console.print("\n  [yellow]⚠️  LangSmith non configurato[/yellow]")
        
        # Summary
        console.print()
        console.print("  [cyan]─" * 50 + "[/cyan]")
        console.print(f"  🔍 LangSmith: {'Abilitato' if self.state.langsmith_enabled else 'Disabilitato'}")
        if self.state.langsmith_enabled:
            console.print(f"  🔑 API Key: {'*' * 20}...{self.state.langsmith_api_key[-8:]}")
            console.print(f"  📁 Project ID: {self.state.langsmith_project_id or 'Non specificato'}")
            console.print(f"  🏢 Org ID: {self.state.langsmith_org_id or 'Non specificato'}")
            console.print(f"  🛠️  Tool Names: {', '.join(self.state.langsmith_tool_names) or 'Nessuno'}")
        console.print("  [cyan]─" * 50 + "[/cyan]")
        console.print()
        
        console.print("  [dim]Premi INVIO per continuare, 'b' per tornare indietro...[/dim]")
        nav = input("  ").strip().lower()
        
        if nav == 'b':
            return True, 'back'
        elif nav == 'q':
            return False, 'quit'
        
        self.state.mark_step_complete(self.step_number)
        return True, 'next'
