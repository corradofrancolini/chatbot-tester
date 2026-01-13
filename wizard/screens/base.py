"""
Base Wizard Screen - Common functionality for all wizard screens.
"""

from typing import Optional

from textual.app import ComposeResult
from textual.containers import Container, Vertical
from textual.widgets import Static
from textual.widget import Widget

from wizard.utils import WizardState


class BaseWizardScreen(Widget):
    """
    Base class for all wizard screens.

    Note: These are Widgets, not Screens, because they are
    mounted inside the main app's content area.
    """

    DEFAULT_CSS = """
    BaseWizardScreen {
        width: 1fr;
        height: auto;
    }
    """

    # Override in subclasses
    GROUP_NUMBER: int = 0
    GROUP_NAME: str = ""
    GROUP_DESCRIPTION: str = ""
    IS_OPTIONAL: bool = False

    def __init__(self, state: Optional[WizardState] = None, **kwargs) -> None:
        """
        Initialize the screen.

        Args:
            state: Current wizard state
        """
        super().__init__(**kwargs)
        self.state = state or WizardState()

    def compose(self) -> ComposeResult:
        """Create the screen layout."""
        yield Container(
            self._create_header(),
            self._create_content(),
            id="screen-container",
        )

    def _create_header(self) -> Container:
        """Create the screen header."""
        badge = "[yellow]OPTIONAL[/yellow]" if self.IS_OPTIONAL else "[red]REQUIRED[/red]"
        return Container(
            Static(
                f"[bold]{self.GROUP_NUMBER}. {self.GROUP_NAME}[/bold]  {badge}",
                classes="screen-title",
            ),
            Static(self.GROUP_DESCRIPTION, classes="screen-description"),
            id="screen-header",
        )

    def _create_content(self) -> Container:
        """
        Create the main content area.

        Override this in subclasses to add form fields.
        """
        return Container(
            Static("Content goes here", id="placeholder-content"),
            id="screen-content",
        )

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
        yield Static(f"[bold]{self.title}[/bold]", classes="preview-title")
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
                    Static(f"  {label}: {value}", classes="preview-item")
                )
