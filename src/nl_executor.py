"""
Natural Language Executor - Maps intents to CLI actions

Bridges NLProcessor output to existing run.py functions.
"""

from dataclasses import dataclass
from typing import Optional, Any, Dict
from pathlib import Path
import sys

from .nl_processor import Intent, ActionType
from .ui import ConsoleUI, get_ui
from .config_loader import ConfigLoader


@dataclass
class ExecutionResult:
    """Result of executing an intent"""
    success: bool
    message: str
    data: Optional[Any] = None


class ActionExecutor:
    """
    Executes parsed intents by calling existing CLI functions.

    Usage:
        executor = ActionExecutor(ui)
        result = await executor.execute(intent)
    """

    def __init__(self, ui: ConsoleUI = None):
        self.ui = ui or get_ui()
        self.loader = ConfigLoader()

    async def execute(self, intent: Intent) -> ExecutionResult:
        """
        Execute a parsed intent.

        Args:
            intent: Parsed Intent from NLProcessor

        Returns:
            ExecutionResult with success status and message
        """
        if intent.action == ActionType.UNKNOWN:
            return ExecutionResult(
                success=False,
                message=intent.error or "Comando non riconosciuto. Digita 'help' per vedere i comandi."
            )

        # Route to appropriate handler
        handlers = {
            ActionType.RUN_TESTS: self._run_tests,
            ActionType.EXPORT_REPORT: self._export_report,
            ActionType.COMPARE_RUNS: self._compare_runs,
            ActionType.SHOW_STATUS: self._show_status,
            ActionType.LIST_PROJECTS: self._list_projects,
            ActionType.CREATE_PROJECT: self._create_project,
            ActionType.SHOW_REGRESSIONS: self._show_regressions,
            ActionType.DETECT_FLAKY: self._detect_flaky,
            ActionType.HEALTH_CHECK: self._health_check,
            ActionType.SHOW_PERFORMANCE: self._show_performance,
            ActionType.HELP: self._show_help,
        }

        handler = handlers.get(intent.action)
        if handler:
            try:
                return await handler(intent)
            except Exception as e:
                return ExecutionResult(
                    success=False,
                    message=f"Errore esecuzione: {str(e)}"
                )

        return ExecutionResult(
            success=False,
            message=f"Handler non implementato per {intent.action.value}"
        )

    def _validate_project(self, intent: Intent) -> Optional[str]:
        """Validate project exists, return error message if not"""
        if not intent.project:
            projects = self.loader.list_projects()
            if len(projects) == 1:
                # Auto-select if only one project
                intent.project = projects[0]
                self.ui.muted(f"  [Usando progetto: {intent.project}]")
                return None
            return f"Specifica un progetto. Disponibili: {', '.join(projects)}" if projects else "Nessun progetto configurato."

        projects = self.loader.list_projects()
        if intent.project not in projects:
            # Try fuzzy match
            matches = [p for p in projects if intent.project.lower() in p.lower()]
            if len(matches) == 1:
                intent.project = matches[0]
                self.ui.muted(f"  [Usando progetto: {intent.project}]")
                return None
            return f"Progetto '{intent.project}' non trovato. Disponibili: {', '.join(projects)}"

        return None

    async def _run_tests(self, intent: Intent) -> ExecutionResult:
        """Execute test run"""
        # Validate project
        error = self._validate_project(intent)
        if error:
            return ExecutionResult(success=False, message=error)

        if intent.cloud:
            # Cloud execution via CircleCI
            return await self._run_tests_cloud(intent)
        else:
            # Local execution
            return await self._run_tests_local(intent)

    async def _run_tests_cloud(self, intent: Intent) -> ExecutionResult:
        """Execute tests on CircleCI"""
        from .circleci_client import CircleCIClient

        ci_client = CircleCIClient()
        if not ci_client.is_available():
            return ExecutionResult(
                success=False,
                message="CircleCI non configurato. Imposta CIRCLECI_TOKEN."
            )

        self.ui.print(f"\n  Avvio test su CircleCI...")
        self.ui.print(f"    Progetto: {intent.project}")
        self.ui.print(f"    Modalita: {intent.mode or 'auto'}")
        self.ui.print(f"    Test: {intent.test_filter or 'pending'}")
        if intent.test_ids:
            self.ui.print(f"    Test specifici: {len(intent.test_ids)}")
        if intent.new_run:
            self.ui.print(f"    Nuovo run: Si")
        self.ui.print("")

        test_ids_str = ",".join(intent.test_ids) if intent.test_ids else ""

        success, data = ci_client.trigger_pipeline(
            intent.project,
            intent.mode or 'auto',
            intent.test_filter or 'pending',
            intent.new_run,
            intent.test_limit or 0,
            test_ids_str
        )

        if success:
            pipeline_number = data.get('number', '?')
            url = f"https://app.circleci.com/pipelines/gh/corradofrancolini/chatbot-tester-private/{pipeline_number}"
            self.ui.print(f"  URL: {url}")
            return ExecutionResult(
                success=True,
                message=f"Pipeline #{pipeline_number} avviata!",
                data={'pipeline_number': pipeline_number, 'url': url}
            )
        else:
            error_msg = data.get('error', 'Errore sconosciuto') if data else 'Errore sconosciuto'
            return ExecutionResult(
                success=False,
                message=f"Errore CircleCI: {error_msg}"
            )

    async def _run_tests_local(self, intent: Intent) -> ExecutionResult:
        """Execute tests locally"""
        from .tester import TestMode

        try:
            project = self.loader.load_project(intent.project)
            settings = self.loader.load_global_settings()

            # Import run_test_session from run.py
            sys.path.insert(0, str(Path(__file__).parent.parent))
            from run import run_test_session

            mode_map = {
                'train': TestMode.TRAIN,
                'assisted': TestMode.ASSISTED,
                'auto': TestMode.AUTO
            }
            mode = mode_map.get(intent.mode or 'auto', TestMode.AUTO)

            self.ui.print(f"\n  Avvio test locali...")
            self.ui.print(f"    Progetto: {intent.project}")
            self.ui.print(f"    Modalita: {mode.value}")
            self.ui.print(f"    Test: {intent.test_filter or 'pending'}")
            self.ui.print("")

            test_ids_str = ",".join(intent.test_ids) if intent.test_ids else ""

            await run_test_session(
                project,
                settings,
                mode,
                test_filter=intent.test_filter or 'pending',
                single_test=intent.test_id,
                force_new_run=intent.new_run,
                no_interactive=True,
                single_turn=intent.single_turn,
                test_limit=intent.test_limit or 0,
                test_ids=test_ids_str
            )

            return ExecutionResult(
                success=True,
                message=f"Test completati per {intent.project}"
            )

        except FileNotFoundError:
            return ExecutionResult(
                success=False,
                message=f"Progetto '{intent.project}' non trovato"
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                message=f"Errore esecuzione: {str(e)}"
            )

    async def _export_report(self, intent: Intent) -> ExecutionResult:
        """Export report"""
        error = self._validate_project(intent)
        if error:
            return ExecutionResult(success=False, message=error)

        try:
            # Create args-like object
            class Args:
                pass

            args = Args()
            args.project = intent.project
            args.export = intent.export_format or 'html'
            args.export_run = intent.run_number

            sys.path.insert(0, str(Path(__file__).parent.parent))
            from run import run_export_commands

            run_export_commands(args)

            return ExecutionResult(
                success=True,
                message=f"Report {intent.export_format or 'html'} esportato per {intent.project}"
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                message=f"Errore export: {str(e)}"
            )

    async def _compare_runs(self, intent: Intent) -> ExecutionResult:
        """Compare two runs"""
        error = self._validate_project(intent)
        if error:
            return ExecutionResult(success=False, message=error)

        try:
            if intent.run_a and intent.run_b:
                compare_value = f"{intent.run_a}:{intent.run_b}"
            else:
                compare_value = 'latest'

            class Args:
                pass

            args = Args()
            args.project = intent.project
            args.compare = compare_value
            args.regressions = None
            args.flaky = None

            sys.path.insert(0, str(Path(__file__).parent.parent))
            from run import run_cli_analysis

            run_cli_analysis(args)

            return ExecutionResult(
                success=True,
                message=f"Confronto completato per {intent.project}"
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                message=f"Errore confronto: {str(e)}"
            )

    async def _show_regressions(self, intent: Intent) -> ExecutionResult:
        """Show regressions"""
        error = self._validate_project(intent)
        if error:
            return ExecutionResult(success=False, message=error)

        try:
            class Args:
                pass

            args = Args()
            args.project = intent.project
            args.compare = None
            args.regressions = intent.run_number if intent.run_number else 0
            args.flaky = None

            sys.path.insert(0, str(Path(__file__).parent.parent))
            from run import run_cli_analysis

            run_cli_analysis(args)

            return ExecutionResult(
                success=True,
                message=f"Analisi regressioni completata per {intent.project}"
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                message=f"Errore analisi: {str(e)}"
            )

    async def _detect_flaky(self, intent: Intent) -> ExecutionResult:
        """Detect flaky tests"""
        error = self._validate_project(intent)
        if error:
            return ExecutionResult(success=False, message=error)

        try:
            class Args:
                pass

            args = Args()
            args.project = intent.project
            args.compare = None
            args.regressions = None
            args.flaky = 10

            sys.path.insert(0, str(Path(__file__).parent.parent))
            from run import run_cli_analysis

            run_cli_analysis(args)

            return ExecutionResult(
                success=True,
                message=f"Analisi flaky tests completata per {intent.project}"
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                message=f"Errore analisi: {str(e)}"
            )

    async def _show_status(self, intent: Intent) -> ExecutionResult:
        """Show project status"""
        if intent.project:
            error = self._validate_project(intent)
            if error:
                return ExecutionResult(success=False, message=error)

            try:
                project = self.loader.load_project(intent.project)
                from .config_loader import RunConfig
                run_config = RunConfig.load(project.run_config_file)

                self.ui.print(f"\n  Stato progetto: {intent.project}")
                self.ui.print(f"    Ambiente: {run_config.env}")
                self.ui.print(f"    RUN attiva: {run_config.active_run}")
                self.ui.print(f"    Test completati: {run_config.tests_completed}")
                self.ui.print(f"    Ultimo test: {run_config.last_test_id or 'N/A'}")
                self.ui.print(f"    Prompt version: {run_config.prompt_version or 'N/A'}")
                self.ui.print(f"    Single turn: {'Si' if run_config.single_turn else 'No'}")
                self.ui.print("")

                return ExecutionResult(
                    success=True,
                    message=f"Stato mostrato per {intent.project}"
                )
            except Exception as e:
                return ExecutionResult(
                    success=False,
                    message=f"Errore: {str(e)}"
                )
        else:
            # Show all projects status
            return await self._list_projects(intent)

    async def _list_projects(self, intent: Intent) -> ExecutionResult:
        """List available projects"""
        projects = self.loader.list_projects()

        if not projects:
            return ExecutionResult(
                success=True,
                message="Nessun progetto configurato. Usa 'crea nuovo progetto' per iniziare."
            )

        self.ui.print("\n  Progetti disponibili:")
        for p in projects:
            try:
                project = self.loader.load_project(p)
                from .config_loader import RunConfig
                run_config = RunConfig.load(project.run_config_file)
                status = f"RUN {run_config.active_run}, {run_config.tests_completed} test"
            except:
                status = "N/A"
            self.ui.print(f"    - {p} ({status})")
        self.ui.print("")

        return ExecutionResult(
            success=True,
            message=f"Trovati {len(projects)} progetti",
            data={'projects': projects}
        )

    async def _create_project(self, intent: Intent) -> ExecutionResult:
        """Create new project (launches wizard)"""
        self.ui.print("\n  Avvio wizard creazione progetto...")

        try:
            from wizard.main import run_wizard
            success = run_wizard(language="it")

            if success:
                return ExecutionResult(
                    success=True,
                    message="Progetto creato con successo!"
                )
            else:
                return ExecutionResult(
                    success=False,
                    message="Creazione progetto annullata"
                )
        except Exception as e:
            return ExecutionResult(
                success=False,
                message=f"Errore wizard: {str(e)}"
            )

    async def _health_check(self, intent: Intent) -> ExecutionResult:
        """Run health check"""
        try:
            project = None
            settings = None

            if intent.project:
                error = self._validate_project(intent)
                if not error:
                    project = self.loader.load_project(intent.project)
                    settings = self.loader.load_global_settings()

            sys.path.insert(0, str(Path(__file__).parent.parent))
            from run import run_health_check

            success = run_health_check(project, settings)

            return ExecutionResult(
                success=success,
                message="Health check completato" if success else "Health check fallito"
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                message=f"Errore health check: {str(e)}"
            )

    async def _show_performance(self, intent: Intent) -> ExecutionResult:
        """Show performance metrics"""
        error = self._validate_project(intent)
        if error:
            return ExecutionResult(success=False, message=error)

        try:
            class Args:
                pass

            args = Args()
            args.project = intent.project
            args.perf_report = intent.run_number if intent.run_number else 0
            args.perf_dashboard = None
            args.perf_compare = None
            args.perf_export = None
            args.list_runs = None

            sys.path.insert(0, str(Path(__file__).parent.parent))
            from run import run_cli_performance

            run_cli_performance(args)

            return ExecutionResult(
                success=True,
                message=f"Performance mostrate per {intent.project}"
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                message=f"Errore performance: {str(e)}"
            )

    async def _show_help(self, intent: Intent) -> ExecutionResult:
        """Show help"""
        help_text = """
  Comandi disponibili (linguaggio naturale):

  ESECUZIONE TEST:
    - "lancia test [progetto] in auto"
    - "esegui [progetto] nel cloud"
    - "testa [progetto] con nuova run"
    - "esegui solo test falliti di [progetto]"
    - "esegui primi 5 test di [progetto]"
    - "esegui TEST_001 di [progetto]"

  EXPORT:
    - "esporta pdf di [progetto]"
    - "esporta excel run 15 di [progetto]"

  ANALISI:
    - "confronta run 15 e 16 di [progetto]"
    - "mostra regressioni [progetto]"
    - "test flaky [progetto]"
    - "performance [progetto]"

  PROGETTI:
    - "quali progetti ho?" / "lista progetti"
    - "stato [progetto]"
    - "crea nuovo progetto"

  SISTEMA:
    - "health check"
    - "help" / "aiuto"

  Per uscire dalla chat: "exit" o "quit"
"""
        self.ui.print(help_text)

        return ExecutionResult(
            success=True,
            message="Aiuto mostrato"
        )
