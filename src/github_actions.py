"""
GitHub Actions Integration - Esecuzione test nel cloud

Permette di lanciare test su GitHub Actions senza browser locale.
Richiede: gh CLI installato e autenticato.
"""

import subprocess
import json
from dataclasses import dataclass
from typing import Optional, List, Tuple
from enum import Enum


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
