"""
UI Module - CLI interface with Rich

Handles:
- Formatted output with colors
- Progress bar
- Tables and panels
- Interactive input
- Selection menus
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
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn, TimeRemainingColumn, ProgressColumn
    from rich.text import Text as RichText
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
    """Predefined styles"""
    SUCCESS = "green"
    ERROR = "red"
    WARNING = "yellow"
    INFO = "dim"
    MUTED = "dim"
    HIGHLIGHT = "bold"


@dataclass
class MenuItem:
    """Menu item"""
    key: str
    label: str
    description: str = ""
    disabled: bool = False
    recommended: bool = False


class ConsoleUI:
    """
    Console interface with Rich.

    Fallback to print() if Rich not available.

    Usage:
        ui = ConsoleUI()
        ui.header("Title")
        ui.success("Operation completed!")

        choice = ui.menu([
            MenuItem("1", "Option 1"),
            MenuItem("2", "Option 2")
        ])
    """

    def __init__(self, use_colors: bool = True, quiet: bool = False):
        """
        Initialize the console.

        Args:
            use_colors: Enable colors (default True, auto-detect TTY)
            quiet: Minimal output (default False)
        """
        import os
        import sys

        self.quiet = quiet

        # TTY detection (clig.dev compliant)
        is_tty = sys.stdout.isatty()
        no_color_env = os.environ.get('NO_COLOR')
        term_dumb = os.environ.get('TERM', '').lower() == 'dumb'

        # Disable colors if: not TTY, NO_COLOR set, TERM=dumb, or explicit
        if not is_tty or no_color_env or term_dumb:
            use_colors = False

        self.use_colors = use_colors and RICH_AVAILABLE
        self.is_tty = is_tty

        if self.use_colors:
            self.console = Console()
        else:
            self.console = None

    # ==================== BASE OUTPUT ====================

    def print(self, message: str, style: Optional[str] = None) -> None:
        """Print message"""
        if self.console:
            self.console.print(message, style=style)
        else:
            print(message)

    def success(self, message: str) -> None:
        """Success message"""
        self.print(f"✓ {message}", UIStyle.SUCCESS.value)

    def error(self, message: str) -> None:
        """Error message"""
        self.print(f"✗ {message}", UIStyle.ERROR.value)

    def warning(self, message: str) -> None:
        """Warning message"""
        self.print(f"! {message}", UIStyle.WARNING.value)

    def info(self, message: str) -> None:
        """Informational message"""
        self.print(f"> {message}", UIStyle.INFO.value)

    def muted(self, message: str) -> None:
        """Secondary text"""
        self.print(message, UIStyle.MUTED.value)

    # ==================== STRUCTURES ====================

    def header(self, title: str, subtitle: str = "") -> None:
        """Main app header (with light box)"""
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
        """Section header (minimal)"""
        if self.console:
            self.console.print(f"\n[bold]{title}[/bold]")
        else:
            print(f"\n{title}")

    def divider(self) -> None:
        """Divider line"""
        if self.console:
            self.console.rule(style="dim")
        else:
            print("-" * 40)

    # ==================== TABLES ====================

    def table(self,
              headers: List[str],
              rows: List[List[str]],
              title: str = "") -> None:
        """Print table"""
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
        """Statistics row"""
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
                     description: str = "Progress") -> 'ProgressContext':
        """
        Create progress bar.

        Usage:
            with ui.progress_bar(100) as progress:
                for i in range(100):
                    progress.advance()
        """
        return ProgressContext(self, total, description)

    def spinner(self, message: str) -> 'SpinnerContext':
        """
        Create spinner for long operations.

        Usage:
            with ui.spinner("Loading..."):
                do_something()
        """
        return SpinnerContext(self, message)

    # ==================== INPUT ====================

    def input(self,
              prompt: str,
              default: str = "",
              password: bool = False) -> str:
        """Text input"""
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
        """Yes/no confirmation"""
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
        Selection menu.

        Args:
            items: Options list
            prompt: Prompt message
            allow_back: Show "back" option

        Returns:
            Selected option key or None if back
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
            self.print("  b    Back", UIStyle.MUTED.value)

        self.print("")

        # Get input
        valid_keys = [i.key for i in items if not i.disabled]
        if allow_back:
            valid_keys.extend(['b', 'back'])

        while True:
            choice = self.input(prompt).strip()

            if choice in valid_keys:
                if choice in ['b', 'back']:
                    return None
                return choice

            self.warning(f"Invalid option: {choice}")

    def select_multiple(self,
                        items: List[MenuItem],
                        prompt: str = "Select (comma-separated) >") -> List[str]:
        """
        Multiple selection.

        Returns:
            List of selected keys
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
        """Header for wizard step"""
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
        """Wizard configuration summary"""
        self.print("\n[bold]Summary[/bold]\n" if self.console else "\nSummary\n")

        # Calculate max key width for alignment
        max_key_len = max(len(k) for k in settings.keys()) if settings else 0

        for key, value in settings.items():
            # Format value
            if isinstance(value, bool):
                val_str = "yes" if value else "no"
            elif isinstance(value, list):
                val_str = ", ".join(str(v) for v in value) if value else "-"
            elif value is None or value == "":
                val_str = "-"
            else:
                val_str = str(value)

            self.print(f"  {key:<{max_key_len}}  {val_str}")

    # ==================== SPECIAL MESSAGES ====================

    def error_panel(self,
                    error_type: str,
                    detail: str,
                    solutions: List[str]) -> None:
        """Error panel with solutions"""
        if self.console:
            self.console.print(f"\n[red]✗ Error: {error_type}[/red]")
            self.console.print(f"  [dim]{detail}[/dim]")

            if solutions:
                self.console.print(f"\n  [bold]Solutions:[/bold]")
                for s in solutions:
                    self.console.print(f"  · {s}")
        else:
            print(f"\n✗ Error: {error_type}")
            print(f"  {detail}")

            if solutions:
                print(f"\n  Solutions:")
                for s in solutions:
                    print(f"  · {s}")

    def help_text(self, text: str) -> None:
        """Help text"""
        if self.console:
            self.console.print(f"[dim]{text}[/dim]")
        else:
            print(f"  {text}")

    def clear(self) -> None:
        """Clear the screen"""
        if self.console:
            self.console.clear()
        else:
            print("\033[H\033[J", end="")


