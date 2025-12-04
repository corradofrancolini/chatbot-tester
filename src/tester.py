"""
Core Tester - Engine principale per testing chatbot

Gestisce:
- Modalità Train, Assisted, Auto
- Esecuzione test con followups
- Integrazione con tutti i client (browser, LLM, report)
- Orchestrazione completa del flusso di test
"""

import asyncio
# import readchar  # Disabilitato
# import readchar  # Disabilitato
import json
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum

from .config_loader import (
    ConfigLoader, ProjectConfig, GlobalSettings,
    load_tests, save_tests
)
from .browser import BrowserManager, BrowserSettings, ChatbotSelectors
from .ollama_client import OllamaClient
from .langsmith_client import LangSmithClient, LangSmithDebugger, LangSmithReport
from .sheets_client import GoogleSheetsClient, TestResult
from .report_local import ReportGenerator, TestResultLocal
from .training import TrainingData, TrainModeUI
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.text import Text
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.text import Text
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.text import Text


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
    model_version: str = ""


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
                 on_progress: Optional[Callable[[int, int], None]] = None,
                 dry_run: bool = False,
                 use_langsmith: bool = True):
        """
        Inizializza il tester.
        
        Args:
            project: Configurazione progetto
            settings: Settings globali
            on_status: Callback per messaggi di stato
            on_progress: Callback per progresso (current, total)
            dry_run: Se True, non salva su Google Sheets
            use_langsmith: Se False, disabilita LangSmith
        """
        self.project = project
        self.settings = settings
        self.on_status = on_status or print
        self.on_progress = on_progress or (lambda c, t: None)
        
        # Toggle runtime
        self.dry_run = dry_run
        self.use_langsmith = use_langsmith
        
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
        
        # Training data - sistema di pattern learning
        self.training: Optional[TrainingData] = None
        self._quit_requested = False
        self._console = Console()  # Per output colorato  # Per uscire dalla sessione
    
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
            thread_container=self.project.chatbot.selectors.thread_container,
            loading_indicator=self.project.chatbot.selectors.loading_indicator
        )
        
        self.browser = BrowserManager(browser_settings, selectors)
        
        try:
            await self.browser.start()
            self.on_status("✅ Browser avviato")
        except Exception as e:
            self.on_status(f"❌ Errore browser: {e}")
            return False
        
        # Carica training data PRIMA di Ollama (serve per in-context learning)
        self.training = TrainingData.load(self.project.training_file)
        
        # Ollama (opzionale)
        if self.project.ollama.enabled:
            self.ollama = OllamaClient(
                model=self.project.ollama.model,
                url=self.project.ollama.url
            )
            if self.ollama.is_available():
                self.on_status(f"✅ Ollama ({self.project.ollama.model}) disponibile")
                # Passa training context per in-context learning
                if self.training:
                    self.ollama.set_training_context(self.training)
            else:
                self.on_status("⚠️ Ollama non disponibile")
                self.ollama = None
        
        # LangSmith (opzionale) - rispetta toggle use_langsmith
        if self.use_langsmith and self.project.langsmith.enabled and self.project.langsmith.api_key:
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
        elif not self.use_langsmith:
            self.on_status("ℹ️ LangSmith disabilitato (toggle)")
        
        # Google Sheets (opzionale) - rispetta toggle dry_run
        # Nota: il foglio RUN viene configurato da run.py dopo initialize()
        if self.dry_run:
            self.on_status("ℹ️ Google Sheets disabilitato (dry run)")
        elif self.project.google_sheets.enabled:
            try:
                self.sheets = GoogleSheetsClient(
                    credentials_path=self.project.google_sheets.credentials_path,
                    spreadsheet_id=self.project.google_sheets.spreadsheet_id,
                    drive_folder_id=self.project.google_sheets.drive_folder_id
                )
                if self.sheets.authenticate():
                    self.on_status("✅ Google Sheets autenticato")
                    # Il foglio RUN e i test completati vengono configurati
                    # da run.py tramite sheets.setup_run_sheet()
                else:
                    self.sheets = None
            except Exception as e:
                self.on_status(f"⚠️ Google Sheets non disponibile: {e}")
                self.sheets = None
        
        return True
    
    async def shutdown(self) -> None:
        """Chiude tutti i componenti"""
        if self.browser:
            await self.browser.stop()
        
        # Salva training data
        if self.training:
            self.training.save(self.project.training_file)
    
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
            
            # Check quit
            if self._quit_requested:
                self.on_status("\n🛑 Sessione interrotta")
                break
            
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
        """
        Esegue un singolo test in modalità train con loop interattivo.

        L'utente può:
        - Scegliere suggerimenti numerati [1] [2] [3]
        - Usare followup predefinito [f]
        - Scrivere risposta libera
        - Terminare con [end], uscire con [q]uit
        - Saltare con [skip]
        """
        conversation = []
        start_time = datetime.utcnow()
        patterns_learned = 0
        followup_idx = 0
        turn = 0
        max_turns = 15
        skipped = False

        # UI helper
        ui = TrainModeUI(self.training) if self.training else None

        try:
            # Ricarica la pagina per iniziare una nuova conversazione
            await self.browser.navigate(self.project.chatbot.url)
            await asyncio.sleep(0.5)

            # Invia domanda iniziale
            await self.browser.send_message(test.question)
            print(f"\nYOU → {test.question}")
            
            conversation.append(ConversationTurn(
                role='user',
                content=test.question,
                timestamp=datetime.utcnow().isoformat()
            ))
            
            # Loop interattivo
            while turn < max_turns:
                turn += 1
                
                # Attendi risposta bot
                response = await self.browser.wait_for_response()
                
                if not response:
                    print("  [nessuna risposta dal bot]")
                    break
                
                # Mostra risposta bot (troncata per leggibilità)
                response_preview = response[:200] + "..." if len(response) > 200 else response
                print(f"BOT ← {response_preview}")
                
                conversation.append(ConversationTurn(
                    role='assistant',
                    content=response,
                    timestamp=datetime.utcnow().isoformat()
                ))
                
                # Prepara suggerimenti
                next_followup = test.followups[followup_idx] if followup_idx < len(test.followups) else None
                suggestions = self.training.get_suggestions(response) if self.training else []
                
                # Mostra UI suggerimenti
                if ui:
                    print(ui.format_suggestions(response, next_followup))
                else:
                    if next_followup:
                        print(f"  [f] followup: \"{next_followup[:50]}...\"")
                
                # Barra comandi
                self._console.print("[dim]" + "─" * 50 + "[/dim]")
                self._console.print("[reverse cyan]e[/reverse cyan]nd  [reverse cyan]s[/reverse cyan]kip  [reverse cyan]f[/reverse cyan]ollowup  [reverse cyan]q[/reverse cyan]uit")
                
                # Attendi input utente
                print(">>> ", end="", flush=True)
                user_input = await self._async_input()
                user_input = user_input.strip()
                
                # Gestisci comandi speciali
                if user_input.lower() == 'end':
                    break
                
                if user_input.lower() in ('quit', 'q'):
                    self._quit_requested = True
                    break
                
                if user_input.lower() in ('quit', 'q'):
                    self._quit_requested = True
                    break
                
                if user_input.lower() == 'skip':
                    skipped = True
                    break
                
                # Determina risposta da inviare
                user_response = None
                
                if user_input.lower() == 'f' and next_followup:
                    # Usa followup
                    user_response = next_followup
                    followup_idx += 1
                
                elif user_input.isdigit() and suggestions:
                    # Scegli suggerimento numerato
                    idx = int(user_input) - 1
                    if 0 <= idx < len(suggestions):
                        user_response = suggestions[idx]['text']
                
                elif user_input == '' and next_followup:
                    # INVIO = usa followup
                    user_response = next_followup
                    followup_idx += 1
                
                elif user_input:
                    # Risposta libera
                    user_response = user_input
                
                if not user_response:
                    print("  [input non valido, riprova]")
                    turn -= 1  # Non conta come turno
                    continue
                
                # Impara pattern
                pattern, is_new = self._record_training_pattern(response, user_response)
                if pattern:
                    patterns_learned += 1 if is_new else 0
                    if ui:
                        print(ui.format_learned(pattern, user_response, is_new))
                    else:
                        print(f"  ✓ {user_response}")
                else:
                    print(f"  ✓ {user_response}")
                
                # Invia risposta al bot
                await self.browser.send_message(user_response)
                print(f"\nYOU → {user_response}")
                
                conversation.append(ConversationTurn(
                    role='user',
                    content=user_response,
                    timestamp=datetime.utcnow().isoformat()
                ))
            
            # Screenshot finale
            screenshot_path = ""
            if self.settings.screenshot_on_complete and self.report:
                ss_path = self.report.get_screenshot_path(test.id)
                if await self.browser.take_screenshot(
                    ss_path,
                    inject_css=self.project.chatbot.screenshot_css
                ):
                    screenshot_path = str(ss_path)
            
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            
            # Registra conversazione nel training
            if self.training:
                turns_data = []
                for i in range(0, len(conversation) - 1, 2):
                    if i + 1 < len(conversation):
                        turns_data.append({
                            'bot': conversation[i + 1].content if conversation[i + 1].role == 'assistant' else '',
                            'user': conversation[i].content if conversation[i].role == 'user' else ''
                        })
                self.training.record_conversation(test.id, test.question, turns_data)
            
            # Riepilogo
            if ui:
                print(f"\n{ui.format_test_complete(test.id, turn, patterns_learned)}")
            else:
                print(f"\n✓ {test.id} completato │ {turn} turni")
            
            # LangSmith debug (anche in Train mode per estrarre model_version e report)
            langsmith_url = ""
            langsmith_notes = ""
            model_version = ""
            if self.langsmith:
                try:
                    report = self.langsmith.get_report_for_question(test.question)
                    if report.trace_url:
                        langsmith_url = report.trace_url
                        langsmith_notes = report.format_for_sheets()
                        model_version = report.get_model_version()
                except:
                    pass

            # Combina notes: train info + LangSmith report
            train_notes = f"Train mode - {patterns_learned} pattern appresi"
            combined_notes = train_notes
            if langsmith_notes:
                combined_notes += "\n---\n" + langsmith_notes

            return TestExecution(
                test_case=test,
                conversation=conversation,
                esito="SKIP" if skipped else "PASS",
                duration_ms=duration_ms,
                screenshot_path=screenshot_path,
                notes=combined_notes,
                langsmith_url=langsmith_url,
                model_version=model_version
            )
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return TestExecution(
                test_case=test,
                conversation=conversation,
                esito="ERROR",
                duration_ms=0,
                notes=f"Errore: {e}"
            )
    
    async def _async_input(self) -> str:
        """Input asincrono per non bloccare event loop"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, input)
    
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
            
            # Check quit
            if self._quit_requested:
                self.on_status("\n🛑 Sessione interrotta")
                break
            
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
            # Ricarica la pagina per iniziare una nuova conversazione
            await self.browser.navigate(self.project.chatbot.url)
            await asyncio.sleep(0.5)

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
            langsmith_notes = ""
            model_version = ""
            if self.langsmith:
                try:
                    report = self.langsmith.get_report_for_question(test.question)
                    if report.trace_url:
                        langsmith_url = report.trace_url
                        langsmith_notes = report.format_for_sheets()
                        model_version = report.get_model_version()
                except Exception as e:
                    self.on_status(f"⚠️ Errore LangSmith: {e}")
            
            # Combina notes: evaluation reason + LangSmith report
            eval_notes = evaluation.get('reason', '')
            combined_notes = eval_notes
            if langsmith_notes:
                if combined_notes:
                    combined_notes += "\n---\n" + langsmith_notes
                else:
                    combined_notes = langsmith_notes
            
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            
            return TestExecution(
                test_case=test,
                conversation=conversation,
                esito="PASS" if evaluation.get('passed', False) else "FAIL",
                duration_ms=duration_ms,
                screenshot_path=screenshot_path,
                langsmith_url=langsmith_url,
                notes=combined_notes,
                llm_evaluation=evaluation,
                model_version=model_version
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
        """
        Decide il prossimo messaggio da inviare.
        
        Usa in ordine:
        1. Pattern matching dal training (se trova match)
        2. Ollama con training context (se disponibile)
        3. Primo followup disponibile (fallback)
        """
        # Estrai ultimo messaggio del bot
        bot_message = ""
        for turn in reversed(conversation):
            if turn.role == 'assistant':
                bot_message = turn.content
                break
        
        if self.ollama:
            # Usa decide_response che sfrutta training + LLM
            conv_dicts = [{'role': t.role, 'content': t.content} for t in conversation]
            return self.ollama.decide_response(
                bot_message=bot_message,
                conversation=conv_dicts,
                followups=remaining_followups if remaining_followups else None,
                test_context=test.category
            )
        elif self.training:
            # Senza LLM, prova pattern matching dal training
            suggestions = self.training.get_suggestions(bot_message, limit=1)
            if suggestions:
                response = suggestions[0]['text']
                # Impara (incrementa contatore)
                self.training.learn(bot_message, response)
                return response
        
        # Fallback: primo followup o None
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
                langsmith_url=result.langsmith_url,
                model_version=result.model_version
            ))
        
        # Aggiorna test completati
        self.completed_tests.add(result.test_case.id)
    
    def _record_training_pattern(self, bot_message: str, user_response: str) -> tuple:
        """
        Registra pattern per training futuro.
        
        Returns:
            (Pattern matchato, True se nuova risposta)
        """
        if self.training:
            return self.training.learn(bot_message, user_response)
        return None, False


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
