import asyncio
import time
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any, TYPE_CHECKING
from dataclasses import asdict

from ..models import TestCase, TestExecution, ConversationTurn, TestResult, TestMode, ExecutionContext

if TYPE_CHECKING:
    from ..browser import BrowserManager
    from ..ollama_client import OllamaClient
    from ..langsmith_client import LangSmithClient
    from ..config_loader import GlobalSettings, RunConfig
    from ..training import TrainingData
    from ..performance import PerformanceCollector
    from ..evaluation import Evaluator
    from ..baselines import BaselinesCache
    from ..report_local import ReportGenerator
    from rich.console import Console


class TestExecutor:
    """
    Executes individual tests in various modes (Auto, Train, Assisted).
    Handles conversation flow, interactions, and result collection.
    """

    def __init__(self, context: ExecutionContext):
        """
        Initialize executor with bundled dependencies.

        Args:
            context: ExecutionContext containing all required dependencies
        """
        self.ctx = context

        # Convenience aliases for frequently accessed attributes
        self.browser = context.browser
        self.settings = context.settings
        self.ollama = context.ollama
        self.langsmith = context.langsmith
        self.training = context.training
        self.evaluator = context.evaluator
        self.baselines = context.baselines
        self.perf_collector = context.perf_collector
        self.report = context.report
        self.sheets = context.sheets
        self.run_config = context.run_config
        self.console = context.console
        self.project = context.project
        self.single_turn = context.single_turn

        # State
        self._quit_requested = False

    def on_status(self, msg: str) -> None:
        """Log status message (fallback to print if console not set)"""
        if self.console:
            self.console.print(f"[dim]{msg}[/dim]")
        else:
            print(msg)

    def decide_next_message(self,
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

    async def execute_auto_test(self, test: TestCase, max_turns: int) -> TestExecution:
        """Esegue un singolo test in modalità auto"""
        if self.perf_collector:
            self.perf_collector.start_test(test.id, test.category)

        self.on_status(f"Avvio test {test.id}: {test.question[:60]}...")
        start_time = datetime.utcnow()
        conversation: List[ConversationTurn] = []
        remaining_followups = list(test.followups) if test.followups else []

        # Reset sessione
        await self.browser.reset_session()
        self.browser.start_new_test(test.id)

        # Invia domanda iniziale
        self.on_status("Invio domanda...")
        await self.browser.send_message(test.question)
        print(f"\nYOU → {test.question}")

        conversation.append(ConversationTurn(
            role='user',
            content=test.question,
            timestamp=start_time.isoformat()
        ))

        # Loop di conversazione
        turn = 0
        while turn < max_turns:
            turn += 1

            # PHASE: Wait for bot response
            if self.perf_collector:
                self.perf_collector.start_phase("wait_response")

            chatbot_start = time.perf_counter()
            response = await self.browser.wait_for_response()
            chatbot_duration_ms = (time.perf_counter() - chatbot_start) * 1000

            if self.perf_collector:
                self.perf_collector.end_phase()
                self.perf_collector.record_service_call(
                    service="chatbot",
                    operation="response",
                    duration_ms=chatbot_duration_ms,
                    success=response is not None
                )
                if self.browser.last_response_timing:
                    self.perf_collector.record_service_call(
                        service="chatbot",
                        operation="ttfr",
                        duration_ms=self.browser.last_response_timing.ttfr_ms,
                        success=True
                    )

            if not response:
                self.on_status("! Nessuna risposta dal bot")
                if self.perf_collector:
                    self.perf_collector.record_timeout()
                break

            conversation.append(ConversationTurn(
                role='assistant',
                content=response,
                timestamp=datetime.utcnow().isoformat()
            ))

            self.on_status(f"Bot: {response[:60]}...")

            # Se single_turn, esci dopo la prima risposta
            if self.single_turn:
                self.on_status("Conversazione completata (single turn)")
                break

            # Decidi prossimo messaggio
            next_message = self.decide_next_message(
                conversation,
                remaining_followups,
                test
            )

            if not next_message:
                self.on_status("Conversazione completata")
                break

            # Rimuovi followup usato
            if next_message in remaining_followups:
                remaining_followups.remove(next_message)

            self.on_status(f"{next_message[:60]}...")
            await self.browser.send_message(next_message)

            conversation.append(ConversationTurn(
                role='user',
                content=next_message,
                timestamp=datetime.utcnow().isoformat()
            ))

        # Finale: Screenshot e Valutazione
        try:
            # PHASE: Screenshot
            skip_ss = False
            if self.project:
                skip_ss = getattr(self.project.chatbot, 'skip_screenshot', False)
            if self.run_config:
                skip_ss = skip_ss or getattr(self.run_config, 'skip_screenshots', False)

            if self.perf_collector and not skip_ss:
                self.perf_collector.start_phase("screenshot")

            screenshot_path = ""
            if self.settings.screenshot_on_complete and not skip_ss and self.report:
                ss_path = self.report.get_screenshot_path(test.id)
                success = await self.browser.take_conversation_screenshot(
                    path=ss_path,
                    hide_elements=['.llm__prompt', '.llm__footer', '.llm__busyIndicator', '.llm__scrollDown'],
                    thread_selector='.llm__thread'
                )
                if not success:
                    success = await self.browser.take_screenshot(
                        ss_path,
                        inject_css=self.project.chatbot.screenshot_css if self.project else None
                    )
                if success:
                    screenshot_path = str(ss_path)

            if self.perf_collector and not skip_ss:
                self.perf_collector.end_phase()

            html_response = None
            if self.settings.screenshot_on_complete and not skip_ss:
                html_response = await self.browser.get_thread_html()

            # Valutazione LLM
            final_response = conversation[-1].content if conversation else ""
            evaluation = None

            # LangSmith fetch
            langsmith_url = ""
            langsmith_report = ""
            model_version = ""
            report = None
            if self.langsmith:
                try:
                    langsmith_start = time.perf_counter()
                    report = self.langsmith.get_report_for_question(test.question)
                    langsmith_duration_ms = (time.perf_counter() - langsmith_start) * 1000

                    if self.perf_collector:
                        self.perf_collector.record_service_call(
                            service="langsmith",
                            operation="get_report",
                            duration_ms=langsmith_duration_ms,
                            success=report.trace_url is not None
                        )

                    if report.trace_url:
                        langsmith_url = report.trace_url
                        langsmith_report = report.format_for_sheets()
                        model_version = report.get_model_version()
                except Exception as e:
                    self.on_status(f"! Errore LangSmith: {e}")

            # Priorità 1: Evaluator
            if self.evaluator:
                try:
                    expected_answer = getattr(test, 'expected_answer', None)
                    rag_context_file = getattr(test, 'rag_context_file', None)

                    if not expected_answer and self.baselines:
                        baseline = self.baselines.get(test.id)
                        if baseline:
                            expected_answer = baseline.answer
                            self.on_status(f"  Baseline: usando golden answer da RUN {baseline.run_number}")

                    rag_context = None
                    auto_rag_cfg = self.settings.evaluation.auto_rag_context
                    use_auto_rag = auto_rag_cfg.enabled and (not rag_context_file or not auto_rag_cfg.prefer_manual)

                    if use_auto_rag and not rag_context_file and report and report.sources:
                        rag_context = report.get_rag_context(
                            max_docs=auto_rag_cfg.max_documents,
                            max_chars=auto_rag_cfg.max_chars
                        )
                        if rag_context:
                            self.on_status(f"  Auto RAG context: {len(report.sources)} docs")

                    output_validation = getattr(test, 'output_validation', None)

                    eval_result = self.evaluator.evaluate(
                        question=test.question,
                        response=final_response,
                        expected_answer=expected_answer,
                        expected_behavior=test.expected,
                        rag_context_file=rag_context_file,
                        rag_context=rag_context,
                        output_validation=output_validation,
                        html_response=html_response,
                        screenshot_path=screenshot_path if screenshot_path else None
                    )

                    evaluation = {
                        'passed': eval_result.passed,
                        'reason': eval_result.judge_reasoning or eval_result.summary(),
                        'details': eval_result.to_dict()
                    }
                except Exception as e:
                    self.on_status(f"! Errore Evaluation: {e}")
                    evaluation = None

            # Priorità 2: Ollama
            if evaluation is None and self.ollama:
                evaluation = self.ollama.evaluate_test_result(
                    test_case={'question': test.question, 'category': test.category, 'expected': test.expected},
                    conversation=[{'role': t.role, 'content': t.content} for t in conversation],
                    final_response=final_response
                )

            if evaluation is None:
                evaluation = {'passed': None, 'reason': 'Valutazione manuale richiesta'}

            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            test_result = "PASS" if evaluation.get('passed', False) else "FAIL"
            if self.perf_collector:
                self.perf_collector.end_test(test_result)

            return TestExecution(
                test_case=test,
                conversation=conversation,
                result=test_result,
                duration_ms=duration_ms,
                screenshot_path=screenshot_path,
                langsmith_url=langsmith_url,
                langsmith_report=langsmith_report,
                notes="",
                llm_evaluation=evaluation,
                model_version=model_version,
                prompt_version=self.run_config.prompt_version if self.run_config else ""
            )

        except Exception as e:
            if self.perf_collector:
                self.perf_collector.record_error(str(e))
                self.perf_collector.end_test("ERROR")

            return TestExecution(
                test_case=test,
                conversation=conversation,
                result="ERROR",
                duration_ms=0,
                notes=f"Errore: {e}"
            )

    async def execute_and_save(self, test: TestCase, max_turns: int = 10) -> TestExecution:
        """
        Execute test and persist results (deep module pattern).

        Combines execute_auto_test with persist for standalone usage.
        ChatbotTester can use this instead of calling both separately.

        Args:
            test: Test case to execute
            max_turns: Maximum conversation turns

        Returns:
            TestExecution with persisted results
        """
        execution = await self.execute_auto_test(test, max_turns)
        self.persist(execution)
        return execution

    def persist(self, execution: TestExecution) -> None:
        """
        Persist test execution to all configured outputs.

        Saves to:
        - Local report (if report configured)
        - Google Sheets (if sheets configured)

        Args:
            execution: Completed test execution to save
        """
        import time
        from pathlib import Path
        from zoneinfo import ZoneInfo

        date_str = datetime.now(ZoneInfo("Europe/Rome")).strftime('%Y-%m-%d %H:%M:%S')

        # Format conversation
        conv_str = "\n".join([
            f"{'USER' if t.role == 'user' else 'BOT'}: {t.content}"
            for t in execution.conversation
        ])

        # Save to local report
        if self.report:
            self.report.add_result(TestResult(
                test_id=execution.test_case.id,
                date=date_str,
                mode=self.ctx.current_mode.value.upper(),
                question=execution.test_case.question,
                conversation=conv_str,
                screenshot_path=execution.screenshot_path,
                result=execution.result,
                notes=execution.notes,
                langsmith_url=execution.langsmith_url,
                duration_ms=execution.duration_ms,
                category=execution.test_case.category,
                followups_count=len(execution.test_case.followups)
            ))

        # Save to Google Sheets
        sheets = self.ctx.sheets
        if sheets:
            sheets_start = time.perf_counter()

            screenshot_urls = None
            if execution.screenshot_path:
                screenshot_urls = sheets.upload_screenshot(
                    Path(execution.screenshot_path),
                    execution.test_case.id
                )

            # Build timing string from browser timing
            timing_str = ""
            if self.browser and self.browser.last_response_timing:
                timing = self.browser.last_response_timing
                if timing.ttfr_ms > 0 or timing.total_ms > 0:
                    ttfr_sec = timing.ttfr_ms / 1000
                    total_sec = timing.total_ms / 1000
                    timing_str = f"{ttfr_sec:.1f}s → {total_sec:.1f}s"

            # Extract evaluation metrics
            eval_data = execution.llm_evaluation or {}
            eval_details = eval_data.get('details', {})

            sheets.append_result(TestResult(
                test_id=execution.test_case.id,
                date=date_str,
                mode=self.ctx.current_mode.value.upper(),
                question=execution.test_case.question,
                expected=getattr(execution.test_case, 'expected_answer', '') or "",  # Golden answer
                conversation=conv_str[:5000],  # Sheets limit
                screenshot_urls=screenshot_urls,
                prompt_version=execution.prompt_version,
                model_version=execution.model_version,
                environment=self.run_config.env if self.run_config else "DEV",
                result=execution.result,  # PASS/FAIL from evaluation
                notes="",  # Empty - reviewer notes
                langsmith_report=execution.langsmith_report,
                langsmith_url=execution.langsmith_url,
                timing=timing_str,
                # GGP fields
                section=execution.test_case.section,
                target=execution.test_case.test_target,
                run_number=self.run_config.active_run if self.run_config else 0,
                # Evaluation metrics
                semantic_score=eval_details.get('semantic_score'),
                judge_score=eval_details.get('judge_score'),
                groundedness=eval_details.get('groundedness'),
                faithfulness=eval_details.get('faithfulness'),
                relevance=eval_details.get('relevance'),
                overall_score=eval_details.get('overall_score'),
                judge_reasoning=eval_data.get('reason', '')[:500]
            ))

            # Track Sheets performance
            sheets_duration_ms = (time.perf_counter() - sheets_start) * 1000
            if self.perf_collector and self.perf_collector._current_test is None:
                if self.perf_collector.run_metrics.test_metrics:
                    self.perf_collector.run_metrics.test_metrics[-1].add_service_call(
                        service="google_sheets",
                        operation="save_result",
                        duration_ms=sheets_duration_ms,
                        success=True
                    )
