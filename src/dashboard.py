"""
Dashboard Multi-Panel - Interface à la lazygit

A modern TUI dashboard that shows all features at a glance with inline shortcuts.
"""

import sys
import tty
import termios
import select
from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple, Any, Callable
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.live import Live
from rich.align import Align
from rich import box


# ============================================================================
# ENUMS AND CONSTANTS
# ============================================================================

class PanelType(Enum):
    """Panel types for focus navigation"""
    PROJECTS = auto()
    STATUS = auto()
    ACTIONS = auto()
    RUNS = auto()


# Shortcuts registry - maps shortcut to (action_name, description)
SHORTCUTS = {
    # Run
    "r": ("run", "Run tests"),
    "c": ("continue", "Continue run"),
    "s": ("stop", "Stop current"),
    # Analysis
    "cmp": ("compare", "Compare runs"),
    "reg": ("regressions", "Regressions"),
    "flk": ("flaky", "Flaky tests"),
    "cov": ("coverage", "Coverage"),
    "stb": ("stability", "Stability"),
    "prf": ("performance", "Performance"),
    "cal": ("calibrate", "Calibration"),
    # Tools
    "exp": ("export", "Export"),
    "cld": ("cloud", "Cloud"),
    "fin": ("finetune", "Finetuning"),
    "prm": ("prompts", "Prompts"),
    "dgn": ("diagnose", "Diagnose"),
    "lst": ("list", "List runs"),
    # Settings
    "lng": ("language", "Language"),
    "ntf": ("notifications", "Notifications"),
    "brw": ("browser", "Browser"),
    "log": ("logging", "Logging"),
    # Navigation
    "n": ("new_project", "New project"),
    "?": ("help", "Help"),
    "q": ("quit", "Quit"),
}

# Actions organized by category for display
ACTIONS_BY_CATEGORY = {
    "RUN": [
        ("r", "Run tests"),
        ("c", "Continue"),
        ("s", "Stop"),
    ],
    "ANALYSIS": [
        ("cmp", "Compare runs"),
        ("reg", "Regressions"),
        ("flk", "Flaky tests"),
        ("cov", "Coverage"),
        ("stb", "Stability"),
        ("prf", "Performance"),
        ("cal", "Calibration"),
    ],
    "TOOLS": [
        ("exp", "Export"),
        ("cld", "Cloud"),
        ("fin", "Finetuning"),
        ("prm", "Prompts"),
        ("dgn", "Diagnose"),
        ("lst", "List runs"),
    ],
    "SETTINGS": [
        ("lng", "Language"),
        ("ntf", "Notifications"),
        ("brw", "Browser"),
        ("log", "Logging"),
    ],
}


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class ServiceHealth:
    """Health status of a service"""
    name: str
    status: str  # "ok", "error", "disabled"
    latency_ms: Optional[int] = None
    error_msg: Optional[str] = None


@dataclass
class RunInfo:
    """Information about current run"""
    run_number: int
    project: str
    environment: str
    mode: str
    total_tests: int
    completed: int
    passed: int
    failed: int
    started_at: datetime
    eta_minutes: Optional[int] = None


@dataclass
class RunSummary:
    """Summary of a completed run"""
    run_number: int
    project: str
    date: datetime
    total_tests: int
    passed: int
    failed: int
    duration_minutes: int
    status: str  # "complete", "running", "regressions", "failed"


@dataclass
class DashboardState:
    """Central state for the dashboard"""
    # Projects
    projects: List[str] = field(default_factory=list)
    selected_project: Optional[str] = None
    project_index: int = 0

    # Navigation
    focused_panel: PanelType = PanelType.PROJECTS
    run_index: int = 0  # Selected row in runs panel

    # Status
    services: List[ServiceHealth] = field(default_factory=list)
    current_run: Optional[RunInfo] = None

    # Recent runs
    recent_runs: List[RunSummary] = field(default_factory=list)

    # Terminal
    terminal_size: Tuple[int, int] = (80, 24)

    # Input
    input_buffer: str = ""
    show_help: bool = False

    # Messages
    status_message: str = ""
    error_message: str = ""


