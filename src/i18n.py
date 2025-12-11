"""
Internationalization (i18n) - Sistema traduzioni IT/EN

Gestisce:
- Traduzioni per l'interfaccia utente
- Supporto italiano (default) e inglese
- Caricamento da file YAML
- Fallback a chiave se traduzione mancante
"""

from pathlib import Path
from typing import Optional, Dict, Any
import yaml


# Traduzioni integrate (fallback se file YAML non disponibili)
TRANSLATIONS = {
    'it': {
        # Generale
        'app_name': 'Chatbot Tester',
        'welcome': 'Benvenuto in Chatbot Tester',
        'goodbye': 'Arrivederci!',
        'yes': 'Sì',
        'no': 'No',
        'back': 'Indietro',
        'next': 'Avanti',
        'skip': 'Salta',
        'cancel': 'Annulla',
        'confirm': 'Conferma',
        'save': 'Salva',
        'exit': 'Esci',
        'help': 'Aiuto',
        'error': 'Errore',
        'warning': 'Attenzione',
        'success': 'Successo',
        'loading': 'Caricamento...',
        'processing': 'Elaborazione...',
        'done': 'Fatto',
        'recommended': 'raccomandato',
        'optional': 'opzionale',
        'required': 'richiesto',
        
        # Menu principale
        'menu_new_project': 'Nuovo progetto',
        'menu_open_project': 'Apri progetto esistente',
        'menu_settings': 'Impostazioni',
        'menu_help': 'Guida',
        'menu_exit': 'Esci',
        
        # Modalità test
        'mode_train': 'Train',
        'mode_train_desc': 'Apprendimento da interazione umana',
        'mode_assisted': 'Assisted',
        'mode_assisted_desc': 'LLM con supervisione umana',
        'mode_auto': 'Auto',
        'mode_auto_desc': 'Test completamente automatici',
        
        # Wizard - Titoli step
        'wizard_step_prerequisites': 'Verifica Prerequisiti',
        'wizard_step_project_info': 'Informazioni Progetto',
        'wizard_step_chatbot_url': 'URL Chatbot',
        'wizard_step_selectors': 'Rilevamento Selettori',
        'wizard_step_google_sheets': 'Google Sheets',
        'wizard_step_langsmith': 'LangSmith',
        'wizard_step_ollama': 'Ollama LLM',
        'wizard_step_test_cases': 'Test Cases',
        'wizard_step_summary': 'Riepilogo',
        
        # Wizard - Descrizioni step
        'wizard_desc_prerequisites': 'Verifichiamo che il sistema abbia tutto il necessario',
        'wizard_desc_project_info': 'Dai un nome al tuo progetto di test',
        'wizard_desc_chatbot_url': 'Indica dove si trova il chatbot da testare',
        'wizard_desc_selectors': 'Identifichiamo gli elementi UI del chatbot',
        'wizard_desc_google_sheets': 'Configura report su Google Sheets (opzionale)',
        'wizard_desc_langsmith': 'Configura integrazione debugging LangSmith (opzionale)',
        'wizard_desc_ollama': 'Configura LLM locale per modalità Assisted/Auto (opzionale)',
        'wizard_desc_test_cases': 'Importa o crea i tuoi test cases',
        'wizard_desc_summary': 'Rivedi le impostazioni prima di salvare',
        
        # Wizard - Messaggi
        'wizard_time_remaining': '~{minutes} min rimanenti',
        'wizard_session_found': 'Trovata sessione precedente (step {current}/{total})',
        'wizard_session_continue': 'Continua da dove eri',
        'wizard_session_restart': 'Ricomincia da capo',
        
        # Prerequisiti
        'prereq_checking': 'Verifica prerequisiti in corso...',
        'prereq_macos': 'Sistema operativo macOS',
        'prereq_python': 'Python {version}+',
        'prereq_homebrew': 'Homebrew installato',
        'prereq_git': 'Git installato',
        'prereq_disk_space': 'Spazio disco ({required} richiesti)',
        'prereq_internet': 'Connessione internet',
        'prereq_all_ok': 'Tutti i prerequisiti soddisfatti!',
        'prereq_missing': 'Prerequisiti mancanti',
        
        # Progetto
        'project_name_prompt': 'Nome progetto (es. my-chatbot)',
        'project_name_invalid': 'Nome non valido. Usa solo lettere, numeri e trattini.',
        'project_name_exists': 'Un progetto con questo nome esiste già',
        'project_description_prompt': 'Descrizione (opzionale)',
        
        # URL Chatbot
        'url_prompt': 'URL completo del chatbot',
        'url_invalid': 'Formato URL non valido',
        'url_testing': 'Test connessione in corso...',
        'url_reachable': 'URL raggiungibile',
        'url_unreachable': 'URL non raggiungibile',
        'url_login_required': 'Login richiesto',
        'url_login_waiting': 'Effettua il login nel browser...',
        'url_login_timeout': 'Timeout login scaduto',
        'url_login_success': 'Login completato!',
        
        # Selettori
        'selectors_auto_detecting': 'Rilevamento automatico selettori...',
        'selectors_found': 'Selettori rilevati automaticamente',
        'selectors_not_found': 'Alcuni selettori non rilevati',
        'selectors_click_learn': 'Apprendimento da click',
        'selectors_click_textarea': 'Clicca sul campo di input (textarea)',
        'selectors_click_submit': 'Clicca sul bottone invio',
        'selectors_click_bot_message': 'Clicca su un messaggio del bot',
        'selectors_manual': 'Inserisci manualmente',
        'selectors_confirm': 'Conferma selettori',
        
        # Google Sheets
        'sheets_skip': 'Solo report locale (salta)',
        'sheets_configure': 'Configura Google Sheets',
        'sheets_later': 'Configuro dopo',
        'sheets_credentials_prompt': 'Path al file credentials OAuth',
        'sheets_spreadsheet_prompt': 'ID o URL dello Spreadsheet',
        'sheets_folder_prompt': 'ID o URL cartella Drive per screenshot',
        'sheets_testing': 'Test connessione Google...',
        'sheets_auth_required': 'Autorizzazione richiesta nel browser',
        'sheets_connected': 'Google Sheets connesso!',
        'sheets_error': 'Errore connessione Google Sheets',
        
        # LangSmith
        'langsmith_skip': 'Non uso LangSmith',
        'langsmith_configure': 'Configura LangSmith',
        'langsmith_later': 'Configuro dopo',
        'langsmith_api_key_prompt': 'API Key LangSmith',
        'langsmith_project_prompt': 'Project ID (dalla URL)',
        'langsmith_org_prompt': 'Org ID (opzionale)',
        'langsmith_testing': 'Test connessione LangSmith...',
        'langsmith_connected': 'LangSmith connesso!',
        'langsmith_detecting_tools': 'Rilevamento tool names...',
        'langsmith_tools_found': 'Tools rilevati: {tools}',
        
        # Ollama
        'ollama_skip': 'Skip (solo modalità Train)',
        'ollama_install': 'Installa Ollama + Mistral',
        'ollama_configure': 'Già installato, configura',
        'ollama_checking': 'Verifica Ollama...',
        'ollama_not_installed': 'Ollama non installato',
        'ollama_not_running': 'Ollama non in esecuzione',
        'ollama_model_missing': 'Modello {model} non disponibile',
        'ollama_ready': 'Ollama pronto con {model}',
        'ollama_installing': 'Installazione Ollama...',
        'ollama_pulling_model': 'Download modello {model}...',
        
        # Test Cases
        'tests_import': 'Importa da file (JSON/CSV/Excel)',
        'tests_create': 'Crea manualmente',
        'tests_skip': 'Inizia senza test (li aggiungo dopo)',
        'tests_file_prompt': 'Path al file da importare',
        'tests_file_invalid': 'Formato file non supportato',
        'tests_imported': '{count} test importati',
        'tests_create_question': 'Domanda da testare',
        'tests_create_followups': 'Followup (uno per riga, vuoto per finire)',
        'tests_create_another': 'Aggiungere un altro test?',
        'tests_created': '{count} test creati',
        
        # Riepilogo
        'summary_title': 'Riepilogo Configurazione',
        'summary_project': 'Progetto',
        'summary_chatbot': 'Chatbot URL',
        'summary_selectors': 'Selettori',
        'summary_google_sheets': 'Google Sheets',
        'summary_langsmith': 'LangSmith',
        'summary_ollama': 'Ollama',
        'summary_tests': 'Test Cases',
        'summary_save': 'Salvare la configurazione?',
        'summary_saved': 'Configurazione salvata!',
        'summary_start_now': 'Avviare il tool ora?',
        
        # Test execution
        'test_starting': 'Avvio sessione di test...',
        'test_progress': 'Test {current}/{total}',
        'test_sending': 'Invio domanda...',
        'test_waiting': 'Attesa risposta...',
        'test_screenshot': 'Cattura screenshot...',
        'test_evaluating': 'Valutazione risposta...',
        'test_complete': 'Test completato',
        'test_skipped': 'Test saltato (già completato)',
        'test_error': 'Errore durante il test',
        'test_passed': 'PASS',
        'test_failed': 'FAIL',
        
        # Report
        'report_generating': 'Generazione report...',
        'report_saved': 'Report salvato in: {path}',
        'report_uploaded': 'Report caricato su Google Sheets',
        
        # Errori
        'error_generic': 'Si è verificato un errore',
        'error_connection': 'Errore di connessione',
        'error_timeout': 'Timeout operazione',
        'error_file_not_found': 'File non trovato',
        'error_invalid_config': 'Configurazione non valida',
        'error_browser': 'Errore browser',
        'error_auth': 'Errore autenticazione',
    },
    
    'en': {
        # General
        'app_name': 'Chatbot Tester',
        'welcome': 'Welcome to Chatbot Tester',
        'goodbye': 'Goodbye!',
        'yes': 'Yes',
        'no': 'No',
        'back': 'Back',
        'next': 'Next',
        'skip': 'Skip',
        'cancel': 'Cancel',
        'confirm': 'Confirm',
        'save': 'Save',
        'exit': 'Exit',
        'help': 'Help',
        'error': 'Error',
        'warning': 'Warning',
        'success': 'Success',
        'loading': 'Loading...',
        'processing': 'Processing...',
        'done': 'Done',
        'recommended': 'recommended',
        'optional': 'optional',
        'required': 'required',
        
        # Main menu
        'menu_new_project': 'New project',
        'menu_open_project': 'Open existing project',
        'menu_settings': 'Settings',
        'menu_help': 'Help',
        'menu_exit': 'Exit',
        
        # Test modes
        'mode_train': 'Train',
        'mode_train_desc': 'Learning from human interaction',
        'mode_assisted': 'Assisted',
        'mode_assisted_desc': 'LLM with human supervision',
        'mode_auto': 'Auto',
        'mode_auto_desc': 'Fully automated testing',
        
        # Wizard - Step titles
        'wizard_step_prerequisites': 'Check Prerequisites',
        'wizard_step_project_info': 'Project Information',
        'wizard_step_chatbot_url': 'Chatbot URL',
        'wizard_step_selectors': 'Selector Detection',
        'wizard_step_google_sheets': 'Google Sheets',
        'wizard_step_langsmith': 'LangSmith',
        'wizard_step_ollama': 'Ollama LLM',
        'wizard_step_test_cases': 'Test Cases',
        'wizard_step_summary': 'Summary',
        
        # Wizard - Step descriptions
        'wizard_desc_prerequisites': "Let's verify your system has everything needed",
        'wizard_desc_project_info': 'Give your test project a name',
        'wizard_desc_chatbot_url': 'Specify where the chatbot to test is located',
        'wizard_desc_selectors': "Let's identify the chatbot UI elements",
        'wizard_desc_google_sheets': 'Configure Google Sheets reporting (optional)',
        'wizard_desc_langsmith': 'Configure LangSmith debugging integration (optional)',
        'wizard_desc_ollama': 'Configure local LLM for Assisted/Auto modes (optional)',
        'wizard_desc_test_cases': 'Import or create your test cases',
        'wizard_desc_summary': 'Review settings before saving',
        
        # Wizard - Messages
        'wizard_time_remaining': '~{minutes} min remaining',
        'wizard_session_found': 'Previous session found (step {current}/{total})',
        'wizard_session_continue': 'Continue where you left off',
        'wizard_session_restart': 'Start over',
        
        # Prerequisites
        'prereq_checking': 'Checking prerequisites...',
        'prereq_macos': 'macOS operating system',
        'prereq_python': 'Python {version}+',
        'prereq_homebrew': 'Homebrew installed',
        'prereq_git': 'Git installed',
        'prereq_disk_space': 'Disk space ({required} required)',
        'prereq_internet': 'Internet connection',
        'prereq_all_ok': 'All prerequisites satisfied!',
        'prereq_missing': 'Missing prerequisites',
        
        # Project
        'project_name_prompt': 'Project name (e.g. my-chatbot)',
        'project_name_invalid': 'Invalid name. Use only letters, numbers and hyphens.',
        'project_name_exists': 'A project with this name already exists',
        'project_description_prompt': 'Description (optional)',
        
        # URL Chatbot
        'url_prompt': 'Full chatbot URL',
        'url_invalid': 'Invalid URL format',
        'url_testing': 'Testing connection...',
        'url_reachable': 'URL reachable',
        'url_unreachable': 'URL unreachable',
        'url_login_required': 'Login required',
        'url_login_waiting': 'Please login in the browser...',
        'url_login_timeout': 'Login timeout expired',
        'url_login_success': 'Login completed!',
        
        # Selectors
        'selectors_auto_detecting': 'Auto-detecting selectors...',
        'selectors_found': 'Selectors detected automatically',
        'selectors_not_found': 'Some selectors not detected',
        'selectors_click_learn': 'Learn from click',
        'selectors_click_textarea': 'Click on the input field (textarea)',
        'selectors_click_submit': 'Click on the submit button',
        'selectors_click_bot_message': 'Click on a bot message',
        'selectors_manual': 'Enter manually',
        'selectors_confirm': 'Confirm selectors',
        
        # Google Sheets
        'sheets_skip': 'Local report only (skip)',
        'sheets_configure': 'Configure Google Sheets',
        'sheets_later': 'Configure later',
        'sheets_credentials_prompt': 'Path to OAuth credentials file',
        'sheets_spreadsheet_prompt': 'Spreadsheet ID or URL',
        'sheets_folder_prompt': 'Drive folder ID or URL for screenshots',
        'sheets_testing': 'Testing Google connection...',
        'sheets_auth_required': 'Authorization required in browser',
        'sheets_connected': 'Google Sheets connected!',
        'sheets_error': 'Google Sheets connection error',
        
        # LangSmith
        'langsmith_skip': "I don't use LangSmith",
        'langsmith_configure': 'Configure LangSmith',
        'langsmith_later': 'Configure later',
        'langsmith_api_key_prompt': 'LangSmith API Key',
        'langsmith_project_prompt': 'Project ID (from URL)',
        'langsmith_org_prompt': 'Org ID (optional)',
        'langsmith_testing': 'Testing LangSmith connection...',
        'langsmith_connected': 'LangSmith connected!',
        'langsmith_detecting_tools': 'Detecting tool names...',
        'langsmith_tools_found': 'Tools detected: {tools}',
        
        # Ollama
        'ollama_skip': 'Skip (Train mode only)',
        'ollama_install': 'Install Ollama + Mistral',
        'ollama_configure': 'Already installed, configure',
        'ollama_checking': 'Checking Ollama...',
        'ollama_not_installed': 'Ollama not installed',
        'ollama_not_running': 'Ollama not running',
        'ollama_model_missing': 'Model {model} not available',
        'ollama_ready': 'Ollama ready with {model}',
        'ollama_installing': 'Installing Ollama...',
        'ollama_pulling_model': 'Downloading model {model}...',
        
        # Test Cases
        'tests_import': 'Import from file (JSON/CSV/Excel)',
        'tests_create': 'Create manually',
        'tests_skip': 'Start without tests (add later)',
        'tests_file_prompt': 'Path to file to import',
        'tests_file_invalid': 'Unsupported file format',
        'tests_imported': '{count} tests imported',
        'tests_create_question': 'Question to test',
        'tests_create_followups': 'Followups (one per line, empty to finish)',
        'tests_create_another': 'Add another test?',
        'tests_created': '{count} tests created',
        
        # Summary
        'summary_title': 'Configuration Summary',
        'summary_project': 'Project',
        'summary_chatbot': 'Chatbot URL',
        'summary_selectors': 'Selectors',
        'summary_google_sheets': 'Google Sheets',
        'summary_langsmith': 'LangSmith',
        'summary_ollama': 'Ollama',
        'summary_tests': 'Test Cases',
        'summary_save': 'Save configuration?',
        'summary_saved': 'Configuration saved!',
        'summary_start_now': 'Start the tool now?',
        
        # Test execution
        'test_starting': 'Starting test session...',
        'test_progress': 'Test {current}/{total}',
        'test_sending': 'Sending question...',
        'test_waiting': 'Waiting for response...',
        'test_screenshot': 'Capturing screenshot...',
        'test_evaluating': 'Evaluating response...',
        'test_complete': 'Test completed',
        'test_skipped': 'Test skipped (already completed)',
        'test_error': 'Error during test',
        'test_passed': 'PASS',
        'test_failed': 'FAIL',
        
        # Report
        'report_generating': 'Generating report...',
        'report_saved': 'Report saved to: {path}',
        'report_uploaded': 'Report uploaded to Google Sheets',
        
        # Errors
        'error_generic': 'An error occurred',
        'error_connection': 'Connection error',
        'error_timeout': 'Operation timeout',
        'error_file_not_found': 'File not found',
        'error_invalid_config': 'Invalid configuration',
        'error_browser': 'Browser error',
        'error_auth': 'Authentication error',
    }
}


