"""
UI Module - Interfaccia CLI con Rich

Gestisce:
- Output formattato con colori
- Progress bar
- Tabelle e pannelli
- Input interattivo
- Menu di selezione
- Wizard UI
"""

from typing import Optional, List, Callable, Any
from dataclasses import dataclass
from enum import Enum
from functools import wraps
import sys
import os

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
    from rich.prompt import Prompt, Confirm
    from rich.text import Text
    from rich.style import Style
    from rich.live import Live
    from rich.layout import Layout
    from rich.markdown import Markdown
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


class UIStyle(Enum):
    """Stili predefiniti"""
    SUCCESS = "green"
    ERROR = "red"
    WARNING = "yellow"
    INFO = "blue"
    MUTED = "dim"
    HIGHLIGHT = "cyan bold"


@dataclass
class MenuItem:
    """Voce di menu"""
    key: str
    label: str
    description: str = ""
    disabled: bool = False
    recommended: bool = False


class ConsoleUI:
    """
    Interfaccia console con Rich.
    
    Fallback a print() se Rich non disponibile.
    
    Usage:
        ui = ConsoleUI()
        ui.header("Titolo")
        ui.success("Operazione completata!")
        
        choice = ui.menu([
            MenuItem("1", "Opzione 1"),
            MenuItem("2", "Opzione 2")
        ])
    """
    
    def __init__(self, use_colors: bool = True):
        """
        Inizializza la console.
        
        Args:
            use_colors: Abilita colori (default True)
        """
        self.use_colors = use_colors and RICH_AVAILABLE
        
        if self.use_colors:
            self.console = Console()
        else:
            self.console = None
    
    # ==================== OUTPUT BASE ====================
    
    def print(self, message: str, style: Optional[str] = None) -> None:
        """Stampa messaggio"""
        if self.console:
            self.console.print(message, style=style)
        else:
            print(message)
    
    def success(self, message: str) -> None:
        """Messaggio di successo"""
        self.print(f"✅ {message}", UIStyle.SUCCESS.value)
    
    def error(self, message: str) -> None:
        """Messaggio di errore"""
        self.print(f"❌ {message}", UIStyle.ERROR.value)
    
    def warning(self, message: str) -> None:
        """Messaggio di warning"""
        self.print(f"⚠️ {message}", UIStyle.WARNING.value)
    
    def info(self, message: str) -> None:
        """Messaggio informativo"""
        self.print(f"ℹ️ {message}", UIStyle.INFO.value)
    
    def muted(self, message: str) -> None:
        """Testo secondario"""
        self.print(message, UIStyle.MUTED.value)
    
    # ==================== STRUTTURE ====================
    
    def header(self, title: str, subtitle: str = "") -> None:
        """Header principale"""
        if self.console:
            content = f"[bold]{title}[/bold]"
            if subtitle:
                content += f"\n[dim]{subtitle}[/dim]"
            
            self.console.print(Panel(
                content,
                border_style="blue",
                padding=(1, 2)
            ))
        else:
            print(f"\n{'='*50}")
            print(f"  {title}")
            if subtitle:
                print(f"  {subtitle}")
            print(f"{'='*50}\n")
    
    def section(self, title: str) -> None:
        """Intestazione sezione"""
        if self.console:
            self.console.print(f"\n[bold cyan]▶ {title}[/bold cyan]")
        else:
            print(f"\n--- {title} ---")
    
    def divider(self) -> None:
        """Linea divisoria"""
        if self.console:
            self.console.rule(style="dim")
        else:
            print("-" * 40)
    
    # ==================== TABELLE ====================
    
    def table(self, 
              headers: List[str],
              rows: List[List[str]],
              title: str = "") -> None:
        """Stampa tabella"""
        if self.console:
            table = Table(title=title, show_header=True, header_style="bold")
            
            for h in headers:
                table.add_column(h)
            
            for row in rows:
                table.add_row(*row)
            
            self.console.print(table)
        else:
            if title:
                print(f"\n{title}")
            
            # Header
            print(" | ".join(headers))
            print("-" * (sum(len(h) for h in headers) + len(headers) * 3))
            
            # Rows
            for row in rows:
                print(" | ".join(row))
    
    def stats_row(self, stats: dict) -> None:
        """Riga di statistiche"""
        if self.console:
            parts = []
            for k, v in stats.items():
                parts.append(f"[bold]{k}:[/bold] {v}")
            self.console.print("  ".join(parts))
        else:
            print("  ".join(f"{k}: {v}" for k, v in stats.items()))
    
    # ==================== PROGRESS ====================
    
    def progress_bar(self, 
                     total: int,
                     description: str = "Progresso") -> 'ProgressContext':
        """
        Crea progress bar.
        
        Usage:
            with ui.progress_bar(100) as progress:
                for i in range(100):
                    progress.advance()
        """
        return ProgressContext(self, total, description)
    
    def spinner(self, message: str) -> 'SpinnerContext':
        """
        Crea spinner per operazioni lunghe.
        
        Usage:
            with ui.spinner("Caricamento..."):
                do_something()
        """
        return SpinnerContext(self, message)
    
    # ==================== INPUT ====================
    
    def input(self, 
              prompt: str,
              default: str = "",
              password: bool = False) -> str:
        """Input testuale"""
        if self.console:
            return Prompt.ask(prompt, default=default, password=password)
        else:
            if default:
                result = input(f"{prompt} [{default}]: ").strip()
                return result if result else default
            else:
                return input(f"{prompt}: ").strip()
    
    def confirm(self, 
                question: str,
                default: bool = False) -> bool:
        """Conferma sì/no"""
        if self.console:
            return Confirm.ask(question, default=default)
        else:
            suffix = "[Y/n]" if default else "[y/N]"
            response = input(f"{question} {suffix}: ").strip().lower()
            
            if not response:
                return default
            return response in ['y', 'yes', 's', 'sì', 'si']
    
    def menu(self, 
             items: List[MenuItem],
             prompt: str = "Scegli un'opzione",
             allow_back: bool = False) -> Optional[str]:
        """
        Menu di selezione.
        
        Args:
            items: Lista opzioni
            prompt: Messaggio prompt
            allow_back: Mostra opzione "indietro"
            
        Returns:
            Key dell'opzione selezionata o None se back
        """
        # Mostra opzioni
        self.print("")
        for item in items:
            if item.disabled:
                style = "dim"
                suffix = " (non disponibile)"
            elif item.recommended:
                style = "green"
                suffix = " [raccomandato]"
            else:
                style = None
                suffix = ""
            
            # Escape delle parentesi quadre per Rich
            key_display = item.key.replace("[", "\\[").replace("]", "\\]")
            line = f"  \\[{key_display}] {item.label}{suffix}"
            if item.description:
                line += f"\n      {item.description}"
            
            self.print(line, style)
        
        if allow_back:
            self.print("  \\[back] Indietro", UIStyle.MUTED.value)
        
        self.print("")
        
        # Ottieni input
        valid_keys = [i.key for i in items if not i.disabled]
        if allow_back:
            valid_keys.append('back')
        
        while True:
            choice = self.input(prompt).strip()
            
            if choice in valid_keys:
                if choice == 'back':
                    return None
                return choice
            
            self.warning(f"Opzione non valida: {choice}")
    
    def select_multiple(self,
                        items: List[MenuItem],
                        prompt: str = "Seleziona (separati da virgola)") -> List[str]:
        """
        Selezione multipla.
        
        Returns:
            Lista di keys selezionate
        """
        # Mostra opzioni
        self.print("")
        for item in items:
            line = f"  [{item.key}] {item.label}"
            self.print(line)
        
        self.print("")
        
        choice = self.input(prompt)
        selected = [c.strip() for c in choice.split(',')]
        
        valid_keys = [i.key for i in items]
        return [s for s in selected if s in valid_keys]
    
    # ==================== WIZARD ====================
    
    def wizard_step(self,
                    step_number: int,
                    total_steps: int,
                    title: str,
                    description: str = "",
                    time_estimate: str = "") -> None:
        """Header per step wizard"""
        progress_pct = int((step_number / total_steps) * 100)
        bar_filled = int(progress_pct / 5)
        bar = "█" * bar_filled + "░" * (20 - bar_filled)
        
        if self.console:
            self.console.print(Panel(
                f"[bold]Step {step_number}/{total_steps}[/bold] {bar} {time_estimate}\n\n"
                f"[bold cyan]{title}[/bold cyan]\n"
                f"[dim]{description}[/dim]",
                border_style="blue"
            ))
        else:
            print(f"\n{'='*50}")
            print(f"Step {step_number}/{total_steps} [{bar}] {time_estimate}")
            print(f"\n{title}")
            if description:
                print(f"{description}")
            print(f"{'='*50}\n")
    
    def wizard_summary(self, settings: dict) -> None:
        """Riepilogo configurazione wizard"""
        if self.console:
            table = Table(title="Riepilogo Configurazione", show_header=True)
            table.add_column("Impostazione", style="cyan")
            table.add_column("Valore")
            
            for key, value in settings.items():
                # Formatta valore
                if isinstance(value, bool):
                    val_str = "✅ Sì" if value else "❌ No"
                elif isinstance(value, list):
                    val_str = ", ".join(str(v) for v in value) or "(vuoto)"
                elif value is None or value == "":
                    val_str = "(non configurato)"
                else:
                    val_str = str(value)
                
                table.add_row(key, val_str)
            
            self.console.print(table)
        else:
            print("\n--- Riepilogo Configurazione ---")
            for key, value in settings.items():
                print(f"  {key}: {value}")
    
    # ==================== MESSAGGI SPECIALI ====================
    
    def error_panel(self,
                    error_type: str,
                    detail: str,
                    solutions: List[str]) -> None:
        """Pannello errore con soluzioni"""
        if self.console:
            solution_text = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(solutions))
            
            self.console.print(Panel(
                f"[bold red]❌ ERRORE: {error_type}[/bold red]\n\n"
                f"Dettaglio: {detail}\n\n"
                f"[bold]💡 Possibili soluzioni:[/bold]\n{solution_text}",
                border_style="red",
                title="Errore"
            ))
        else:
            print(f"\n❌ ERRORE: {error_type}")
            print(f"   Dettaglio: {detail}")
            print("\n💡 Possibili soluzioni:")
            for i, s in enumerate(solutions):
                print(f"   {i+1}. {s}")
    
    def help_text(self, text: str) -> None:
        """Testo di aiuto"""
        if self.console:
            self.console.print(Markdown(text))
        else:
            print(text)
    
    def clear(self) -> None:
        """Pulisce lo schermo"""
        if self.console:
            self.console.clear()
        else:
            print("\033[H\033[J", end="")


