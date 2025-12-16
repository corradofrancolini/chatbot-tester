"""
Wizard utility functions.
Provides helpers for validation, state management, and common operations.
"""

import os
import re
import json
import socket
import platform
import subprocess
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field, asdict


# Project root directory
PROJECT_ROOT = Path(__file__).parent.parent


@dataclass
class WizardState:
    """
    Stores the current state of the wizard.
    Persisted to disk between sessions.
    """
    current_step: int = 1
    completed_steps: List[int] = field(default_factory=list)
    started_at: str = ""
    last_updated: str = ""

    # Step data
    project_name: str = ""
    project_description: str = ""
    chatbot_url: str = ""
    needs_login: bool = False
    skip_screenshot: bool = False

    # Selectors
    selectors: Dict[str, str] = field(default_factory=lambda: {
        "textarea": "",
        "submit_button": "",
        "bot_messages": "",
        "thread_container": ""
    })

    # Google Sheets
    google_sheets_enabled: bool = False
    spreadsheet_id: str = ""
    drive_folder_id: str = ""

    # LangSmith
    langsmith_enabled: bool = False
    langsmith_api_key: str = ""
    langsmith_project_id: str = ""
    langsmith_org_id: str = ""
    langsmith_tool_names: List[str] = field(default_factory=list)

    # Ollama
    ollama_enabled: bool = False
    ollama_model: str = "mistral"

    # Tests
    tests: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert state to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'WizardState':
        """Create state from dictionary."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def mark_step_complete(self, step: int) -> None:
        """Mark a step as completed."""
        if step not in self.completed_steps:
            self.completed_steps.append(step)
        self.last_updated = datetime.utcnow().isoformat()

    def is_step_complete(self, step: int) -> bool:
        """Check if a step is complete."""
        return step in self.completed_steps


class StateManager:
    """
    Manages wizard state persistence.
    Saves/loads state to/from JSON file.
    """

    def __init__(self, project_name: str = ""):
        self.project_name = project_name
        self._state: Optional[WizardState] = None

    @property
    def state_file(self) -> Path:
        """Get path to state file."""
        if self.project_name:
            return PROJECT_ROOT / "projects" / self.project_name / ".wizard_state.json"
        return PROJECT_ROOT / ".wizard_state.json"

    def load(self) -> WizardState:
        """Load state from file or create new."""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    data = json.load(f)
                    self._state = WizardState.from_dict(data)
            except (json.JSONDecodeError, TypeError):
                self._state = WizardState()
        else:
            self._state = WizardState()
            self._state.started_at = datetime.utcnow().isoformat()

        return self._state

    def save(self, state: WizardState) -> None:
        """Save state to file."""
        state.last_updated = datetime.utcnow().isoformat()

        # Ensure directory exists
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

        with open(self.state_file, 'w') as f:
            json.dump(state.to_dict(), f, indent=2)

        self._state = state

    def clear(self) -> None:
        """Remove state file."""
        if self.state_file.exists():
            self.state_file.unlink()
        self._state = None

    def has_previous_session(self) -> bool:
        """Check if there's a previous incomplete session."""
        if not self.state_file.exists():
            return False

        state = self.load()
        return state.current_step > 1 and len(state.completed_steps) < 9


# Validators

def validate_project_name(name: str) -> Tuple[bool, str]:
    """
    Validate project name.

    Returns:
        (is_valid, error_message)
    """
    if not name:
        return False, "Il nome non può essere vuoto"

    if len(name) < 2:
        return False, "Il nome deve essere di almeno 2 caratteri"

    if len(name) > 50:
        return False, "Il nome non può superare 50 caratteri"

    if not re.match(r'^[a-z0-9][a-z0-9-]*[a-z0-9]$|^[a-z0-9]$', name):
        return False, "Usa solo lettere minuscole, numeri e trattini"

    # Check if project exists
    project_dir = PROJECT_ROOT / "projects" / name
    if project_dir.exists():
        return False, "Un progetto con questo nome esiste già"

    return True, ""


def validate_url(url: str) -> Tuple[bool, str]:
    """
    Validate URL format.

    Returns:
        (is_valid, error_message)
    """
    if not url:
        return False, "L'URL non può essere vuoto"

    if not re.match(r'^https?://', url):
        return False, "L'URL deve iniziare con http:// o https://"

    # Basic URL pattern
    url_pattern = re.compile(
        r'^https?://'
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'
        r'localhost|'
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
        r'(?::\d+)?'
        r'(?:/?|[/?]\S+)$', re.IGNORECASE
    )

    if not url_pattern.match(url):
        return False, "Formato URL non valido"

    return True, ""


def validate_langsmith_key(key: str) -> bool:
    """Validate LangSmith API key format."""
    return key.startswith('lsv2_sk_') or key.startswith('ls__')


