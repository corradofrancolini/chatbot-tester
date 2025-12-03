"""
Base class for wizard steps.
"""

from abc import ABC, abstractmethod
from typing import Optional, Tuple
from src.ui import WizardUI, console
from src.i18n import t
from wizard.utils import WizardState


class BaseStep(ABC):
    """
    Abstract base class for wizard steps.
    Each step must implement run() and can optionally implement validate().
    """
    
    step_number: int = 0
    step_key: str = ""  # e.g., 'step1', 'step2'
    is_optional: bool = False
    estimated_time: float = 1.0  # minutes
    
    def __init__(self, ui: WizardUI, state: WizardState):
        """
        Initialize step.
        
        Args:
            ui: Wizard UI instance
            state: Current wizard state
        """
        self.ui = ui
        self.state = state
    
    @property
    def title(self) -> str:
        """Get translated step title."""
        return t(f'{self.step_key}.title')
    
    @property
    def description(self) -> str:
        """Get translated step description."""
        return t(f'{self.step_key}.description')
    
    @property
    def help_text(self) -> str:
        """Get translated help text."""
        return t(f'{self.step_key}.help')
    
    def show(self, content: any = None) -> None:
        """Display the step screen."""
        self.ui.show_step(
            step_num=self.step_number,
            title=self.title,
            description=self.description,
            content=content,
            show_skip=self.is_optional
        )
    
    def show_help(self) -> None:
        """Display help for this step."""
        self.ui.show_help(self.help_text)
    
    @abstractmethod
    def run(self) -> Tuple[bool, str]:
        """
        Execute the step logic.
        
        Returns:
            (success, action) where action is:
            - 'next': proceed to next step
            - 'back': go back to previous step
            - 'quit': exit wizard
            - 'skip': skip this optional step
            - 'retry': retry this step
        """
        pass
    
    def validate(self) -> Tuple[bool, str]:
        """
        Validate step data.
        Override in subclass if validation needed.
        
        Returns:
            (is_valid, error_message)
        """
        return True, ""
    
    def on_enter(self) -> None:
        """Called when entering the step. Override for setup."""
        pass
    
    def on_exit(self) -> None:
        """Called when leaving the step. Override for cleanup."""
        pass
    
    def handle_input(self, key: str) -> Optional[str]:
        """
        Handle special key input.
        
        Args:
            key: Key pressed
            
        Returns:
            Action string or None to continue
        """
        if key == 'q':
            from src.ui import confirm_exit
            if confirm_exit():
                return 'quit'
        elif key == '?' or key == 'h':
            self.show_help()
        elif key == 'b' or key == '←':
            if self.step_number > 1:
                return 'back'
        elif key == 's' and self.is_optional:
            return 'skip'
        
        return None