class ProgressContext:
    """Context manager per progress bar"""
    
    def __init__(self, ui: ConsoleUI, total: int, description: str):
        self.ui = ui
        self.total = total
        self.description = description
        self.current = 0
        self._progress = None
        self._task = None
    
    def __enter__(self):
        if self.ui.console:
            self._progress = Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                console=self.ui.console
            )
            self._progress.start()
            self._task = self._progress.add_task(self.description, total=self.total)
        return self
    
    def __exit__(self, *args):
        if self._progress:
            self._progress.stop()
    
    def advance(self, amount: int = 1) -> None:
        """Avanza la progress bar"""
        self.current += amount
        if self._progress and self._task is not None:
            self._progress.advance(self._task, amount)
        elif not self.ui.console:
            pct = int(self.current / self.total * 100)
            print(f"\r{self.description}: {pct}%", end="", flush=True)
            if self.current >= self.total:
                print()
    
    def update(self, description: str) -> None:
        """Aggiorna descrizione"""
        if self._progress and self._task is not None:
            self._progress.update(self._task, description=description)


class SpinnerContext:
    """Context manager per spinner"""
    
    def __init__(self, ui: ConsoleUI, message: str):
        self.ui = ui
        self.message = message
        self._progress = None
        self._task = None
    
    def __enter__(self):
        if self.ui.console:
            self._progress = Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=self.ui.console
            )
            self._progress.start()
            self._task = self._progress.add_task(self.message, total=None)
        else:
            print(f"⏳ {self.message}...", end="", flush=True)
        return self
    
    def __exit__(self, *args):
        if self._progress:
            self._progress.stop()
        elif not self.ui.console:
            print(" fatto")
    
    def update(self, message: str) -> None:
        """Aggiorna messaggio"""
        if self._progress and self._task is not None:
            self._progress.update(self._task, description=message)


