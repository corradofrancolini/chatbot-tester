"""
Parallel Test Runner - Esecuzione test in parallelo

Permette di eseguire piu test contemporaneamente usando
pool di browser Playwright. Ottimizza i tempi di esecuzione
per suite di test grandi.

Features:
- Pool di browser riutilizzabili
- Esecuzione parallela con asyncio
- Retry automatico con backoff
- Progress tracking in tempo reale
- Rate limiting per evitare sovraccarico
"""

import asyncio
from dataclasses import dataclass, field
from typing import Optional, List, Callable, Any, Dict
from datetime import datetime
from enum import Enum
from pathlib import Path
import time

from .browser import BrowserManager, BrowserSettings, ChatbotSelectors
from .tester import TestCase, TestExecution, ConversationTurn


class RetryStrategy(Enum):
    """Strategie di retry disponibili"""
    NONE = "none"
    LINEAR = "linear"          # Attesa fissa tra retry
    EXPONENTIAL = "exponential"  # Backoff esponenziale


@dataclass
class ParallelConfig:
    """Configurazione per esecuzione parallela"""
    max_workers: int = 3               # Numero browser paralleli
    retry_strategy: RetryStrategy = RetryStrategy.EXPONENTIAL
    max_retries: int = 2               # Tentativi massimi per test
    base_delay_ms: int = 1000          # Delay base tra retry
    max_delay_ms: int = 30000          # Delay massimo
    rate_limit_per_minute: int = 60    # Limite richieste/minuto
    batch_size: int = 10               # Test per batch
    timeout_per_test_ms: int = 120000  # Timeout singolo test


@dataclass
class WorkerState:
    """Stato di un worker nel pool"""
    worker_id: int
    browser: Optional[BrowserManager] = None
    is_busy: bool = False
    tests_completed: int = 0
    current_test: Optional[str] = None
    last_activity: float = 0.0


@dataclass
class ParallelResult:
    """Risultato esecuzione parallela"""
    total_tests: int
    completed: int
    passed: int
    failed: int
    errors: int
    skipped: int
    duration_ms: int
    results: List[TestExecution] = field(default_factory=list)
    worker_stats: Dict[int, Dict] = field(default_factory=dict)


class BrowserPool:
    """
    Pool di browser riutilizzabili per esecuzione parallela.

    Gestisce un numero fisso di istanze browser che vengono
    riutilizzate tra i test per evitare l'overhead di avvio.
    """

    def __init__(self,
                 size: int,
                 settings: BrowserSettings,
                 selectors: ChatbotSelectors):
        self.size = size
        self.settings = settings
        self.selectors = selectors
        self._workers: Dict[int, WorkerState] = {}
        self._available: asyncio.Queue = asyncio.Queue()
        self._lock = asyncio.Lock()
        self._initialized = False

    async def initialize(self) -> bool:
        """Inizializza il pool di browser"""
        import shutil
        from pathlib import Path

        if self._initialized:
            return True

        print(f"Inizializzazione pool di {self.size} browser...")

        for i in range(self.size):
            worker = WorkerState(worker_id=i)

            # Crea directory worker e copia auth state se presente
            worker_data_dir = None
            if self.settings.user_data_dir:
                worker_data_dir = Path(self.settings.user_data_dir) / f"worker_{i}"
                worker_data_dir.mkdir(parents=True, exist_ok=True)

                # Copia state.json (auth) nella directory worker
                parent_state = Path(self.settings.user_data_dir) / "state.json"
                if parent_state.exists():
                    worker_state = worker_data_dir / "state.json"
                    shutil.copy2(parent_state, worker_state)
                    print(f"  Worker {i}: auth state copiato")

            # Crea una copia delle settings con user_data_dir univoco
            worker_settings = BrowserSettings(
                headless=self.settings.headless,
                viewport_width=self.settings.viewport_width,
                viewport_height=self.settings.viewport_height,
                device_scale_factor=self.settings.device_scale_factor,
                user_data_dir=worker_data_dir,
                timeout_page_load=self.settings.timeout_page_load,
                timeout_bot_response=self.settings.timeout_bot_response
            )

            worker.browser = BrowserManager(worker_settings, self.selectors)

            try:
                await worker.browser.start()
                worker.last_activity = time.time()
                self._workers[i] = worker
                await self._available.put(i)
                print(f"  Worker {i}: pronto")
            except Exception as e:
                print(f"  Worker {i}: errore - {e}")
                # Continua con gli altri worker

        self._initialized = len(self._workers) > 0

        if self._initialized:
            print(f"Pool inizializzato: {len(self._workers)} browser attivi")
        else:
            print("Errore: nessun browser disponibile")

        return self._initialized

    async def acquire(self, timeout_seconds: float = 60) -> Optional[WorkerState]:
        """
        Ottiene un worker dal pool.

        Args:
            timeout_seconds: Timeout attesa worker

        Returns:
            WorkerState o None se timeout
        """
        try:
            worker_id = await asyncio.wait_for(
                self._available.get(),
                timeout=timeout_seconds
            )

            async with self._lock:
                worker = self._workers[worker_id]
                worker.is_busy = True
                worker.last_activity = time.time()
                return worker

        except asyncio.TimeoutError:
            return None

    async def release(self, worker: WorkerState) -> None:
        """Rilascia un worker al pool"""
        async with self._lock:
            worker.is_busy = False
            worker.current_test = None
            worker.last_activity = time.time()
            await self._available.put(worker.worker_id)

    async def shutdown(self) -> None:
        """Chiude tutti i browser nel pool"""
        print("Chiusura pool browser...")

        for worker_id, worker in self._workers.items():
            if worker.browser:
                try:
                    await worker.browser.stop()
                    print(f"  Worker {worker_id}: chiuso")
                except Exception as e:
                    print(f"  Worker {worker_id}: errore chiusura - {e}")

        self._workers.clear()
        self._initialized = False

    def get_stats(self) -> Dict[int, Dict]:
        """Statistiche dei worker"""
        stats = {}
        for worker_id, worker in self._workers.items():
            stats[worker_id] = {
                "tests_completed": worker.tests_completed,
                "is_busy": worker.is_busy,
                "current_test": worker.current_test,
                "last_activity": worker.last_activity
            }
        return stats


