"""
Form Field Widgets - Validated input fields for the wizard.
"""

from typing import Callable, Optional, Tuple
import re

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.reactive import reactive
from textual.widgets import Input, Static
from textual.message import Message


class ValidatedInput(Input):
    """
    Input field with real-time validation.

    Features:
    - Custom validator function
    - Visual feedback (border color)
    - Error message display
    - Success indicator
    """

    is_valid: reactive[bool] = reactive(False)
    error_message: reactive[str] = reactive("")

    class Validated(Message):
        """Emitted when validation state changes."""

        def __init__(self, is_valid: bool, value: str, error: str = "") -> None:
            self.is_valid = is_valid
            self.value = value
            self.error = error
            super().__init__()

    def __init__(
        self,
        placeholder: str = "",
        validator: Optional[Callable[[str], Tuple[bool, str]]] = None,
        required: bool = False,
        **kwargs,
    ) -> None:
        """
        Initialize validated input.

        Args:
            placeholder: Placeholder text
            validator: Function(value) -> (is_valid, error_message)
            required: If True, empty value is invalid
        """
        super().__init__(placeholder=placeholder, **kwargs)
        self._validator = validator
        self._required = required

    def on_input_changed(self, event: Input.Changed) -> None:
        """Validate on every change."""
        self._validate(event.value)

    def _validate(self, value: str) -> None:
        """Run validation and update state."""
        # Check required
        if self._required and not value.strip():
            self.is_valid = False
            self.error_message = "This field is required"
            self._update_visual_state()
            self.post_message(self.Validated(False, value, self.error_message))
            return

        # Run custom validator
        if self._validator:
            is_valid, error = self._validator(value)
            self.is_valid = is_valid
            self.error_message = error if not is_valid else ""
        else:
            # No validator, consider valid if not empty (when required)
            self.is_valid = True
            self.error_message = ""

        self._update_visual_state()
        self.post_message(self.Validated(self.is_valid, value, self.error_message))

    def _update_visual_state(self) -> None:
        """Update CSS classes based on validation state."""
        self.remove_class("-valid", "-invalid")
        if self.value:
            if self.is_valid:
                self.add_class("-valid")
            else:
                self.add_class("-invalid")


class ValidatedURL(ValidatedInput):
    """
    Specialized input for URLs with built-in URL validation.
    """

    URL_PATTERN = re.compile(
        r'^https?://'  # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain
        r'localhost|'  # localhost
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # or IP
        r'(?::\d+)?'  # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)

    def __init__(self, placeholder: str = "https://...", **kwargs) -> None:
        super().__init__(
            placeholder=placeholder,
            validator=self._validate_url,
            **kwargs,
        )

    def _validate_url(self, value: str) -> Tuple[bool, str]:
        """Validate URL format."""
        if not value:
            return (False, "URL is required")

        if not self.URL_PATTERN.match(value):
            return (False, "Invalid URL format")

        if not value.startswith(("http://", "https://")):
            return (False, "URL must start with http:// or https://")

        return (True, "")


class FormGroup(Vertical):
    """
    A form group with label, input, help text, and validation message.

    Layout:
    ```
    Label [REQUIRED/OPTIONAL]
    [Input Field]
    Help text (dim)
    Validation error (red, if any)
    ```
    """

    def __init__(
        self,
        label: str,
        input_widget: ValidatedInput,
        help_text: str = "",
        required: bool = False,
        **kwargs,
    ) -> None:
        """
        Initialize form group.

        Args:
            label: Field label
            input_widget: The input widget (ValidatedInput or subclass)
            help_text: Help text shown below input
            required: Show REQUIRED badge if True
        """
        super().__init__(**kwargs)
        self.label_text = label
        self.input_widget = input_widget
        self.help_text = help_text
        self._required = required
        self.add_class("form-group")

    def compose(self) -> ComposeResult:
        """Create the form group layout."""
        # Label with optional badge
        label_content = self.label_text
        if self._required:
            yield Static(
                f"{label_content} [red]*[/red]",
                classes="form-label",
            )
        else:
            yield Static(label_content, classes="form-label")

        # Input widget
        yield self.input_widget

        # Help text
        if self.help_text:
            yield Static(self.help_text, classes="form-help")

        # Validation message (initially hidden)
        yield Static("", id=f"validation-{self.input_widget.id}", classes="validation-error hidden")

    def on_validated_input_validated(self, event: ValidatedInput.Validated) -> None:
        """Update validation message when input validates."""
        validation_widget = self.query_one(f"#validation-{self.input_widget.id}", Static)
        if event.error:
            validation_widget.update(f"! {event.error}")
            validation_widget.remove_class("hidden")
        else:
            validation_widget.add_class("hidden")


# Common validators
def validate_project_name(value: str) -> Tuple[bool, str]:
    """Validate project name."""
    if not value:
        return (False, "Project name is required")

    if len(value) < 2:
        return (False, "Project name must be at least 2 characters")

    if len(value) > 50:
        return (False, "Project name must be at most 50 characters")

    if not re.match(r'^[a-zA-Z][a-zA-Z0-9_-]*$', value):
        return (False, "Project name must start with a letter and contain only letters, numbers, - and _")

    return (True, "")


def validate_not_empty(value: str) -> Tuple[bool, str]:
    """Validate that value is not empty."""
    if not value.strip():
        return (False, "This field cannot be empty")
    return (True, "")
