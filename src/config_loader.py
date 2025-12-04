"""
Config Loader - Caricamento configurazioni YAML e .env

Gestisce:
- Settings globali (settings.yaml)
- Configurazioni progetto (project.yaml)
- Variabili ambiente (.env)
- Validazione e default values
"""

import os
import json
import yaml
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from dotenv import load_dotenv


@dataclass
class SelectorsConfig:
    """Configurazione selettori CSS del chatbot"""
    textarea: str = ""
    submit_button: str = ""
    bot_messages: str = ""
    thread_container: str = ""
    loading_indicator: str = ""


@dataclass
class TimeoutsConfig:
    """Configurazione timeout in millisecondi"""
    page_load: int = 30000
    bot_response: int = 60000


@dataclass
class ChatbotConfig:
    """Configurazione chatbot target"""
    url: str = ""
    selectors: SelectorsConfig = field(default_factory=SelectorsConfig)
    timeouts: TimeoutsConfig = field(default_factory=TimeoutsConfig)
    screenshot_css: str = ""


@dataclass
class TestDefaultsConfig:
    """Valori di default per i test"""
    email: str = ""
    countries: list = field(default_factory=list)
    confirmations: list = field(default_factory=lambda: ["yes", "no"])


@dataclass
class GoogleSheetsConfig:
    """Configurazione Google Sheets"""
    enabled: bool = False
    spreadsheet_id: str = ""
    drive_folder_id: str = ""
    credentials_path: str = ""


@dataclass
class LangSmithConfig:
    """Configurazione LangSmith"""
    enabled: bool = False
    api_key: str = ""
    project_id: str = ""
    org_id: str = ""
    tool_names: list = field(default_factory=list)


@dataclass
class OllamaConfig:
    """Configurazione Ollama LLM"""
    enabled: bool = False
    model: str = "mistral"
    url: str = "http://localhost:11434/api/generate"


@dataclass
class BrowserConfig:
    """Configurazione browser Playwright"""
    headless: bool = False
    viewport_width: int = 1280
    viewport_height: int = 720
    device_scale_factor: int = 2


@dataclass
class ReportConfig:
    """Configurazione report"""
    local_enabled: bool = True
    formats: list = field(default_factory=lambda: ["html", "csv"])


@dataclass
class ProjectConfig:
    """Configurazione completa di un progetto"""
    name: str = ""
    description: str = ""
    language: str = "it"
    created: str = ""
    
    chatbot: ChatbotConfig = field(default_factory=ChatbotConfig)
    test_defaults: TestDefaultsConfig = field(default_factory=TestDefaultsConfig)
    google_sheets: GoogleSheetsConfig = field(default_factory=GoogleSheetsConfig)
    langsmith: LangSmithConfig = field(default_factory=LangSmithConfig)
    ollama: OllamaConfig = field(default_factory=OllamaConfig)
    
    # Paths derivati
    project_dir: Path = field(default_factory=Path)
    tests_file: Path = field(default_factory=Path)
    training_file: Path = field(default_factory=Path)
    run_config_file: Path = field(default_factory=Path)
    browser_data_dir: Path = field(default_factory=Path)


@dataclass
class GlobalSettings:
    """Settings globali dell'applicazione"""
    version: str = "1.0.0"
    language: str = "it"
    browser: BrowserConfig = field(default_factory=BrowserConfig)
    report: ReportConfig = field(default_factory=ReportConfig)
    max_turns: int = 15
    screenshot_on_complete: bool = True
    colors: bool = True
    progress_bar: bool = True