def validate_file_path(path: str, must_exist: bool = True, extensions: Optional[List[str]] = None) -> Tuple[bool, str]:
    """
    Validate file path.

    Returns:
        (is_valid, error_message)
    """
    if not path:
        return False, "Il percorso non può essere vuoto"

    expanded = os.path.expanduser(path)

    if must_exist and not os.path.exists(expanded):
        return False, "File non trovato"

    if extensions:
        ext = os.path.splitext(expanded)[1].lower()
        if ext not in extensions:
            return False, f"Formato non supportato. Usa: {', '.join(extensions)}"

    return True, ""


# System checks

def check_macos_version() -> Tuple[bool, str]:
    """
    Check macOS version.

    Returns:
        (is_ok, version_string)
    """
    if platform.system() != 'Darwin':
        return False, "Non macOS"

    version = platform.mac_ver()[0]
    major = int(version.split('.')[0])

    return major >= 12, version


def check_python_version() -> Tuple[bool, str]:
    """
    Check Python version.

    Returns:
        (is_ok, version_string)
    """
    import sys
    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    is_ok = sys.version_info >= (3, 10)

    return is_ok, version


def check_homebrew() -> bool:
    """Check if Homebrew is installed."""
    return shutil.which('brew') is not None


def check_git() -> Tuple[bool, str]:
    """
    Check Git installation.

    Returns:
        (is_installed, version_string)
    """
    git_path = shutil.which('git')
    if not git_path:
        return False, ""

    try:
        result = subprocess.run(['git', '--version'], capture_output=True, text=True)
        version = result.stdout.strip().replace('git version ', '')
        return True, version
    except:
        return False, ""


def check_disk_space(min_mb: int = 500) -> Tuple[bool, int]:
    """
    Check available disk space.

    Returns:
        (is_enough, available_mb)
    """
    stat = os.statvfs(str(PROJECT_ROOT))
    available_mb = (stat.f_bavail * stat.f_frsize) // (1024 * 1024)

    return available_mb >= min_mb, available_mb


def check_internet() -> bool:
    """Check internet connectivity."""
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=3)
        return True
    except OSError:
        return False


def check_ollama_installed() -> bool:
    """Check if Ollama is installed."""
    return shutil.which('ollama') is not None


def check_ollama_running() -> bool:
    """Check if Ollama server is running."""
    try:
        import requests
        response = requests.get("http://localhost:11434/api/tags", timeout=2)
        return response.status_code == 200
    except:
        return False


def check_ollama_model(model: str = "mistral") -> bool:
    """Check if a specific Ollama model is installed."""
    try:
        import requests
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        if response.status_code == 200:
            models = response.json().get('models', [])
            return any(model in m.get('name', '') for m in models)
    except:
        pass
    return False


# Network helpers

def test_url_reachable(url: str, timeout: int = 10) -> Tuple[bool, int]:
    """
    Test if a URL is reachable.

    Returns:
        (is_reachable, status_code)
    """
    try:
        import requests
        response = requests.head(url, timeout=timeout, allow_redirects=True)
        return True, response.status_code
    except requests.RequestException:
        return False, 0


# File helpers

def get_project_dir(project_name: str) -> Path:
    """Get project directory path."""
    return PROJECT_ROOT / "projects" / project_name


def ensure_project_dirs(project_name: str) -> None:
    """Create project directory structure."""
    project_dir = get_project_dir(project_name)

    dirs = [
        project_dir,
        project_dir / "browser-data",
        PROJECT_ROOT / "reports" / project_name,
    ]

    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)


def save_project_config(state: WizardState) -> None:
    """
    Save project configuration from wizard state.
    Creates project.yaml in the project directory.
    """
    import yaml

    config = {
        'project': {
            'name': state.project_name,
            'description': state.project_description,
            'created': datetime.now().strftime('%Y-%m-%d'),
            'language': 'it'
        },
        'chatbot': {
            'url': state.chatbot_url,
            'selectors': state.selectors,
            'screenshot_css': '',
            'skip_screenshot': state.skip_screenshot,
            'timeouts': {
                'page_load': 30000,
                'bot_response': 60000
            }
        },
        'test_defaults': {
            'email': 'test@example.com',
            'countries': ['Italy', 'Germany', 'France'],
            'confirmations': ['yes', 'no']
        },
        'google_sheets': {
            'enabled': state.google_sheets_enabled,
            'spreadsheet_id': state.spreadsheet_id,
            'drive_folder_id': state.drive_folder_id
        },
        'langsmith': {
            'enabled': state.langsmith_enabled,
            'api_key_env': 'LANGSMITH_API_KEY',
            'project_id': state.langsmith_project_id,
            'org_id': state.langsmith_org_id,
            'tool_names': state.langsmith_tool_names
        },
        'ollama': {
            'enabled': state.ollama_enabled,
            'model': state.ollama_model,
            'url': 'http://localhost:11434/api/generate'
        }
    }

    project_dir = get_project_dir(state.project_name)
    project_dir.mkdir(parents=True, exist_ok=True)

    config_file = project_dir / "project.yaml"
    with open(config_file, 'w') as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def save_tests(project_name: str, tests: List[Dict[str, Any]]) -> None:
    """Save tests to JSON file."""
    project_dir = get_project_dir(project_name)
    tests_file = project_dir / "tests.json"

    with open(tests_file, 'w') as f:
        json.dump(tests, f, indent=2, ensure_ascii=False)


