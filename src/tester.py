"""
Core Tester - Engine principale per testing chatbot

Gestisce:
- Modalità Train, Assisted, Auto
- Esecuzione test con followups
- Integrazione con tutti i client (browser, LLM, report)
- Orchestrazione completa del flusso di test
"""

import asyncio
import json
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum

from .config_loader import (
    ConfigLoader, ProjectConfig, GlobalSettings,
    load_tests, save_tests, load_training_data, save_training_data
)
from .browser import BrowserManager, BrowserSettings, ChatbotSelectors
from .ollama_client import OllamaClient
from .langsmith_client import LangSmithClient, LangSmithDebugger
from .sheets_client import GoogleSheetsClient, TestResult
from .report_local import ReportGenerator, TestResultLocal


class TestMode(Enum):
    """Modalità di test disponibili"""
    TRAIN = "train"       # Apprendimento da interazione umana
    ASSISTED = "assisted"  # LLM con supervisione umana
    AUTO = "auto"         # Completamente automatico


@dataclass
class TestCase:
    """Definizione di un test case"""
    id: str
    question: str
    category: str = ""
    expected: str = ""
    followups: List[str] = field(default_factory=list)
    data: Dict[str, Any] = field(default_factory=dict)  # email, country, etc.
    tags: List[str] = field(default_factory=list)


@dataclass
class ConversationTurn:
    """Singolo turno di conversazione"""
    role: str  # 'user' o 'assistant'
    content: str
    timestamp: str = ""


@dataclass
class TestExecution:
    """Risultato esecuzione di un test"""
    test_case: TestCase
    conversation: List[ConversationTurn]
    esito: str  # PASS, FAIL, SKIP, ERROR
    duration_ms: int
    screenshot_path: str = ""
    langsmith_url: str = ""
    notes: str = ""
    llm_evaluation: Optional[Dict] = None


