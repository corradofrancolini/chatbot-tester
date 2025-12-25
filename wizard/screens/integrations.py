"""
Integrations Screen - Group 3: Optional service integrations.

Placeholder for Phase 3 implementation.
"""

from typing import Optional

from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Static, TabbedContent, TabPane

from wizard.screens.base import BaseWizardScreen
from wizard.utils import WizardState


class IntegrationsScreen(BaseWizardScreen):
    """
    Integrations screen with tabbed interface.

    TODO: Phase 3 implementation will include:
    - Google Sheets tab (OAuth flow, spreadsheet selection)
    - LangSmith tab (API key, project selection)
    - Ollama tab (installation, model selection, evaluation config)
    """

    GROUP_NUMBER = 3
    GROUP_NAME = "Integrations"
    GROUP_DESCRIPTION = "Configure optional service integrations"
    IS_OPTIONAL = True

    def __init__(self, state: Optional[WizardState] = None) -> None:
        super().__init__(state)

    def _create_content(self) -> Container:
        """Create tabbed content."""
        return Container(
            Static("[bold]Optional Integrations[/bold]", classes="text-primary"),
            Static("[dim]Configure external services for enhanced functionality[/dim]"),
            Static(""),
            TabbedContent(
                TabPane("Google Sheets", self._sheets_content(), id="tab-sheets"),
                TabPane("LangSmith", self._langsmith_content(), id="tab-langsmith"),
                TabPane("Ollama", self._ollama_content(), id="tab-ollama"),
                id="integration-tabs",
            ),
            id="form-container",
        )

    def _sheets_content(self) -> Container:
        """Google Sheets tab content (placeholder)."""
        return Container(
            Static("[yellow]Google Sheets integration - Phase 3[/yellow]"),
            Static(""),
            Static("[dim]Features planned:[/dim]"),
            Static("  - OAuth authentication"),
            Static("  - Spreadsheet selection/creation"),
            Static("  - Automatic result sync"),
            Static(""),
            Static("[dim]Skip this section to configure later.[/dim]"),
        )

    def _langsmith_content(self) -> Container:
        """LangSmith tab content (placeholder)."""
        return Container(
            Static("[yellow]LangSmith integration - Phase 3[/yellow]"),
            Static(""),
            Static("[dim]Features planned:[/dim]"),
            Static("  - API key configuration"),
            Static("  - Project selection"),
            Static("  - Trace collection"),
            Static(""),
            Static("[dim]Skip this section to configure later.[/dim]"),
        )

    def _ollama_content(self) -> Container:
        """Ollama tab content (placeholder)."""
        return Container(
            Static("[yellow]Ollama + Evaluation - Phase 3[/yellow]"),
            Static(""),
            Static("[dim]Features planned:[/dim]"),
            Static("  - Ollama installation check"),
            Static("  - Model selection (Mistral, etc.)"),
            Static("  - Evaluation metrics configuration"),
            Static("  - Score thresholds"),
            Static(""),
            Static("[dim]Skip this section to configure later.[/dim]"),
        )

    def validate(self) -> bool:
        """Always valid (optional group)."""
        return True

    def save_state(self) -> None:
        """Save placeholder state."""
        # Mark all integration steps as complete/skipped
        self.state.mark_step_complete(5)  # Google Sheets
        self.state.mark_step_complete(6)  # LangSmith
        self.state.mark_step_complete(7)  # Ollama
        self.state.mark_step_complete(8)  # Evaluation