# ==================== WIZARD UI ====================

class WizardUI:
    """
    UI specifica per il wizard di setup.
    Fornisce metodi per navigazione step, progress, input guidato.
    """
    
    def __init__(self, total_steps: int = 9):
        self.console = Console() if RICH_AVAILABLE else None
        self.total_steps = total_steps
        self.current_step = 0
    
    def show_header(self, step_number: int, title: str, description: str = "", time_remaining: str = "") -> None:
        """Mostra header dello step"""
        self.current_step = step_number
        progress_pct = int((step_number / self.total_steps) * 100)
        bar_filled = int(progress_pct / 5)
        bar = "█" * bar_filled + "░" * (20 - bar_filled)
        
        if self.console:
            self.console.print(Panel(
                f"[bold]Step {step_number}/{self.total_steps}[/bold] {bar} {time_remaining}\n\n"
                f"[bold cyan]{title}[/bold cyan]\n"
                f"[dim]{description}[/dim]",
                border_style="blue",
                title="CHATBOT TESTER - SETUP"
            ))
        else:
            print(f"\n{'='*60}")
            print(f"CHATBOT TESTER - SETUP")
            print(f"Step {step_number}/{self.total_steps} [{bar}] {time_remaining}")
            print(f"\n{title}")
            if description:
                print(f"{description}")
            print(f"{'='*60}\n")
    
    def show_success(self, message: str) -> None:
        """Messaggio successo"""
        if self.console:
            self.console.print(f"[green]✅ {message}[/green]")
        else:
            print(f"✅ {message}")
    
    def show_error(self, message: str) -> None:
        """Messaggio errore"""
        if self.console:
            self.console.print(f"[red]❌ {message}[/red]")
        else:
            print(f"❌ {message}")
    
    def show_warning(self, message: str) -> None:
        """Messaggio warning"""
        if self.console:
            self.console.print(f"[yellow]⚠️ {message}[/yellow]")
        else:
            print(f"⚠️ {message}")
    
    def show_info(self, message: str) -> None:
        """Messaggio informativo"""
        if self.console:
            self.console.print(f"[blue]ℹ️ {message}[/blue]")
        else:
            print(f"ℹ️ {message}")
    
    def show_tip(self, message: str) -> None:
        """Suggerimento"""
        if self.console:
            self.console.print(f"[dim]💡 {message}[/dim]")
        else:
            print(f"💡 {message}")
    
    def ask_input(self, prompt: str, default: str = "") -> str:
        """Chiedi input"""
        if self.console:
            return Prompt.ask(prompt, default=default)
        else:
            if default:
                result = input(f"{prompt} [{default}]: ").strip()
                return result if result else default
            return input(f"{prompt}: ").strip()
    
    def ask_confirm(self, question: str, default: bool = False) -> bool:
        """Chiedi conferma"""
        if self.console:
            return Confirm.ask(question, default=default)
        else:
            suffix = "[Y/n]" if default else "[y/N]"
            response = input(f"{question} {suffix}: ").strip().lower()
            if not response:
                return default
            return response in ['y', 'yes', 's', 'sì', 'si']
    
    def show_options(self, options: List[tuple], prompt: str = "Scelta") -> str:
        """Mostra opzioni e ritorna scelta"""
        print("")
        for key, label, desc in options:
            if self.console:
                if desc:
                    self.console.print(f"  \\[{key}] {label}\n      [dim]{desc}[/dim]")
                else:
                    self.console.print(f"  \\[{key}] {label}")
            else:
                print(f"  [{key}] {label}")
                if desc:
                    print(f"      {desc}")
        print("")
        
        valid_keys = [opt[0] for opt in options]
        while True:
            choice = self.ask_input(prompt)
            if choice in valid_keys:
                return choice
            self.show_warning(f"Opzione non valida: {choice}")
    
    def show_summary(self, settings: dict) -> None:
        """Mostra riepilogo configurazione"""
        if self.console:
            table = Table(title="Riepilogo Configurazione", show_header=True)
            table.add_column("Impostazione", style="cyan")
            table.add_column("Valore")
            
            for key, value in settings.items():
                if isinstance(value, bool):
                    val_str = "✅ Sì" if value else "❌ No"
                elif isinstance(value, list):
                    val_str = ", ".join(str(v) for v in value) or "(vuoto)"
                elif value is None or value == "":
                    val_str = "(non configurato)"
                else:
                    val_str = str(value)
                table.add_row(key, val_str)
            
            self.console.print(table)
        else:
            print("\n--- Riepilogo ---")
            for key, value in settings.items():
                print(f"  {key}: {value}")
    
    def show_spinner(self, message: str):
        """Ritorna context manager per spinner"""
        return SpinnerContext(ConsoleUI(), message)
    
    def show_step(self, step_num: int, title: str, description: str = "", 
                  content: str = "", show_skip: bool = False) -> None:
        """
        Mostra step del wizard.
        
        Args:
            step_num: Numero step corrente
            title: Titolo step
            description: Descrizione
            content: Contenuto principale
            show_skip: Mostra opzione skip
        """
        self.current_step = step_num
        progress_pct = int((step_num / self.total_steps) * 100)
        bar_filled = int(progress_pct / 5)
        bar = "█" * bar_filled + "░" * (20 - bar_filled)
        
        if self.console:
            header_text = (
                f"[bold]Step {step_num}/{self.total_steps}[/bold] {bar}\n\n"
                f"[bold cyan]{title}[/bold cyan]"
            )
            if description:
                header_text += f"\n[dim]{description}[/dim]"
            
            self.console.print(Panel(
                header_text,
                border_style="blue",
                title="CHATBOT TESTER - SETUP"
            ))
            
            if content:
                self.console.print(content)
            
            if show_skip:
                self.console.print("\n[dim]Premi [s] per saltare questo step[/dim]")
        else:
            print(f"\n{'='*60}")
            print(f"CHATBOT TESTER - SETUP")
            print(f"Step {step_num}/{self.total_steps} [{bar}]")
            print(f"\n{title}")
            if description:
                print(f"{description}")
            print(f"{'='*60}")
            if content:
                print(content)
            if show_skip:
                print("\nPremi [s] per saltare questo step")
    
    def show_help(self, help_text: str) -> None:
        """
        Mostra testo di aiuto.
        
        Args:
            help_text: Testo markdown di aiuto
        """
        if self.console:
            self.console.print(Panel(
                Markdown(help_text),
                border_style="green",
                title="💡 Aiuto"
            ))
        else:
            print("\n--- Aiuto ---")
            print(help_text)
            print("-" * 40)
    
    def clear(self) -> None:
        """Pulisce schermo"""
        if self.console:
            self.console.clear()
        else:
            os.system('cls' if os.name == 'nt' else 'clear')