# ============================================================================
# KEYBOARD HANDLER
# ============================================================================

class KeyboardHandler:
    """Non-blocking keyboard input handler"""

    def __init__(self):
        self.fd = sys.stdin.fileno()
        self.old_settings = None

    def start(self):
        """Enter raw mode for keyboard capture"""
        self.old_settings = termios.tcgetattr(self.fd)
        tty.setraw(self.fd)

    def stop(self):
        """Restore terminal settings"""
        if self.old_settings:
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old_settings)

    def get_key(self, timeout: float = 0.1) -> Optional[str]:
        """Get key press with timeout (non-blocking)"""
        rlist, _, _ = select.select([sys.stdin], [], [], timeout)
        if rlist:
            ch = sys.stdin.read(1)
            # Handle escape sequences (arrows, etc.)
            if ch == '\x1b':
                # Check for more characters
                rlist2, _, _ = select.select([sys.stdin], [], [], 0.01)
                if rlist2:
                    ch2 = sys.stdin.read(1)
                    if ch2 == '[':
                        ch3 = sys.stdin.read(1)
                        if ch3 == 'A': return 'UP'
                        if ch3 == 'B': return 'DOWN'
                        if ch3 == 'C': return 'RIGHT'
                        if ch3 == 'D': return 'LEFT'
                        if ch3 == 'Z': return 'SHIFT_TAB'
                return 'ESC'
            elif ch == '\t':
                return 'TAB'
            elif ch == '\r' or ch == '\n':
                return 'ENTER'
            elif ch == '\x7f' or ch == '\x08':
                return 'BACKSPACE'
            elif ch == '\x03':  # Ctrl+C
                return 'CTRL_C'
            return ch
        return None


# ============================================================================
# PANEL BUILDERS
# ============================================================================

class ProjectsPanel:
    """Projects panel with selection"""

    def __init__(self, state: DashboardState):
        self.state = state

    def render(self, focused: bool = False) -> Panel:
        """Render projects panel"""
        content = []

        for i, project in enumerate(self.state.projects):
            is_selected = i == self.state.project_index
            prefix = "▸ " if is_selected else "  "
            number = f"[{i+1}]" if i < 9 else "   "

            if is_selected:
                line = Text(f"{prefix}{project}", style="bold cyan")
                line.append(f"  {number}", style="dim")
            else:
                line = Text(f"{prefix}{project}", style="white")
                line.append(f"  {number}", style="dim")

            content.append(line)

        # Add separator and actions
        if content:
            content.append(Text(""))
            content.append(Text("─" * 18, style="dim"))
        content.append(Text("[n] New project", style="dim cyan"))
        content.append(Text("[↵] Open selected", style="dim cyan"))

        # Join all content
        text = Text("\n").join(content) if content else Text("No projects", style="dim")

        border_style = "cyan bold" if focused else "dim"
        return Panel(
            text,
            title="PROJECTS",
            border_style=border_style,
            box=box.ROUNDED,
            padding=(0, 1)
        )


