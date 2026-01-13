"""
Finalize Screen - Group 4: Test import and summary.

Combines:
- Test import from various sources
- Configuration summary
- Save and launch options
"""

from typing import Optional, List, Dict, Any
from pathlib import Path
import json

from textual.app import ComposeResult
from textual.containers import Container, Vertical, Horizontal, ScrollableContainer
from textual.widgets import Static, Button, DataTable, TabbedContent, TabPane
from textual.reactive import reactive

from wizard.screens.base import BaseWizardScreen, PreviewPanel
from wizard.widgets.fields import ValidatedInput, FormGroup
from wizard.utils import WizardState, load_tests_from_file, get_project_dir


# Test templates
TEST_TEMPLATES = {
    "basic": {
        "name": "Basic",
        "description": "General chatbot tests (3 tests)",
        "tests": [
            {"id": "TEST_001", "question": "Hello", "category": "greeting", "followups": []},
            {"id": "TEST_002", "question": "How can I contact support?", "category": "support", "followups": ["And via email?"]},
            {"id": "TEST_003", "question": "What services do you offer?", "category": "info", "followups": []},
        ],
    },
    "support": {
        "name": "Customer Support",
        "description": "Support-focused tests (4 tests)",
        "tests": [
            {"id": "TEST_001", "question": "I have a problem", "category": "support", "followups": ["Nothing works"]},
            {"id": "TEST_002", "question": "I want to speak with an operator", "category": "escalation", "followups": []},
            {"id": "TEST_003", "question": "How do I file a complaint?", "category": "complaint", "followups": ["Where do I send it?"]},
            {"id": "TEST_004", "question": "What is your phone number?", "category": "contact", "followups": []},
        ],
    },
    "ecommerce": {
        "name": "E-commerce",
        "description": "Online shop tests (4 tests)",
        "tests": [
            {"id": "TEST_001", "question": "How can I track my order?", "category": "order", "followups": []},
            {"id": "TEST_002", "question": "I want to return an item", "category": "return", "followups": ["What are the deadlines?"]},
            {"id": "TEST_003", "question": "Available payment methods", "category": "payment", "followups": []},
            {"id": "TEST_004", "question": "Shipping costs", "category": "shipping", "followups": ["And for international?"]},
        ],
    },
}