class SpeedColumn(ProgressColumn):
    """Custom column showing tests/minute speed"""

    def render(self, task) -> RichText:
        """Render speed as tests/min"""
        elapsed = task.elapsed
        if elapsed and elapsed > 0 and task.completed > 0:
            speed = (task.completed / elapsed) * 60  # tests per minute
            return RichText(f"{speed:.1f} test/min", style="cyan")
        return RichText("-- test/min", style="dim")


class PhaseColumn(ProgressColumn):
    """Custom column showing current phase"""

    def render(self, task) -> RichText:
        """Render current phase"""
        phase = task.fields.get("phase", "")
        if phase:
            return RichText(f"[{phase}]", style="yellow")
        return RichText("")


class ProgressContext:
    """Context manager for enhanced progress bar with ETA, speed, and phase"""

    def __init__(self, ui: ConsoleUI, total: int, description: str):
        self.ui = ui
        self.total = total
        self.description = description
        self.current = 0
        self._progress = None
        self._task = None
        self._phase = ""

    def __enter__(self):
        if self.ui.console:
            self._progress = Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                TextColumn("•"),
                TimeElapsedColumn(),
                TextColumn("/"),
                TimeRemainingColumn(),
                TextColumn("•"),
                SpeedColumn(),
                PhaseColumn(),
                console=self.ui.console,
                refresh_per_second=2
            )
            self._progress.start()
            self._task = self._progress.add_task(self.description, total=self.total, phase="")
        return self

    def __exit__(self, *args):
        if self._progress:
            self._progress.stop()

    def advance(self, amount: int = 1) -> None:
        """Advance the progress bar"""
        self.current += amount
        if self._progress and self._task is not None:
            self._progress.advance(self._task, amount)
        elif not self.ui.console:
            pct = int(self.current / self.total * 100)
            print(f"\r{self.description}: {pct}%", end="", flush=True)
            if self.current >= self.total:
                print()

    def update(self, description: str = None, phase: str = None) -> None:
        """Update description and/or phase"""
        if self._progress and self._task is not None:
            updates = {}
            if description is not None:
                updates["description"] = description
            if phase is not None:
                self._phase = phase
                updates["phase"] = phase
            if updates:
                self._progress.update(self._task, **updates)

    def set_phase(self, phase: str) -> None:
        """Set current phase (e.g., 'sending', 'waiting', 'screenshot')"""
        self.update(phase=phase)


