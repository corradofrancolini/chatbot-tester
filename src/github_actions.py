"""
GitHub Actions Integration - Esecuzione test nel cloud

Permette di lanciare test su GitHub Actions senza browser locale.
Richiede: gh CLI installato e autenticato.
"""

import subprocess
import json
import re
import time
from dataclasses import dataclass, field
from typing import Optional, List, Tuple, Callable
from enum import Enum
from datetime import datetime


class RunStatus(Enum):
    """Stato di un workflow run"""
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failure"
    SUCCESS = "success"
    CANCELLED = "cancelled"


@dataclass
class WorkflowRun:
    """Rappresenta un run di workflow"""
    id: int
    name: str
    status: str
    conclusion: Optional[str]
    created_at: str
    url: str


class GitHubActionsClient:
    """
    Client per interagire con GitHub Actions via gh CLI.

    Usage:
        client = GitHubActionsClient()

        # Verifica disponibilita
        if not client.is_available():
            print("gh CLI non disponibile")
            return

        # Lancia workflow
        success, msg = client.trigger_workflow("my-chatbot", "auto")

        # Lista run recenti
        runs = client.list_runs()

        # Stato run specifico
        run = client.get_run_status(run_id)
    """

    WORKFLOW_FILE = "chatbot-test.yml"

    def __init__(self):
        self._gh_available: Optional[bool] = None
        self._repo: Optional[str] = None

    def is_available(self) -> bool:
        """Verifica se gh CLI e disponibile e autenticato"""
        if self._gh_available is not None:
            return self._gh_available

        try:
            # Verifica gh installato
            result = subprocess.run(
                ["gh", "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode != 0:
                self._gh_available = False
                return False

            # Verifica autenticazione
            result = subprocess.run(
                ["gh", "auth", "status"],
                capture_output=True,
                text=True,
                timeout=5
            )
            self._gh_available = result.returncode == 0
            return self._gh_available

        except (subprocess.TimeoutExpired, FileNotFoundError):
            self._gh_available = False
            return False

    def get_install_instructions(self) -> str:
        """Istruzioni per installare gh CLI"""
        return """
Per usare l'esecuzione cloud, installa GitHub CLI:

  brew install gh
  gh auth login

Poi riprova.
"""

    def trigger_workflow(
        self,
        project: str,
        mode: str = "auto",
        tests: str = "pending",
        new_run: bool = False
    ) -> Tuple[bool, str]:
        """
        Lancia il workflow di test.

        Args:
            project: Nome progetto
            mode: Modalita test (train/assisted/auto)
            tests: Quali test (all/pending/failed)
            new_run: Se creare nuovo run

        Returns:
            (success, message)
        """
        if not self.is_available():
            return False, "gh CLI non disponibile"

        try:
            cmd = [
                "gh", "workflow", "run", self.WORKFLOW_FILE,
                "-f", f"project={project}",
                "-f", f"mode={mode}",
                "-f", f"tests={tests}",
                "-f", f"new_run={'true' if new_run else 'false'}"
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                return True, f"Workflow avviato per '{project}' in modalita '{mode}'"
            else:
                error = result.stderr.strip() or result.stdout.strip()
                return False, f"Errore: {error}"

        except subprocess.TimeoutExpired:
            return False, "Timeout nell'avvio del workflow"
        except Exception as e:
            return False, f"Errore: {str(e)}"

    def list_runs(self, limit: int = 10) -> List[WorkflowRun]:
        """
        Lista i run recenti del workflow.

        Args:
            limit: Numero massimo di run da restituire

        Returns:
            Lista di WorkflowRun
        """
        if not self.is_available():
            return []

        try:
            result = subprocess.run(
                [
                    "gh", "run", "list",
                    "--workflow", self.WORKFLOW_FILE,
                    "--limit", str(limit),
                    "--json", "databaseId,displayTitle,status,conclusion,createdAt,url"
                ],
                capture_output=True,
                text=True,
                timeout=15
            )

            if result.returncode != 0:
                return []

            data = json.loads(result.stdout)
            runs = []

            for item in data:
                runs.append(WorkflowRun(
                    id=item.get("databaseId", 0),
                    name=item.get("displayTitle", ""),
                    status=item.get("status", ""),
                    conclusion=item.get("conclusion"),
                    created_at=item.get("createdAt", ""),
                    url=item.get("url", "")
                ))

            return runs

        except (subprocess.TimeoutExpired, json.JSONDecodeError):
            return []

    def get_run_status(self, run_id: int) -> Optional[WorkflowRun]:
        """
        Ottiene lo stato di un run specifico.

        Args:
            run_id: ID del run

        Returns:
            WorkflowRun o None
        """
        if not self.is_available():
            return None

        try:
            result = subprocess.run(
                [
                    "gh", "run", "view", str(run_id),
                    "--json", "databaseId,displayTitle,status,conclusion,createdAt,url"
                ],
                capture_output=True,
                text=True,
                timeout=15
            )

            if result.returncode != 0:
                return None

            item = json.loads(result.stdout)

            return WorkflowRun(
                id=item.get("databaseId", 0),
                name=item.get("displayTitle", ""),
                status=item.get("status", ""),
                conclusion=item.get("conclusion"),
                created_at=item.get("createdAt", ""),
                url=item.get("url", "")
            )

        except (subprocess.TimeoutExpired, json.JSONDecodeError):
            return None

    def watch_run(self, run_id: int = None) -> Tuple[bool, str]:
        """
        Apre il watch interattivo per un run (o l'ultimo).

        Args:
            run_id: ID del run (None = ultimo)

        Returns:
            (success, message)
        """
        if not self.is_available():
            return False, "gh CLI non disponibile"

        try:
            cmd = ["gh", "run", "watch"]
            if run_id:
                cmd.append(str(run_id))

            # Questo comando e interattivo, quindi usiamo call
            result = subprocess.call(cmd, timeout=600)

            return result == 0, "Watch completato"

        except subprocess.TimeoutExpired:
            return False, "Timeout"
        except Exception as e:
            return False, str(e)

    def download_artifacts(self, run_id: int, dest_dir: str = ".") -> Tuple[bool, str]:
        """
        Scarica gli artifacts di un run.

        Args:
            run_id: ID del run
            dest_dir: Directory di destinazione

        Returns:
            (success, message)
        """
        if not self.is_available():
            return False, "gh CLI non disponibile"

        try:
            result = subprocess.run(
                ["gh", "run", "download", str(run_id), "-D", dest_dir],
                capture_output=True,
                text=True,
                timeout=120
            )

            if result.returncode == 0:
                return True, f"Artifacts scaricati in {dest_dir}"
            else:
                return False, result.stderr.strip() or "Errore download"

        except subprocess.TimeoutExpired:
            return False, "Timeout download"

    def get_run_logs(self, run_id: int) -> Tuple[bool, str]:
        """
        Ottiene i log di un run.

        Args:
            run_id: ID del run

        Returns:
            (success, logs)
        """
        if not self.is_available():
            return False, "gh CLI non disponibile"

        try:
            result = subprocess.run(
                ["gh", "run", "view", str(run_id), "--log"],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                return True, result.stdout
            else:
                return False, result.stderr.strip()

        except subprocess.TimeoutExpired:
            return False, "Timeout"

    def get_job_id(self, run_id: int) -> Optional[int]:
        """
        Ottiene l'ID del job principale di un run.

        Args:
            run_id: ID del run

        Returns:
            Job ID o None
        """
        if not self.is_available():
            return None

        try:
            result = subprocess.run(
                ["gh", "run", "view", str(run_id), "--json", "jobs"],
                capture_output=True,
                text=True,
                timeout=15
            )

            if result.returncode != 0:
                return None

            data = json.loads(result.stdout)
            jobs = data.get("jobs", [])
            if jobs:
                return jobs[0].get("databaseId")
            return None

        except (subprocess.TimeoutExpired, json.JSONDecodeError):
            return None

    def get_job_steps(self, job_id: int) -> List[dict]:
        """
        Ottiene gli step di un job con il loro stato.

        Args:
            job_id: ID del job

        Returns:
            Lista di step con nome, stato, conclusione
        """
        if not self.is_available():
            return []

        try:
            result = subprocess.run(
                ["gh", "api", f"/repos/{{owner}}/{{repo}}/actions/jobs/{job_id}",
                 "--jq", ".steps"],
                capture_output=True,
                text=True,
                timeout=15
            )

            if result.returncode != 0:
                return []

            return json.loads(result.stdout)

        except (subprocess.TimeoutExpired, json.JSONDecodeError):
            return []

    def stream_run_logs(self, run_id: int) -> subprocess.Popen:
        """
        Avvia lo streaming dei log in tempo reale.

        Args:
            run_id: ID del run

        Returns:
            Processo Popen per leggere stdout
        """
        return subprocess.Popen(
            ["gh", "run", "watch", str(run_id), "--exit-status"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )


@dataclass
class TestProgress:
    """Stato di avanzamento di un test"""
    test_id: str
    status: str = "pending"  # pending, running, passed, failed, error
    question: str = ""
    response: str = ""
    duration_ms: int = 0


@dataclass
class CloudRunProgress:
    """Stato complessivo di un run cloud"""
    run_id: int
    status: str = "queued"  # queued, in_progress, completed
    conclusion: Optional[str] = None  # success, failure, cancelled
    current_step: str = ""
    total_tests: int = 0
    completed_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    tests: List[TestProgress] = field(default_factory=list)
    start_time: Optional[datetime] = None
    sheets_run: Optional[int] = None
    langsmith_connected: bool = False
    sheets_connected: bool = False
    error_message: str = ""


class CloudRunMonitor:
    """
    Monitora l'esecuzione di un run cloud con barra di avanzamento.

    Usage:
        monitor = CloudRunMonitor(run_id)
        monitor.watch(on_update=callback)

    Il callback riceve CloudRunProgress ad ogni aggiornamento.
    """

    def __init__(self, client: GitHubActionsClient, run_id: int):
        self.client = client
        self.run_id = run_id
        self.progress = CloudRunProgress(run_id=run_id)
        self._last_log_position = 0

    def get_status(self) -> CloudRunProgress:
        """Ottiene lo stato corrente del run"""
        run = self.client.get_run_status(self.run_id)
        if run:
            self.progress.status = run.status
            self.progress.conclusion = run.conclusion

        return self.progress

    def parse_logs(self, logs: str) -> CloudRunProgress:
        """
        Analizza i log per estrarre lo stato dei test.

        Args:
            logs: Output dei log del workflow

        Returns:
            CloudRunProgress aggiornato
        """
        # Cerca connessioni servizi
        if "✓ LangSmith connesso" in logs:
            self.progress.langsmith_connected = True

        if "✓ Google Sheets connesso" in logs:
            self.progress.sheets_connected = True
            # Estrai numero RUN
            match = re.search(r"Google Sheets connesso - Run (\d+)", logs)
            if match:
                self.progress.sheets_run = int(match.group(1))

        # Cerca step corrente
        steps = [
            ("Checkout repository", "checkout"),
            ("Setup Python", "setup_python"),
            ("Install dependencies", "install_deps"),
            ("Install Playwright", "install_playwright"),
            ("Setup project configuration", "setup_config"),
            ("Create .* project", "create_project"),
            ("Run health check", "health_check"),
            ("Execute tests", "execute_tests"),
            ("Upload test reports", "upload_reports"),
        ]

        for pattern, step_id in steps:
            if re.search(f"✓.*{pattern}", logs):
                self.progress.current_step = step_id

        # Cerca test in esecuzione
        test_pattern = r"--- Test (\d+)/(\d+): (TEST_\d+) ---"
        for match in re.finditer(test_pattern, logs):
            current = int(match.group(1))
            total = int(match.group(2))
            test_id = match.group(3)

            self.progress.total_tests = total
            self.progress.completed_tests = current - 1

            # Aggiorna lista test
            if not any(t.test_id == test_id for t in self.progress.tests):
                self.progress.tests.append(TestProgress(
                    test_id=test_id,
                    status="running"
                ))

        # Cerca test completati con risposta
        response_pattern = r"Bot: (.+?)\.{3}"
        for match in re.finditer(response_pattern, logs):
            # Marca l'ultimo test running come completato
            for test in reversed(self.progress.tests):
                if test.status == "running":
                    test.status = "passed"
                    test.response = match.group(1)[:100]
                    break

        # Cerca riepilogo finale
        summary_pattern = r"Totale: (\d+)\s+Passati: (\d+)\s+Falliti: (\d+)"
        match = re.search(summary_pattern, logs)
        if match:
            self.progress.total_tests = int(match.group(1))
            self.progress.passed_tests = int(match.group(2))
            self.progress.failed_tests = int(match.group(3))
            self.progress.completed_tests = self.progress.total_tests

        # Cerca errori
        error_pattern = r"✗ Errore: (.+)"
        match = re.search(error_pattern, logs)
        if match:
            self.progress.error_message = match.group(1)

        return self.progress

    def watch(
        self,
        on_update: Optional[Callable[[CloudRunProgress], None]] = None,
        poll_interval: float = 3.0,
        timeout: int = 600
    ) -> CloudRunProgress:
        """
        Monitora il run fino al completamento.

        Args:
            on_update: Callback chiamato ad ogni aggiornamento
            poll_interval: Intervallo di polling in secondi
            timeout: Timeout massimo in secondi

        Returns:
            Stato finale del run
        """
        start = time.time()
        self.progress.start_time = datetime.now()

        while time.time() - start < timeout:
            # Ottieni stato run
            run = self.client.get_run_status(self.run_id)
            if not run:
                time.sleep(poll_interval)
                continue

            self.progress.status = run.status
            self.progress.conclusion = run.conclusion

            # Ottieni log se in esecuzione
            if run.status == "in_progress":
                success, logs = self.client.get_run_logs(self.run_id)
                if success:
                    self.parse_logs(logs)

            # Callback
            if on_update:
                on_update(self.progress)

            # Completato?
            if run.status == "completed":
                # Ultimo parsing log
                success, logs = self.client.get_run_logs(self.run_id)
                if success:
                    self.parse_logs(logs)
                if on_update:
                    on_update(self.progress)
                break

            time.sleep(poll_interval)

        return self.progress


def create_progress_display():
    """
    Crea un display Rich per il monitoraggio cloud.

    Returns:
        Funzione callback per CloudRunMonitor.watch()
    """
    try:
        from rich.console import Console
        from rich.live import Live
        from rich.table import Table
        from rich.panel import Panel
        from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
        from rich.layout import Layout
        from rich import box
    except ImportError:
        # Fallback senza Rich
        def simple_callback(progress: CloudRunProgress):
            print(f"\r[{progress.status}] {progress.completed_tests}/{progress.total_tests} test", end="")
        return simple_callback

    console = Console()

    def render_progress(progress: CloudRunProgress) -> Panel:
        """Genera il pannello di stato"""

        # Status icon
        status_icons = {
            "queued": "⏳",
            "in_progress": "🔄",
            "completed": "✅" if progress.conclusion == "success" else "❌"
        }
        status_icon = status_icons.get(progress.status, "❓")

        # Header
        header = f"{status_icon} Run #{progress.run_id}"
        if progress.sheets_run:
            header += f" → Google Sheets RUN {progress.sheets_run}"

        # Services
        services = []
        if progress.langsmith_connected:
            services.append("[green]✓ LangSmith[/green]")
        if progress.sheets_connected:
            services.append("[green]✓ Google Sheets[/green]")

        # Build table
        table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
        table.add_column("Key", style="dim")
        table.add_column("Value")

        table.add_row("Stato", f"[cyan]{progress.status}[/cyan]")
        if progress.current_step:
            table.add_row("Step", progress.current_step)
        if services:
            table.add_row("Servizi", " ".join(services))

        # Progress bar
        if progress.total_tests > 0:
            pct = (progress.completed_tests / progress.total_tests) * 100
            bar_width = 30
            filled = int(bar_width * progress.completed_tests / progress.total_tests)
            bar = "█" * filled + "░" * (bar_width - filled)
            table.add_row(
                "Test",
                f"[green]{bar}[/green] {progress.completed_tests}/{progress.total_tests} ({pct:.0f}%)"
            )

        # Results
        if progress.completed_tests > 0:
            table.add_row(
                "Risultati",
                f"[green]✓ {progress.passed_tests}[/green] [red]✗ {progress.failed_tests}[/red]"
            )

        # Error
        if progress.error_message:
            table.add_row("Errore", f"[red]{progress.error_message}[/red]")

        # Test list (last 5)
        if progress.tests:
            test_lines = []
            for test in progress.tests[-5:]:
                icon = {"pending": "○", "running": "●", "passed": "✓", "failed": "✗"}.get(test.status, "?")
                color = {"pending": "dim", "running": "yellow", "passed": "green", "failed": "red"}.get(test.status, "white")
                test_lines.append(f"[{color}]{icon} {test.test_id}[/{color}]")
            table.add_row("Test", "\n".join(test_lines))

        return Panel(table, title=header, border_style="blue")

    # Create Live display
    live = Live(render_progress(CloudRunProgress(run_id=0)), console=console, refresh_per_second=2)

    def update_callback(progress: CloudRunProgress):
        live.update(render_progress(progress))

    # Return tuple: (start_live, callback, stop_live)
    return live, update_callback


def watch_cloud_run(run_id: Optional[int] = None) -> CloudRunProgress:
    """
    Monitora un run cloud con display interattivo.

    Args:
        run_id: ID del run (None = ultimo run)

    Returns:
        Stato finale del run
    """
    client = GitHubActionsClient()

    if not client.is_available():
        print("❌ gh CLI non disponibile")
        print(client.get_install_instructions())
        return CloudRunProgress(run_id=0, error_message="gh CLI non disponibile")

    # Se non specificato, prendi ultimo run
    if run_id is None:
        runs = client.list_runs(limit=1)
        if not runs:
            print("❌ Nessun run trovato")
            return CloudRunProgress(run_id=0, error_message="Nessun run trovato")
        run_id = runs[0].id
        print(f"📍 Monitoraggio run #{run_id}")

    # Crea monitor e display
    monitor = CloudRunMonitor(client, run_id)

    try:
        live, callback = create_progress_display()

        with live:
            progress = monitor.watch(on_update=callback)

        # Riepilogo finale
        print()
        if progress.conclusion == "success":
            print(f"✅ Run completato con successo!")
        else:
            print(f"❌ Run fallito: {progress.error_message or progress.conclusion}")

        if progress.sheets_run:
            print(f"📊 Risultati su Google Sheets: RUN {progress.sheets_run}")

        return progress

    except Exception as e:
        print(f"❌ Errore monitoraggio: {e}")
        return monitor.progress