class ParallelTestRunner:
    """
    Esecutore di test paralleli con pool di browser.

    Usage:
        config = ParallelConfig(max_workers=3)
        runner = ParallelTestRunner(project, settings, config)

        results = await runner.run(test_cases)

        print(f"Completati: {results.completed}/{results.total_tests}")
        print(f"Passati: {results.passed}, Falliti: {results.failed}")
    """

    def __init__(self,
                 browser_settings: BrowserSettings,
                 selectors: ChatbotSelectors,
                 config: ParallelConfig,
                 ollama_client: Any = None,
                 langsmith_client: Any = None,
                 on_progress: Optional[Callable[[int, int, str], None]] = None,
                 on_test_complete: Optional[Callable[[TestExecution], None]] = None,
                 report_dir: Optional[Path] = None,
                 run_config: Any = None,
                 screenshot_css: str = ""):
        """
        Args:
            browser_settings: Settings browser
            selectors: Selettori chatbot
            config: Configurazione parallela
            ollama_client: Client Ollama per valutazione
            langsmith_client: Client LangSmith per debug
            on_progress: Callback (completed, total, current_test_id)
            on_test_complete: Callback per ogni test completato
            report_dir: Directory per salvare screenshots
            run_config: Configurazione run (per prompt_version, env)
            screenshot_css: CSS da iniettare per screenshots
        """
        self.browser_settings = browser_settings
        self.selectors = selectors
        self.config = config
        self.ollama = ollama_client
        self.langsmith = langsmith_client
        self.on_progress = on_progress or (lambda c, t, s: None)
        self.on_test_complete = on_test_complete
        self.report_dir = report_dir
        self.run_config = run_config
        self.screenshot_css = screenshot_css

        self._pool: Optional[BrowserPool] = None
        self._rate_limiter = RateLimiter(config.rate_limit_per_minute)
        self._completed = 0
        self._total = 0
        self._results_lock = asyncio.Lock()

    async def run(self,
                  tests: List[TestCase],
                  chatbot_url: str,
                  single_turn: bool = False) -> ParallelResult:
        """
        Esegue i test in parallelo.

        Args:
            tests: Lista test da eseguire
            chatbot_url: URL del chatbot
            single_turn: Se True, solo domanda iniziale

        Returns:
            ParallelResult con statistiche e risultati
        """
        self._total = len(tests)
        self._completed = 0
        start_time = time.time()
        results: List[TestExecution] = []

        if not tests:
            return ParallelResult(
                total_tests=0,
                completed=0,
                passed=0,
                failed=0,
                errors=0,
                skipped=0,
                duration_ms=0
            )

        # Inizializza pool browser
        self._pool = BrowserPool(
            size=min(self.config.max_workers, len(tests)),
            settings=self.browser_settings,
            selectors=self.selectors
        )

        if not await self._pool.initialize():
            return ParallelResult(
                total_tests=len(tests),
                completed=0,
                passed=0,
                failed=0,
                errors=len(tests),
                skipped=0,
                duration_ms=0
            )

        try:
            # Semaforo per limitare parallelismo PRIMA di creare i task
            semaphore = asyncio.Semaphore(self.config.max_workers)

            async def run_with_semaphore(test):
                """Esegue test con controllo semaforo"""
                async with semaphore:
                    return await self._run_single_test(test, chatbot_url, single_turn)

            # Esegui tutti i test con parallelismo controllato
            print(f"Avvio {len(tests)} test con {self.config.max_workers} worker paralleli...")
            completed_results = await asyncio.gather(
                *[run_with_semaphore(test) for test in tests],
                return_exceptions=True
            )

            # Processa risultati
            for i, result in enumerate(completed_results):
                if isinstance(result, Exception):
                    # Log errore e crea risultato ERROR
                    print(f"  Test {tests[i].id}: EXCEPTION - {result}")
                    results.append(TestExecution(
                        test_case=tests[i],
                        conversation=[],
                        result="ERROR",
                        duration_ms=0,
                        notes=f"Exception: {result}"
                    ))
                elif isinstance(result, TestExecution):
                    results.append(result)
                else:
                    print(f"  Test {tests[i].id}: risultato inatteso - {type(result)}")

        finally:
            await self._pool.shutdown()

        # Calcola statistiche
        duration_ms = int((time.time() - start_time) * 1000)
        passed = sum(1 for r in results if r.result == "PASS")
        failed = sum(1 for r in results if r.result == "FAIL")
        errors = sum(1 for r in results if r.result == "ERROR")
        skipped = sum(1 for r in results if r.result == "SKIP")

        return ParallelResult(
            total_tests=len(tests),
            completed=len(results),
            passed=passed,
            failed=failed,
            errors=errors,
            skipped=skipped,
            duration_ms=duration_ms,
            results=results,
            worker_stats=self._pool.get_stats() if self._pool else {}
        )

    async def _run_single_test(self,
                                test: TestCase,
                                chatbot_url: str,
                                single_turn: bool) -> TestExecution:
        """Esegue un singolo test con retry"""
        last_error = None

        for attempt in range(self.config.max_retries + 1):
            try:
                # Rate limiting
                await self._rate_limiter.acquire()

                # Ottieni worker dal pool
                worker = await self._pool.acquire(timeout_seconds=60)

                if not worker:
                    raise RuntimeError("Nessun worker disponibile")

                worker.current_test = test.id

                try:
                    result = await self._execute_test(
                        worker, test, chatbot_url, single_turn
                    )

                    # Aggiorna statistiche worker
                    worker.tests_completed += 1

                    # Progress callback
                    async with self._results_lock:
                        self._completed += 1
                        self.on_progress(self._completed, self._total, test.id)

                    # Test complete callback
                    if self.on_test_complete:
                        self.on_test_complete(result)

                    return result

                finally:
                    await self._pool.release(worker)

            except Exception as e:
                last_error = e

                # Calcola delay per retry
                if attempt < self.config.max_retries:
                    delay = self._calculate_retry_delay(attempt)
                    print(f"  Test {test.id}: retry {attempt + 1}/{self.config.max_retries} "
                          f"tra {delay}ms ({e})")
                    await asyncio.sleep(delay / 1000)

        # Tutti i retry falliti
        return TestExecution(
            test_case=test,
            conversation=[],
            result="ERROR",
            duration_ms=0,
            notes=f"Fallito dopo {self.config.max_retries + 1} tentativi: {last_error}"
        )

    async def _execute_test(self,
                            worker: WorkerState,
                            test: TestCase,
                            chatbot_url: str,
                            single_turn: bool) -> TestExecution:
        """Esecuzione effettiva di un test"""
        conversation = []
        start_time = time.time()

        browser = worker.browser

        # Naviga al chatbot
        await browser.navigate(chatbot_url)
        await asyncio.sleep(0.5)

        # Invia domanda iniziale
        await browser.send_message(test.question)

        conversation.append(ConversationTurn(
            role='user',
            content=test.question,
            timestamp=datetime.utcnow().isoformat()
        ))

        # Attendi risposta
        response = await browser.wait_for_response()

        if response:
            conversation.append(ConversationTurn(
                role='assistant',
                content=response,
                timestamp=datetime.utcnow().isoformat()
            ))

        # Se non single_turn, continua con followup
        if not single_turn and response:
            remaining_followups = test.followups.copy()
            turn = 0
            max_turns = 10

            while turn < max_turns and remaining_followups:
                turn += 1

                # Decidi prossimo messaggio
                next_msg = self._decide_next(
                    conversation, remaining_followups, test
                )

                if not next_msg:
                    break

                if next_msg in remaining_followups:
                    remaining_followups.remove(next_msg)

                await browser.send_message(next_msg)

                conversation.append(ConversationTurn(
                    role='user',
                    content=next_msg,
                    timestamp=datetime.utcnow().isoformat()
                ))

                response = await browser.wait_for_response()

                if response:
                    conversation.append(ConversationTurn(
                        role='assistant',
                        content=response,
                        timestamp=datetime.utcnow().isoformat()
                    ))
                else:
                    break

        # Screenshot
        screenshot_path = ""
        if self.report_dir:
            try:
                ss_dir = self.report_dir / "screenshots"
                ss_dir.mkdir(parents=True, exist_ok=True)
                ss_path = ss_dir / f"{test.id}.png"

                # Usa take_conversation_screenshot se disponibile
                if hasattr(browser, 'take_conversation_screenshot'):
                    success = await browser.take_conversation_screenshot(
                        path=ss_path,
                        hide_elements=['.llm__prompt', '.llm__footer', '.llm__busyIndicator', '.llm__scrollDown'],
                        thread_selector='.llm__thread'
                    )
                else:
                    success = await browser.take_screenshot(ss_path)

                if success:
                    screenshot_path = str(ss_path)
            except Exception as e:
                print(f"  Screenshot error for {test.id}: {e}")

        # LangSmith
        langsmith_url = ""
        langsmith_report = ""
        model_version = ""
        vector_store = ""
        if self.langsmith:
            try:
                report = self.langsmith.get_report_for_question(test.question)
                if report and report.trace_url:
                    langsmith_url = report.trace_url
                    langsmith_report = report.format_for_sheets()
                    model_version = report.get_model_version()
                    vector_store = report.vector_store
            except Exception as e:
                print(f"  LangSmith error for {test.id}: {e}")

        # Timing from browser
        timing_str = ""
        if hasattr(browser, 'last_response_timing') and browser.last_response_timing:
            timing = browser.last_response_timing
            if timing.ttfr_ms > 0 or timing.total_ms > 0:
                ttfr_sec = timing.ttfr_ms / 1000
                total_sec = timing.total_ms / 1000
                timing_str = f"{ttfr_sec:.1f}s → {total_sec:.1f}s"

        # Valutazione
        evaluation = {"passed": None, "reason": ""}
        if self.ollama and conversation:
            final_response = conversation[-1].content if conversation[-1].role == 'assistant' else ""
            evaluation = self.ollama.evaluate_test_result(
                test_case={'question': test.question, 'category': test.category, 'expected': test.expected},
                conversation=[{'role': t.role, 'content': t.content} for t in conversation],
                final_response=final_response
            )

        duration_ms = int((time.time() - start_time) * 1000)

        # Prompt version from run_config
        prompt_version = ""
        if self.run_config and hasattr(self.run_config, 'prompt_version'):
            prompt_version = self.run_config.prompt_version

        return TestExecution(
            test_case=test,
            conversation=conversation,
            result="PASS" if evaluation.get('passed', False) else "FAIL",
            duration_ms=duration_ms,
            screenshot_path=screenshot_path,
            notes=evaluation.get('reason', ''),
            langsmith_url=langsmith_url,
            langsmith_report=langsmith_report,
            llm_evaluation=evaluation,
            model_version=model_version,
            prompt_version=prompt_version,
            timing=timing_str,
            vector_store=vector_store
        )

    def _decide_next(self,
                     conversation: List[ConversationTurn],
                     followups: List[str],
                     test: TestCase) -> Optional[str]:
        """Decide prossimo messaggio (versione semplificata)"""
        if self.ollama:
            bot_message = ""
            for turn in reversed(conversation):
                if turn.role == 'assistant':
                    bot_message = turn.content
                    break

            conv_dicts = [{'role': t.role, 'content': t.content} for t in conversation]
            return self.ollama.decide_response(
                bot_message=bot_message,
                conversation=conv_dicts,
                followups=followups if followups else None,
                test_context=test.category
            )

        return followups[0] if followups else None

    def _calculate_retry_delay(self, attempt: int) -> int:
        """Calcola delay per retry basato sulla strategia"""
        if self.config.retry_strategy == RetryStrategy.NONE:
            return 0

        if self.config.retry_strategy == RetryStrategy.LINEAR:
            return self.config.base_delay_ms

        if self.config.retry_strategy == RetryStrategy.EXPONENTIAL:
            delay = self.config.base_delay_ms * (2 ** attempt)
            return min(delay, self.config.max_delay_ms)

        return self.config.base_delay_ms


