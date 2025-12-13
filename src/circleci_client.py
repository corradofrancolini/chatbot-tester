"""
CircleCI client for cloud test execution.

Provides integration with CircleCI API for triggering pipelines,
monitoring executions, and managing workflows.
"""

import os
import time
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Tuple, Callable
from enum import Enum

try:
    import requests
except ImportError:
    requests = None


class PipelineStatus(Enum):
    """Pipeline status values."""
    CREATED = "created"
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    ERROR = "error"
    CANCELED = "canceled"
    NOT_RUN = "not_run"
    ON_HOLD = "on_hold"
    UNKNOWN = "unknown"


@dataclass
class PipelineRun:
    """Represents a CircleCI pipeline run."""
    id: str
    number: int
    state: str
    created_at: str
    project: Optional[str] = None
    branch: str = "main"

    @property
    def status(self) -> PipelineStatus:
        try:
            return PipelineStatus(self.state.lower())
        except ValueError:
            return PipelineStatus.UNKNOWN

    @property
    def is_active(self) -> bool:
        return self.status in (
            PipelineStatus.CREATED,
            PipelineStatus.PENDING,
            PipelineStatus.RUNNING,
            PipelineStatus.ON_HOLD
        )

    @property
    def is_success(self) -> bool:
        return self.status == PipelineStatus.SUCCESS

    @property
    def is_failed(self) -> bool:
        return self.status in (PipelineStatus.FAILED, PipelineStatus.ERROR)

    @property
    def status_icon(self) -> str:
        icons = {
            PipelineStatus.CREATED: "🔵",
            PipelineStatus.PENDING: "🟡",
            PipelineStatus.RUNNING: "🟠",
            PipelineStatus.ON_HOLD: "⏸️",
            PipelineStatus.SUCCESS: "✅",
            PipelineStatus.FAILED: "❌",
            PipelineStatus.ERROR: "💥",
            PipelineStatus.CANCELED: "🚫",
            PipelineStatus.NOT_RUN: "⚪",
            PipelineStatus.UNKNOWN: "❓",
        }
        return icons.get(self.status, "❓")

    @property
    def url(self) -> str:
        return f"https://app.circleci.com/pipelines/gh/corradofrancolini/chatbot-tester-private/{self.number}"


@dataclass
class WorkflowRun:
    """Represents a CircleCI workflow within a pipeline."""
    id: str
    name: str
    status: str
    pipeline_id: str
    created_at: str
    stopped_at: Optional[str] = None

    @property
    def is_active(self) -> bool:
        return self.status.lower() in ("running", "on_hold", "pending")

    @property
    def is_success(self) -> bool:
        return self.status.lower() == "success"

    @property
    def status_icon(self) -> str:
        status_lower = self.status.lower()
        icons = {
            "running": "🟠",
            "success": "✅",
            "failed": "❌",
            "error": "💥",
            "canceled": "🚫",
            "on_hold": "⏸️",
            "pending": "🟡",
            "not_run": "⚪",
        }
        return icons.get(status_lower, "❓")


@dataclass
class CloudRunProgress:
    """Progress information for monitoring."""
    pipeline_id: str
    workflow_id: Optional[str] = None
    status: str = "pending"
    current_step: str = ""
    tests_total: int = 0
    tests_completed: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    error_message: Optional[str] = None

    @property
    def progress_percent(self) -> float:
        if self.tests_total == 0:
            return 0.0
        return (self.tests_completed / self.tests_total) * 100