@dataclass
class RunConfig:
    """Configurazione della RUN attiva"""
    env: str = "DEV"
    prompt_version: str = ""
    model_version: str = ""
    active_run: Optional[int] = None
    run_start: Optional[str] = None
    tests_completed: int = 0
    mode: str = "train"
    last_test_id: Optional[str] = None
    # Toggle runtime
    dry_run: bool = False          # Se True, non salva su Google Sheets
    use_langsmith: bool = True     # Se False, disabilita LangSmith
    use_rag: bool = False          # Se True, usa RAG locale
    use_ollama: bool = True        # Se False, disabilita Ollama (solo Train mode)
    
    @classmethod
    def load(cls, file_path: Path) -> 'RunConfig':
        """Carica RunConfig da file JSON con gestione errori"""
        if not file_path.exists():
            return cls()
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return cls(
                env=data.get('env', 'DEV'),
                prompt_version=data.get('prompt_version', ''),
                model_version=data.get('model_version', ''),
                active_run=data.get('active_run'),
                run_start=data.get('run_start'),
                tests_completed=data.get('tests_completed', 0),
                mode=data.get('mode', 'train'),
                last_test_id=data.get('last_test_id'),
                dry_run=data.get('dry_run', False),
                use_langsmith=data.get('use_langsmith', True),
                use_rag=data.get('use_rag', False),
                use_ollama=data.get('use_ollama', True)
            )
        except (json.JSONDecodeError, IOError) as e:
            print(f"! Errore caricamento run_config: {e}")
            return cls()
    
    def save(self, file_path: Path) -> bool:
        """Salva RunConfig su file JSON"""
        try:
            data = {
                'env': self.env,
                'prompt_version': self.prompt_version,
                'model_version': self.model_version,
                'active_run': self.active_run,
                'run_start': self.run_start,
                'tests_completed': self.tests_completed,
                'mode': self.mode,
                'last_test_id': self.last_test_id,
                'dry_run': self.dry_run,
                'use_langsmith': self.use_langsmith,
                'use_rag': self.use_rag,
                'use_ollama': self.use_ollama
            }
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            return True
        except IOError as e:
            print(f"✗ Errore salvataggio run_config: {e}")
            return False
    
    def reset(self) -> None:
        """Reset della RUN attiva (mantiene toggle)"""
        self.active_run = None
        self.run_start = None
        self.tests_completed = 0
        self.last_test_id = None


