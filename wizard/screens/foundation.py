"""
Foundation Screen - Group 1: Project name and Chatbot URL.

Combines the original steps:
- Step 2: Project Info (name, description)
- Step 3: Chatbot URL (URL, optional login)
"""

from typing import Optional

from textual.app import ComposeResult
from textual.containers import Container, Vertical
from textual.widgets import Static, Button, Checkbox
from textual.message import Message

from wizard.screens.base import BaseWizardScreen, PreviewPanel
from wizard.widgets.fields import (
    ValidatedInput, ValidatedURL, FormGroup,
    validate_project_name, validate_not_empty,
)
from wizard.utils import WizardState


class FoundationScreen(BaseWizardScreen):
    """
    Foundation screen for project setup.

    Collects:
    - Project name (required)
    - Project description (optional)
    - Chatbot URL (required)
    - Login required flag
    """

    GROUP_NUMBER = 1
    GROUP_NAME = "Foundation"
    GROUP_DESCRIPTION = "Set up your project and chatbot URL"
    IS_OPTIONAL = False

    def __init__(self, state: Optional[WizardState] = None) -> None:
        super().__init__(state)
        self._all_valid = False

    def _create_content(self) -> Container:
        """Create the form content."""
        # Project name input
        self.project_name_input = ValidatedInput(
            placeholder="my-chatbot",
            validator=validate_project_name,
            required=True,
            id="project-name",
        )

        # Description input
        self.description_input = ValidatedInput(
            placeholder="Optional description of your chatbot",
            id="description",
        )

        # URL input
        self.url_input = ValidatedURL(
            placeholder="https://example.com/chatbot",
            required=True,
            id="chatbot-url",
        )

        # Login checkbox
        self.login_checkbox = Checkbox("Chatbot requires login", id="requires-login")

        return Container(
            # Section 1: Project Info
            Static("[bold]Project Information[/bold]", classes="text-primary"),
            Static("", classes="spacer"),

            FormGroup(
                label="Project Name",
                input_widget=self.project_name_input,
                help_text="Unique identifier for your project (letters, numbers, - and _)",
                required=True,
            ),

            FormGroup(
                label="Description",
                input_widget=self.description_input,
                help_text="Brief description of the chatbot being tested",
                required=False,
            ),

            Static("", classes="spacer"),

            # Section 2: Chatbot URL
            Static("[bold]Chatbot Configuration[/bold]", classes="text-primary"),
            Static("", classes="spacer"),

            FormGroup(
                label="Chatbot URL",
                input_widget=self.url_input,
                help_text="The URL where your chatbot is accessible",
                required=True,
            ),

            Container(
                self.login_checkbox,
                Static(
                    "[dim]Check this if the chatbot requires authentication[/dim]",
                    classes="form-help",
                ),
                classes="form-group",
            ),

            Static("", classes="spacer"),

            # Preview panel
            PreviewPanel(title="Configuration Preview", id="preview"),

            id="form-container",
        )

    def on_mount(self) -> None:
        """Load existing state when screen mounts."""
        super().on_mount()
        self.load_state()
        self._update_preview()

    def load_state(self) -> None:
        """Load existing values from state."""
        if self.state.project_name:
            self.project_name_input.value = self.state.project_name

        if self.state.project_description:
            self.description_input.value = self.state.project_description

        if self.state.chatbot_url:
            self.url_input.value = self.state.chatbot_url

        if self.state.requires_login:
            self.login_checkbox.value = True

    def on_validated_input_validated(self, event: ValidatedInput.Validated) -> None:
        """Update preview when fields change."""
        self._update_preview()
        self._check_all_valid()

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        """Update preview when login checkbox changes."""
        self._update_preview()

    def _update_preview(self) -> None:
        """Update the preview panel with current values."""
        preview = self.query_one("#preview", PreviewPanel)
        preview.update_preview({
            "Project": self.project_name_input.value or "[dim]not set[/dim]",
            "Description": self.description_input.value or "[dim]none[/dim]",
            "URL": self.url_input.value or "[dim]not set[/dim]",
            "Login": "Required" if self.login_checkbox.value else "Not required",
        })

    def _check_all_valid(self) -> None:
        """Check if all required fields are valid."""
        self._all_valid = (
            self.project_name_input.is_valid and
            self.url_input.is_valid
        )

    def validate(self) -> bool:
        """Validate all form fields."""
        # Force validation of all fields
        if not self.project_name_input.value:
            self.notify("Project name is required", severity="error")
            self.project_name_input.focus()
            return False

        if not self.project_name_input.is_valid:
            self.notify(
                self.project_name_input.error_message or "Invalid project name",
                severity="error",
            )
            self.project_name_input.focus()
            return False

        if not self.url_input.value:
            self.notify("Chatbot URL is required", severity="error")
            self.url_input.focus()
            return False

        if not self.url_input.is_valid:
            self.notify(
                self.url_input.error_message or "Invalid URL",
                severity="error",
            )
            self.url_input.focus()
            return False

        return True

    def save_state(self) -> None:
        """Save form data to wizard state."""
        self.state.project_name = self.project_name_input.value.strip()
        self.state.project_description = self.description_input.value.strip()
        self.state.chatbot_url = self.url_input.value.strip()
        self.state.requires_login = self.login_checkbox.value

        # Mark original steps as complete
        self.state.mark_step_complete(2)  # Project Info
        self.state.mark_step_complete(3)  # Chatbot URL
