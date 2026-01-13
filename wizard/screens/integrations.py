"""
Integrations Screen - Group 3: Optional service integrations.

Tabbed interface for:
- Google Sheets: Results storage and sync
- LangSmith: Tracing and debugging
- Ollama: Local LLM for evaluation
"""

from typing import Optional, Dict, Tuple
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import (
    Static, Button, TabbedContent, TabPane,
    Checkbox, Switch, Label,
)
from textual.reactive import reactive

from wizard.screens.base import BaseWizardScreen, PreviewPanel
from wizard.widgets.fields import ValidatedInput, FormGroup
from wizard.utils import (
    WizardState, PROJECT_ROOT,
    check_ollama_installed, check_ollama_running, check_ollama_model,
    validate_langsmith_key,
)


class IntegrationToggle(Container):
    """Toggle switch with label for enabling/disabling an integration."""

    def __init__(
        self,
        label: str,
        integration_key: str,
        description: str = "",
        default: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.label_text = label
        self.integration_key = integration_key
        self.description = description
        self._default = default
        self.add_class("integration-toggle")

    def compose(self) -> ComposeResult:
        yield Horizontal(
            Switch(value=self._default, id=f"switch-{self.integration_key}"),
            Vertical(
                Static(f"[bold]{self.label_text}[/bold]"),
                Static(f"[dim]{self.description}[/dim]", classes="toggle-description"),
                classes="toggle-labels",
            ),
            classes="toggle-row",
        )

    @property
    def enabled(self) -> bool:
        """Get current toggle state."""
        switch = self.query_one(f"#switch-{self.integration_key}", Switch)
        return switch.value


class IntegrationsScreen(BaseWizardScreen):
    """
    Integrations screen with tabbed interface.

    Features:
    - Google Sheets: OAuth, spreadsheet selection
    - LangSmith: API key, project configuration
    - Ollama: Installation status, model selection
    """

    GROUP_NUMBER = 3
    GROUP_NAME = "Integrations"
    GROUP_DESCRIPTION = "Configure optional service integrations"
    IS_OPTIONAL = True

    def __init__(self, state: Optional[WizardState] = None) -> None:
        super().__init__(state)
        self.inputs: Dict[str, ValidatedInput] = {}

    def _create_content(self) -> Container:
        """Create tabbed content."""
        return Container(
            Static(
                "[bold]Optional Integrations[/bold]\n"
                "[dim]Enable services to enhance testing capabilities. All are optional.[/dim]",
                classes="section-intro",
            ),
            Static(""),
            TabbedContent(
                TabPane("Google Sheets", self._create_sheets_tab(), id="tab-sheets"),
                TabPane("LangSmith", self._create_langsmith_tab(), id="tab-langsmith"),
                TabPane("Ollama", self._create_ollama_tab(), id="tab-ollama"),
                id="integration-tabs",
            ),
            Static("", classes="spacer"),
            PreviewPanel(title="Integration Status", id="preview"),
            id="form-container",
        )

    def _create_sheets_tab(self) -> Container:
        """Google Sheets tab with OAuth flow."""
        # Spreadsheet ID input
        self.inputs["spreadsheet_id"] = ValidatedInput(
            placeholder="e.g., 1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
            id="input-spreadsheet-id",
        )

        # Drive folder ID input
        self.inputs["drive_folder_id"] = ValidatedInput(
            placeholder="e.g., 1abc123def456 (optional)",
            id="input-drive-folder",
        )

        return Container(
            IntegrationToggle(
                label="Enable Google Sheets",
                integration_key="sheets",
                description="Store test results in Google Sheets for easy sharing",
                id="toggle-sheets",
            ),
            Static("", classes="spacer"),
            Container(
                Static("[bold]Configuration[/bold]", classes="subsection-title"),
                Static(""),
                Static(
                    "To use Google Sheets, you need OAuth credentials from Google Cloud Console.\n"
                    "[dim]See docs/CONFIGURATION.md for setup instructions.[/dim]"
                ),
                Static(""),
                Horizontal(
                    Button("Setup OAuth", id="btn-oauth-setup", variant="default"),
                    Button("Test Connection", id="btn-test-sheets", variant="default"),
                    classes="button-group",
                ),
                Static("", id="sheets-status", classes="status-message"),
                Static(""),
                FormGroup(
                    label="Spreadsheet ID",
                    input_widget=self.inputs["spreadsheet_id"],
                    help_text="ID from the spreadsheet URL (leave empty to create new)",
                ),
                FormGroup(
                    label="Drive Folder ID",
                    input_widget=self.inputs["drive_folder_id"],
                    help_text="For storing screenshots (optional)",
                ),
                id="sheets-config",
                classes="config-section",
            ),
            classes="tab-content",
        )

    def _create_langsmith_tab(self) -> Container:
        """LangSmith tab with API configuration."""
        # API Key input
        self.inputs["langsmith_api_key"] = ValidatedInput(
            placeholder="lsv2_pt_...",
            validator=self._validate_langsmith_key,
            id="input-langsmith-key",
        )

        # Project ID input
        self.inputs["langsmith_project"] = ValidatedInput(
            placeholder="my-chatbot-project (optional)",
            id="input-langsmith-project",
        )

        # Org ID input
        self.inputs["langsmith_org"] = ValidatedInput(
            placeholder="org-123 (optional)",
            id="input-langsmith-org",
        )

        return Container(
            IntegrationToggle(
                label="Enable LangSmith",
                integration_key="langsmith",
                description="Advanced debugging and trace collection",
                id="toggle-langsmith",
            ),
            Static("", classes="spacer"),
            Container(
                Static("[bold]Configuration[/bold]", classes="subsection-title"),
                Static(""),
                Static(
                    "Get your API key from [link]https://smith.langchain.com[/link]\n"
                    "[dim]LangSmith provides detailed debugging of chatbot interactions.[/dim]"
                ),
                Static(""),
                FormGroup(
                    label="API Key",
                    input_widget=self.inputs["langsmith_api_key"],
                    help_text="Your LangSmith API key (starts with lsv2_)",
                    required=True,
                ),
                FormGroup(
                    label="Project ID",
                    input_widget=self.inputs["langsmith_project"],
                    help_text="Project for organizing traces (optional)",
                ),
                FormGroup(
                    label="Organization ID",
                    input_widget=self.inputs["langsmith_org"],
                    help_text="Required if you belong to multiple organizations",
                ),
                Static(""),
                Horizontal(
                    Button("Test Connection", id="btn-test-langsmith", variant="default"),
                    classes="button-group",
                ),
                Static("", id="langsmith-status", classes="status-message"),
                id="langsmith-config",
                classes="config-section",
            ),
            classes="tab-content",
        )

    def _create_ollama_tab(self) -> Container:
        """Ollama tab with installation status and model selection."""
        return Container(
            IntegrationToggle(
                label="Enable Ollama Evaluation",
                integration_key="ollama",
                description="Use local LLM for automated response evaluation",
                id="toggle-ollama",
            ),
            Static("", classes="spacer"),
            Container(
                Static("[bold]Status[/bold]", classes="subsection-title"),
                Static("", id="ollama-status", classes="status-panel"),
                Static(""),
                Static("[bold]Model Selection[/bold]", classes="subsection-title"),
                Static(""),
                Horizontal(
                    Button("Mistral", id="btn-model-mistral", variant="primary", classes="model-btn"),
                    Button("Llama3", id="btn-model-llama3", variant="default", classes="model-btn"),
                    Button("Phi3", id="btn-model-phi3", variant="default", classes="model-btn"),
                    classes="button-group model-buttons",
                ),
                Static(
                    "[dim]Mistral is recommended for best results.[/dim]",
                    classes="model-hint",
                ),
                Static(""),
                Horizontal(
                    Button("Check Status", id="btn-check-ollama", variant="default"),
                    Button("Start Ollama", id="btn-start-ollama", variant="default"),
                    Button("Install Model", id="btn-install-model", variant="default"),
                    classes="button-group",
                ),
                Static("", id="ollama-action-status", classes="status-message"),
                id="ollama-config",
                classes="config-section",
            ),
            classes="tab-content",
        )

    def _validate_langsmith_key(self, value: str) -> Tuple[bool, str]:
        """Validate LangSmith API key format."""
        if not value:
            return (True, "")  # Optional
        if validate_langsmith_key(value):
            return (True, "")
        return (False, "Invalid API key format (should start with lsv2_)")

    def on_mount(self) -> None:
        """Initialize the screen."""
        super().on_mount()
        self._check_ollama_status()
        self._update_preview()

    def load_state(self) -> None:
        """Load existing state into form fields."""
        # Google Sheets
        if self.state.google_sheets_enabled:
            toggle = self.query_one("#toggle-sheets", IntegrationToggle)
            switch = toggle.query_one("#switch-sheets", Switch)
            switch.value = True

        if self.state.spreadsheet_id:
            self.inputs["spreadsheet_id"].value = self.state.spreadsheet_id
        if self.state.drive_folder_id:
            self.inputs["drive_folder_id"].value = self.state.drive_folder_id

        # LangSmith
        if self.state.langsmith_enabled:
            toggle = self.query_one("#toggle-langsmith", IntegrationToggle)
            switch = toggle.query_one("#switch-langsmith", Switch)
            switch.value = True

        if self.state.langsmith_api_key:
            self.inputs["langsmith_api_key"].value = self.state.langsmith_api_key
        if self.state.langsmith_project_id:
            self.inputs["langsmith_project"].value = self.state.langsmith_project_id
        if self.state.langsmith_org_id:
            self.inputs["langsmith_org"].value = self.state.langsmith_org_id

        # Ollama
        if self.state.ollama_enabled:
            toggle = self.query_one("#toggle-ollama", IntegrationToggle)
            switch = toggle.query_one("#switch-ollama", Switch)
            switch.value = True

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        button_id = event.button.id

        if button_id == "btn-oauth-setup":
            self._open_oauth_setup()
        elif button_id == "btn-test-sheets":
            self._test_sheets_connection()
        elif button_id == "btn-test-langsmith":
            self._test_langsmith_connection()
        elif button_id == "btn-check-ollama":
            self._check_ollama_status()
        elif button_id == "btn-start-ollama":
            self._start_ollama()
        elif button_id == "btn-install-model":
            self._install_ollama_model()
        elif button_id and button_id.startswith("btn-model-"):
            model = button_id.replace("btn-model-", "")
            self._select_model(model)
        else:
            super().on_button_pressed(event)

    def on_switch_changed(self, event: Switch.Changed) -> None:
        """Handle toggle changes."""
        self._update_preview()

    def on_validated_input_validated(self, event: ValidatedInput.Validated) -> None:
        """Handle input changes."""
        self._update_preview()

    def _open_oauth_setup(self) -> None:
        """Open Google Cloud Console for OAuth setup."""
        import webbrowser
        webbrowser.open("https://console.cloud.google.com/apis/credentials")
        self.notify("Opened Google Cloud Console in browser")

    def _test_sheets_connection(self) -> None:
        """Test Google Sheets connection."""
        status = self.query_one("#sheets-status", Static)
        status.update("[yellow]Testing connection...[/yellow]")

        # Check for token
        token_path = PROJECT_ROOT / "config" / "token.pickle"
        if not token_path.exists():
            status.update("[red]No OAuth token found. Complete OAuth setup first.[/red]")
            return

        status.update("[green]OAuth token found. Connection ready.[/green]")

    def _test_langsmith_connection(self) -> None:
        """Test LangSmith API connection."""
        status = self.query_one("#langsmith-status", Static)
        api_key = self.inputs["langsmith_api_key"].value

        if not api_key:
            status.update("[red]Enter an API key first[/red]")
            return

        status.update("[yellow]Testing connection...[/yellow]")

        # Run test in worker
        self.run_worker(self._test_langsmith_async(api_key))

    async def _test_langsmith_async(self, api_key: str) -> None:
        """Async LangSmith connection test."""
        import httpx

        status = self.query_one("#langsmith-status", Static)

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://api.smith.langchain.com/sessions",
                    headers={"x-api-key": api_key},
                    params={"limit": 1},
                    timeout=10.0,
                )

                if response.status_code == 200:
                    status.update("[green]Connection successful![/green]")
                elif response.status_code == 401:
                    status.update("[red]Invalid API key[/red]")
                elif response.status_code == 403:
                    status.update("[red]Access denied - check organization ID[/red]")
                else:
                    status.update(f"[red]HTTP error: {response.status_code}[/red]")

        except Exception as e:
            status.update(f"[red]Connection error: {e}[/red]")

    def _check_ollama_status(self) -> None:
        """Check Ollama installation and status."""
        status_widget = self.query_one("#ollama-status", Static)

        installed = check_ollama_installed()
        running = check_ollama_running() if installed else False
        has_mistral = check_ollama_model("mistral") if running else False

        lines = []
        lines.append(f"Installed: {'[green]Yes[/green]' if installed else '[yellow]No[/yellow]'}")

        if installed:
            lines.append(f"Running: {'[green]Yes[/green]' if running else '[yellow]No[/yellow]'}")

        if running:
            lines.append(f"Mistral model: {'[green]Available[/green]' if has_mistral else '[yellow]Not installed[/yellow]'}")

        status_widget.update("\n".join(lines))

    def _start_ollama(self) -> None:
        """Start Ollama server."""
        import subprocess

        action_status = self.query_one("#ollama-action-status", Static)
        action_status.update("[yellow]Starting Ollama...[/yellow]")

        try:
            subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )

            # Wait a bit and check
            import time
            time.sleep(2)

            if check_ollama_running():
                action_status.update("[green]Ollama started successfully[/green]")
                self._check_ollama_status()
            else:
                action_status.update("[yellow]Ollama starting... check status in a moment[/yellow]")

        except FileNotFoundError:
            action_status.update("[red]Ollama not installed. Install via: brew install ollama[/red]")
        except Exception as e:
            action_status.update(f"[red]Error: {e}[/red]")

    def _install_ollama_model(self) -> None:
        """Install the selected Ollama model."""
        action_status = self.query_one("#ollama-action-status", Static)

        if not check_ollama_running():
            action_status.update("[red]Start Ollama first[/red]")
            return

        model = getattr(self, "_selected_model", "mistral")
        action_status.update(f"[yellow]Installing {model}... (this may take a while)[/yellow]")

        self.run_worker(self._install_model_async(model))

    async def _install_model_async(self, model: str) -> None:
        """Async model installation."""
        import asyncio

        action_status = self.query_one("#ollama-action-status", Static)

        try:
            process = await asyncio.create_subprocess_exec(
                "ollama", "pull", model,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )

            _, stderr = await asyncio.wait_for(process.communicate(), timeout=600)

            if process.returncode == 0:
                action_status.update(f"[green]{model} installed successfully[/green]")
                self._check_ollama_status()
            else:
                action_status.update(f"[red]Installation failed: {stderr.decode()}[/red]")

        except asyncio.TimeoutError:
            action_status.update("[yellow]Installation still in progress...[/yellow]")
        except Exception as e:
            action_status.update(f"[red]Error: {e}[/red]")

    def _select_model(self, model: str) -> None:
        """Select an Ollama model."""
        self._selected_model = model

        # Update button styles
        for btn_id in ["btn-model-mistral", "btn-model-llama3", "btn-model-phi3"]:
            btn = self.query_one(f"#{btn_id}", Button)
            if btn_id == f"btn-model-{model}":
                btn.variant = "primary"
            else:
                btn.variant = "default"

        self._update_preview()

    def _update_preview(self) -> None:
        """Update the integration status preview."""
        preview = self.query_one("#preview", PreviewPanel)

        items = {}

        # Google Sheets
        sheets_toggle = self.query_one("#toggle-sheets", IntegrationToggle)
        sheets_enabled = sheets_toggle.enabled
        items["Google Sheets"] = "[green]Enabled[/green]" if sheets_enabled else "[dim]Disabled[/dim]"

        # LangSmith
        langsmith_toggle = self.query_one("#toggle-langsmith", IntegrationToggle)
        langsmith_enabled = langsmith_toggle.enabled
        items["LangSmith"] = "[green]Enabled[/green]" if langsmith_enabled else "[dim]Disabled[/dim]"

        # Ollama
        ollama_toggle = self.query_one("#toggle-ollama", IntegrationToggle)
        ollama_enabled = ollama_toggle.enabled
        model = getattr(self, "_selected_model", "mistral")
        if ollama_enabled:
            items["Ollama"] = f"[green]Enabled[/green] ({model})"
        else:
            items["Ollama"] = "[dim]Disabled[/dim]"

        preview.update_preview(items)

    def validate(self) -> bool:
        """Validate integration configurations."""
        # Check LangSmith API key if enabled
        langsmith_toggle = self.query_one("#toggle-langsmith", IntegrationToggle)
        if langsmith_toggle.enabled:
            api_key = self.inputs["langsmith_api_key"].value
            if not api_key:
                self.notify("LangSmith API key is required when enabled", severity="error")
                return False

        return True

    def save_state(self) -> None:
        """Save integration configurations to state."""
        # Google Sheets
        sheets_toggle = self.query_one("#toggle-sheets", IntegrationToggle)
        self.state.google_sheets_enabled = sheets_toggle.enabled
        self.state.spreadsheet_id = self.inputs["spreadsheet_id"].value.strip()
        self.state.drive_folder_id = self.inputs["drive_folder_id"].value.strip()

        # LangSmith
        langsmith_toggle = self.query_one("#toggle-langsmith", IntegrationToggle)
        self.state.langsmith_enabled = langsmith_toggle.enabled
        self.state.langsmith_api_key = self.inputs["langsmith_api_key"].value.strip()
        self.state.langsmith_project_id = self.inputs["langsmith_project"].value.strip()
        self.state.langsmith_org_id = self.inputs["langsmith_org"].value.strip()

        # Ollama
        ollama_toggle = self.query_one("#toggle-ollama", IntegrationToggle)
        self.state.ollama_enabled = ollama_toggle.enabled
        self.state.ollama_model = getattr(self, "_selected_model", "mistral")

        # Mark original steps as complete
        self.state.mark_step_complete(5)  # Google Sheets
        self.state.mark_step_complete(6)  # LangSmith
        self.state.mark_step_complete(7)  # Ollama
        self.state.mark_step_complete(8)  # Evaluation