class I18n:
    """
    Gestore traduzioni.
    
    Usage:
        i18n = I18n('it')  # o 'en'
        
        # Traduzione semplice
        msg = i18n.t('welcome')
        
        # Con interpolazione
        msg = i18n.t('test_progress', current=1, total=10)
        
        # Cambio lingua
        i18n.set_language('en')
    """
    
    def __init__(self, language: str = 'it', locales_dir: Optional[Path] = None):
        """
        Inizializza il gestore traduzioni.
        
        Args:
            language: Codice lingua ('it' o 'en')
            locales_dir: Directory file YAML traduzioni (opzionale)
        """
        self.language = language
        self.locales_dir = locales_dir
        self._translations: Dict[str, str] = {}
        
        self._load_translations()
    
    def _load_translations(self) -> None:
        """Carica le traduzioni per la lingua corrente"""
        # Prima prova da file YAML
        if self.locales_dir:
            yaml_file = self.locales_dir / f"{self.language}.yaml"
            if yaml_file.exists():
                try:
                    with open(yaml_file, 'r', encoding='utf-8') as f:
                        self._translations = yaml.safe_load(f) or {}
                        return
                except:
                    pass
        
        # Fallback a traduzioni integrate
        self._translations = TRANSLATIONS.get(self.language, TRANSLATIONS['it']).copy()
    
    def set_language(self, language: str) -> None:
        """
        Cambia lingua.
        
        Args:
            language: Codice lingua ('it' o 'en')
        """
        if language in ['it', 'en']:
            self.language = language
            self._load_translations()
    
    def t(self, key: str, **kwargs) -> str:
        """
        Ottiene una traduzione.

        Args:
            key: Chiave traduzione (supporta dot notation, es. 'main_menu.new_project')
            **kwargs: Valori per interpolazione

        Returns:
            Testo tradotto
        """
        # Supporta chiavi nidificate con dot notation
        text = self._get_nested(key)

        # Interpolazione
        if kwargs:
            try:
                text = text.format(**kwargs)
            except KeyError:
                pass

        return text

    def _get_nested(self, key: str) -> str:
        """
        Recupera un valore da una struttura nidificata usando dot notation.

        Args:
            key: Chiave con dot notation (es. 'main_menu.new_project')

        Returns:
            Valore trovato o la chiave stessa come fallback
        """
        # Prima prova chiave diretta (per compatibilità con traduzioni flat)
        if key in self._translations:
            value = self._translations[key]
            if isinstance(value, str):
                return value

        # Poi prova navigazione nidificata
        parts = key.split('.')
        current = self._translations

        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                # Chiave non trovata, ritorna la chiave stessa
                return key

        if isinstance(current, str):
            return current

        # Se il risultato non è una stringa, ritorna la chiave
        return key
    
    def __call__(self, key: str, **kwargs) -> str:
        """Shortcut per t()"""
        return self.t(key, **kwargs)
    
    @property
    def available_languages(self) -> list[str]:
        """Lingue disponibili"""
        return ['it', 'en']
    
    def get_all_translations(self) -> Dict[str, str]:
        """Ritorna tutte le traduzioni correnti"""
        return self._translations.copy()


# Istanza globale
_i18n: Optional[I18n] = None


def get_i18n(language: str = 'it') -> I18n:
    """Ottiene l'istanza i18n globale"""
    global _i18n
    if _i18n is None:
        # Trova automaticamente la directory locales
        locales_dir = Path(__file__).parent.parent / 'locales'
        if locales_dir.exists():
            _i18n = I18n(language, locales_dir)
        else:
            _i18n = I18n(language)
    return _i18n


def set_language(language: str) -> None:
    """Imposta la lingua globale"""
    global _i18n
    if _i18n is None:
        # Trova automaticamente la directory locales
        locales_dir = Path(__file__).parent.parent / 'locales'
        if locales_dir.exists():
            _i18n = I18n(language, locales_dir)
        else:
            _i18n = I18n(language)
    else:
        _i18n.set_language(language)


def t(key: str, **kwargs) -> str:
    """Shortcut globale per traduzione"""
    return get_i18n().t(key, **kwargs)
