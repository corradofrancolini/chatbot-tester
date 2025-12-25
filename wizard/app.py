"""
Wizard App - New Textual-based setup wizard.

This is the main entry point for the new wizard UI.
Uses Textual for a modern, reactive TUI experience.
"""

from pathlib import Path
from typing import Optional
from datetime import datetime

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.reactive import reactive
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Static, Footer, Header
from textual.screen import Screen

from wizard.utils import WizardState, StateManager
from wizard.widgets.sidebar import ProgressSidebar


class WizardGroup:
    """Represents a wizard group (consolidated step)."""

    FOUNDATION = 1      # Project + URL
    INTERFACE = 2       # Selectors
    INTEGRATIONS = 3    # Google Sheets, LangSmith, Ollama
    FINALIZE = 4        # Tests + Summary

    NAMES = {
        1: "Foundation",
        2: "Interface",
        3: "Integrations",
        4: "Finalize",
    }

    DESCRIPTIONS = {
        1: "Project name and chatbot URL",
        2: "CSS selectors detection",
        3: "Optional integrations",
        4: "Import tests and finish",
    }

    REQUIRED = {1, 2, 4}  # Groups 1, 2, 4 are required
    OPTIONAL = {3}         # Group 3 is optional


class WizardApp(App):
    """
    Main Textual App for the setup wizard.

    Features:
    - 4 consolidated groups (from original 10 steps)
    - Sidebar with progress
    - Non-linear navigation
    - Session recovery
    - Live validation
    """

    CSS_PATH = "styles.tcss"

    TITLE = "Chatbot Tester Setup"
    SUB_TITLE = "Configuration Wizard"

    BINDINGS = [
        Binding("ctrl+s", "save_and_exit", "Save & Exit"),
        Binding("ctrl+q", "quit_wizard", "Quit"),
        Binding("f1", "show_help", "Help"),
        Binding("escape", "go_back", "Back"),
    ]

    # Reactive state
    current_group: reactive[int] = reactive(1)
    completed_groups: reactive[set] = reactive(set)

    def __init__(
        self,
        language: str = "it",
        project_name: str = "",
        legacy_mode: bool = False,
    ):
        """
        Initialize the wizard app.

        Args:
            language: 'it' or 'en'
            project_name: Optional project name for reconfiguration
            legacy_mode: If True, use old Rich-based wizard
        """
        super().__init__()
        self.language = language
        self.project_name = project_name
        self.legacy_mode = legacy_mode

        # State management
        self.state_manager = StateManager(project_name)
        self.state: Optional[WizardState] = None

    def compose(self) -> ComposeResult:
        """Create the app layout."""
        yield Header()
        yield Container(
            self._create_sidebar(),
            self._create_main_content(),
            id="main-container",
        )
        yield Footer()

    def _create_sidebar(self) -> Container:
        """Create the progress sidebar."""
        return ProgressSidebar(
            current=self.current_group,
            completed=self.completed_groups,
            id="sidebar",
        )

    def _create_main_content(self) -> Container:
        """Create the main content area placeholder."""
        return Container(
            Static("Loading...", id="content-placeholder"),
            id="main-content",
        )

    async def on_mount(self) -> None:
        """Called when app is mounted - initialize state and show first screen."""
        # Check for existing session
        if self.state_manager.has_previous_session():
            self.state = self.state_manager.load()
            # Map old step number to new group
            self.current_group = self._map_step_to_group(self.state.current_step)
            self.completed_groups = self._get_completed_groups()
        else:
            self.state = self.state_manager.load()
            if not self.state.started_at:
                self.state.started_at = datetime.utcnow().isoformat()

        # Run prerequisites check in background
        self.run_worker(self._check_prerequisites())

        # Show first screen
        await self._show_group(self.current_group)

    def _map_step_to_group(self, step: int) -> int:
        """Map old step number (1-10) to new group (1-4)."""
        if step <= 3:
            return WizardGroup.FOUNDATION
        elif step == 4:
            return WizardGroup.INTERFACE
        elif step <= 8:
            return WizardGroup.INTEGRATIONS
        else:
            return WizardGroup.FINALIZE

    def _get_completed_groups(self) -> set:
        """Get set of completed groups based on state."""
        completed = set()
        for step in self.state.completed_steps:
            group = self._map_step_to_group(step)
            # A group is complete when all its steps are done
            if group == WizardGroup.FOUNDATION and {2, 3}.issubset(self.state.completed_steps):
                completed.add(group)
            elif group == WizardGroup.INTERFACE and 4 in self.state.completed_steps:
                completed.add(group)
            elif group == WizardGroup.INTEGRATIONS and {5, 6, 7, 8}.issubset(self.state.completed_steps):
                completed.add(group)
            elif group == WizardGroup.FINALIZE and {9, 10}.issubset(self.state.completed_steps):
                completed.add(group)
        return completed

    async def _check_prerequisites(self) -> None:
        """Background check for prerequisites."""
        from wizard.utils import check_prerequisites
        issues = check_prerequisites()
        if issues:
            self.notify(
                f"Prerequisites check found {len(issues)} issue(s)",
                severity="warning",
            )

    async def _show_group(self, group: int) -> None:
        """Show the screen for the specified group."""
        # Import screens lazily
        if group == WizardGroup.FOUNDATION:
            from wizard.screens.foundation import FoundationScreen
            await self.push_screen(FoundationScreen(self.state))
        elif group == WizardGroup.INTERFACE:
            from wizard.screens.interface import InterfaceScreen
            await self.push_screen(InterfaceScreen(self.state))
        elif group == WizardGroup.INTEGRATIONS:
            from wizard.screens.integrations import IntegrationsScreen
            await self.push_screen(IntegrationsScreen(self.state))
        elif group == WizardGroup.FINALIZE:
            from wizard.screens.finalize import FinalizeScreen
            await self.push_screen(FinalizeScreen(self.state))

    def watch_current_group(self, group: int) -> None:
        """React to group changes."""
        # Update sidebar (only if it exists - not during initial compose)
        try:
            sidebar = self.query_one("#sidebar", ProgressSidebar)
            sidebar.current = group
        except Exception:
            pass  # Sidebar not yet mounted

    def action_save_and_exit(self) -> None:
        """Save state and exit."""
        if self.state:
            self.state_manager.save(self.state)
            self.notify("Progress saved. Resume anytime.")
        self.exit(return_code=0)

    def action_quit_wizard(self) -> None:
        """Quit without saving (with confirmation)."""
        self.push_screen(ConfirmQuitScreen())

    def action_go_back(self) -> None:
        """Go to previous group."""
        if self.current_group > 1:
            self.current_group -= 1
            self.run_worker(self._show_group(self.current_group))

    def action_show_help(self) -> None:
        """Show help for current context."""
        self.notify("Press Tab to navigate, Enter to confirm, Escape to go back")

    def advance_to_next_group(self) -> None:
        """Called when current group is completed."""
        self.completed_groups.add(self.current_group)
        if self.current_group < 4:
            self.current_group += 1
            self.run_worker(self._show_group(self.current_group))
        else:
            self._finalize()

    def _finalize(self) -> None:
        """Complete the wizard."""
        from wizard.utils import ensure_project_dirs, save_project_config, save_tests

        # Save configuration
        ensure_project_dirs(self.state.project_name)
        save_project_config(self.state)

        if self.state.tests:
            save_tests(self.state.project_name, self.state.tests)

        # Clear wizard state
        self.state_manager.clear()

        self.notify("Setup complete!", severity="information")
        self.exit(return_code=0)


class ConfirmQuitScreen(Screen):
    """Confirmation screen for quitting."""

    BINDINGS = [
        Binding("y", "confirm_quit", "Yes"),
        Binding("n", "cancel_quit", "No"),
        Binding("escape", "cancel_quit", "Cancel"),
    ]

    def compose(self) -> ComposeResult:
        yield Container(
            Static("Are you sure you want to quit?", id="quit-message"),
            Static("Your progress will NOT be saved.", id="quit-warning"),
            Horizontal(
                Static("[Y] Yes, quit"),
                Static("[N] No, continue"),
                id="quit-buttons",
            ),
            id="quit-dialog",
        )

    def action_confirm_quit(self) -> None:
        self.app.exit(return_code=1)

    def action_cancel_quit(self) -> None:
        self.app.pop_screen()


def run_textual_wizard(
    language: str = "it",
    project_name: str = "",
) -> bool:
    """
    Run the new Textual-based wizard.

    Args:
        language: 'it' or 'en'
        project_name: Optional project name

    Returns:
        True if completed successfully
    """
    app = WizardApp(language=language, project_name=project_name)
    result = app.run()
    return result == 0


if __name__ == "__main__":
    run_textual_wizard()