class CircleCIClient:
    """Client for CircleCI API operations."""

    API_URL = "https://circleci.com/api/v2"
    PROJECT_SLUG = "gh/corradofrancolini/chatbot-tester-private"

    def __init__(self, token: Optional[str] = None, project_slug: Optional[str] = None):
        self.token = token or os.environ.get("CIRCLECI_TOKEN", "")
        if project_slug:
            self.PROJECT_SLUG = project_slug

    def is_available(self) -> bool:
        """Check if CircleCI integration is available."""
        if requests is None:
            return False
        if not self.token:
            return False
        return True

    def get_install_instructions(self) -> str:
        """Get instructions for setting up CircleCI."""
        return """
Per configurare CircleCI:

1. Vai su https://app.circleci.com/settings/user/tokens
2. Crea un nuovo Personal API Token
3. Esegui nel terminale:
   export CIRCLECI_TOKEN="il-tuo-token"

   Oppure aggiungi a ~/.zshrc per renderlo permanente:
   echo 'export CIRCLECI_TOKEN="il-tuo-token"' >> ~/.zshrc
"""

    def _headers(self) -> dict:
        """Get API headers."""
        return {
            "Circle-Token": self.token,
            "Content-Type": "application/json"
        }

    def _api_get(self, endpoint: str) -> Optional[dict]:
        """Make GET request to CircleCI API."""
        if not self.is_available():
            return None

        url = f"{self.API_URL}{endpoint}"
        try:
            response = requests.get(url, headers=self._headers(), timeout=30)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception:
            return None

    def _api_post(self, endpoint: str, data: dict = None) -> Tuple[bool, Optional[dict]]:
        """Make POST request to CircleCI API."""
        if not self.is_available():
            return False, None

        url = f"{self.API_URL}{endpoint}"
        try:
            response = requests.post(
                url,
                headers=self._headers(),
                json=data or {},
                timeout=30
            )
            if response.status_code in (200, 201, 202):
                return True, response.json()
            return False, {"error": response.text, "status": response.status_code}
        except Exception as e:
            return False, {"error": str(e)}

    def trigger_pipeline(
        self,
        project: str,
        mode: str = "auto",
        tests: str = "pending",
        new_run: bool = False
    ) -> Tuple[bool, dict]:
        """
        Trigger a new pipeline.

        Args:
            project: Project name (e.g., "silicon-b")
            mode: Test mode ("auto", "assisted", "train")
            tests: Which tests ("all", "pending", "failed")
            new_run: Whether to create new Google Sheets run

        Returns:
            Tuple of (success, response_data)
        """
        payload = {
            "branch": "main",
            "parameters": {
                "manual_trigger": True,
                "project": project,
                "mode": mode,
                "tests": tests,
                "new_run": new_run
            }
        }

        endpoint = f"/project/{self.PROJECT_SLUG}/pipeline"
        return self._api_post(endpoint, payload)

    def list_pipelines(self, limit: int = 10, branch: str = None) -> List[PipelineRun]:
        """
        List recent pipelines.

        Args:
            limit: Maximum number of pipelines to return
            branch: Filter by branch (optional)

        Returns:
            List of PipelineRun objects
        """
        endpoint = f"/project/{self.PROJECT_SLUG}/pipeline"
        if branch:
            endpoint += f"?branch={branch}"

        data = self._api_get(endpoint)
        if not data:
            return []

        pipelines = []
        for item in data.get("items", [])[:limit]:
            pipelines.append(PipelineRun(
                id=item.get("id", ""),
                number=item.get("number", 0),
                state=item.get("state", "unknown"),
                created_at=item.get("created_at", ""),
                branch=item.get("vcs", {}).get("branch", "main")
            ))

        return pipelines

    def get_pipeline(self, pipeline_id: str) -> Optional[PipelineRun]:
        """Get a specific pipeline by ID."""
        data = self._api_get(f"/pipeline/{pipeline_id}")
        if not data:
            return None

        return PipelineRun(
            id=data.get("id", ""),
            number=data.get("number", 0),
            state=data.get("state", "unknown"),
            created_at=data.get("created_at", ""),
            branch=data.get("vcs", {}).get("branch", "main")
        )

    def get_pipeline_workflows(self, pipeline_id: str) -> List[WorkflowRun]:
        """Get workflows for a pipeline."""
        data = self._api_get(f"/pipeline/{pipeline_id}/workflow")
        if not data:
            return []

        workflows = []
        for item in data.get("items", []):
            workflows.append(WorkflowRun(
                id=item.get("id", ""),
                name=item.get("name", ""),
                status=item.get("status", "unknown"),
                pipeline_id=pipeline_id,
                created_at=item.get("created_at", ""),
                stopped_at=item.get("stopped_at")
            ))

        return workflows

    def get_workflow(self, workflow_id: str) -> Optional[WorkflowRun]:
        """Get a specific workflow by ID."""
        data = self._api_get(f"/workflow/{workflow_id}")
        if not data:
            return None

        return WorkflowRun(
            id=data.get("id", ""),
            name=data.get("name", ""),
            status=data.get("status", "unknown"),
            pipeline_id=data.get("pipeline_id", ""),
            created_at=data.get("created_at", ""),
            stopped_at=data.get("stopped_at")
        )

    def cancel_workflow(self, workflow_id: str) -> bool:
        """Cancel a running workflow."""
        success, _ = self._api_post(f"/workflow/{workflow_id}/cancel")
        return success

    def get_workflow_jobs(self, workflow_id: str) -> List[dict]:
        """Get jobs for a workflow."""
        data = self._api_get(f"/workflow/{workflow_id}/job")
        if not data:
            return []
        return data.get("items", [])

    def watch_pipeline(
        self,
        pipeline_id: str,
        on_update: Optional[Callable[[CloudRunProgress], None]] = None,
        poll_interval: float = 5.0,
        timeout: int = 1800
    ) -> CloudRunProgress:
        """
        Watch a pipeline until completion.

        Args:
            pipeline_id: Pipeline ID to watch
            on_update: Callback function for progress updates
            poll_interval: Seconds between status checks
            timeout: Maximum seconds to wait

        Returns:
            Final CloudRunProgress
        """
        start_time = time.time()
        progress = CloudRunProgress(pipeline_id=pipeline_id, status="pending")

        while time.time() - start_time < timeout:
            # Get pipeline status
            pipeline = self.get_pipeline(pipeline_id)
            if not pipeline:
                progress.status = "error"
                progress.error_message = "Pipeline not found"
                break

            # Get workflows
            workflows = self.get_pipeline_workflows(pipeline_id)

            if workflows:
                workflow = workflows[0]  # Main workflow
                progress.workflow_id = workflow.id
                progress.status = workflow.status
                progress.current_step = workflow.name

                # Check jobs for more detail
                jobs = self.get_workflow_jobs(workflow.id)
                for job in jobs:
                    if job.get("status") == "running":
                        progress.current_step = job.get("name", "")
                        break
            else:
                progress.status = pipeline.state

            # Call update callback
            if on_update:
                on_update(progress)

            # Check if done
            if not pipeline.is_active and workflows:
                if not any(w.is_active for w in workflows):
                    break

            time.sleep(poll_interval)

        return progress