class ConfigLoader:
    """
    Loader centralizzato per tutte le configurazioni.
    
    Usage:
        loader = ConfigLoader(base_dir="/path/to/chatbot-tester")
        settings = loader.load_global_settings()
        project = loader.load_project("my-project")
    """
    
    def __init__(self, base_dir: Optional[str] = None):
        """
        Inizializza il loader.
        
        Args:
            base_dir: Directory base dell'installazione. Se None, usa la directory corrente.
        """
        if base_dir:
            self.base_dir = Path(base_dir)
        else:
            # Risale dalla directory src/ alla root
            self.base_dir = Path(__file__).parent.parent
        
        self.config_dir = self.base_dir / "config"
        self.projects_dir = self.base_dir / "projects"
        self.reports_dir = self.base_dir / "reports"
        
        # Carica .env se esiste
        env_file = self.config_dir / ".env"
        if env_file.exists():
            load_dotenv(env_file)
    
    def load_global_settings(self) -> GlobalSettings:
        """Carica settings globali da settings.yaml"""
        settings_file = self.config_dir / "settings.yaml"
        
        if not settings_file.exists():
            return GlobalSettings()
        
        with open(settings_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}
        
        settings = GlobalSettings()
        
        # App settings
        app = data.get('app', {})
        settings.version = app.get('version', settings.version)
        settings.language = app.get('language', settings.language)
        
        # Browser settings
        browser = data.get('browser', {})
        settings.browser.headless = browser.get('headless', False)
        viewport = browser.get('viewport', {})
        settings.browser.viewport_width = viewport.get('width', 1280)
        settings.browser.viewport_height = viewport.get('height', 720)
        settings.browser.device_scale_factor = browser.get('device_scale_factor', 2)
        
        # Test settings
        test = data.get('test', {})
        settings.max_turns = test.get('max_turns', 15)
        settings.screenshot_on_complete = test.get('screenshot_on_complete', True)
        
        # Report settings
        reports = data.get('reports', {})
        local = reports.get('local', {})
        settings.report.local_enabled = local.get('enabled', True)
        settings.report.formats = local.get('format', ['html', 'csv'])
        
        # UI settings
        ui = data.get('ui', {})
        settings.colors = ui.get('colors', True)
        settings.progress_bar = ui.get('progress_bar', True)
        
        return settings
    
    def load_project(self, project_name: str) -> ProjectConfig:
        """
        Carica configurazione di un progetto specifico.
        
        Args:
            project_name: Nome del progetto
            
        Returns:
            ProjectConfig con tutte le impostazioni
            
        Raises:
            FileNotFoundError: Se il progetto non esiste
            ValueError: Se la configurazione è invalida
        """
        project_dir = self.projects_dir / project_name
        config_file = project_dir / "project.yaml"
        
        if not config_file.exists():
            raise FileNotFoundError(f"Progetto '{project_name}' non trovato in {project_dir}")
        
        with open(config_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}
        
        config = ProjectConfig()
        
        # Info progetto
        project = data.get('project', {})
        config.name = project.get('name', project_name)
        config.description = project.get('description', '')
        config.language = project.get('language', 'it')
        config.created = project.get('created', '')
        
        # Chatbot config
        chatbot = data.get('chatbot', {})
        config.chatbot.url = chatbot.get('url', '')
        
        selectors = chatbot.get('selectors', {})
        config.chatbot.selectors = SelectorsConfig(
            textarea=selectors.get('textarea', ''),
            submit_button=selectors.get('submit_button', ''),
            bot_messages=selectors.get('bot_messages', ''),
            thread_container=selectors.get('thread_container', ''),
            loading_indicator=selectors.get('loading_indicator', '')
        )
        
        timeouts = chatbot.get('timeouts', {})
        config.chatbot.timeouts = TimeoutsConfig(
            page_load=timeouts.get('page_load', 30000),
            bot_response=timeouts.get('bot_response', 60000)
        )
        
        config.chatbot.screenshot_css = chatbot.get('screenshot_css', '')
        
        # Test defaults
        defaults = data.get('test_defaults', {})
        config.test_defaults = TestDefaultsConfig(
            email=defaults.get('email', ''),
            countries=defaults.get('countries', []),
            confirmations=defaults.get('confirmations', ['yes', 'no'])
        )
        
        # Google Sheets
        sheets = data.get('google_sheets', {})
        config.google_sheets = GoogleSheetsConfig(
            enabled=sheets.get('enabled', False),
            spreadsheet_id=sheets.get('spreadsheet_id', ''),
            drive_folder_id=sheets.get('drive_folder_id', ''),
            credentials_path=os.getenv('GOOGLE_OAUTH_CREDENTIALS', '')
        )
        
        # LangSmith
        ls = data.get('langsmith', {})
        api_key_env = ls.get('api_key_env', 'LANGSMITH_API_KEY')
        config.langsmith = LangSmithConfig(
            enabled=ls.get('enabled', False),
            api_key=os.getenv(api_key_env, ''),
            project_id=ls.get('project_id', ''),
            org_id=ls.get('org_id', ''),
            tool_names=ls.get('tool_names', [])
        )
        
        # Ollama
        ollama = data.get('ollama', {})
        config.ollama = OllamaConfig(
            enabled=ollama.get('enabled', False),
            model=ollama.get('model', 'mistral'),
            url=ollama.get('url', 'http://localhost:11434/api/generate')
        )
        
        # Paths derivati
        config.project_dir = project_dir
        config.tests_file = project_dir / "tests.json"
        config.training_file = project_dir / "training_data.json"
        config.run_config_file = project_dir / "run_config.json"
        config.browser_data_dir = project_dir / "browser-data"
        
        return config
    
    def list_projects(self) -> list[str]:
        """Ritorna lista dei progetti disponibili"""
        if not self.projects_dir.exists():
            return []
        
        projects = []
        for item in self.projects_dir.iterdir():
            if item.is_dir() and (item / "project.yaml").exists():
                projects.append(item.name)
        
        return sorted(projects)
    
    def project_exists(self, project_name: str) -> bool:
        """Verifica se un progetto esiste"""
        return (self.projects_dir / project_name / "project.yaml").exists()
    
    def save_project(self, config: ProjectConfig) -> None:
        """
        Salva la configurazione di un progetto.
        
        Args:
            config: ProjectConfig da salvare
        """
        project_dir = self.projects_dir / config.name
        project_dir.mkdir(parents=True, exist_ok=True)
        
        # Crea browser-data directory
        (project_dir / "browser-data").mkdir(exist_ok=True)
        
        # Costruisci il dizionario YAML
        data = {
            'project': {
                'name': config.name,
                'description': config.description,
                'created': config.created,
                'language': config.language
            },
            'chatbot': {
                'url': config.chatbot.url,
                'selectors': {
                    'textarea': config.chatbot.selectors.textarea,
                    'submit_button': config.chatbot.selectors.submit_button,
                    'bot_messages': config.chatbot.selectors.bot_messages,
                    'thread_container': config.chatbot.selectors.thread_container
                },
                'timeouts': {
                    'page_load': config.chatbot.timeouts.page_load,
                    'bot_response': config.chatbot.timeouts.bot_response
                },
                'screenshot_css': config.chatbot.screenshot_css
            },
            'test_defaults': {
                'email': config.test_defaults.email,
                'countries': config.test_defaults.countries,
                'confirmations': config.test_defaults.confirmations
            },
            'google_sheets': {
                'enabled': config.google_sheets.enabled,
                'spreadsheet_id': config.google_sheets.spreadsheet_id,
                'drive_folder_id': config.google_sheets.drive_folder_id
            },
            'langsmith': {
                'enabled': config.langsmith.enabled,
                'api_key_env': 'LANGSMITH_API_KEY',
                'project_id': config.langsmith.project_id,
                'org_id': config.langsmith.org_id,
                'tool_names': config.langsmith.tool_names
            },
            'ollama': {
                'enabled': config.ollama.enabled,
                'model': config.ollama.model,
                'url': config.ollama.url
            }
        }
        
        config_file = project_dir / "project.yaml"
        with open(config_file, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    
    def get_report_dir(self, project_name: str, run_number: Optional[int] = None) -> Path:
        """
        Ottiene la directory per i report di un progetto.
        
        Args:
            project_name: Nome del progetto
            run_number: Numero run (opzionale, se None crea nuovo)
            
        Returns:
            Path alla directory del report
        """
        project_reports = self.reports_dir / project_name
        project_reports.mkdir(parents=True, exist_ok=True)
        
        if run_number is None:
            # Trova il prossimo numero run
            existing = [d for d in project_reports.iterdir() if d.is_dir() and d.name.startswith('run_')]
            if existing:
                numbers = [int(d.name.replace('run_', '')) for d in existing]
                run_number = max(numbers) + 1
            else:
                run_number = 1
        
        run_dir = project_reports / f"run_{run_number:03d}"
        run_dir.mkdir(exist_ok=True)
        (run_dir / "screenshots").mkdir(exist_ok=True)
        
        return run_dir


def load_tests(tests_file: Path) -> list[dict]:
    """
    Carica i test cases da file JSON.
    
    Args:
        tests_file: Path al file tests.json
        
    Returns:
        Lista di test cases
    """
    import json
    
    if not tests_file.exists():
        return []
    
    with open(tests_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_tests(tests_file: Path, tests: list[dict]) -> None:
    """
    Salva i test cases su file JSON.
    
    Args:
        tests_file: Path al file tests.json
        tests: Lista di test cases
    """
    import json
    
    with open(tests_file, 'w', encoding='utf-8') as f:
        json.dump(tests, f, indent=2, ensure_ascii=False)


def load_training_data(training_file: Path) -> dict:
    """
    Carica i dati di training.
    
    Args:
        training_file: Path al file training_data.json
        
    Returns:
        Dizionario con dati training
    """
    import json
    
    if not training_file.exists():
        return {"patterns": [], "examples": []}
    
    with open(training_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_training_data(training_file: Path, data: dict) -> None:
    """
    Salva i dati di training.
    
    Args:
        training_file: Path al file training_data.json
        data: Dizionario con dati training
    """
    import json
    
    with open(training_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