# ==================== FUNZIONI GLOBALI ====================

# Console globale per import diretto
console = Console() if RICH_AVAILABLE else None


def clear_screen() -> None:
    """Pulisce lo schermo"""
    os.system('cls' if os.name == 'nt' else 'clear')


def ask_session_recovery(session_info: dict) -> bool:
    """
    Chiede se riprendere sessione precedente.
    
    Args:
        session_info: Info sulla sessione (step, data, etc.)
    
    Returns:
        True se l'utente vuole continuare
    """
    if console:
        console.print(Panel(
            f"[bold]Trovata sessione precedente[/bold]\n\n"
            f"Step: {session_info.get('current_step', '?')}/{session_info.get('total_steps', '?')}\n"
            f"Ultimo aggiornamento: {session_info.get('last_updated', 'N/A')[:19]}",
            border_style="yellow",
            title="Sessione Precedente"
        ))
        return Confirm.ask("Vuoi continuare da dove eri rimasto?", default=True)
    else:
        print("\n--- Sessione Precedente ---")
        print(f"Step: {session_info.get('current_step', '?')}/{session_info.get('total_steps', '?')}")
        response = input("Vuoi continuare da dove eri rimasto? [Y/n]: ").strip().lower()
        return response != 'n'


def confirm_exit() -> bool:
    """
    Conferma uscita dal wizard.
    
    Returns:
        True se l'utente vuole uscire
    """
    if console:
        return Confirm.ask("[yellow]Vuoi davvero uscire?[/yellow] Il progresso sarà salvato", default=False)
    else:
        response = input("Vuoi davvero uscire? Il progresso sarà salvato [y/N]: ").strip().lower()
        return response in ['y', 'yes', 's', 'sì']