class StatusPanel:
    """Status panel showing services and current run"""

    def __init__(self, state: DashboardState):
        self.state = state

    def render(self, focused: bool = False) -> Panel:
        """Render status panel"""
        # Create two-column layout
        table = Table.grid(padding=(0, 2))
        table.add_column("services", justify="left")
        table.add_column("run", justify="left")

        # Services column
        services_text = Text()
        services_text.append("Services\n", style="bold white")
        services_text.append("─" * 24 + "\n", style="dim")

        for svc in self.state.services:
            if svc.status == "ok":
                icon = "✓"
                style = "green"
                extra = f" ({svc.latency_ms}ms)" if svc.latency_ms else ""
            elif svc.status == "error":
                icon = "✗"
                style = "red"
                extra = f" {svc.error_msg}" if svc.error_msg else ""
            else:  # disabled
                icon = "○"
                style = "dim"
                extra = " Not configured"

            services_text.append(f"{icon} ", style=style)
            services_text.append(f"{svc.name}", style="white")
            services_text.append(f"{extra}\n", style="dim")

        services_text.append("\n")

        # System status
        if self.state.error_message:
            services_text.append("System: ", style="white")
            services_text.append("Error ●", style="red bold")
        else:
            services_text.append("System: ", style="white")
            services_text.append("Ready ●", style="green")

        # Run column
        run_text = Text()
        run_text.append("Current Run\n", style="bold white")
        run_text.append("─" * 30 + "\n", style="dim")

        if self.state.current_run:
            run = self.state.current_run
            pct = (run.completed / run.total_tests * 100) if run.total_tests > 0 else 0
            rate = (run.passed / run.completed * 100) if run.completed > 0 else 0

            run_text.append(f"Project:  ", style="dim")
            run_text.append(f"{run.project}\n", style="cyan bold")
            run_text.append(f"RUN:      ", style="dim")
            run_text.append(f"{run.run_number}  ", style="white bold")
            run_text.append(f"ENV: {run.environment}\n", style="dim")
            run_text.append(f"Mode:     {run.mode}\n\n", style="dim")

            # Progress bar
            filled = int(pct / 5)  # 20 chars width
            bar = "█" * filled + "░" * (20 - filled)
            run_text.append(f"Progress: ", style="dim")
            run_text.append(bar, style="cyan")
            run_text.append(f" {run.completed}/{run.total_tests}\n", style="white")

            # Stats
            run_text.append(f"Pass: ", style="dim")
            run_text.append(f"{run.passed}", style="green")
            run_text.append(f"  Fail: ", style="dim")
            run_text.append(f"{run.failed}", style="red")
            run_text.append(f"  Rate: ", style="dim")
            rate_style = "green" if rate >= 90 else ("yellow" if rate >= 70 else "red")
            run_text.append(f"{rate:.1f}%\n", style=rate_style)

            # Timing
            started = run.started_at.strftime("%H:%M")
            run_text.append(f"Started: {started}", style="dim")
            if run.eta_minutes:
                eta = (run.started_at.replace(minute=run.started_at.minute + run.eta_minutes))
                run_text.append(f"  ETA: ~{eta.strftime('%H:%M')}", style="dim")
        else:
            run_text.append("\nNo active run.\n\n", style="dim")
            run_text.append("Press ", style="dim")
            run_text.append("[r]", style="cyan bold")
            run_text.append(" to start tests", style="dim")

        table.add_row(services_text, run_text)

        border_style = "cyan bold" if focused else "dim"
        return Panel(
            table,
            title="STATUS",
            border_style=border_style,
            box=box.ROUNDED,
            padding=(0, 1)
        )


class ActionsPanel:
    """Actions panel with shortcut grid"""

    def __init__(self, state: DashboardState):
        self.state = state

    def render(self, focused: bool = False, compact: bool = False) -> Panel:
        """Render actions panel"""
        if compact:
            return self._render_compact(focused)
        return self._render_full(focused)

    def _render_full(self, focused: bool) -> Panel:
        """Full 4-column layout"""
        table = Table.grid(padding=(0, 3))
        for _ in range(4):
            table.add_column(justify="left", min_width=20)

        # Headers
        headers = list(ACTIONS_BY_CATEGORY.keys())
        header_row = []
        for h in headers:
            text = Text(h, style="bold white underline")
            header_row.append(text)
        table.add_row(*header_row)

        # Find max rows needed
        max_rows = max(len(actions) for actions in ACTIONS_BY_CATEGORY.values())

        # Build rows
        for i in range(max_rows):
            row = []
            for cat in headers:
                actions = ACTIONS_BY_CATEGORY[cat]
                if i < len(actions):
                    shortcut, label = actions[i]
                    text = Text()
                    text.append(f"[{shortcut}]", style="cyan bold")
                    text.append(f" {label}", style="white")
                    row.append(text)
                else:
                    row.append(Text(""))
            table.add_row(*row)

        border_style = "cyan bold" if focused else "dim"
        return Panel(
            table,
            title="ACTIONS",
            border_style=border_style,
            box=box.ROUNDED,
            padding=(0, 1)
        )

    def _render_compact(self, focused: bool) -> Panel:
        """Compact single-row layout"""
        text = Text()
        all_actions = []
        for cat, actions in ACTIONS_BY_CATEGORY.items():
            all_actions.extend(actions[:3])  # First 3 per category

        for i, (shortcut, label) in enumerate(all_actions):
            if i > 0:
                text.append("  ", style="dim")
            text.append(f"[{shortcut}]", style="cyan bold")
            text.append(f" {label[:8]}", style="white")  # Truncate label

        border_style = "cyan bold" if focused else "dim"
        return Panel(
            text,
            title="ACTIONS",
            border_style=border_style,
            box=box.ROUNDED,
            padding=(0, 1)
        )


