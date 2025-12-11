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
    INFO = "dim"
    MUTED = "dim"
    HIGHLIGHT = "bold"


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

    def __init__(self, use_colors: bool = True, quiet: bool = False):
        """
        Inizializza la console.

        Args:
            use_colors: Abilita colori (default True, auto-detect TTY)
            quiet: Output minimo (default False)
        """
        import os
        import sys

        self.quiet = quiet

        # TTY detection (clig.dev compliant)
        is_tty = sys.stdout.isatty()
        no_color_env = os.environ.get('NO_COLOR')
        term_dumb = os.environ.get('TERM', '').lower() == 'dumb'

        # Disabilita colori se: non TTY, NO_COLOR set, TERM=dumb, o esplicito
        if not is_tty or no_color_env or term_dumb:
            use_colors = False

        self.use_colors = use_colors and RICH_AVAILABLE
        self.is_tty = is_tty

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
        self.print(f"✓ {message}", UIStyle.SUCCESS.value)

    def error(self, message: str) -> None:
        """Messaggio di errore"""
        self.print(f"✗ {message}", UIStyle.ERROR.value)

    def warning(self, message: str) -> None:
        """Messaggio di warning"""
        self.print(f"! {message}", UIStyle.WARNING.value)

    def info(self, message: str) -> None:
        """Messaggio informativo"""
        self.print(f"> {message}", UIStyle.INFO.value)

    def muted(self, message: str) -> None:
        """Testo secondario"""
        self.print(message, UIStyle.MUTED.value)

    # ==================== STRUTTURE ====================

    def header(self, title: str, subtitle: str = "") -> None:
        """Header principale app (con box leggero)"""
        if self.console:
            content = f"[bold]{title}[/bold]"
            if subtitle:
                content += f"\n[dim]{subtitle}[/dim]"

            self.console.print(Panel(
                content,
                border_style="dim",
                padding=(0, 2)
            ))
        else:
            print(f"\n{title}")
            if subtitle:
                print(f"{subtitle}")
            print()

    def section(self, title: str) -> None:
        """Intestazione sezione (minimal)"""
        if self.console:
            self.console.print(f"\n[bold]{title}[/bold]")
        else:
            print(f"\n{title}")

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
             prompt: str = ">",
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
        self.print("")
        for item in items:
            if item.disabled:
                style = "dim"
            elif item.recommended:
                style = "green"
            else:
                style = None

            # Formato: "  key  Label — Description"
            key_display = item.key
            line = f"  {key_display:4} {item.label}"

            if item.recommended:
                line += " [recommended]"
            elif item.disabled:
                line += " [disabled]"

            if item.description:
                line += f" — {item.description}"

            self.print(line, style)

        if allow_back:
            self.print("  b    Indietro", UIStyle.MUTED.value)

        self.print("")

        # Ottieni input
        valid_keys = [i.key for i in items if not i.disabled]
        if allow_back:
            valid_keys.extend(['b', 'back'])

        while True:
            choice = self.input(prompt).strip()

            if choice in valid_keys:
                if choice in ['b', 'back']:
                    return None
                return choice

            self.warning(f"Opzione non valida: {choice}")

    def select_multiple(self,
                        items: List[MenuItem],
                        prompt: str = "Seleziona (separati da virgola) >") -> List[str]:
        """
        Selezione multipla.

        Returns:
            Lista di keys selezionate
        """
        self.print("")
        for item in items:
            line = f"  {item.key:4} {item.label}"
            if item.description:
                line += f" — {item.description}"
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
        if self.console:
            header = f"[dim][{step_number}/{total_steps}][/dim] [bold]{title}[/bold]"
            if time_estimate:
                header += f" [dim]{time_estimate}[/dim]"
            self.console.print(f"\n{header}")
            if description:
                self.console.print(f"      [dim]{description}[/dim]")
        else:
            header = f"[{step_number}/{total_steps}] {title}"
            if time_estimate:
                header += f" {time_estimate}"
            print(f"\n{header}")
            if description:
                print(f"      {description}")

    def wizard_summary(self, settings: dict) -> None:
        """Riepilogo configurazione wizard"""
        self.print("\n[bold]Riepilogo[/bold]\n" if self.console else "\nRiepilogo\n")

        # Calcola larghezza massima chiave per allineamento
        max_key_len = max(len(k) for k in settings.keys()) if settings else 0

        for key, value in settings.items():
            # Formatta valore
            if isinstance(value, bool):
                val_str = "yes" if value else "no"
            elif isinstance(value, list):
                val_str = ", ".join(str(v) for v in value) if value else "-"
            elif value is None or value == "":
                val_str = "-"
            else:
                val_str = str(value)

            self.print(f"  {key:<{max_key_len}}  {val_str}")

    # ==================== MESSAGGI SPECIALI ====================

    def error_panel(self,
                    error_type: str,
                    detail: str,
                    solutions: List[str]) -> None:
        """Pannello errore con soluzioni"""
        if self.console:
            self.console.print(f"\n[red]✗ Errore: {error_type}[/red]")
            self.console.print(f"  [dim]{detail}[/dim]")

            if solutions:
                self.console.print(f"\n  [bold]Soluzioni:[/bold]")
                for s in solutions:
                    self.console.print(f"  · {s}")
        else:
            print(f"\n✗ Errore: {error_type}")
            print(f"  {detail}")

            if solutions:
                print(f"\n  Soluzioni:")
                for s in solutions:
                    print(f"  · {s}")

    def help_text(self, text: str) -> None:
        """Testo di aiuto"""
        if self.console:
            self.console.print(f"[dim]{text}[/dim]")
        else:
            print(f"  {text}")

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
            print(f"{self.message}...", end="", flush=True)
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

        if self.console:
            header = f"[dim][{step_number}/{self.total_steps}][/dim] [bold]{title}[/bold]"
            if time_remaining:
                header += f" [dim]{time_remaining}[/dim]"
            self.console.print(f"\n{header}")
            if description:
                self.console.print(f"      [dim]{description}[/dim]")
        else:
            header = f"[{step_number}/{self.total_steps}] {title}"
            if time_remaining:
                header += f" {time_remaining}"
            print(f"\n{header}")
            if description:
                print(f"      {description}")

    def show_success(self, message: str) -> None:
        """Messaggio successo"""
        if self.console:
            self.console.print(f"[green]✓ {message}[/green]")
        else:
            print(f"✓ {message}")

    def show_error(self, title: str, details: str = "", solutions: list = None) -> str:
        """
        Messaggio errore con opzioni di recovery.

        Args:
            title: Titolo errore
            details: Dettagli errore (opzionale)
            solutions: Lista soluzioni suggerite (opzionale)

        Returns:
            'r' per retry, 's' per skip, 'q' per quit
        """
        if self.console:
            self.console.print(f"\n[red]✗ Errore: {title}[/red]")
            if details:
                self.console.print(f"  [dim]{details}[/dim]")
            if solutions:
                self.console.print("\n  [yellow]Soluzioni suggerite:[/yellow]")
                for sol in solutions:
                    self.console.print(f"    • {sol}")
            self.console.print("\n  [dim][r] Riprova  [s] Salta  [q] Esci[/dim]")
        else:
            print(f"\n✗ Errore: {title}")
            if details:
                print(f"  {details}")
            if solutions:
                print("\n  Soluzioni suggerite:")
                for sol in solutions:
                    print(f"    • {sol}")
            print("\n  [r] Riprova  [s] Salta  [q] Esci")

        while True:
            choice = input("  Scelta: ").strip().lower()
            if choice in ['r', 's', 'q']:
                return choice
            print("  Inserisci r, s, o q")

    def show_warning(self, message: str) -> None:
        """Messaggio warning"""
        if self.console:
            self.console.print(f"[yellow]! {message}[/yellow]")
        else:
            print(f"! {message}")

    def show_info(self, message: str) -> None:
        """Messaggio informativo"""
        if self.console:
            self.console.print(f"[blue]> {message}[/blue]")
        else:
            print(f"> {message}")

    def show_tip(self, message: str) -> None:
        """Suggerimento"""
        if self.console:
            self.console.print(f"[dim]~ {message}[/dim]")
        else:
            print(f"~ {message}")

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

    def show_options(self, options: List[tuple], prompt: str = ">") -> str:
        """Mostra opzioni e ritorna scelta"""
        print("")
        for key, label, desc in options:
            line = f"  {key:4} {label}"
            if desc:
                line += f" — {desc}"
            if self.console:
                self.console.print(line)
            else:
                print(line)
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
            self.console.print("\n[bold]Riepilogo[/bold]\n")
        else:
            print("\nRiepilogo\n")

        # Calcola larghezza massima chiave per allineamento
        max_key_len = max(len(k) for k in settings.keys()) if settings else 0

        for key, value in settings.items():
            if isinstance(value, bool):
                val_str = "yes" if value else "no"
            elif isinstance(value, list):
                val_str = ", ".join(str(v) for v in value) if value else "-"
            elif value is None or value == "":
                val_str = "-"
            else:
                val_str = str(value)

            line = f"  {key:<{max_key_len}}  {val_str}"
            if self.console:
                self.console.print(line)
            else:
                print(line)

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

        if self.console:
            header = f"[dim][{step_num}/{self.total_steps}][/dim] [bold]{title}[/bold]"
            self.console.print(f"\n{header}")
            if description:
                self.console.print(f"      [dim]{description}[/dim]")

            if content:
                self.console.print(content)

            if show_skip:
                self.console.print("[dim]      s per saltare[/dim]")
        else:
            print(f"\n[{step_num}/{self.total_steps}] {title}")
            if description:
                print(f"      {description}")
            if content:
                print(content)
            if show_skip:
                print("      s per saltare")

    def show_help(self, help_text: str) -> None:
        """
        Mostra testo di aiuto.

        Args:
            help_text: Testo di aiuto
        """
        if self.console:
            self.console.print(f"\n[bold]Aiuto[/bold]")
            self.console.print(f"[dim]{help_text}[/dim]")
        else:
            print(f"\nAiuto")
            print(f"  {help_text}")

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
    step = session_info.get('current_step', '?')
    total = session_info.get('total_steps', '?')

    if console:
        console.print(f"\n> Sessione precedente trovata (step {step}/{total})")
        return Confirm.ask("  Continuare?", default=True)
    else:
        print(f"\n> Sessione precedente trovata (step {step}/{total})")
        response = input("  Continuare? [Y/n]: ").strip().lower()
        return response != 'n'


def confirm_exit() -> bool:
    """
    Conferma uscita dal wizard.

    Returns:
        True se l'utente vuole uscire
    """
    if console:
        return Confirm.ask("Uscire? Il progresso sarà salvato", default=False)
    else:
        response = input("Uscire? Il progresso sarà salvato [y/N]: ").strip().lower()
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
                print(f"{message}...", end="", flush=True)
                result = func(*args, **kwargs)
                print(" done")
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


def get_ui(use_colors: bool = True, quiet: bool = False) -> ConsoleUI:
    """
    Ottiene l'istanza UI globale.

    Args:
        use_colors: Abilita colori (auto-detect TTY se True)
        quiet: Output minimo (solo errori)
    """
    global _default_ui
    if _default_ui is None:
        _default_ui = ConsoleUI(use_colors, quiet)
    return _default_ui


def reset_ui() -> None:
    """Reset UI instance (utile per test)"""
    global _default_ui
    _default_ui = None