def with_spinner(message: str):
    """
    Decorator per eseguire funzione con spinner.
    
    Usage:
        @with_spinner("Caricamento...")
        def do_something():
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if console:
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    console=console
                ) as progress:
                    progress.add_task(message, total=None)
                    return func(*args, **kwargs)
            else:
                print(f"⏳ {message}...", end="", flush=True)
                result = func(*args, **kwargs)
                print(" fatto")
                return result
        return wrapper
    return decorator


def ask_confirm(question: str, default: bool = False) -> bool:
    """
    Chiede conferma sì/no.
    
    Args:
        question: Domanda da porre
        default: Valore default se l'utente preme solo INVIO
    
    Returns:
        True/False
    """
    if console:
        return Confirm.ask(question, default=default)
    else:
        suffix = "[Y/n]" if default else "[y/N]"
        response = input(f"{question} {suffix}: ").strip().lower()
        if not response:
            return default
        return response in ['y', 'yes', 's', 'sì', 'si']


def ask(prompt: str, default: str = "") -> str:
    """
    Chiede input testuale.
    
    Args:
        prompt: Messaggio prompt
        default: Valore default
    
    Returns:
        Input dell'utente
    """
    if console:
        return Prompt.ask(prompt, default=default)
    else:
        if default:
            result = input(f"{prompt} [{default}]: ").strip()
            return result if result else default
        return input(f"{prompt}: ").strip()


def show_key_value(key: str, value: Any, style: str = "") -> None:
    """
    Mostra coppia chiave-valore.
    
    Args:
        key: Nome chiave
        value: Valore
        style: Stile Rich opzionale
    """
    if console:
        if style:
            console.print(f"  [bold]{key}:[/bold] [{style}]{value}[/{style}]")
        else:
            console.print(f"  [bold]{key}:[/bold] {value}")
    else:
        print(f"  {key}: {value}")


# ==================== SINGLETON ====================

_default_ui: Optional[ConsoleUI] = None


def get_ui(use_colors: bool = True) -> ConsoleUI:
    """Ottiene l'istanza UI globale"""
    global _default_ui
    if _default_ui is None:
        _default_ui = ConsoleUI(use_colors)
    return _default_ui