class ChatbotTester:
    """
    Engine principale per testing chatbot.
    
    Supporta tre modalità:
    - TRAIN: L'utente interagisce, il sistema impara
    - ASSISTED: LLM propone, utente conferma/corregge
    - AUTO: LLM gestisce tutto automaticamente
    
    Usage:
        tester = ChatbotTester(project_config, global_settings)
        
        # Modalità train
        await tester.run_train_session(test_cases)
        
        # Modalità auto
        await tester.run_auto_session(test_cases)
    """
    
    def __init__(self, 
                 project: ProjectConfig,
                 settings: GlobalSettings,
                 on_status: Optional[Callable[[str], None]] = None,
                 on_progress: Optional[Callable[[int, int], None]] = None):
        """
        Inizializza il tester.
        
        Args:
            project: Configurazione progetto
            settings: Settings globali
            on_status: Callback per messaggi di stato
            on_progress: Callback per progresso (current, total)
        """
        self.project = project
        self.settings = settings
        self.on_status = on_status or print
        self.on_progress = on_progress or (lambda c, t: None)
        
        # Browser
        self.browser: Optional[BrowserManager] = None
        
        # Clients opzionali
        self.ollama: Optional[OllamaClient] = None
        self.langsmith: Optional[LangSmithClient] = None
        self.sheets: Optional[GoogleSheetsClient] = None
        
        # Report locale
        self.report: Optional[ReportGenerator] = None
        
        # Stato
        self.current_mode: TestMode = TestMode.TRAIN
        self.completed_tests: set = set()
        self.current_test: Optional[TestCase] = None
        
        # Training data
        self.training_data: Dict = {"patterns": [], "examples": []}
    
    async def initialize(self) -> bool:
        """
        Inizializza tutti i componenti.
        
        Returns:
            True se inizializzazione riuscita
        """
        self.on_status("🔧 Inizializzazione componenti...")
        
        # Browser
        browser_settings = BrowserSettings(
            headless=self.settings.browser.headless,
            viewport_width=self.settings.browser.viewport_width,
            viewport_height=self.settings.browser.viewport_height,
            device_scale_factor=self.settings.browser.device_scale_factor,
            user_data_dir=self.project.browser_data_dir,
            timeout_page_load=self.project.chatbot.timeouts.page_load,
            timeout_bot_response=self.project.chatbot.timeouts.bot_response
        )
        
        selectors = ChatbotSelectors(
            textarea=self.project.chatbot.selectors.textarea,
            submit_button=self.project.chatbot.selectors.submit_button,
            bot_messages=self.project.chatbot.selectors.bot_messages,
            thread_container=self.project.chatbot.selectors.thread_container
        )
        
        self.browser = BrowserManager(browser_settings, selectors)
        
        try:
            await self.browser.start()
            self.on_status("✅ Browser avviato")
        except Exception as e:
            self.on_status(f"❌ Errore browser: {e}")
            return False
        
        # Ollama (opzionale)
        if self.project.ollama.enabled:
            self.ollama = OllamaClient(
                model=self.project.ollama.model,
                url=self.project.ollama.url
            )
            if self.ollama.is_available():
                self.on_status(f"✅ Ollama ({self.project.ollama.model}) disponibile")
            else:
                self.on_status("⚠️ Ollama non disponibile")
                self.ollama = None
        
        # LangSmith (opzionale)
        if self.project.langsmith.enabled and self.project.langsmith.api_key:
            self.langsmith = LangSmithClient(
                api_key=self.project.langsmith.api_key,
                project_id=self.project.langsmith.project_id,
                org_id=self.project.langsmith.org_id,
                tool_names=self.project.langsmith.tool_names
            )
            if self.langsmith.is_available():
                self.on_status("✅ LangSmith connesso")
            else:
                self.on_status("⚠️ LangSmith non raggiungibile")
                self.langsmith = None
        
        # Google Sheets (opzionale)
        if self.project.google_sheets.enabled:
            try:
                self.sheets = GoogleSheetsClient(
                    credentials_path=self.project.google_sheets.credentials_path,
                    spreadsheet_id=self.project.google_sheets.spreadsheet_id,
                    drive_folder_id=self.project.google_sheets.drive_folder_id
                )
                if self.sheets.authenticate():
                    self.on_status("✅ Google Sheets connesso")
                    self.completed_tests = self.sheets.get_completed_tests()
                    self.on_status(f"   {len(self.completed_tests)} test già completati")
                else:
                    self.sheets = None
            except Exception as e:
                self.on_status(f"⚠️ Google Sheets non disponibile: {e}")
                self.sheets = None
        
        # Carica training data
        self.training_data = load_training_data(self.project.training_file)
        
        return True
    
    async def shutdown(self) -> None:
        """Chiude tutti i componenti"""
        if self.browser:
            await self.browser.stop()
        
        # Salva training data
        save_training_data(self.project.training_file, self.training_data)
    
    async def navigate_to_chatbot(self) -> bool:
        """Naviga al chatbot e gestisce login se necessario"""
        self.on_status(f"🌐 Navigazione a {self.project.chatbot.url}")
        
        success = await self.browser.navigate(self.project.chatbot.url)
        if not success:
            return False
        
        # Verifica se serve login
        is_ready = await self.browser.is_element_visible(
            self.project.chatbot.selectors.textarea,
            timeout_ms=5000
        )
        
        if not is_ready:
            self.on_status("🔐 Login richiesto...")
            success = await self.browser.wait_for_login(
                check_selector=self.project.chatbot.selectors.textarea,
                timeout_minutes=5
            )
            if not success:
                return False
        
        self.on_status("✅ Chatbot pronto")
        return True
    
    def load_test_cases(self) -> List[TestCase]:
        """Carica i test cases dal file"""
        raw_tests = load_tests(self.project.tests_file)
        
        tests = []
        for t in raw_tests:
            tests.append(TestCase(
                id=t.get('id', ''),
                question=t.get('question', ''),
                category=t.get('category', ''),
                expected=t.get('expected', ''),
                followups=t.get('followups', []),
                data=t.get('data', {}),
                tags=t.get('tags', [])
            ))
        
        return tests
    
    def filter_pending_tests(self, tests: List[TestCase]) -> List[TestCase]:
        """Filtra test già completati"""
        return [t for t in tests if t.id not in self.completed_tests]
    
    # ==================== MODALITÀ TRAIN ====================
    
    async def run_train_session(self, 
                                 tests: List[TestCase],
                                 skip_completed: bool = True) -> List[TestExecution]:
        """
        Esegue sessione di training.
        
        L'utente interagisce manualmente, il sistema registra.
        
        Args:
            tests: Test cases da eseguire
            skip_completed: Salta test già completati
            
        Returns:
            Lista risultati
        """
        self.current_mode = TestMode.TRAIN
        
        if skip_completed:
            tests = self.filter_pending_tests(tests)
        
        if not tests:
            self.on_status("ℹ️ Nessun test da eseguire")
            return []
        
        self.on_status(f"📚 TRAIN MODE - {len(tests)} test")
        
        # Setup report
        loader = ConfigLoader()
        report_dir = loader.get_report_dir(self.project.name)
        self.report = ReportGenerator(report_dir, self.project.name)
        self.report.mode = "TRAIN"
        
        results = []
        
        for i, test in enumerate(tests):
            self.on_progress(i + 1, len(tests))
            self.current_test = test
            
            self.on_status(f"\n--- Test {i+1}/{len(tests)}: {test.id} ---")
            self.on_status(f"📝 {test.question}")
            
            result = await self._execute_train_test(test)
            results.append(result)
            
            # Salva nel report
            self._save_result(result)
            
            # Chiedi se continuare
            if i < len(tests) - 1:
                self.on_status("\n[Premi INVIO per il prossimo test, 'q' per uscire]")
                # In un'implementazione reale, qui ci sarebbe input()
        
        # Genera report finale
        report_paths = self.report.generate()
        self.on_status(f"\n📊 Report generato: {report_paths['html']}")
        
        return results
    
    async def _execute_train_test(self, test: TestCase) -> TestExecution:
        """Esegue un singolo test in modalità train"""
        conversation = []
        start_time = datetime.utcnow()
        
        try:
            # Invia domanda iniziale
            await self.browser.send_message(test.question)
            
            conversation.append(ConversationTurn(
                role='user',
                content=test.question,
                timestamp=datetime.utcnow().isoformat()
            ))
            
            # Attendi risposta
            response = await self.browser.wait_for_response()
            
            if response:
                conversation.append(ConversationTurn(
                    role='assistant',
                    content=response,
                    timestamp=datetime.utcnow().isoformat()
                ))
                
                # Registra pattern per training
                self._record_training_pattern(test.question, response)
            
            # Gestisci followups manualmente
            # In un'implementazione reale, qui ci sarebbe interazione utente
            
            # Screenshot
            screenshot_path = ""
            if self.settings.screenshot_on_complete:
                ss_path = self.report.get_screenshot_path(test.id)
                if await self.browser.take_screenshot(
                    ss_path,
                    inject_css=self.project.chatbot.screenshot_css
                ):
                    screenshot_path = str(ss_path)
            
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            
            # In train mode, l'esito è sempre da confermare manualmente
            return TestExecution(
                test_case=test,
                conversation=conversation,
                esito="PASS",  # Default, l'utente può correggere
                duration_ms=duration_ms,
                screenshot_path=screenshot_path,
                notes="Train mode - verificare manualmente"
            )
            
        except Exception as e:
            return TestExecution(
                test_case=test,
                conversation=conversation,
                esito="ERROR",
                duration_ms=0,
                notes=f"Errore: {e}"
            )
    
    # ==================== MODALITÀ AUTO ====================
    
    async def run_auto_session(self,
                                tests: List[TestCase],
                                skip_completed: bool = True,
                                max_turns: Optional[int] = None) -> List[TestExecution]:
        """
        Esegue sessione automatica.
        
        LLM gestisce l'intera conversazione senza intervento umano.
        
        Args:
            tests: Test cases da eseguire
            skip_completed: Salta test già completati
            max_turns: Numero massimo turni per test
            
        Returns:
            Lista risultati
        """
        if not self.ollama:
            self.on_status("❌ Modalità Auto richiede Ollama")
            return []
        
        self.current_mode = TestMode.AUTO
        max_turns = max_turns or self.settings.max_turns
        
        if skip_completed:
            tests = self.filter_pending_tests(tests)
        
        if not tests:
            self.on_status("ℹ️ Nessun test da eseguire")
            return []
        
        self.on_status(f"🤖 AUTO MODE - {len(tests)} test")
        
        # Setup report
        loader = ConfigLoader()
        report_dir = loader.get_report_dir(self.project.name)
        self.report = ReportGenerator(report_dir, self.project.name)
        self.report.mode = "AUTO"
        
        results = []
        
        for i, test in enumerate(tests):
            self.on_progress(i + 1, len(tests))
            self.current_test = test
            
            self.on_status(f"\n--- Test {i+1}/{len(tests)}: {test.id} ---")
            
            result = await self._execute_auto_test(test, max_turns)
            results.append(result)
            
            # Salva nel report
            self._save_result(result)
            
            # Pausa tra test
            await asyncio.sleep(1)
        
        # Genera report finale
        report_paths = self.report.generate()
        self.on_status(f"\n📊 Report generato: {report_paths['html']}")
        
        return results
    
    async def _execute_auto_test(self, test: TestCase, max_turns: int) -> TestExecution:
        """Esegue un singolo test in modalità auto"""
        conversation = []
        start_time = datetime.utcnow()
        remaining_followups = test.followups.copy()
        
        try:
            # Invia domanda iniziale
            self.on_status(f"📤 {test.question[:60]}...")
            await self.browser.send_message(test.question)
            
            conversation.append(ConversationTurn(
                role='user',
                content=test.question,
                timestamp=datetime.utcnow().isoformat()
            ))
            
            # Loop conversazione
            turn = 0
            while turn < max_turns:
                turn += 1
                
                # Attendi risposta bot
                response = await self.browser.wait_for_response()
                
                if not response:
                    self.on_status("⚠️ Nessuna risposta dal bot")
                    break
                
                conversation.append(ConversationTurn(
                    role='assistant',
                    content=response,
                    timestamp=datetime.utcnow().isoformat()
                ))
                
                self.on_status(f"📥 Bot: {response[:60]}...")
                
                # Decidi prossimo messaggio
                next_message = self._decide_next_message(
                    conversation,
                    remaining_followups,
                    test
                )
                
                if not next_message:
                    self.on_status("✅ Conversazione completata")
                    break
                
                # Rimuovi followup usato
                if next_message in remaining_followups:
                    remaining_followups.remove(next_message)
                
                # Invia followup
                self.on_status(f"📤 {next_message[:60]}...")
                await self.browser.send_message(next_message)
                
                conversation.append(ConversationTurn(
                    role='user',
                    content=next_message,
                    timestamp=datetime.utcnow().isoformat()
                ))
            
            # Screenshot finale
            screenshot_path = ""
            if self.settings.screenshot_on_complete:
                ss_path = self.report.get_screenshot_path(test.id)
                if await self.browser.take_screenshot(
                    ss_path,
                    inject_css=self.project.chatbot.screenshot_css
                ):
                    screenshot_path = str(ss_path)
            
            # Valutazione LLM
            final_response = conversation[-1].content if conversation else ""
            evaluation = self.ollama.evaluate_test_result(
                test_case={'question': test.question, 'category': test.category, 'expected': test.expected},
                conversation=[{'role': t.role, 'content': t.content} for t in conversation],
                final_response=final_response
            )
            
            # LangSmith debug
            langsmith_url = ""
            if self.langsmith:
                debug = LangSmithDebugger(self.langsmith)
                debug_info = debug.debug_conversation(test.question)
                if debug_info.get('found'):
                    langsmith_url = debug_info.get('trace_url', '')
            
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            
            return TestExecution(
                test_case=test,
                conversation=conversation,
                esito="PASS" if evaluation.get('passed', False) else "FAIL",
                duration_ms=duration_ms,
                screenshot_path=screenshot_path,
                langsmith_url=langsmith_url,
                notes=evaluation.get('reason', ''),
                llm_evaluation=evaluation
            )
            
        except Exception as e:
            return TestExecution(
                test_case=test,
                conversation=conversation,
                esito="ERROR",
                duration_ms=0,
                notes=f"Errore: {e}"
            )
    
    def _decide_next_message(self,
                              conversation: List[ConversationTurn],
                              remaining_followups: List[str],
                              test: TestCase) -> Optional[str]:
        """Decide il prossimo messaggio da inviare"""
        if not remaining_followups:
            return None
        
        if self.ollama:
            # Usa LLM per decidere
            conv_dicts = [{'role': t.role, 'content': t.content} for t in conversation]
            return self.ollama.decide_followup(
                conversation=conv_dicts,
                available_followups=remaining_followups,
                test_context=test.category
            )
        else:
            # Senza LLM, usa il primo followup disponibile
            return remaining_followups[0] if remaining_followups else None
    
    # ==================== MODALITÀ ASSISTED ====================
    
    async def run_assisted_session(self,
                                    tests: List[TestCase],
                                    skip_completed: bool = True) -> List[TestExecution]:
        """
        Esegue sessione assistita.
        
        LLM propone azioni, utente conferma o corregge.
        
        Args:
            tests: Test cases da eseguire
            skip_completed: Salta test già completati
            
        Returns:
            Lista risultati
        """
        if not self.ollama:
            self.on_status("⚠️ Modalità Assisted senza LLM, fallback a Train")
            return await self.run_train_session(tests, skip_completed)
        
        self.current_mode = TestMode.ASSISTED
        
        # Implementazione simile a auto ma con conferme utente
        # Per brevità, delega a auto con logging extra
        self.on_status("🤝 ASSISTED MODE - LLM + supervisione umana")
        
        return await self.run_auto_session(tests, skip_completed)
    
    # ==================== HELPERS ====================
    
    def _save_result(self, result: TestExecution) -> None:
        """Salva risultato nei report"""
        date_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        
        # Formatta conversazione
        conv_str = "\n".join([
            f"{'USER' if t.role == 'user' else 'BOT'}: {t.content}"
            for t in result.conversation
        ])
        
        # Report locale
        if self.report:
            self.report.add_result(TestResultLocal(
                test_id=result.test_case.id,
                date=date_str,
                mode=self.current_mode.value.upper(),
                question=result.test_case.question,
                conversation=conv_str,
                screenshot_path=result.screenshot_path,
                esito=result.esito,
                notes=result.notes,
                langsmith_url=result.langsmith_url,
                duration_ms=result.duration_ms,
                category=result.test_case.category,
                followups_count=len(result.test_case.followups)
            ))
        
        # Google Sheets
        if self.sheets:
            screenshot_url = ""
            if result.screenshot_path:
                screenshot_url = self.sheets.upload_screenshot(
                    Path(result.screenshot_path),
                    result.test_case.id
                ) or ""
            
            self.sheets.append_result(TestResult(
                test_id=result.test_case.id,
                date=date_str,
                mode=self.current_mode.value.upper(),
                question=result.test_case.question,
                conversation=conv_str[:5000],  # Limite Sheets
                screenshot_url=screenshot_url,
                esito=result.esito,
                notes=result.notes,
                langsmith_url=result.langsmith_url
            ))
        
        # Aggiorna test completati
        self.completed_tests.add(result.test_case.id)
    
    def _record_training_pattern(self, question: str, response: str) -> None:
        """Registra pattern per training futuro"""
        pattern = {
            'question': question,
            'response_preview': response[:200],
            'timestamp': datetime.utcnow().isoformat()
        }
        
        self.training_data['patterns'].append(pattern)
        
        # Limita dimensione
        if len(self.training_data['patterns']) > 1000:
            self.training_data['patterns'] = self.training_data['patterns'][-500:]


async def run_single_test(project: ProjectConfig,
                          settings: GlobalSettings,
                          test_id: str,
                          mode: TestMode = TestMode.TRAIN) -> Optional[TestExecution]:
    """
    Esegue un singolo test.
    
    Utility per test rapidi o debugging.
    """
    tester = ChatbotTester(project, settings)
    
    try:
        if not await tester.initialize():
            return None
        
        if not await tester.navigate_to_chatbot():
            return None
        
        tests = tester.load_test_cases()
        test = next((t for t in tests if t.id == test_id), None)
        
        if not test:
            print(f"Test {test_id} non trovato")
            return None
        
        if mode == TestMode.AUTO:
            results = await tester.run_auto_session([test], skip_completed=False)
        else:
            results = await tester.run_train_session([test], skip_completed=False)
        
        return results[0] if results else None
        
    finally:
        await tester.shutdown()