class RecentRunsPanel:
    """Recent runs table panel"""

    def __init__(self, state: DashboardState):
        self.state = state

    def render(self, focused: bool = False, compact: bool = False) -> Panel:
        """Render recent runs panel"""
        table = Table(
            box=box.SIMPLE,
            show_header=True,
            header_style="bold white",
            padding=(0, 1)
        )

        if compact:
            table.add_column("#", style="dim", width=4)
            table.add_column("Project", width=12)
            table.add_column("Date", width=8)
            table.add_column("Tests", width=8)
            table.add_column("Rate", width=6)
            table.add_column("", width=10)  # Status
        else:
            table.add_column("#", style="dim", width=5)
            table.add_column("Project", width=15)
            table.add_column("Date", width=14)
            table.add_column("Tests", width=10)
            table.add_column("Pass", width=6)
            table.add_column("Fail", width=6)
            table.add_column("Rate", width=8)
            table.add_column("Duration", width=10)
            table.add_column("Status", width=12)

        for i, run in enumerate(self.state.recent_runs[:5]):  # Show last 5
            is_selected = i == self.state.run_index
            row_style = "reverse" if is_selected and focused else None

            # Format date
            now = datetime.now()
            if run.date.date() == now.date():
                date_str = run.date.strftime("Today %H:%M")
            elif (now - run.date).days == 1:
                date_str = "Yesterday"
            else:
                date_str = run.date.strftime("%b %d")

            # Rate with color
            rate = (run.passed / run.total_tests * 100) if run.total_tests > 0 else 0
            rate_style = "green" if rate >= 90 else ("yellow" if rate >= 70 else "red")
            rate_text = Text(f"{rate:.1f}%", style=rate_style)

            # Status with icon
            status_icons = {
                "complete": ("✓", "green"),
                "running": ("←", "cyan"),
                "regressions": ("⚠", "yellow"),
                "failed": ("✗", "red"),
            }
            icon, style = status_icons.get(run.status, ("?", "dim"))
            status_text = Text(f"{icon} {run.status}", style=style)

            if compact:
                table.add_row(
                    str(run.run_number),
                    run.project[:12],
                    date_str[:8],
                    str(run.total_tests),
                    rate_text,
                    status_text,
                    style=row_style
                )
            else:
                table.add_row(
                    str(run.run_number),
                    run.project,
                    date_str,
                    str(run.total_tests),
                    str(run.passed),
                    str(run.failed),
                    rate_text,
                    f"{run.duration_minutes}m",
                    status_text,
                    style=row_style
                )

        if not self.state.recent_runs:
            if compact:
                table.add_row("", "No runs yet", "", "", "", "")
            else:
                table.add_row("", "No runs yet", "", "", "", "", "", "", "")

        # Footer with actions
        footer = Text()
        footer.append("\n[Enter]", style="cyan bold")
        footer.append(" View  ", style="dim")
        footer.append("[d]", style="cyan bold")
        footer.append(" Delete  ", style="dim")
        footer.append("[e]", style="cyan bold")
        footer.append(" Export  ", style="dim")
        footer.append("[↑↓]", style="cyan bold")
        footer.append(" Navigate", style="dim")

        content = Table.grid()
        content.add_row(table)
        content.add_row(footer)

        border_style = "cyan bold" if focused else "dim"
        return Panel(
            content,
            title="RECENT RUNS",
            border_style=border_style,
            box=box.ROUNDED,
            padding=(0, 1)
        )