def create_progress_display():
    """Create a Rich-based progress display for monitoring."""
    try:
        from rich.live import Live
        from rich.panel import Panel
        from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
        from rich.table import Table
        from rich.console import Console

        return {
            "Live": Live,
            "Panel": Panel,
            "Progress": Progress,
            "SpinnerColumn": SpinnerColumn,
            "TextColumn": TextColumn,
            "BarColumn": BarColumn,
            "Table": Table,
            "Console": Console
        }
    except ImportError:
        return None


def watch_cloud_run(
    client: CircleCIClient,
    pipeline_id: str,
    poll_interval: float = 5.0
) -> CloudRunProgress:
    """
    Watch a cloud run with visual progress display.

    Args:
        client: CircleCIClient instance
        pipeline_id: Pipeline ID to watch
        poll_interval: Seconds between updates

    Returns:
        Final CloudRunProgress
    """
    rich_components = create_progress_display()

    if rich_components:
        Console = rich_components["Console"]
        console = Console()

        def on_update(progress: CloudRunProgress):
            icon = "🟠" if progress.status == "running" else "🟡"
            if progress.status == "success":
                icon = "✅"
            elif progress.status in ("failed", "error"):
                icon = "❌"

            console.print(f"\r{icon} {progress.status}: {progress.current_step}", end="")

        console.print(f"\n  Monitorando pipeline {pipeline_id}...\n")
        result = client.watch_pipeline(pipeline_id, on_update=on_update, poll_interval=poll_interval)
        console.print("\n")
        return result
    else:
        # Fallback without Rich
        def on_update(progress: CloudRunProgress):
            print(f"\r  Status: {progress.status} - {progress.current_step}", end="", flush=True)

        print(f"\n  Monitorando pipeline {pipeline_id}...")
        result = client.watch_pipeline(pipeline_id, on_update=on_update, poll_interval=poll_interval)
        print("\n")
        return result