class SpinnerContext:
    """Context manager for spinner"""

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
            print(" done")

    def update(self, message: str) -> None:
        """Update message"""
        if self._progress and self._task is not None:
            self._progress.update(self._task, description=message)


# ==================== WIZARD UI ====================

class WizardUI:
    """
    UI specific for setup wizard.
    Provides methods for step navigation, progress, guided input.
    """

    def __init__(self, total_steps: int = 9):
        self.console = Console() if RICH_AVAILABLE else None
        self.total_steps = total_steps
        self.current_step = 0

    def show_header(self, step_number: int, title: str, description: str = "", time_remaining: str = "") -> None:
        """Show step header"""
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
        """Success message"""
        if self.console:
            self.console.print(f"[green]✓ {message}[/green]")
        else:
            print(f"✓ {message}")

    def show_error(self, title: str, details: str = "", solutions: list = None) -> str:
        """
        Error message with recovery options.

        Args:
            title: Error title
            details: Error details (optional)
            solutions: List of suggested solutions (optional)

        Returns:
            'r' for retry, 's' for skip, 'q' for quit
        """
        if self.console:
            self.console.print(f"\n[red]✗ Error: {title}[/red]")
            if details:
                self.console.print(f"  [dim]{details}[/dim]")
            if solutions:
                self.console.print("\n  [yellow]Suggested solutions:[/yellow]")
                for sol in solutions:
                    self.console.print(f"    • {sol}")
            self.console.print("\n  [dim][r] Retry  [s] Skip  [q] Quit[/dim]")
        else:
            print(f"\n✗ Error: {title}")
            if details:
                print(f"  {details}")
            if solutions:
                print("\n  Suggested solutions:")
                for sol in solutions:
                    print(f"    • {sol}")
            print("\n  [r] Retry  [s] Skip  [q] Quit")

        while True:
            choice = input("  Choice: ").strip().lower()
            if choice in ['r', 's', 'q']:
                return choice
            print("  Enter r, s, or q")

    def show_warning(self, message: str) -> None:
        """Warning message"""
        if self.console:
            self.console.print(f"[yellow]! {message}[/yellow]")
        else:
            print(f"! {message}")

    def show_info(self, message: str) -> None:
        """Informational message"""
        if self.console:
            self.console.print(f"[blue]> {message}[/blue]")
        else:
            print(f"> {message}")

    def show_tip(self, message: str) -> None:
        """Tip/suggestion"""
        if self.console:
            self.console.print(f"[dim]~ {message}[/dim]")
        else:
            print(f"~ {message}")

    def ask_input(self, prompt: str, default: str = "") -> str:
        """Ask for input"""
        if self.console:
            return Prompt.ask(prompt, default=default)
        else:
            if default:
                result = input(f"{prompt} [{default}]: ").strip()
                return result if result else default
            return input(f"{prompt}: ").strip()

    def ask_confirm(self, question: str, default: bool = False) -> bool:
        """Ask for confirmation"""
        if self.console:
            return Confirm.ask(question, default=default)
        else:
            suffix = "[Y/n]" if default else "[y/N]"
            response = input(f"{question} {suffix}: ").strip().lower()
            if not response:
                return default
            return response in ['y', 'yes', 's', 'sì', 'si']

    def show_options(self, options: List[tuple], prompt: str = ">") -> str:
        """Show options and return choice"""
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
            self.show_warning(f"Invalid option: {choice}")

    def show_summary(self, settings: dict) -> None:
        """Show configuration summary"""
        if self.console:
            self.console.print("\n[bold]Summary[/bold]\n")
        else:
            print("\nSummary\n")

        # Calculate max key width for alignment
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
        """Return context manager for spinner"""
        return SpinnerContext(ConsoleUI(), message)

    def show_step(self, step_num: int, title: str, description: str = "",
                  content: str = "", show_skip: bool = False) -> None:
        """
        Show wizard step.

        Args:
            step_num: Current step number
            title: Step title
            description: Description
            content: Main content
            show_skip: Show skip option
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
                self.console.print("[dim]      s to skip[/dim]")
        else:
            print(f"\n[{step_num}/{self.total_steps}] {title}")
            if description:
                print(f"      {description}")
            if content:
                print(content)
            if show_skip:
                print("      s to skip")

    def show_help(self, help_text: str) -> None:
        """
        Show help text.

        Args:
            help_text: Help text
        """
        if self.console:
            self.console.print(f"\n[bold]Help[/bold]")
            self.console.print(f"[dim]{help_text}[/dim]")
        else:
            print(f"\nHelp")
            print(f"  {help_text}")

    def clear(self) -> None:
        """Clear screen"""
        if self.console:
            self.console.clear()
        else:
            os.system('cls' if os.name == 'nt' else 'clear')


# ==================== GLOBAL FUNCTIONS ====================

# Global console for direct import
console = Console() if RICH_AVAILABLE else None


def clear_screen() -> None:
    """Clear the screen"""
    os.system('cls' if os.name == 'nt' else 'clear')


def ask_session_recovery(session_info: dict) -> bool:
    """
    Ask whether to resume previous session.

    Args:
        session_info: Session info (step, data, etc.)

    Returns:
        True if user wants to continue
    """
    step = session_info.get('current_step', '?')
    total = session_info.get('total_steps', '?')

    if console:
        console.print(f"\n> Previous session found (step {step}/{total})")
        return Confirm.ask("  Continue?", default=True)
    else:
        print(f"\n> Previous session found (step {step}/{total})")
        response = input("  Continue? [Y/n]: ").strip().lower()
        return response != 'n'


def confirm_exit() -> bool:
    """
    Confirm exit from wizard.

    Returns:
        True if user wants to exit
    """
    if console:
        return Confirm.ask("Exit? Progress will be saved", default=False)
    else:
        response = input("Exit? Progress will be saved [y/N]: ").strip().lower()
        return response in ['y', 'yes', 's', 'sì']


def with_spinner(message: str):
    """
    Decorator to execute function with spinner.

    Usage:
        @with_spinner("Loading...")
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
    Ask yes/no confirmation.

    Args:
        question: Question to ask
        default: Default value if user only presses ENTER

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
    Ask for text input.

    Args:
        prompt: Prompt message
        default: Default value

    Returns:
        User input
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
    Show key-value pair.

    Args:
        key: Key name
        value: Value
        style: Optional Rich style
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
    Get global UI instance.

    Args:
        use_colors: Enable colors (auto-detect TTY if True)
        quiet: Minimal output (errors only)
    """
    global _default_ui
    if _default_ui is None:
        _default_ui = ConsoleUI(use_colors, quiet)
    return _default_ui


def reset_ui() -> None:
    """Reset UI instance (useful for testing)"""
    global _default_ui
    _default_ui = None