def load_tests_from_file(file_path: str) -> List[Dict[str, Any]]:
    """
    Load tests from various file formats.

    Supports: JSON, CSV, Excel

    Note: For advanced import with field mapping and validation,
    use src.test_importer.TestImporter instead.
    """
    path = Path(file_path)
    ext = path.suffix.lower()

    if ext == '.json':
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # Handle both array and object with 'tests' key
            if isinstance(data, list):
                return data
            elif isinstance(data, dict):
                return data.get('tests', data.get('data', []))
            return []

    elif ext == '.csv':
        import csv
        tests = []
        with open(path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                test = {
                    'id': row.get('id', f"TEST-{len(tests)+1:03d}"),
                    'question': row.get('question', ''),
                    'category': row.get('category', ''),
                    'expected': row.get('expected', ''),
                    'followups': []
                }
                # Collect followup columns
                for key, value in row.items():
                    if key.startswith('followup') and value:
                        test['followups'].append(value)
                # Handle expected_topics
                if 'expected_topics' in row and row['expected_topics']:
                    test['expected_topics'] = [
                        t.strip() for t in row['expected_topics'].split(',') if t.strip()
                    ]
                # Handle tags
                if 'tags' in row and row['tags']:
                    test['tags'] = [
                        t.strip() for t in row['tags'].split(',') if t.strip()
                    ]
                tests.append(test)
        return tests

    elif ext in ['.xlsx', '.xls']:
        import pandas as pd
        df = pd.read_excel(path)
        tests = []
        for _, row in df.iterrows():
            test = {
                'id': str(row.get('id', f"TEST-{len(tests)+1:03d}")),
                'question': str(row.get('question', '')),
                'category': str(row.get('category', '')) if pd.notna(row.get('category')) else '',
                'expected': str(row.get('expected', '')) if pd.notna(row.get('expected')) else '',
                'followups': []
            }
            for col in df.columns:
                if col.startswith('followup') and pd.notna(row[col]):
                    test['followups'].append(str(row[col]))
            # Handle expected_topics
            if 'expected_topics' in df.columns and pd.notna(row.get('expected_topics')):
                topics = str(row['expected_topics'])
                test['expected_topics'] = [t.strip() for t in topics.split(',') if t.strip()]
            # Handle tags
            if 'tags' in df.columns and pd.notna(row.get('tags')):
                tags = str(row['tags'])
                test['tags'] = [t.strip() for t in tags.split(',') if t.strip()]
            tests.append(test)
        return tests

    else:
        raise ValueError(f"Unsupported file format: {ext}")


def load_existing_tests(project_name: str) -> List[Dict[str, Any]]:
    """
    Load existing tests from project's tests.json.

    Args:
        project_name: Name of the project

    Returns:
        List of test dicts, or empty list if no tests exist
    """
    project_dir = get_project_dir(project_name)
    tests_file = project_dir / "tests.json"

    if not tests_file.exists():
        return []

    try:
        with open(tests_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            return []
    except (json.JSONDecodeError, IOError):
        return []


def extract_spreadsheet_id(url_or_id: str) -> str:
    """
    Extract Google Sheets spreadsheet ID from URL or return as-is.

    Args:
        url_or_id: Spreadsheet ID or full Google Sheets URL

    Returns:
        Spreadsheet ID string
    """
    import re

    # If it's already just an ID
    if re.match(r'^[\w\-]+$', url_or_id) and 'google.com' not in url_or_id:
        return url_or_id

    # Extract from URL
    match = re.search(r'/spreadsheets/d/([a-zA-Z0-9_-]+)', url_or_id)
    if match:
        return match.group(1)

    return url_or_id


# CSS Selector patterns for auto-detection

TEXTAREA_SELECTORS = [
    "#llm-prompt-textarea",
    "[data-testid='chat-input']",
    "textarea[placeholder*='message' i]",
    "textarea[placeholder*='type' i]",
    "textarea[placeholder*='ask' i]",
    "textarea[placeholder*='scrivi' i]",
    "textarea[placeholder*='digita' i]",
    ".chat-input textarea",
    "textarea.prompt",
    "form textarea",
    "[contenteditable='true']",
]

SUBMIT_SELECTORS = [
    "button.llm__prompt-submit",
    "button[type='submit']",
    "button[aria-label*='send' i]",
    "button[aria-label*='invia' i]",
    "button:has(svg[class*='send'])",
    ".send-button",
    "button.submit",
    "form button:last-child",
    "[data-testid='send-button']",
]

BOT_MESSAGE_SELECTORS = [
    ".llm__message--assistant .llm__text-body",
    "[data-role='assistant']",
    ".message.assistant",
    ".message.bot",
    ".bot-message",
    ".ai-response",
    "[class*='assistant']",
    "[class*='bot-response']",
    ".chat-message.ai",
]

CONTAINER_SELECTORS = [
    ".chat-thread",
    ".message-list",
    ".conversation",
    "[class*='thread']",
    "[class*='messages']",
    "main",
]