class FinalizeScreen(BaseWizardScreen):
    """
    Finalize screen for test import and configuration summary.

    Features:
    - Test import from file (JSON, CSV)
    - Test import from template
    - Configuration summary
    - Save and launch options
    """

    GROUP_NUMBER = 4
    GROUP_NAME = "Finalize"
    GROUP_DESCRIPTION = "Import tests and complete setup"
    IS_OPTIONAL = False

    tests: reactive[list] = reactive(list, init=False)

    def __init__(self, state: Optional[WizardState] = None) -> None:
        super().__init__(state)
        self.tests = []
        self._selected_template = "basic"

    def _create_content(self) -> Container:
        """Create finalize content."""
        return Container(
            TabbedContent(
                TabPane("Import Tests", self._create_import_tab(), id="tab-import"),
                TabPane("Summary", self._create_summary_tab(), id="tab-summary"),
                id="finalize-tabs",
            ),
            id="form-container",
        )

    def _create_import_tab(self) -> Container:
        """Create test import section."""
        # File path input
        self.file_input = ValidatedInput(
            placeholder="/path/to/tests.json or tests.csv",
            id="input-test-file",
        )

        return Container(
            Static("[bold]Import Test Cases[/bold]", classes="text-primary"),
            Static(
                "[dim]Import tests from a file or use a predefined template.[/dim]"
            ),
            Static(""),

            # File import
            Static("[bold]From File[/bold]", classes="subsection-title"),
            FormGroup(
                label="Test File",
                input_widget=self.file_input,
                help_text="JSON or CSV file with test definitions",
            ),
            Horizontal(
                Button("Import File", id="btn-import-file", variant="default"),
                classes="button-group",
            ),
            Static("", id="import-status", classes="status-message"),
            Static(""),

            # Template selection
            Static("[bold]From Template[/bold]", classes="subsection-title"),
            Static("[dim]Choose a predefined test set to get started quickly.[/dim]"),
            Static(""),
            Horizontal(
                Button("Basic", id="btn-template-basic", variant="primary", classes="template-btn"),
                Button("Support", id="btn-template-support", variant="default", classes="template-btn"),
                Button("E-commerce", id="btn-template-ecommerce", variant="default", classes="template-btn"),
                classes="button-group template-buttons",
            ),
            Static("", id="template-description", classes="template-hint"),
            Horizontal(
                Button("Use Template", id="btn-use-template", variant="default"),
                classes="button-group",
            ),
            Static(""),

            # Test preview
            Static("[bold]Imported Tests[/bold]", classes="subsection-title"),
            self._create_tests_table(),
            Static("", id="test-count", classes="status-message"),

            classes="tab-content",
        )

    def _create_tests_table(self) -> Container:
        """Create the tests preview table."""
        table = DataTable(id="tests-table")
        table.add_column("ID", width=12)
        table.add_column("Question", width=40)
        table.add_column("Category", width=12)
        table.add_column("F/U", width=4)
        return Container(table, classes="table-container")

    def _create_summary_tab(self) -> Container:
        """Create configuration summary section."""
        return Container(
            Static("[bold]Configuration Summary[/bold]", classes="text-primary"),
            Static("[dim]Review your setup before saving.[/dim]"),
            Static(""),
            Vertical(
                # Project section
                Static("[bold cyan]Project[/bold cyan]"),
                Static("", id="summary-project"),
                Static(""),

                # Chatbot section
                Static("[bold cyan]Chatbot[/bold cyan]"),
                Static("", id="summary-chatbot"),
                Static(""),

                # Selectors section
                Static("[bold cyan]Selectors[/bold cyan]"),
                Static("", id="summary-selectors"),
                Static(""),

                # Integrations section
                Static("[bold cyan]Integrations[/bold cyan]"),
                Static("", id="summary-integrations"),
                Static(""),

                # Tests section
                Static("[bold cyan]Tests[/bold cyan]"),
                Static("", id="summary-tests"),

                id="summary-content",
            ),
            Static(""),
            Static("[bold]Ready to Save[/bold]", classes="text-primary"),
            Static(
                "Click [bold]Continue[/bold] to save your configuration and complete setup.",
                classes="save-hint",
            ),
            classes="tab-content",
        )

    def on_mount(self) -> None:
        """Initialize the screen."""
        super().on_mount()
        self._select_template("basic")
        self._update_summary()
        self._update_tests_table()

    def load_state(self) -> None:
        """Load existing tests from state."""
        if self.state.tests:
            self.tests = list(self.state.tests)
            self._update_tests_table()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        button_id = event.button.id

        if button_id == "btn-import-file":
            self._import_from_file()
        elif button_id == "btn-use-template":
            self._apply_template()
        elif button_id and button_id.startswith("btn-template-"):
            template = button_id.replace("btn-template-", "")
            self._select_template(template)
        else:
            super().on_button_pressed(event)

    def _select_template(self, template_key: str) -> None:
        """Select a test template."""
        self._selected_template = template_key

        # Update button styles
        for key in TEST_TEMPLATES:
            btn = self.query_one(f"#btn-template-{key}", Button)
            if key == template_key:
                btn.variant = "primary"
            else:
                btn.variant = "default"

        # Update description
        template = TEST_TEMPLATES[template_key]
        desc = self.query_one("#template-description", Static)
        desc.update(f"[dim]{template['description']}[/dim]")

    def _apply_template(self) -> None:
        """Apply the selected template."""
        template = TEST_TEMPLATES[self._selected_template]
        self.tests = [dict(t) for t in template["tests"]]  # Deep copy
        self._update_tests_table()
        self.notify(f"Loaded {len(self.tests)} tests from {template['name']} template")

    def _import_from_file(self) -> None:
        """Import tests from a file."""
        status = self.query_one("#import-status", Static)
        file_path = self.file_input.value.strip()

        if not file_path:
            status.update("[red]Enter a file path first[/red]")
            return

        path = Path(file_path).expanduser()

        if not path.exists():
            status.update("[red]File not found[/red]")
            return

        status.update("[yellow]Importing...[/yellow]")

        try:
            tests = load_tests_from_file(str(path))

            if tests:
                self.tests = tests
                self._update_tests_table()
                status.update(f"[green]Imported {len(tests)} tests[/green]")
                self.notify(f"Imported {len(tests)} tests from file")
            else:
                status.update("[yellow]No valid tests found in file[/yellow]")

        except json.JSONDecodeError as e:
            status.update(f"[red]Invalid JSON: {e}[/red]")
        except Exception as e:
            status.update(f"[red]Error: {e}[/red]")

    def _update_tests_table(self) -> None:
        """Update the tests preview table."""
        table = self.query_one("#tests-table", DataTable)
        table.clear()

        for test in self.tests[:20]:  # Show max 20
            test_id = test.get("id", "-")
            question = test.get("question", "")
            if len(question) > 40:
                question = question[:37] + "..."
            category = test.get("category", "-")[:12]
            followups = len(test.get("followups", []))

            table.add_row(
                test_id,
                question,
                category,
                str(followups) if followups else "-",
            )

        if len(self.tests) > 20:
            table.add_row("...", f"[dim]+{len(self.tests) - 20} more[/dim]", "", "")

        # Update count
        count = self.query_one("#test-count", Static)
        if self.tests:
            total_followups = sum(len(t.get("followups", [])) for t in self.tests)
            count.update(f"[green]{len(self.tests)} tests, {total_followups} followups[/green]")
        else:
            count.update("[dim]No tests imported[/dim]")

        # Update summary
        self._update_summary()

    def _update_summary(self) -> None:
        """Update the configuration summary."""
        # Project
        project = self.query_one("#summary-project", Static)
        project.update(
            f"  Name: [bold]{self.state.project_name or 'Not set'}[/bold]\n"
            f"  Description: {self.state.project_description or '[dim]None[/dim]'}"
        )

        # Chatbot
        chatbot = self.query_one("#summary-chatbot", Static)
        chatbot.update(
            f"  URL: [bold]{self.state.chatbot_url or 'Not set'}[/bold]\n"
            f"  Login: {'Required' if self.state.requires_login else 'Not required'}"
        )

        # Selectors
        selectors = self.query_one("#summary-selectors", Static)
        sel = self.state.selectors or {}
        sel_lines = []
        for key, label in [("textarea", "Input"), ("submit_button", "Button"), ("bot_messages", "Messages")]:
            value = sel.get(key, "")
            status = "[green]OK[/green]" if value else "[red]Missing[/red]"
            sel_lines.append(f"  {label}: {status}")
        selectors.update("\n".join(sel_lines))

        # Integrations
        integrations = self.query_one("#summary-integrations", Static)
        int_lines = []
        int_lines.append(
            f"  Google Sheets: {'[green]Enabled[/green]' if self.state.google_sheets_enabled else '[dim]Disabled[/dim]'}"
        )
        int_lines.append(
            f"  LangSmith: {'[green]Enabled[/green]' if self.state.langsmith_enabled else '[dim]Disabled[/dim]'}"
        )
        int_lines.append(
            f"  Ollama: {'[green]Enabled[/green]' if self.state.ollama_enabled else '[dim]Disabled[/dim]'}"
        )
        integrations.update("\n".join(int_lines))

        # Tests
        tests = self.query_one("#summary-tests", Static)
        test_count = len(self.tests)
        if test_count > 0:
            total_followups = sum(len(t.get("followups", [])) for t in self.tests)
            tests.update(
                f"  Test cases: [green]{test_count}[/green]\n"
                f"  Followups: {total_followups}"
            )
        else:
            tests.update("  [yellow]No tests imported (you can add them later)[/yellow]")

    def validate(self) -> bool:
        """Validate before finalizing."""
        if not self.state.project_name:
            self.notify("Project name is required", severity="error")
            return False

        if not self.state.chatbot_url:
            self.notify("Chatbot URL is required", severity="error")
            return False

        # Check required selectors
        sel = self.state.selectors or {}
        required = ["textarea", "submit_button", "bot_messages"]
        missing = [k for k in required if not sel.get(k)]

        if missing:
            self.notify(f"Missing selectors: {', '.join(missing)}", severity="warning")
            # Don't block, just warn

        return True

    def save_state(self) -> None:
        """Save final state including tests."""
        self.state.tests = self.tests
        self.state.mark_step_complete(9)   # Test Import
        self.state.mark_step_complete(10)  # Summary

    def action_continue_action(self) -> None:
        """Override to complete wizard instead of advancing."""
        if self.validate():
            self.save_state()
            # Show completion notification
            self.notify(
                f"Setup complete! Project saved to projects/{self.state.project_name}/",
                severity="information",
            )
            # This will trigger the finalization in the app
            self.app._finalize()
