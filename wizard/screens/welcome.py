"""
Welcome Screen - Entry point for the wizard.

Shows options to:
- Create a new project
- Continue an incomplete session
- Reconfigure an existing project
"""

from pathlib import Path
from typing import Optional, List

from textual.app import ComposeResult
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Static, Button, ListView, ListItem, Label
from textual.widget import Widget
from textual.message import Message

from wizard.utils import WizardState, StateManager


class WelcomeScreen(Widget):
    """
    Welcome screen showing project options.
    """

    DEFAULT_CSS = """
    WelcomeScreen {
        width: 1fr;
        height: auto;
    }

    .welcome-title {
        text-align: center;
        text-style: bold;
        color: #00D9FF;
        padding: 1 0;
    }

    .welcome-subtitle {
        text-align: center;
        color: #888888;
        padding-bottom: 2;
    }

    .section-title {
        color: #00D9FF;
        text-style: bold;
        padding: 1 0;
    }

    .project-list {
        height: auto;
        max-height: 12;
        background: #252525;
        border: tall #3a3a3a;
        margin: 1 0;
    }

    .project-item {
        padding: 0 1;
    }

    .project-item:hover {
        background: #333333;
    }

    .action-buttons {
        align: center middle;
        height: auto;
        padding: 2 0;
    }

    .action-buttons Button {
        margin: 0 1;
    }

    .resume-panel {
        background: #2a3a2a;
        border: tall #00FF88;
        padding: 1;
        margin: 1 0;
    }

    .resume-title {
        color: #00FF88;
        text-style: bold;
    }
    """

    class ProjectSelected(Message):
        """Emitted when a project is selected."""
        def __init__(self, project_name: str, is_new: bool = False) -> None:
            self.project_name = project_name
            self.is_new = is_new
            super().__init__()

    class ResumeSession(Message):
        """Emitted when user wants to resume incomplete session."""
        pass

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._existing_projects: List[str] = []
        self._has_incomplete_session = False
        self._incomplete_project_name = ""

    def compose(self) -> ComposeResult:
        # Check for existing projects and incomplete session
        self._scan_projects()
        self._check_incomplete_session()

        yield Container(
            Static("Welcome to Chatbot Tester", classes="welcome-title"),
            Static("Configure your chatbot testing project", classes="welcome-subtitle"),

            # Resume incomplete session (if exists)
            self._create_resume_section(),

            # New project section
            Container(
                Static("[bold]Start Fresh[/bold]", classes="section-title"),
                Static("Create a new testing project from scratch."),
                Horizontal(
                    Button("New Project", id="btn-new-project", variant="primary"),
                    classes="action-buttons",
                ),
            ),

            # Existing projects section
            self._create_existing_projects_section(),

            id="welcome-container",
        )

    def _scan_projects(self) -> None:
        """Scan for existing projects."""
        projects_dir = Path("projects")
        if projects_dir.exists():
            self._existing_projects = [
                d.name for d in projects_dir.iterdir()
                if d.is_dir() and (d / "project.yaml").exists()
            ]
            self._existing_projects.sort()

    def _check_incomplete_session(self) -> None:
        """Check for incomplete wizard session."""
        state_manager = StateManager("")
        if state_manager.has_previous_session():
            state = state_manager.load()
            if state and state.project_name:
                self._has_incomplete_session = True
                self._incomplete_project_name = state.project_name

    def _create_resume_section(self) -> Container:
        """Create resume section if incomplete session exists."""
        if not self._has_incomplete_session:
            return Container()  # Empty container

        return Container(
            Static("[bold]Resume Session[/bold]", classes="resume-title"),
            Static(
                f"You have an incomplete session for project: [bold]{self._incomplete_project_name}[/bold]"
            ),
            Horizontal(
                Button("Resume", id="btn-resume", variant="primary"),
                Button("Discard", id="btn-discard", variant="warning"),
                classes="action-buttons",
            ),
            classes="resume-panel",
        )

    def _create_existing_projects_section(self) -> Container:
        """Create section showing existing projects."""
        if not self._existing_projects:
            return Container(
                Static("[bold]Existing Projects[/bold]", classes="section-title"),
                Static("[dim]No existing projects found.[/dim]"),
            )

        items = []
        for project in self._existing_projects:
            items.append(
                ListItem(Label(f"  {project}"), id=f"project-{project}")
            )

        return Container(
            Static("[bold]Reconfigure Existing Project[/bold]", classes="section-title"),
            Static("Select a project to modify its configuration:"),
            ListView(*items, id="project-list", classes="project-list"),
            Horizontal(
                Button("Edit Selected", id="btn-edit-project", variant="default"),
                classes="action-buttons",
            ),
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-new-project":
            self.post_message(self.ProjectSelected("", is_new=True))
        elif event.button.id == "btn-resume":
            self.post_message(self.ResumeSession())
        elif event.button.id == "btn-discard":
            # Clear the incomplete session
            StateManager("").clear()
            self._has_incomplete_session = False
            self.notify("Session discarded")
            self.refresh()
        elif event.button.id == "btn-edit-project":
            self._edit_selected_project()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle project selection from list."""
        if event.item and event.item.id:
            project_name = event.item.id.replace("project-", "")
            self.post_message(self.ProjectSelected(project_name, is_new=False))

    def _edit_selected_project(self) -> None:
        """Edit the currently selected project in the list."""
        try:
            list_view = self.query_one("#project-list", ListView)
            if list_view.highlighted_child:
                item_id = list_view.highlighted_child.id
                if item_id:
                    project_name = item_id.replace("project-", "")
                    self.post_message(self.ProjectSelected(project_name, is_new=False))
        except Exception:
            self.notify("Select a project first", severity="warning")
