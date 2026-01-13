"""
Interface Screen - Group 2: CSS Selectors detection.

Provides three modes for configuring chatbot selectors:
- Auto-detect: Browser opens and automatically finds selectors
- Manual: User enters selectors directly
- Interactive: Step-by-step guided detection with testing
"""

from typing import Optional, Dict, List, Tuple

from textual.app import ComposeResult
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Static, Button, TabbedContent, TabPane, DataTable
from textual.reactive import reactive

from wizard.screens.base import BaseWizardScreen, PreviewPanel
from wizard.widgets.fields import ValidatedInput, FormGroup
from wizard.utils import WizardState


# Selector definitions
SELECTOR_FIELDS = [
    ("textarea", "Textarea Input", "CSS selector for the chat input field", True),
    ("submit_button", "Submit Button", "CSS selector for the send/submit button", True),
    ("bot_messages", "Bot Messages", "CSS selector for bot response elements", True),
    ("loading_indicator", "Loading Indicator", "CSS selector for typing/loading indicator", False),
    ("thread_container", "Thread Container", "CSS selector for the chat thread container", False),
    ("content_inner", "Content Inner", "CSS selector for inner content wrapper", False),
]


class SelectorInput(ValidatedInput):
    """Specialized input for CSS selectors."""

    def __init__(
        self,
        selector_key: str,
        placeholder: str = "",
        required: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(
            placeholder=placeholder,
            validator=self._validate_selector if required else None,
            required=required,
            **kwargs,
        )
        self.selector_key = selector_key

    def _validate_selector(self, value: str) -> Tuple[bool, str]:
        """Basic CSS selector validation."""
        if not value.strip():
            return (False, "Selector is required")

        # Basic check - must have at least one valid character pattern
        if not any(c in value for c in [".", "#", "[", ">", " ", ":"]):
            if not value.isalnum():
                return (False, "Invalid selector format")

        return (True, "")


class InterfaceScreen(BaseWizardScreen):
    """
    Interface screen for CSS selector detection.

    Features:
    - Auto-detect mode with browser automation
    - Manual entry mode
    - Live preview of detected selectors
    - Validation of required selectors
    """

    GROUP_NUMBER = 2
    GROUP_NAME = "Interface"
    GROUP_DESCRIPTION = "Configure CSS selectors for chatbot interaction"
    IS_OPTIONAL = False

    detected_selectors: reactive[dict] = reactive(dict, init=False)

    def __init__(self, state: Optional[WizardState] = None) -> None:
        super().__init__(state)
        self.selector_inputs: Dict[str, SelectorInput] = {}
        self.detected_selectors = {}

    def _create_content(self) -> Container:
        """Create the tabbed interface content."""
        return Container(
            TabbedContent(
                TabPane("Auto-detect", self._create_autodetect_tab(), id="tab-auto"),
                TabPane("Manual", self._create_manual_tab(), id="tab-manual"),
                id="selector-tabs",
            ),
            Static("", classes="spacer"),
            self._create_selectors_table(),
            Static("", classes="spacer"),
            PreviewPanel(title="Current Configuration", id="preview"),
            id="form-container",
        )

    def _create_autodetect_tab(self) -> Container:
        """Create the auto-detect mode tab."""
        return Container(
            Static("[bold]Automatic Selector Detection[/bold]", classes="text-primary"),
            Static(""),
            Static(
                "This mode will open a browser window and automatically detect\n"
                "the CSS selectors for your chatbot interface.",
            ),
            Static(""),
            Static("[dim]Requirements:[/dim]"),
            Static("  • Chatbot URL must be accessible"),
            Static("  • Browser will open in visible mode"),
            Static("  • Detection takes ~10-30 seconds"),
            Static(""),
            Horizontal(
                Button("Start Auto-detect", id="btn-autodetect", variant="primary"),
                Button("Quick Detect", id="btn-quickdetect", variant="default"),
                classes="button-group",
            ),
            Static("", id="autodetect-status", classes="status-message"),
            classes="tab-content",
        )

    def _create_manual_tab(self) -> Container:
        """Create the manual entry mode tab."""
        # Create input widgets
        form_groups = []

        for key, label, help_text, required in SELECTOR_FIELDS:
            self.selector_inputs[key] = SelectorInput(
                selector_key=key,
                placeholder=f"e.g., .chat-input, #message-box",
                required=required,
                id=f"selector-{key}",
            )

            form_groups.append(
                FormGroup(
                    label=label,
                    input_widget=self.selector_inputs[key],
                    help_text=help_text,
                    required=required,
                )
            )

        return Container(
            Static("[bold]Manual Selector Entry[/bold]", classes="text-primary"),
            Static(""),
            Static(
                "Enter CSS selectors for each chatbot UI element.\n"
                "[dim]Fields marked with * are required.[/dim]"
            ),
            Static(""),
            *form_groups,
            classes="tab-content",
        )

    def _create_selectors_table(self) -> Container:
        """Create a table showing current selector status."""
        table = DataTable(id="selectors-table")
        table.add_column("Element", width=20)
        table.add_column("Selector", width=40)
        table.add_column("Status", width=12)

        return Container(
            Static("[bold]Selector Status[/bold]", classes="text-primary"),
            table,
            classes="table-container",
        )

    def on_mount(self) -> None:
        """Initialize the screen."""
        super().on_mount()
        self._update_table()
        self._update_preview()

    def load_state(self) -> None:
        """Load existing selectors from state."""
        if self.state.selectors:
            self.detected_selectors = dict(self.state.selectors)
            # Populate manual inputs
            for key, value in self.state.selectors.items():
                if key in self.selector_inputs:
                    self.selector_inputs[key].value = value or ""

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-autodetect":
            self._run_autodetect(quick=False)
        elif event.button.id == "btn-quickdetect":
            self._run_autodetect(quick=True)
        else:
            # Let parent handle navigation buttons
            super().on_button_pressed(event)

    def _run_autodetect(self, quick: bool = True) -> None:
        """Run auto-detection in background."""
        status = self.query_one("#autodetect-status", Static)
        status.update("[yellow]Starting browser...[/yellow]")

        # Run detection in worker
        self.run_worker(
            self._detect_selectors_async(quick),
            name="selector-detection",
            description="Detecting selectors",
        )

    async def _detect_selectors_async(self, quick: bool) -> None:
        """Async selector detection using Playwright."""
        from wizard.workers.browser import detect_selectors

        status = self.query_one("#autodetect-status", Static)

        try:
            status.update("[yellow]Opening browser...[/yellow]")

            result = await detect_selectors(
                url=self.state.chatbot_url,
                quick_mode=quick,
            )

            if result:
                self.detected_selectors = result
                # Update inputs
                for key, value in result.items():
                    if key in self.selector_inputs:
                        self.selector_inputs[key].value = value or ""

                self._update_table()
                self._update_preview()

                found = sum(1 for v in result.values() if v)
                status.update(f"[green]Detected {found}/{len(SELECTOR_FIELDS)} selectors[/green]")
                self.notify(f"Detected {found} selectors", severity="information")
            else:
                status.update("[red]Detection failed - try manual mode[/red]")
                self.notify("Auto-detection failed", severity="error")

        except Exception as e:
            status.update(f"[red]Error: {e}[/red]")
            self.notify(f"Detection error: {e}", severity="error")

    def on_validated_input_validated(self, event: ValidatedInput.Validated) -> None:
        """Update when manual inputs change."""
        if hasattr(event.control, "selector_key"):
            key = event.control.selector_key
            self.detected_selectors[key] = event.value
            self._update_table()
            self._update_preview()

    def _update_table(self) -> None:
        """Update the selectors status table."""
        table = self.query_one("#selectors-table", DataTable)
        table.clear()

        for key, label, _, required in SELECTOR_FIELDS:
            value = self.detected_selectors.get(key, "")

            if value:
                status = "[green]OK[/green]"
            elif required:
                status = "[red]Missing[/red]"
            else:
                status = "[dim]Optional[/dim]"

            table.add_row(label, value or "-", status)

    def _update_preview(self) -> None:
        """Update the preview panel."""
        preview = self.query_one("#preview", PreviewPanel)

        items = {}
        for key, label, _, required in SELECTOR_FIELDS:
            value = self.detected_selectors.get(key, "")
            suffix = " *" if required else ""
            items[f"{label}{suffix}"] = value or "[dim]not set[/dim]"

        preview.update_preview(items)

    def validate(self) -> bool:
        """Validate all required selectors are set."""
        # Collect current values from inputs
        for key, inp in self.selector_inputs.items():
            if inp.value:
                self.detected_selectors[key] = inp.value.strip()

        # Check required fields
        missing = []
        for key, label, _, required in SELECTOR_FIELDS:
            if required and not self.detected_selectors.get(key):
                missing.append(label)

        if missing:
            self.notify(
                f"Missing required selectors: {', '.join(missing)}",
                severity="error",
            )
            return False

        return True

    def save_state(self) -> None:
        """Save selectors to wizard state."""
        # Collect final values
        for key, inp in self.selector_inputs.items():
            if inp.value:
                self.detected_selectors[key] = inp.value.strip()

        self.state.selectors = dict(self.detected_selectors)
        self.state.mark_step_complete(4)  # Original step 4
