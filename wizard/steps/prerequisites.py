"""
Step 1: Prerequisites Check
Verifies system requirements are met before proceeding.
"""

import time
from typing import Tuple, List, Dict
from rich.table import Table
from rich.text import Text
from rich import box

from wizard.steps.base import BaseStep
from wizard.utils import (
    check_macos_version,
    check_python_version,
    check_homebrew,
    check_git,
    check_disk_space,
    check_internet,
)
from src.ui import console, with_spinner, ask_confirm
from src.i18n import t


class PrerequisitesStep(BaseStep):
    """Step 1: Verify system prerequisites."""
    
    step_number = 1
    step_key = "step1"
    is_optional = False
    estimated_time = 0.5
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.checks: List[Dict] = []
    
    def _run_check(self, name: str, check_func, *args) -> Dict:
        """Run a single check and return result dict."""
        try:
            result = check_func(*args)
            if isinstance(result, tuple):
                passed, value = result
            else:
                passed, value = result, ""
            
            return {
                'name': name,
                'passed': passed,
                'value': value
            }
        except Exception as e:
            return {
                'name': name,
                'passed': False,
                'value': str(e)
            }
    
    def _create_results_table(self) -> Table:
        """Create a table showing check results."""
        table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
        table.add_column("Status", width=4)
        table.add_column("Check", width=30)
        table.add_column("Result", width=30)
        
        for check in self.checks:
            status = "✅" if check['passed'] else "❌"
            style = "green" if check['passed'] else "red"
            
            table.add_row(
                status,
                check['name'],
                str(check['value']) if check['value'] else "",
                style=style
            )
        
        return table
    
    def run(self) -> Tuple[bool, str]:
        """Execute prerequisites check."""
        self.show()
        
        self.checks = []
        all_passed = True
        
        # macOS check
        console.print(f"\n  {t('step1.checking_os')}")
        time.sleep(0.3)
        
        result = self._run_check(
            t('step1.os_ok', version='').split()[0] + " Version",  # "macOS Version"
            check_macos_version
        )
        self.checks.append(result)
        
        if result['passed']:
            console.print(f"  ✅ {t('step1.os_ok', version=result['value'])}")
        else:
            console.print(f"  ❌ {t('step1.os_fail')}")
            all_passed = False
        
        # Python check
        console.print(f"  {t('step1.checking_python')}")
        time.sleep(0.2)
        
        result = self._run_check("Python", check_python_version)
        self.checks.append(result)
        
        if result['passed']:
            console.print(f"  ✅ {t('step1.python_ok', version=result['value'])}")
        else:
            console.print(f"  ❌ {t('step1.python_fail')}")
            all_passed = False
        
        # Homebrew check
        console.print(f"  {t('step1.checking_homebrew')}")
        time.sleep(0.2)
        
        homebrew_ok = check_homebrew()
        self.checks.append({
            'name': "Homebrew",
            'passed': homebrew_ok,
            'value': "Installed" if homebrew_ok else "Not found"
        })
        
        if homebrew_ok:
            console.print(f"  ✅ {t('step1.homebrew_ok')}")
        else:
            console.print(f"  ❌ {t('step1.homebrew_fail')}")
            all_passed = False
        
        # Git check
        console.print(f"  {t('step1.checking_git')}")
        time.sleep(0.2)
        
        result = self._run_check("Git", check_git)
        self.checks.append(result)
        
        if result['passed']:
            console.print(f"  ✅ {t('step1.git_ok', version=result['value'])}")
        else:
            console.print(f"  ❌ {t('step1.git_fail')}")
            all_passed = False
        
        # Disk space check
        console.print(f"  {t('step1.checking_disk')}")
        time.sleep(0.2)
        
        result = self._run_check("Disk Space", check_disk_space, 500)
        self.checks.append(result)
        
        if result['passed']:
            console.print(f"  ✅ {t('step1.disk_ok', space=result['value'])}")
        else:
            console.print(f"  ❌ {t('step1.disk_fail')}")
            all_passed = False
        
        # Network check
        console.print(f"  {t('step1.checking_network')}")
        time.sleep(0.2)
        
        network_ok = check_internet()
        self.checks.append({
            'name': "Internet",
            'passed': network_ok,
            'value': "Connected" if network_ok else "No connection"
        })
        
        if network_ok:
            console.print(f"  ✅ {t('step1.network_ok')}")
        else:
            console.print(f"  ❌ {t('step1.network_fail')}")
            all_passed = False
        
        console.print()
        
        # Summary
        if all_passed:
            console.print(f"\n  [bold green]✅ {t('step1.all_ok')}[/bold green]\n")
            console.print("  [dim]Premi INVIO per continuare...[/dim]")
            input()
            return True, 'next'
        else:
            console.print(f"\n  [bold red]❌ {t('step1.some_fail')}[/bold red]\n")
            
            # Show solutions for failed checks
            failed = [c for c in self.checks if not c['passed']]
            
            if any(c['name'] == 'Homebrew' for c in failed):
                console.print("  [yellow]💡 Installa Homebrew con:[/yellow]")
                console.print('  [dim]/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"[/dim]')
                console.print()
            
            if any('Python' in c['name'] for c in failed):
                console.print("  [yellow]💡 Installa Python 3.10+ con:[/yellow]")
                console.print("  [dim]brew install python@3.11[/dim]")
                console.print()
            
            if any(c['name'] == 'Git' for c in failed):
                console.print("  [yellow]💡 Installa Git con:[/yellow]")
                console.print("  [dim]xcode-select --install[/dim]")
                console.print()
            
            # Options
            console.print("\n  [bold]Opzioni:[/bold]")
            console.print("  [r] Riprova i check")
            console.print("  [c] Continua comunque (non raccomandato)")
            console.print("  [q] Esci")
            console.print()
            
            from rich.prompt import Prompt
            choice = Prompt.ask("  Scelta", choices=["r", "c", "q"], default="r")
            
            if choice == 'r':
                return self.run()  # Retry
            elif choice == 'c':
                console.print("\n  [yellow]⚠️  Alcuni prerequisiti mancano, potrebbero esserci problemi.[/yellow]\n")
                return True, 'next'
            else:
                return False, 'quit'
