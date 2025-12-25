"""
Wizard Main - Orchestrates the setup wizard flow.
"""

import sys
from pathlib import Path
from typing import Optional, List
from datetime import datetime

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich import box

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.i18n import t, set_language
from src.ui import WizardUI, console, clear_screen, ask_session_recovery, confirm_exit
from wizard.utils import (
    WizardState, StateManager, PROJECT_ROOT,
    ensure_project_dirs, save_project_config, save_tests
)


class Wizard:
    """
    Main wizard orchestrator.
    Manages step flow, state, and navigation.
    """

    TOTAL_STEPS = 10

    def __init__(self, language: str = "it", project_name: str = ""):
        """
        Initialize the wizard.

        Args:
            language: 'it' or 'en'
            project_name: Optional project name (for reconfiguration)
        """
        set_language(language)
        self.language = language
        self.project_name = project_name

        # Initialize UI
        self.ui = WizardUI(total_steps=self.TOTAL_STEPS)

        # Initialize state manager
        self.state_manager = StateManager(project_name)
        self.state: Optional[WizardState] = None

        # Will be populated with step instances
        self.steps = []

    def _import_steps(self):
        """Import and instantiate step classes."""
        from wizard.steps.prerequisites import PrerequisitesStep
        from wizard.steps.project_info import ProjectInfoStep
        from wizard.steps.chatbot_url import ChatbotUrlStep
        from wizard.steps.selectors import SelectorsStep
        from wizard.steps.google_sheets import GoogleSheetsStep
        from wizard.steps.langsmith import LangSmithStep
        from wizard.steps.ollama import OllamaStep
        from wizard.steps.evaluation import EvaluationStep
        from wizard.steps.test_import import TestImportStep
        from wizard.steps.summary import SummaryStep

        step_classes = [
            PrerequisitesStep,      # Step 1
            ProjectInfoStep,        # Step 2
            ChatbotUrlStep,         # Step 3
            SelectorsStep,          # Step 4
            GoogleSheetsStep,       # Step 5
            LangSmithStep,          # Step 6
            OllamaStep,             # Step 7
            EvaluationStep,         # Step 8 (NEW)
            TestImportStep,         # Step 9
            SummaryStep,            # Step 10
        ]

        # Instantiate each step with UI and state
        self.steps = [cls(self.ui, self.state) for cls in step_classes]

    def _check_existing_session(self) -> bool:
        """
        Check for existing session and ask to continue.

        Returns:
            True if should continue existing session
        """
        if not self.state_manager.has_previous_session():
            return False

        state = self.state_manager.load()
        should_continue = ask_session_recovery({
            'current_step': state.current_step,
            'total_steps': self.TOTAL_STEPS
        })

        if should_continue:
            self.state = state
            return True
        else:
            self.state_manager.clear()
            return False

    def _show_welcome(self):
        """Display welcome screen."""
        clear_screen()

        welcome = Text()
        welcome.append("\n* ", style="bold")
        welcome.append("Benvenuto nel Chatbot Tester Setup Wizard!\n\n", style="bold cyan")
        welcome.append("  Questo wizard ti guiderà nella configurazione del tool.\n", style="white")
        welcome.append("  Tempo stimato: ~15-30 minuti\n", style="dim")

        console.print(Panel(welcome, box=box.DOUBLE))
        input("\n  Premi INVIO per iniziare...")

    def _confirm_quit(self) -> bool:
        """Confirm exit and save state."""
        if confirm_exit():
            # Save state before exiting
            if self.state and self.state.project_name:
                self.state_manager.save(self.state)
                console.print(f"\n  [dim]>  Stato salvato. Riprendi eseguendo di nuovo il wizard.[/dim]")
            return True
        return False

    def run(self) -> bool:
        """
        Run the wizard.

        Returns:
            True if completed successfully, False if cancelled
        """
        self._show_welcome()

        # Check for existing session
        if self._check_existing_session():
            current_step = self.state.current_step
        else:
            # Initialize new state
            self.state = self.state_manager.load()
            if not self.state.started_at:
                self.state.started_at = datetime.utcnow().isoformat()
            current_step = 1

        # Import and initialize steps with current state
        self._import_steps()

        # Main wizard loop
        while current_step <= self.TOTAL_STEPS:
            step = self.steps[current_step - 1]

            # Update step's state reference (in case it changed)
            step.state = self.state

            # Run the step
            success, action = step.run()

            if action == 'next':
                # Mark step complete and advance
                self.state.current_step = current_step + 1
                self.state.mark_step_complete(current_step)
                self.state_manager.save(self.state)
                current_step += 1

            elif action == 'back':
                if current_step > 1:
                    current_step -= 1
                    self.state.current_step = current_step

            elif action == 'skip':
                if step.is_optional:
                    self.state.current_step = current_step + 1
                    self.state_manager.save(self.state)
                    current_step += 1

            elif action == 'retry':
                # Re-run same step
                continue

            elif action == 'quit':
                if self._confirm_quit():
                    return False

        # Wizard completed!
        self._finalize()
        return True

    def _finalize(self):
        """Finalize wizard - save all configs."""
        clear_screen()

        console.print("\n  Salvataggio configurazione...\n")

        # Ensure directories exist
        ensure_project_dirs(self.state.project_name)

        # Save project config
        save_project_config(self.state)

        # Save tests if any
        if self.state.tests:
            save_tests(self.state.project_name, self.state.tests)

        # Clean up wizard state file
        self.state_manager.clear()

        # Show completion message
        console.print(Panel(
            t('step9.next_steps', project=self.state.project_name),
            title="Setup Completato",
            border_style="green",
            box=box.DOUBLE
        ))


def run_wizard(language: str = "it", project_name: str = "", legacy: bool = False) -> bool:
    """
    Convenience function to run the wizard.

    Args:
        language: 'it' or 'en'
        project_name: Optional project name for reconfiguration
        legacy: If True, use the old Rich-based wizard

    Returns:
        True if completed, False if cancelled
    """
    if legacy:
        # Use legacy Rich-based wizard
        wizard = Wizard(language=language, project_name=project_name)
        return wizard.run()
    else:
        # Use new Textual-based wizard
        from wizard.app import run_textual_wizard
        return run_textual_wizard(language=language, project_name=project_name)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Chatbot Tester Setup Wizard")
    parser.add_argument("--lang", choices=["it", "en"], default="it", help="Language")
    parser.add_argument("--project", default="", help="Project name (for reconfiguration)")
    parser.add_argument("--legacy", action="store_true", help="Use legacy Rich-based wizard")

    args = parser.parse_args()

    success = run_wizard(language=args.lang, project_name=args.project, legacy=args.legacy)
    sys.exit(0 if success else 1)
