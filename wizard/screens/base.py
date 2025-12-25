"""
Base Wizard Screen - Common functionality for all wizard screens.
"""

from typing import Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.screen import Screen
from textual.widgets import Static, Button

from wizard.utils import WizardState


class BaseWizardScreen(Screen):
    """
    Base class for all wizard screens.

    Provides:
    - Common layout structure
    - Navigation buttons (Back, Skip, Continue)
    - State management
    - Validation framework
    """

    # Override in subclasses
    GROUP_NUMBER: int = 0
    GROUP_NAME: str = ""
    GROUP_DESCRIPTION: str = ""
    IS_OPTIONAL: bool = False

    BINDINGS = [
        Binding("enter", "continue_action", "Continue", priority=True),
        Binding("escape", "back_action", "Back"),
        Binding("s", "skip_action", "Skip", show=False),
    ]

    def __init__(self, state: Optional[WizardState] = None) -> None:
        """
        Initialize the screen.

        Args:
            state: Current wizard state
        """
        super().__init__()
        self.state = state or WizardState()

    def compose(self) -> ComposeResult:
        """Create the screen layout."""
        yield Container(
            # Header
            self._create_header(),
            # Main content (scrollable)
            ScrollableContainer(
                self._create_content(),
                id="screen-content",
            ),
            # Button bar
            self._create_button_bar(),
            id="screen-container",
        )

    def _create_header(self) -> Container:
        """Create the screen header."""
        badge = "[yellow]OPTIONAL[/yellow]" if self.IS_OPTIONAL else "[red]REQUIRED[/red]"
        return Container(
            Static(
                f"[bold]{self.GROUP_NUMBER}. {self.GROUP_NAME}[/bold] {badge}",
                classes="content-title",
            ),
            Static(self.GROUP_DESCRIPTION, classes="content-description"),
            id="screen-header",
        )

    def _create_content(self) -> Container:
        """
        Create the main content area.

        Override this in subclasses to add form fields.
        """
        return Container(
            Static("Content goes here", id="placeholder-content"),
            id="form-container",
        )

    def _create_button_bar(self) -> Container:
        """Create the bottom button bar."""
        buttons = []

        # Back button (always shown except on first screen)
        if self.GROUP_NUMBER > 1:
            buttons.append(
                Button("Back", id="btn-back", classes="ghost", variant="default")
            )

        # Skip button (only for optional groups)
        if self.IS_OPTIONAL:
            buttons.append(
                Button("Skip Section", id="btn-skip", classes="warning", variant="warning")
            )

        # Continue button (always shown)
        buttons.append(
            Button("Continue", id="btn-continue", classes="primary", variant="primary")
        )

        return Horizontal(*buttons, classes="button-bar")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button clicks."""
        if event.button.id == "btn-back":
            self.action_back_action()
        elif event.button.id == "btn-skip":
            self.action_skip_action()
        elif event.button.id == "btn-continue":
            self.action_continue_action()

    def action_continue_action(self) -> None:
        """Continue to next group (override for validation)."""
        if self.validate():
            self.save_state()
            self.app.advance_to_next_group()

    def action_back_action(self) -> None:
        """Go back to previous group."""
        self.app.pop_screen()

    def action_skip_action(self) -> None:
        """Skip this optional group."""
        if self.IS_OPTIONAL:
            self.app.advance_to_next_group()

    def validate(self) -> bool:
        """
        Validate all form fields.

        Override in subclasses to implement validation.

        Returns:
            True if valid, False otherwise
        """
        return True

    def save_state(self) -> None:
        """
        Save form data to wizard state.

        Override in subclasses to save specific fields.
        """
        pass

    def load_state(self) -> None:
        """
        Load existing data from wizard state.

        Override in subclasses to populate fields.
        """
        pass

    def on_mount(self) -> None:
        """Called when screen is mounted."""
        self.load_state()


class PreviewPanel(Container):
    """
    Preview panel showing current configuration summary.

    Used at the bottom of screens to show what's been configured.
    """

    def __init__(self, title: str = "Preview", **kwargs) -> None:
        super().__init__(**kwargs)
        self.title = title
        self.add_class("preview-panel")

    def compose(self) -> ComposeResult:
        yield Static(self.title, classes="preview-title")
        yield Vertical(id="preview-content")

    def update_preview(self, items: dict) -> None:
        """
        Update preview with key-value pairs.

        Args:
            items: Dict of label -> value
        """
        content = self.query_one("#preview-content", Vertical)
        content.remove_children()

        for label, value in items.items():
            if value:
                content.mount(
                    Static(f"[dim]{label}:[/dim] {value}", classes="preview-item")
                )
