"""
Finalize Screen - Group 4: Test import and summary.

Placeholder for Phase 4 implementation.
"""

from typing import Optional

from textual.app import ComposeResult
from textual.containers import Container, Vertical
from textual.widgets import Static

from wizard.screens.base import BaseWizardScreen, PreviewPanel
from wizard.utils import WizardState


class FinalizeScreen(BaseWizardScreen):
    """
    Finalize screen for test import and configuration summary.

    TODO: Phase 4 implementation will include:
    - Test import from various sources (file, URL, template)
    - DataTable preview of tests
    - Full configuration summary
    - Save and launch options
    """

    GROUP_NUMBER = 4
    GROUP_NAME = "Finalize"
    GROUP_DESCRIPTION = "Import tests and complete setup"
    IS_OPTIONAL = False

    def __init__(self, state: Optional[WizardState] = None) -> None:
        super().__init__(state)

    def _create_content(self) -> Container:
        """Create finalize content."""
        return Container(
            # Test Import Section
            Static("[bold]Test Import[/bold]", classes="text-primary"),
            Static("[dim]Import or create test cases[/dim]"),
            Static(""),
            Static("[yellow]Test import - Phase 4 implementation[/yellow]"),
            Static(""),
            Static("[dim]Features planned:[/dim]"),
            Static("  - Import from JSON/CSV/Excel"),
            Static("  - Import from Google Sheets"),
            Static("  - Create from template"),
            Static("  - Manual test creation"),
            Static(""),

            # Summary Section
            Static("[bold]Configuration Summary[/bold]", classes="text-primary"),
            Static(""),
            self._create_summary(),

            id="form-container",
        )

    def _create_summary(self) -> Container:
        """Create configuration summary."""
        return Container(
            Vertical(
                Static(f"[dim]Project:[/dim] {self.state.project_name or 'Not set'}"),
                Static(f"[dim]URL:[/dim] {self.state.chatbot_url or 'Not set'}"),
                Static(f"[dim]Login:[/dim] {'Required' if self.state.requires_login else 'Not required'}"),
                Static(f"[dim]Tests:[/dim] {len(self.state.tests) if self.state.tests else 0} test(s)"),
                Static(""),
                Static("[dim]Google Sheets:[/dim] " + ("Configured" if self.state.sheets_enabled else "Skipped")),
                Static("[dim]LangSmith:[/dim] " + ("Configured" if self.state.langsmith_enabled else "Skipped")),
                Static("[dim]Ollama:[/dim] " + ("Configured" if self.state.ollama_enabled else "Skipped")),
                id="summary-content",
            ),
            classes="preview-panel",
        )

    def validate(self) -> bool:
        """Validate before finalizing."""
        if not self.state.project_name:
            self.notify("Project name is required", severity="error")
            return False

        if not self.state.chatbot_url:
            self.notify("Chatbot URL is required", severity="error")
            return False

        return True

    def save_state(self) -> None:
        """Save final state."""
        self.state.mark_step_complete(9)   # Test Import
        self.state.mark_step_complete(10)  # Summary

    def action_continue_action(self) -> None:
        """Override to complete wizard instead of advancing."""
        if self.validate():
            self.save_state()
            # This will trigger the finalization in the app
            self.app._finalize()
