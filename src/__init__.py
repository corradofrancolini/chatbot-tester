"""
Chatbot Tester - Core Engine

Moduli disponibili:
- config_loader: Caricamento configurazioni YAML e .env
- tester: Engine principale per testing chatbot
- browser: Wrapper Playwright per automazione browser
- ollama_client: Integrazione LLM locale
- langsmith_client: Integrazione debugging LangSmith
- sheets_client: Integrazione Google Sheets
- report_local: Generazione report HTML/CSV
- ui: Interfaccia CLI con Rich
- i18n: Sistema traduzioni IT/EN
"""

__version__ = "1.0.0"
__author__ = "Chatbot Tester Team"

from .config_loader import (
    ConfigLoader,
    ProjectConfig,
    GlobalSettings,
    load_tests,
    save_tests,
    load_training_data,
    save_training_data
)

from .tester import (
    ChatbotTester,
    TestMode,
    TestCase,
    TestExecution,
    ConversationTurn,
    run_single_test
)

from .browser import (
    BrowserManager,
    BrowserSettings,
    ChatbotSelectors,
    SelectorDetector
)

from .ui import (
    ConsoleUI,
    MenuItem,
    get_ui
)

__all__ = [
    # Config
    'ConfigLoader',
    'ProjectConfig', 
    'GlobalSettings',
    'load_tests',
    'save_tests',
    'load_training_data',
    'save_training_data',
    
    # Tester
    'ChatbotTester',
    'TestMode',
    'TestCase',
    'TestExecution',
    'ConversationTurn',
    'run_single_test',
    
    # Browser
    'BrowserManager',
    'BrowserSettings',
    'ChatbotSelectors',
    'SelectorDetector',
    
    # UI
    'ConsoleUI',
    'MenuItem',
    'get_ui',
]