class RateLimiter:
    """
    Rate limiter con sliding window.

    Previene sovraccarico del server limitando le richieste per minuto.
    """

    def __init__(self, max_per_minute: int):
        self.max_per_minute = max_per_minute
        self._timestamps: List[float] = []
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Attende se necessario per rispettare il rate limit"""
        async with self._lock:
            now = time.time()

            # Rimuovi timestamp vecchi (> 1 minuto)
            self._timestamps = [t for t in self._timestamps if now - t < 60]

            if len(self._timestamps) >= self.max_per_minute:
                # Attendi che il timestamp piu vecchio scada
                oldest = self._timestamps[0]
                wait_time = 60 - (now - oldest) + 0.1
                if wait_time > 0:
                    await asyncio.sleep(wait_time)

            self._timestamps.append(time.time())


@dataclass
class PerformanceMetrics:
    """Metriche di performance per analisi"""
    test_id: str
    duration_ms: int
    browser_init_ms: int = 0
    navigation_ms: int = 0
    response_wait_ms: int = 0
    screenshot_ms: int = 0
    evaluation_ms: int = 0
    retry_count: int = 0


class MetricsCollector:
    """
    Raccoglie metriche di performance per analisi e ottimizzazione.
    """

    def __init__(self):
        self._metrics: List[PerformanceMetrics] = []
        self._lock = asyncio.Lock()

    async def record(self, metrics: PerformanceMetrics) -> None:
        """Registra metriche per un test"""
        async with self._lock:
            self._metrics.append(metrics)

    def get_summary(self) -> Dict[str, Any]:
        """Calcola statistiche aggregate"""
        if not self._metrics:
            return {}

        durations = [m.duration_ms for m in self._metrics]

        return {
            "total_tests": len(self._metrics),
            "total_duration_ms": sum(durations),
            "avg_duration_ms": sum(durations) / len(durations),
            "min_duration_ms": min(durations),
            "max_duration_ms": max(durations),
            "total_retries": sum(m.retry_count for m in self._metrics),
            "breakdown": {
                "avg_navigation_ms": sum(m.navigation_ms for m in self._metrics) / len(self._metrics),
                "avg_response_wait_ms": sum(m.response_wait_ms for m in self._metrics) / len(self._metrics),
                "avg_screenshot_ms": sum(m.screenshot_ms for m in self._metrics) / len(self._metrics),
                "avg_evaluation_ms": sum(m.evaluation_ms for m in self._metrics) / len(self._metrics)
            }
        }

    def export_csv(self, path: str) -> None:
        """Esporta metriche in CSV"""
        import csv

        with open(path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                'test_id', 'duration_ms', 'navigation_ms',
                'response_wait_ms', 'screenshot_ms', 'evaluation_ms', 'retry_count'
            ])

            for m in self._metrics:
                writer.writerow([
                    m.test_id, m.duration_ms, m.navigation_ms,
                    m.response_wait_ms, m.screenshot_ms, m.evaluation_ms, m.retry_count
                ])
