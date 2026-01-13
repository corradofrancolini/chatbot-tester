"""
Wizard App - New Textual-based setup wizard.

This is the main entry point for the new wizard UI.
Uses Textual for a modern, reactive TUI experience.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, TYPE_CHECKING
from datetime import datetime

if TYPE_CHECKING:
    from wizard.screens.welcome import WelcomeScreen

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.reactive import reactive
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import Static, Footer, Header, Button
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
        self._current_content = None

    def compose(self) -> ComposeResult:
        """Create the app layout."""
        yield Header()
        yield Container(
            ProgressSidebar(
                current=self.current_group,
                completed=self.completed_groups,
                id="sidebar",
            ),
            VerticalScroll(id="main-content"),
            id="main-container",
        )
        yield self._create_button_bar()
        yield Footer()

    def _create_button_bar(self) -> Container:
        """Create the bottom navigation bar."""
        return Horizontal(
            Button("Back", id="btn-back", variant="default"),
            Button("Skip", id="btn-skip", variant="warning"),
            Button("Continue", id="btn-continue", variant="primary"),
            id="button-bar",
        )

    async def on_mount(self) -> None:
        """Called when app is mounted - show welcome screen."""
        # Initialize empty state
        self.state = WizardState()

        # Run prerequisites check in background
        self.run_worker(self._check_prerequisites())

        # Show welcome screen first
        await self._show_welcome()

    async def _show_welcome(self) -> None:
        """Show the welcome/project selection screen."""
        from wizard.screens.welcome import WelcomeScreen

        # Hide sidebar and buttons for welcome screen
        self.query_one("#sidebar").display = False
        self.query_one("#button-bar").display = False

        # Mount welcome screen
        scroll_container = self.query_one("#main-content", VerticalScroll)
        if self._current_content:
            await self._current_content.remove()

        welcome = WelcomeScreen()
        self._current_content = welcome
        await scroll_container.mount(welcome)

    def on_welcome_screen_project_selected(
        self, event: "WelcomeScreen.ProjectSelected"
    ) -> None:
        """Handle project selection from welcome screen."""
        from wizard.screens.welcome import WelcomeScreen

        if event.is_new:
            # New project - start fresh
            self.state = WizardState()
            self.state.started_at = datetime.utcnow().isoformat()
        else:
            # Existing project - load its config
            self.project_name = event.project_name
            self.state_manager = StateManager(event.project_name)
            self.state = self._load_existing_project(event.project_name)

        self._start_wizard()

    def on_welcome_screen_resume_session(self, event) -> None:
        """Handle resume session from welcome screen."""
        # Load the incomplete session
        self.state = self.state_manager.load()
        self.current_group = self._map_step_to_group(self.state.current_step)
        self.completed_groups = self._get_completed_groups()
        self._start_wizard()

    def _load_existing_project(self, project_name: str) -> WizardState:
        """Load state from an existing project's config."""
        from wizard.utils import load_project_config

        state = WizardState()
        state.project_name = project_name

        # Load existing project.yaml
        config = load_project_config(project_name)
        if config:
            state.project_description = config.get("description", "")
            state.chatbot_url = config.get("chatbot_url", "")
            state.requires_login = config.get("requires_login", False)
            state.selectors = config.get("selectors", {})
            state.google_sheets_enabled = config.get("google_sheets", {}).get("enabled", False)
            state.langsmith_enabled = config.get("langsmith", {}).get("enabled", False)
            state.ollama_enabled = config.get("ollama", {}).get("enabled", False)

        return state

    def _start_wizard(self) -> None:
        """Start the wizard (show sidebar, buttons, first screen)."""
        # Show sidebar and buttons
        self.query_one("#sidebar").display = True
        self.query_one("#button-bar").display = True

        # Update UI
        self._update_sidebar()
        self._update_buttons()

        # Show first group
        self.run_worker(self._show_group(self.current_group))

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
        """Show the content for the specified group."""
        # Import content lazily
        if group == WizardGroup.FOUNDATION:
            from wizard.screens.foundation import FoundationScreen
            content = FoundationScreen(self.state)
        elif group == WizardGroup.INTERFACE:
            from wizard.screens.interface import InterfaceScreen
            content = InterfaceScreen(self.state)
        elif group == WizardGroup.INTEGRATIONS:
            from wizard.screens.integrations import IntegrationsScreen
            content = IntegrationsScreen(self.state)
        elif group == WizardGroup.FINALIZE:
            from wizard.screens.finalize import FinalizeScreen
            content = FinalizeScreen(self.state)
        else:
            return

        # Get scroll container
        scroll_container = self.query_one("#main-content", VerticalScroll)

        # Remove old content
        if self._current_content:
            await self._current_content.remove()

        # Mount new content directly into scroll container
        self._current_content = content
        await scroll_container.mount(content)

        # Scroll to top and refresh
        scroll_container.scroll_home(animate=False)
        self.refresh()

        # Update sidebar
        self._update_sidebar()
        self._update_buttons()

    def _update_sidebar(self) -> None:
        """Update the sidebar to reflect current state."""
        try:
            sidebar = self.query_one("#sidebar", ProgressSidebar)
            sidebar.current = self.current_group
            sidebar.completed = self.completed_groups
        except Exception:
            pass  # Sidebar not yet mounted

    def _update_buttons(self) -> None:
        """Update button visibility based on current group."""
        try:
            btn_back = self.query_one("#btn-back", Button)
            btn_skip = self.query_one("#btn-skip", Button)

            # Hide back on first group
            btn_back.display = self.current_group > 1

            # Show skip only on optional groups
            btn_skip.display = self.current_group in WizardGroup.OPTIONAL
        except Exception:
            pass

    def watch_current_group(self, group: int) -> None:
        """React to group changes."""
        self._update_sidebar()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-back":
            self.action_go_back()
        elif event.button.id == "btn-skip":
            self.action_skip_group()
        elif event.button.id == "btn-continue":
            self.action_continue()

    def action_continue(self) -> None:
        """Continue to next group."""
        if self._current_content:
            # Validate and save
            if hasattr(self._current_content, 'validate'):
                if not self._current_content.validate():
                    return

            if hasattr(self._current_content, 'save_state'):
                self._current_content.save_state()

            # Save state
            self.state_manager.save(self.state)

        # Advance
        self.advance_to_next_group()

    def action_skip_group(self) -> None:
        """Skip current optional group."""
        if self.current_group in WizardGroup.OPTIONAL:
            self.advance_to_next_group()

    def action_save_and_exit(self) -> None:
        """Save state and exit."""
        if self.state:
            if self._current_content and hasattr(self._current_content, 'save_state'):
                self._current_content.save_state()
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
        self.notify("Tab: navigate | Enter: confirm | Escape: back | Ctrl+S: save & exit")

    def advance_to_next_group(self) -> None:
        """Called when current group is completed."""
        # Mark current as completed
        completed = set(self.completed_groups)
        completed.add(self.current_group)
        self.completed_groups = completed

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
                Button("[Y] Yes, quit", id="btn-yes", variant="error"),
                Button("[N] No, continue", id="btn-no", variant="primary"),
                id="quit-buttons",
            ),
            id="quit-dialog",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-yes":
            self.action_confirm_quit()
        else:
            self.action_cancel_quit()

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
