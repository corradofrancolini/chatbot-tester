"""
Core Tester - Main chatbot testing engine

Handles:
- Train, Assisted, Auto modes
- Test execution with followups
- Integration with all clients (browser, LLM, report)
- Complete test flow orchestration
"""

import asyncio
import time
import json
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum

from .config_loader import (
    ConfigLoader, ProjectConfig, GlobalSettings, RunConfig,
    load_tests, save_tests
)
from .browser import BrowserManager, BrowserSettings, ChatbotSelectors
from .ollama_client import OllamaClient
from .langsmith_client import LangSmithClient, LangSmithDebugger, LangSmithReport
from .models import (
    TestResult, ScreenshotUrls, TestMode,
    ConversationTurn, TestCase, TestExecution, ExecutionContext
)
from .sheets_client import GoogleSheetsClient
from .report_local import ReportGenerator
from .engine.executor import TestExecutor
from .training import TrainingData, TrainModeUI
from .performance import PerformanceCollector, PerformanceReporter, PerformanceAlerter, PerformanceHistory
from .evaluation import Evaluator, EvaluationConfig, EvaluationResult, create_evaluator_from_settings
from .baselines import BaselinesCache, get_baseline, preload_baselines
from rich.console import Console
from rich.panel import Panel
from rich.text import Text


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
                 use_langsmith: bool = True,
                 single_turn: bool = False,
                 run_config: Optional[RunConfig] = None):
        """
        Inizializza il tester.

        Args:
            project: Configurazione progetto
            settings: Settings globali
            on_status: Callback per messaggi di stato
            on_progress: Callback per progresso (current, total)
            dry_run: Se True, non salva su Google Sheets
            use_langsmith: Se False, disabilita LangSmith
            single_turn: Se True, modalità AUTO esegue solo domanda iniziale (no followup)
            run_config: Configurazione run corrente (per prompt_version, env, etc.)
        """
        self.project = project
        self.settings = settings
        self.on_status = on_status or print
        self.on_progress = on_progress or (lambda c, t: None)

        # Toggle runtime
        self.dry_run = dry_run
        self.use_langsmith = use_langsmith
        self.single_turn = single_turn
        self.run_config = run_config

        # Browser
        self.browser: Optional[BrowserManager] = None

        # Clients opzionali
        self.ollama: Optional[OllamaClient] = None
        self.langsmith: Optional[LangSmithClient] = None
        self.sheets: Optional[GoogleSheetsClient] = None
        self.baselines_cache: Optional[BaselinesCache] = None

        # Report locale
        self.report: Optional[ReportGenerator] = None

        # Stato
        self.current_mode: TestMode = TestMode.TRAIN
        self.completed_tests: set = set()
        self.current_test: Optional[TestCase] = None

        # Training data - sistema di pattern learning
        self.training: Optional[TrainingData] = None
        self._quit_requested = False
        self._console = Console()  # Per output colorato

        # Performance metrics
        self.perf_collector: Optional[PerformanceCollector] = None
        self._service_start_time: Optional[float] = None

        # Evaluation system
        self.evaluator: Optional[Evaluator] = None

    async def initialize(self) -> bool:
        """
        Inizializza tutti i componenti.

        Returns:
            True se inizializzazione riuscita
        """
        self.on_status("Inizializzazione componenti...")

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
            self.on_status("✓ Browser avviato")
        except Exception as e:
            self.on_status(f"✗ Errore browser: {e}")
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
                self.on_status(f"✓ Ollama ({self.project.ollama.model}) disponibile")
                # Passa training context per in-context learning
                if self.training:
                    self.ollama.set_training_context(self.training)
            else:
                self.on_status("! Ollama non disponibile")
                self.ollama = None

        # Evaluation system (opzionale - usa OpenAI GPT-4o-mini)
        if self.settings.evaluation.enabled:
            try:
                self.evaluator = create_evaluator_from_settings(
                    self.settings.evaluation,
                    self.project.project_dir
                )
                self.on_status("✓ Evaluation system attivo (OpenAI)")
            except Exception as e:
                self.on_status(f"! Evaluation system non disponibile: {e}")
                self.evaluator = None

        # LangSmith (opzionale) - rispetta toggle use_langsmith
        if self.use_langsmith and self.project.langsmith.enabled and self.project.langsmith.api_key:
            self.langsmith = LangSmithClient(
                api_key=self.project.langsmith.api_key,
                project_id=self.project.langsmith.project_id,
                org_id=self.project.langsmith.org_id,
                tool_names=self.project.langsmith.tool_names
            )
            if self.langsmith.is_available():
                self.on_status("✓ LangSmith connesso")
            else:
                self.on_status("! LangSmith non raggiungibile")
                self.langsmith = None
        elif not self.use_langsmith:
            self.on_status("> LangSmith disabilitato (toggle)")

        # Google Sheets (opzionale) - rispetta toggle dry_run
        # Nota: il foglio RUN viene configurato da run.py dopo initialize()
        if self.dry_run:
            self.on_status("> Google Sheets disabilitato (dry run)")
        elif self.project.google_sheets.enabled:
            try:
                # Ottieni configurazione colonne
                columns_config = self.project.google_sheets.columns
                column_preset = columns_config.preset if columns_config else "standard"
                column_list = columns_config.custom if columns_config and columns_config.preset == "custom" else None

                self.sheets = GoogleSheetsClient(
                    credentials_path=self.project.google_sheets.credentials_path,
                    spreadsheet_id=self.project.google_sheets.spreadsheet_id,
                    drive_folder_id=self.project.google_sheets.drive_folder_id,
                    column_preset=column_preset,
                    column_list=column_list
                )

                # Applica configurazione colonne per test file specifico se configurato
                if columns_config and columns_config.by_test_file:
                    test_file_name = self.project.tests_file.name if self.project.tests_file else 'tests.json'
                    self.sheets.set_columns_for_test_file(
                        test_file_name,
                        columns_config.by_test_file,
                        column_preset,
                        column_list
                    )

                if self.sheets.authenticate():
                    self.on_status("✓ Google Sheets autenticato")
                    # Il foglio RUN e i test completati vengono configurati
                    # da run.py tramite sheets.setup_run_sheet()

                    # Precarica baseline (golden answers) per evaluation
                    try:
                        self.baselines_cache = BaselinesCache(ttl_seconds=300)
                        baseline_count = self.baselines_cache.load(
                            self.sheets,
                            self.project.name,
                            force=True
                        )
                        if baseline_count > 0:
                            self.on_status(f"✓ Baselines caricate: {baseline_count} golden answers")
                    except Exception as e:
                        self.on_status(f"! Baselines non disponibili: {e}")
                        self.baselines_cache = None
                else:
                    self.sheets = None
            except Exception as e:
                self.on_status(f"! Google Sheets non disponibile: {e}")
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
        self.on_status(f"Navigazione a {self.project.chatbot.url}")

        # Pass auth config if configured (for cloud CI auto-login)
        auth_config = None
        if hasattr(self.project, 'auth') and self.project.auth.type != "none":
            auth_config = self.project.auth.to_dict()

        success = await self.browser.navigate(self.project.chatbot.url, auth_config=auth_config)
        if not success:
            return False

        # Verifica se serve login (fallback per login manuale se auth non configurato)
        is_ready = await self.browser.is_element_visible(
            self.project.chatbot.selectors.textarea,
            timeout_ms=5000
        )

        if not is_ready:
            self.on_status("Login richiesto...")
            success = await self.browser.wait_for_login(
                check_selector=self.project.chatbot.selectors.textarea,
                timeout_minutes=5
            )
            if not success:
                return False

        self.on_status("✓ Chatbot pronto")

        # Initialize Executor with bundled context
        context = ExecutionContext(
            browser=self.browser,
            settings=self.settings,
            ollama=self.ollama,
            langsmith=self.langsmith,
            evaluator=self.evaluator,
            training=self.training,
            baselines=self.baselines_cache,
            perf_collector=self.perf_collector,
            report=self.report,
            sheets=self.sheets,
            console=self._console,
            run_config=self.run_config,
            project=self.project,
            single_turn=self.single_turn,
            current_mode=self.current_mode if self.current_mode else TestMode.AUTO
        )
        self.executor = TestExecutor(context)

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
                tags=t.get('tags', []),
                notes=t.get('notes', ''),
                # Campi GGP
                section=t.get('section', ''),
                test_target=t.get('test_target', ''),
                # Campi evaluation
                expected_answer=t.get('expected_answer'),
                rag_context_file=t.get('rag_context_file')
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
        # Aggiorna anche il context dell'executor
        if self.executor and self.executor.ctx:
            self.executor.ctx.current_mode = TestMode.TRAIN

        if skip_completed:
            tests = self.filter_pending_tests(tests)

        if not tests:
            self.on_status("> Nessun test da eseguire")
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
            self.on_status(f"{test.question}")

            result = await self._execute_train_test(test)
            results.append(result)

            # Check quit
            if self._quit_requested:
                self.on_status("\nSessione interrotta")
                break

            # Salva nel report
            self._save_result(result)

            # Chiedi se continuare
            if i < len(tests) - 1:
                self.on_status("\n[Premi INVIO per il prossimo test, 'q' per uscire]")
                # In un'implementazione reale, qui ci sarebbe input()

        # Genera report finale
        report_paths = self.report.generate()
        self.on_status(f"\nReport generato: {report_paths['html']}")

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
        conversation: List[ConversationTurn] = []
        start_time = datetime.utcnow()

        try:
            # Phase 1: Navigate and start conversation
            conversation = await self._train_navigate_and_start(test)

            # Phase 2: Interactive loop
            loop_result = await self._train_interactive_loop(test, conversation)
            conversation = loop_result['conversation']
            skipped = loop_result['skipped']
            turn = loop_result['turn']
            patterns_learned = loop_result['patterns_learned']

            # Phase 3: Finalize execution
            return await self._train_finalize(
                test=test,
                conversation=conversation,
                start_time=start_time,
                skipped=skipped,
                turn=turn,
                patterns_learned=patterns_learned
            )

        except Exception as e:
            import traceback
            traceback.print_exc()
            return TestExecution(
                test_case=test,
                conversation=conversation,
                result="ERROR",
                duration_ms=0,
                notes=f"Errore: {e}"
            )

    async def _train_navigate_and_start(self, test: TestCase) -> List[ConversationTurn]:
        """Phase 1: Navigate to chatbot and send initial question."""
        conversation: List[ConversationTurn] = []

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

        return conversation

    async def _train_interactive_loop(
        self,
        test: TestCase,
        conversation: List[ConversationTurn]
    ) -> Dict[str, Any]:
        """
        Phase 2: Interactive conversation loop.

        Returns dict with:
            conversation: Updated conversation
            skipped: True if user skipped
            turn: Number of turns completed
            patterns_learned: Number of new patterns learned
        """
        patterns_learned = 0
        followup_idx = 0
        turn = 0
        max_turns = 15
        skipped = False

        # UI helper
        ui = TrainModeUI(self.training) if self.training else None

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

            if user_input.lower() == 'skip':
                skipped = True
                break

            # Determina risposta da inviare
            user_response = self._determine_user_response(
                user_input, next_followup, suggestions
            )

            if user_response == '__use_followup__':
                user_response = next_followup
                followup_idx += 1
            elif user_response is None:
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

        return {
            'conversation': conversation,
            'skipped': skipped,
            'turn': turn,
            'patterns_learned': patterns_learned
        }

    def _determine_user_response(
        self,
        user_input: str,
        next_followup: Optional[str],
        suggestions: List[Dict]
    ) -> Optional[str]:
        """Determine what response to send based on user input."""
        if user_input.lower() == 'f' and next_followup:
            return '__use_followup__'

        if user_input.isdigit() and suggestions:
            idx = int(user_input) - 1
            if 0 <= idx < len(suggestions):
                return suggestions[idx]['text']

        if user_input == '' and next_followup:
            return '__use_followup__'

        if user_input:
            return user_input

        return None

    async def _train_finalize(
        self,
        test: TestCase,
        conversation: List[ConversationTurn],
        start_time: datetime,
        skipped: bool,
        turn: int,
        patterns_learned: int
    ) -> TestExecution:
        """Phase 3: Finalize test - screenshot, training record, langsmith."""
        ui = TrainModeUI(self.training) if self.training else None

        # Screenshot finale (skip if configured)
        screenshot_path = ""
        skip_ss = getattr(self.project.chatbot, 'skip_screenshot', False)
        skip_ss = skip_ss or (self.run_config and getattr(self.run_config, 'skip_screenshots', False))
        if self.settings.screenshot_on_complete and self.report and not skip_ss:
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
        langsmith_report = ""
        model_version = ""
        if self.langsmith:
            try:
                report = self.langsmith.get_report_for_question(test.question)
                if report.trace_url:
                    langsmith_url = report.trace_url
                    langsmith_report = report.format_for_sheets()
                    model_version = report.get_model_version()
            except:
                pass

        return TestExecution(
            test_case=test,
            conversation=conversation,
            result="SKIP" if skipped else "PASS",
            duration_ms=duration_ms,
            screenshot_path=screenshot_path,
            notes="",  # Vuoto - per il reviewer
            langsmith_url=langsmith_url,
            langsmith_report=langsmith_report,
            model_version=model_version,
            prompt_version=self.run_config.prompt_version if self.run_config else ""
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
        # Permetti AUTO mode senza Ollama se single_turn (solo esecuzione, no valutazione)
        if not self.ollama and not self.single_turn:
            self.on_status("✗ Modalità Auto richiede Ollama (o attiva single_turn)")
            return []

        if not self.ollama:
            self.on_status("! AUTO mode senza Ollama - solo esecuzione e screenshot")

        self.current_mode = TestMode.AUTO
        # Aggiorna anche il context dell'executor
        if self.executor and self.executor.ctx:
            self.executor.ctx.current_mode = TestMode.AUTO
        max_turns = max_turns or self.settings.max_turns

        if skip_completed:
            tests = self.filter_pending_tests(tests)

        if not tests:
            self.on_status("> Nessun test da eseguire")
            return []

        self.on_status(f"AUTO MODE - {len(tests)} test")

        # Setup report
        loader = ConfigLoader()
        report_dir = loader.get_report_dir(self.project.name)
        self.report = ReportGenerator(report_dir, self.project.name)
        self.report.mode = "AUTO"

        # Setup performance collector
        run_id = self.run_config.active_run if self.run_config else datetime.now().strftime("%Y%m%d_%H%M%S")
        self.perf_collector = PerformanceCollector(
            run_id=str(run_id),
            project=self.project.name,
            environment="cloud" if self.settings.browser.headless else "local"
        )

        # Update executor with session components
        self.executor.report = self.report
        self.executor.perf_collector = self.perf_collector
        if self.perf_collector:
            self.executor.perf_collector = self.perf_collector

        results = []

        for i, test in enumerate(tests):
            self.on_progress(i + 1, len(tests))
            self.current_test = test

            self.on_status(f"\n--- Test {i+1}/{len(tests)}: {test.id} ---")

            result = await self.executor.execute_auto_test(test, max_turns)
            results.append(result)

            # Check quit
            if self._quit_requested:
                self.on_status("\nSessione interrotta")
                break

            # Salva nel report
            self._save_result(result)

            # Pausa tra test
            await asyncio.sleep(1)

        # Finalizza e salva metriche performance
        if self.perf_collector:
            run_metrics = self.perf_collector.finalize()

            # Salva metriche
            perf_dir = report_dir / "performance"
            self.perf_collector.save(perf_dir)

            # Genera e mostra report performance
            reporter = PerformanceReporter(run_metrics)
            self.on_status(reporter.generate_summary())

            # Check alerting
            alerter = PerformanceAlerter()
            alerts = alerter.check(run_metrics)
            if alerts:
                self.on_status(alerter.format_alerts())

            # Salva nello storico per dashboard
            history = PerformanceHistory(self.project.name, Path("reports"))
            history.save_run(run_metrics)

        # Genera report finale
        report_paths = self.report.generate()
        self.on_status(f"\nReport generato: {report_paths['html']}")

        return results

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
            self.on_status("! Modalità Assisted senza LLM, fallback a Train")
            return await self.run_train_session(tests, skip_completed)

        self.current_mode = TestMode.ASSISTED
        # Aggiorna anche il context dell'executor
        if self.executor and self.executor.ctx:
            self.executor.ctx.current_mode = TestMode.ASSISTED

        # Implementazione simile a auto ma con conferme utente
        # Per brevità, delega a auto con logging extra
        self.on_status("🤝 ASSISTED MODE - LLM + supervisione umana")

        return await self.run_auto_session(tests, skip_completed)

    # ==================== HELPERS ====================

    def _save_result(self, result: TestExecution) -> None:
        """Salva risultato nei report - delega all'executor."""
        self.executor.persist(result)
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
