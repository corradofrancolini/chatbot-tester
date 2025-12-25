"""
Interface Screen - Group 2: CSS Selectors detection.

Placeholder for Phase 2 implementation.
"""

from typing import Optional

from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Static

from wizard.screens.base import BaseWizardScreen
from wizard.utils import WizardState


class InterfaceScreen(BaseWizardScreen):
    """
    Interface screen for CSS selector detection.

    TODO: Phase 2 implementation will include:
    - Interactive selector detection mode
    - Quick auto-detect mode
    - Manual entry mode
    - Live preview of selected elements
    """

    GROUP_NUMBER = 2
    GROUP_NAME = "Interface"
    GROUP_DESCRIPTION = "Detect CSS selectors for chatbot interaction"
    IS_OPTIONAL = False

    def __init__(self, state: Optional[WizardState] = None) -> None:
        super().__init__(state)

    def _create_content(self) -> Container:
        """Create placeholder content."""
        return Container(
            Static("[bold]CSS Selectors[/bold]", classes="text-primary"),
            Static(""),
            Static(
                "[yellow]This screen will be implemented in Phase 2.[/yellow]"
            ),
            Static(""),
            Static("[dim]Features planned:[/dim]"),
            Static("  - Interactive selector detection"),
            Static("  - Auto-detect common patterns"),
            Static("  - Manual entry mode"),
            Static("  - Live preview"),
            Static(""),
            Static("[dim]Press Continue to proceed with default selectors.[/dim]"),
            id="form-container",
        )

    def validate(self) -> bool:
        """Always valid for now (placeholder)."""
        return True

    def save_state(self) -> None:
        """Save placeholder state."""
        # Set default selectors for now
        if not self.state.selectors:
            self.state.selectors = {
                "textarea": "textarea",
                "submit_button": "button[type='submit']",
                "bot_messages": ".bot-message",
                "thread_container": ".chat-thread",
            }
        self.state.mark_step_complete(4)