class HelpOverlay:
    """Help overlay panel"""

    @staticmethod
    def render(compact: bool = False) -> Panel:
        """Render help overlay"""
        if compact:
            return HelpOverlay._render_compact()
        return HelpOverlay._render_full()

    @staticmethod
    def _render_full() -> Panel:
        """Full help overlay"""
        table = Table.grid(padding=(0, 4))
        table.add_column(justify="left", min_width=35)
        table.add_column(justify="left", min_width=35)

        # Navigation column
        nav_text = Text()
        nav_text.append("NAVIGATION\n", style="bold cyan underline")
        nav_text.append("──────────\n", style="dim")
        nav_text.append("Tab        ", style="cyan bold")
        nav_text.append("Next panel\n", style="white")
        nav_text.append("Shift+Tab  ", style="cyan bold")
        nav_text.append("Previous panel\n", style="white")
        nav_text.append("j / ↓      ", style="cyan bold")
        nav_text.append("Next item\n", style="white")
        nav_text.append("k / ↑      ", style="cyan bold")
        nav_text.append("Previous item\n", style="white")
        nav_text.append("h / ←      ", style="cyan bold")
        nav_text.append("Panel left\n", style="white")
        nav_text.append("l / →      ", style="cyan bold")
        nav_text.append("Panel right\n", style="white")
        nav_text.append("Enter      ", style="cyan bold")
        nav_text.append("Select / Confirm\n", style="white")
        nav_text.append("Esc        ", style="cyan bold")
        nav_text.append("Cancel / Back\n", style="white")
        nav_text.append("q          ", style="cyan bold")
        nav_text.append("Quit\n", style="white")
        nav_text.append("?          ", style="cyan bold")
        nav_text.append("This help\n\n", style="white")

        nav_text.append("PROJECTS\n", style="bold cyan underline")
        nav_text.append("────────\n", style="dim")
        nav_text.append("1-9        ", style="cyan bold")
        nav_text.append("Select project by number\n", style="white")
        nav_text.append("n          ", style="cyan bold")
        nav_text.append("New project (wizard)\n", style="white")
        nav_text.append("Enter      ", style="cyan bold")
        nav_text.append("Open selected project\n", style="white")

        # Shortcuts column
        shortcut_text = Text()
        shortcut_text.append("RUN\n", style="bold cyan underline")
        shortcut_text.append("───\n", style="dim")
        shortcut_text.append("r          ", style="cyan bold")
        shortcut_text.append("Run tests\n", style="white")
        shortcut_text.append("c          ", style="cyan bold")
        shortcut_text.append("Continue run (pending tests)\n", style="white")
        shortcut_text.append("s          ", style="cyan bold")
        shortcut_text.append("Stop current run\n\n", style="white")

        shortcut_text.append("ANALYSIS\n", style="bold cyan underline")
        shortcut_text.append("────────\n", style="dim")
        shortcut_text.append("cmp        ", style="cyan bold")
        shortcut_text.append("Compare two runs\n", style="white")
        shortcut_text.append("reg        ", style="cyan bold")
        shortcut_text.append("Show regressions\n", style="white")
        shortcut_text.append("flk        ", style="cyan bold")
        shortcut_text.append("Detect flaky tests\n", style="white")
        shortcut_text.append("cov        ", style="cyan bold")
        shortcut_text.append("Coverage analysis\n", style="white")
        shortcut_text.append("stb        ", style="cyan bold")
        shortcut_text.append("Stability report\n", style="white")
        shortcut_text.append("prf        ", style="cyan bold")
        shortcut_text.append("Performance metrics\n", style="white")
        shortcut_text.append("cal        ", style="cyan bold")
        shortcut_text.append("Calibrate thresholds\n\n", style="white")

        shortcut_text.append("TOOLS\n", style="bold cyan underline")
        shortcut_text.append("─────\n", style="dim")
        shortcut_text.append("exp        ", style="cyan bold")
        shortcut_text.append("Export report\n", style="white")
        shortcut_text.append("cld        ", style="cyan bold")
        shortcut_text.append("Cloud execution\n", style="white")
        shortcut_text.append("fin        ", style="cyan bold")
        shortcut_text.append("Finetuning menu\n", style="white")
        shortcut_text.append("prm        ", style="cyan bold")
        shortcut_text.append("Prompt manager\n", style="white")
        shortcut_text.append("dgn        ", style="cyan bold")
        shortcut_text.append("Diagnose failures\n", style="white")
        shortcut_text.append("lst        ", style="cyan bold")
        shortcut_text.append("List all runs\n", style="white")

        table.add_row(nav_text, shortcut_text)

        footer = Text("\n\nPress any key to close this help...", style="dim italic")
        footer = Align.center(footer)

        content = Table.grid()
        content.add_row(Align.center(table))
        content.add_row(footer)

        return Panel(
            content,
            title="KEYBOARD SHORTCUTS",
            border_style="cyan bold",
            box=box.DOUBLE,
            padding=(1, 2)
        )

    @staticmethod
    def _render_compact() -> Panel:
        """Compact help for small terminals"""
        text = Text()
        text.append("NAVIGATION              SHORTCUTS\n", style="bold cyan")
        text.append("Tab    Next panel       r     Run tests      cmp   Compare\n", style="white")
        text.append("j/k    Up/Down          c     Continue       reg   Regressions\n", style="white")
        text.append("Enter  Select           n     New project    flk   Flaky tests\n", style="white")
        text.append("q      Quit             exp   Export         cal   Calibrate\n", style="white")
        text.append("?      Help             lng   Language       dgn   Diagnose\n", style="white")
        text.append("\n", style="white")
        text.append("Press any key to close", style="dim italic")

        return Panel(
            Align.center(text),
            title="HELP",
            border_style="cyan bold",
            box=box.DOUBLE,
            padding=(1, 2)
        )


# ============================================================================
# MAIN DASHBOARD
# ============================================================================

class Dashboard:
    """Main dashboard controller"""

    def __init__(self, config_loader=None):
        self.console = Console()
        self.state = DashboardState()
        self.keyboard = KeyboardHandler()
        self.config_loader = config_loader

        # Panels
        self.projects_panel = ProjectsPanel(self.state)
        self.status_panel = StatusPanel(self.state)
        self.actions_panel = ActionsPanel(self.state)
        self.runs_panel = RecentRunsPanel(self.state)

        # Load initial data
        self._load_projects()
        self._load_services()
        self._load_recent_runs()

    def _load_projects(self):
        """Load projects from config"""
        if self.config_loader:
            try:
                self.state.projects = self.config_loader.list_projects()
                if self.state.projects:
                    self.state.selected_project = self.state.projects[0]
            except Exception as e:
                self.state.error_message = f"Error loading projects: {e}"
                self.state.projects = []

    def _load_services(self):
        """Load services health status"""
        # Default services - will be updated by health check
        self.state.services = [
            ServiceHealth("Ollama", "disabled"),
            ServiceHealth("LangSmith", "disabled"),
            ServiceHealth("Google Sheets", "disabled"),
            ServiceHealth("Chatbot URL", "disabled"),
        ]

    def _load_recent_runs(self):
        """Load recent runs from sheets or local storage"""
        # Placeholder - will be populated from sheets/local storage
        self.state.recent_runs = []

    def _update_terminal_size(self):
        """Update terminal size in state"""
        size = self.console.size
        self.state.terminal_size = (size.width, size.height)

    def _is_compact(self) -> bool:
        """Check if terminal is compact"""
        w, h = self.state.terminal_size
        return w < 100 or h < 30

    def _build_layout(self) -> Layout:
        """Build responsive layout using ratios for flexibility"""
        self._update_terminal_size()
        compact = self._is_compact()
        w, h = self.state.terminal_size

        # Focus states
        projects_focused = self.state.focused_panel == PanelType.PROJECTS
        status_focused = self.state.focused_panel == PanelType.STATUS
        actions_focused = self.state.focused_panel == PanelType.ACTIONS
        runs_focused = self.state.focused_panel == PanelType.RUNS

        # Build all panel content
        header = self._build_header()
        projects = self.projects_panel.render(focused=projects_focused)
        status = self.status_panel.render(focused=status_focused)
        actions = self.actions_panel.render(focused=actions_focused, compact=compact)
        runs = self.runs_panel.render(focused=runs_focused, compact=compact)
        footer = self._build_footer()

        # Build top section (projects + status) first
        top_layout = Layout(name="top")
        projects_width = 20 if compact else 28
        top_layout.split_row(
            Layout(projects, name="projects", size=projects_width),
            Layout(status, name="status")
        )

        # Build main layout
        layout = Layout(name="root")
        layout.split_column(
            Layout(header, name="header", size=3),
            Layout(top_layout, name="top_section", ratio=2),
            Layout(actions, name="actions", ratio=1),
            Layout(runs, name="runs", ratio=2),
            Layout(footer, name="footer", size=3)
        )

        return layout

    def _build_header(self) -> Panel:
        """Build header panel"""
        text = Text()
        text.append(" CHATBOT TESTER", style="bold cyan")
        text.append(" v1.4.0", style="dim")

        if self.state.selected_project:
            text.append("  │  ", style="dim")
            text.append(self.state.selected_project, style="bold white")

        if self.state.status_message:
            text.append("  │  ", style="dim")
            text.append(self.state.status_message, style="yellow")

        if self.state.input_buffer:
            text.append("  │  ", style="dim")
            text.append(f">{self.state.input_buffer}", style="cyan bold")

        return Panel(
            text,
            box=box.ROUNDED,
            border_style="cyan",
            padding=(0, 1)
        )

    def _build_footer(self) -> Panel:
        """Build footer with shortcuts"""
        text = Text()
        text.append("[Tab]", style="cyan bold")
        text.append(" Panel  ", style="dim")
        text.append("[1-9]", style="cyan bold")
        text.append(" Project  ", style="dim")
        text.append("[j/k]", style="cyan bold")
        text.append(" Navigate  ", style="dim")
        text.append("[r]", style="cyan bold")
        text.append(" Run  ", style="dim")
        text.append("[cmp]", style="cyan bold")
        text.append(" Compare  ", style="dim")
        text.append("[?]", style="cyan bold")
        text.append(" Help  ", style="dim")
        text.append("[q]", style="cyan bold")
        text.append(" Quit", style="dim")

        if self.state.selected_project:
            project_text = f"  {self.state.selected_project}"
            text.append(project_text, style="cyan")

        return Panel(text, box=box.SIMPLE, padding=(0, 0))

    def _handle_input(self, key: str) -> Optional[str]:
        """
        Handle keyboard input.

        Returns:
            - None: Continue running
            - "quit": Exit dashboard
            - action name: Execute action and continue/exit as appropriate
        """
        if self.state.show_help:
            # Any key closes help
            self.state.show_help = False
            return None

        # Handle special keys
        if key == 'CTRL_C' or key == 'q':
            return "quit"

        if key == '?':
            self.state.show_help = True
            return None

        if key == 'ESC':
            self.state.input_buffer = ""
            return None

        if key == 'BACKSPACE':
            if self.state.input_buffer:
                self.state.input_buffer = self.state.input_buffer[:-1]
            return None

        # Navigation keys
        if key == 'TAB':
            self._next_panel()
            return None

        if key == 'SHIFT_TAB' or key == 'h' or key == 'LEFT':
            self._prev_panel()
            return None

        if key == 'l' or key == 'RIGHT':
            self._next_panel()
            return None

        if key == 'j' or key == 'DOWN':
            self._navigate_down()
            return None

        if key == 'k' or key == 'UP':
            self._navigate_up()
            return None

        if key == 'ENTER':
            return self._handle_enter()

        # Number keys for project selection
        if key.isdigit() and key != '0':
            idx = int(key) - 1
            if idx < len(self.state.projects):
                self.state.project_index = idx
                self.state.selected_project = self.state.projects[idx]
                return None

        # Build up multi-char shortcuts
        if key.isalpha() or key.isdigit():
            self.state.input_buffer += key.lower()

            # Check for exact match
            if self.state.input_buffer in SHORTCUTS:
                action = SHORTCUTS[self.state.input_buffer][0]
                self.state.input_buffer = ""
                return action

            # Check for possible matches
            possible = [s for s in SHORTCUTS if s.startswith(self.state.input_buffer)]
            if not possible:
                # No matches, check if single char is a shortcut
                if len(self.state.input_buffer) == 1:
                    single = self.state.input_buffer
                    if single in SHORTCUTS:
                        action = SHORTCUTS[single][0]
                        self.state.input_buffer = ""
                        return action
                self.state.input_buffer = ""

        return None

    def _next_panel(self):
        """Move to next panel"""
        panels = list(PanelType)
        idx = panels.index(self.state.focused_panel)
        self.state.focused_panel = panels[(idx + 1) % len(panels)]

    def _prev_panel(self):
        """Move to previous panel"""
        panels = list(PanelType)
        idx = panels.index(self.state.focused_panel)
        self.state.focused_panel = panels[(idx - 1) % len(panels)]

    def _navigate_down(self):
        """Navigate down in current panel"""
        if self.state.focused_panel == PanelType.PROJECTS:
            if self.state.project_index < len(self.state.projects) - 1:
                self.state.project_index += 1
                self.state.selected_project = self.state.projects[self.state.project_index]
        elif self.state.focused_panel == PanelType.RUNS:
            if self.state.run_index < len(self.state.recent_runs) - 1:
                self.state.run_index += 1

    def _navigate_up(self):
        """Navigate up in current panel"""
        if self.state.focused_panel == PanelType.PROJECTS:
            if self.state.project_index > 0:
                self.state.project_index -= 1
                self.state.selected_project = self.state.projects[self.state.project_index]
        elif self.state.focused_panel == PanelType.RUNS:
            if self.state.run_index > 0:
                self.state.run_index -= 1

    def _handle_enter(self) -> Optional[str]:
        """Handle enter key"""
        if self.state.focused_panel == PanelType.PROJECTS:
            if self.state.projects:
                self.state.selected_project = self.state.projects[self.state.project_index]
                self.state.status_message = f"Selected: {self.state.selected_project}"
        elif self.state.focused_panel == PanelType.RUNS:
            if self.state.recent_runs:
                run = self.state.recent_runs[self.state.run_index]
                return f"view_run:{run.run_number}"
        return None

    def run(self) -> Optional[str]:
        """
        Main dashboard loop.

        Returns:
            - None: User quit
            - action name: Execute this action
        """
        self.keyboard.start()
        result = None

        try:
            with Live(self._build_layout(), console=self.console,
                      refresh_per_second=4, screen=True) as live:
                while True:
                    # Check for input
                    key = self.keyboard.get_key(timeout=0.1)

                    if key:
                        action = self._handle_input(key)

                        if action == "quit":
                            break
                        elif action:
                            # Return action to execute
                            result = action
                            break

                    # Update display
                    if self.state.show_help:
                        live.update(HelpOverlay.render(compact=self._is_compact()))
                    else:
                        live.update(self._build_layout())

        finally:
            self.keyboard.stop()

        return result


# ============================================================================
# ENTRY POINT
# ============================================================================

def run_dashboard(config_loader=None) -> Optional[str]:
    """
    Run the dashboard and return the selected action.

    Args:
        config_loader: Optional ConfigLoader instance

    Returns:
        Action to execute, or None if user quit
    """
    dashboard = Dashboard(config_loader)
    return dashboard.run()


if __name__ == "__main__":
    # Test run
    action = run_dashboard()
    if action:
        print(f"Action selected: {action}")
