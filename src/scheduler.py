"""
Scheduler Module - Automazione Test

Gestisce:
- Scheduled runs locali (cron-like)
- Esecuzione distribuita (multi-machine)
- Coordinamento worker
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable
from datetime import datetime, timedelta
from pathlib import Path
from enum import Enum
import json
import threading
import time
import subprocess
import signal
import sys


class ScheduleType(Enum):
    """Tipi di schedule supportati"""
    DAILY = "daily"           # Ogni giorno
    WEEKLY = "weekly"         # Ogni settimana (lunedi)
    HOURLY = "hourly"         # Ogni ora
    INTERVAL = "interval"     # Ogni N minuti
    CRON = "cron"             # Espressione cron


@dataclass
class ScheduleConfig:
    """Configurazione di uno schedule"""
    name: str
    project: str
    schedule_type: ScheduleType
    mode: str = "auto"
    tests: str = "pending"
    new_run: bool = False
    enabled: bool = True

    # Per INTERVAL
    interval_minutes: int = 60

    # Per CRON (semplificato: hour, minute, day_of_week)
    cron_hour: int = 6
    cron_minute: int = 0
    cron_day_of_week: Optional[int] = None  # 0=Mon, 6=Sun, None=every day

    # Ultimo run
    last_run: Optional[str] = None
    next_run: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "project": self.project,
            "schedule_type": self.schedule_type.value,
            "mode": self.mode,
            "tests": self.tests,
            "new_run": self.new_run,
            "enabled": self.enabled,
            "interval_minutes": self.interval_minutes,
            "cron_hour": self.cron_hour,
            "cron_minute": self.cron_minute,
            "cron_day_of_week": self.cron_day_of_week,
            "last_run": self.last_run,
            "next_run": self.next_run
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'ScheduleConfig':
        return cls(
            name=data["name"],
            project=data["project"],
            schedule_type=ScheduleType(data["schedule_type"]),
            mode=data.get("mode", "auto"),
            tests=data.get("tests", "pending"),
            new_run=data.get("new_run", False),
            enabled=data.get("enabled", True),
            interval_minutes=data.get("interval_minutes", 60),
            cron_hour=data.get("cron_hour", 6),
            cron_minute=data.get("cron_minute", 0),
            cron_day_of_week=data.get("cron_day_of_week"),
            last_run=data.get("last_run"),
            next_run=data.get("next_run")
        )


@dataclass
class SchedulerState:
    """Stato dello scheduler"""
    schedules: List[ScheduleConfig] = field(default_factory=list)
    running: bool = False
    current_job: Optional[str] = None
    start_time: Optional[str] = None


class LocalScheduler:
    """
    Scheduler locale per eseguire test su base temporale.

    Usage:
        scheduler = LocalScheduler()

        # Aggiungi schedule
        scheduler.add_schedule(ScheduleConfig(
            name="daily-silicon",
            project="my-chatbot",
            schedule_type=ScheduleType.DAILY,
            cron_hour=6
        ))

        # Avvia scheduler
        scheduler.start()  # Blocca il processo

        # Oppure in background
        scheduler.start_background()
    """

    def __init__(self, config_path: Path = None):
        self._config_path = config_path or Path("config/schedules.json")
        self._state = SchedulerState()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._on_job_complete: Optional[Callable] = None

        # Carica schedules esistenti
        self._load_schedules()

    def _load_schedules(self) -> None:
        """Carica schedules da file"""
        if self._config_path.exists():
            try:
                with open(self._config_path) as f:
                    data = json.load(f)
                self._state.schedules = [
                    ScheduleConfig.from_dict(s) for s in data.get("schedules", [])
                ]
            except Exception as e:
                print(f"! Errore caricamento schedules: {e}")

    def _save_schedules(self) -> None:
        """Salva schedules su file"""
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "schedules": [s.to_dict() for s in self._state.schedules]
        }
        with open(self._config_path, 'w') as f:
            json.dump(data, f, indent=2)

    def add_schedule(self, config: ScheduleConfig) -> None:
        """Aggiunge uno schedule"""
        # Rimuovi se esiste gia con stesso nome
        self._state.schedules = [
            s for s in self._state.schedules if s.name != config.name
        ]
        config.next_run = self._calculate_next_run(config)
        self._state.schedules.append(config)
        self._save_schedules()

    def remove_schedule(self, name: str) -> bool:
        """Rimuove uno schedule"""
        initial_count = len(self._state.schedules)
        self._state.schedules = [
            s for s in self._state.schedules if s.name != name
        ]
        if len(self._state.schedules) < initial_count:
            self._save_schedules()
            return True
        return False

    def list_schedules(self) -> List[ScheduleConfig]:
        """Lista tutti gli schedules"""
        return self._state.schedules.copy()

    def _calculate_next_run(self, config: ScheduleConfig) -> str:
        """Calcola prossimo run per uno schedule"""
        now = datetime.now()

        if config.schedule_type == ScheduleType.HOURLY:
            next_run = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)

        elif config.schedule_type == ScheduleType.INTERVAL:
            next_run = now + timedelta(minutes=config.interval_minutes)

        elif config.schedule_type == ScheduleType.DAILY:
            next_run = now.replace(
                hour=config.cron_hour,
                minute=config.cron_minute,
                second=0,
                microsecond=0
            )
            if next_run <= now:
                next_run += timedelta(days=1)

        elif config.schedule_type == ScheduleType.WEEKLY:
            # Trova prossimo giorno della settimana
            target_day = config.cron_day_of_week or 0  # Default: lunedi
            days_ahead = target_day - now.weekday()
            if days_ahead <= 0:
                days_ahead += 7

            next_run = now.replace(
                hour=config.cron_hour,
                minute=config.cron_minute,
                second=0,
                microsecond=0
            ) + timedelta(days=days_ahead)

        else:
            # Default: domani stessa ora
            next_run = now + timedelta(days=1)

        return next_run.isoformat()

    def _should_run(self, config: ScheduleConfig) -> bool:
        """Controlla se uno schedule deve essere eseguito"""
        if not config.enabled:
            return False

        if not config.next_run:
            return True

        next_run = datetime.fromisoformat(config.next_run)
        return datetime.now() >= next_run

    def _run_job(self, config: ScheduleConfig) -> bool:
        """Esegue un job"""
        self._state.current_job = config.name
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Avvio: {config.name}")

        try:
            cmd = [
                sys.executable, "run.py",
                "-p", config.project,
                "-m", config.mode,
                "--tests", config.tests,
                "--no-interactive",
                "--headless",
                "--skip-health-check"
            ]

            if config.new_run:
                cmd.append("--new-run")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=7200  # 2 ore max
            )

            success = result.returncode == 0
            print(f"[{datetime.now().strftime('%H:%M:%S')}] {'OK' if success else 'FAIL'}: {config.name}")

            if not success and result.stderr:
                print(f"  Error: {result.stderr[:200]}")

            return success

        except subprocess.TimeoutExpired:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] TIMEOUT: {config.name}")
            return False

        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ERROR: {config.name} - {e}")
            return False

        finally:
            # Aggiorna stato
            config.last_run = datetime.now().isoformat()
            config.next_run = self._calculate_next_run(config)
            self._state.current_job = None
            self._save_schedules()

            if self._on_job_complete:
                self._on_job_complete(config)

    def _loop(self) -> None:
        """Loop principale dello scheduler"""
        print(f"Scheduler avviato - {len(self._state.schedules)} schedule(s)")

        while not self._stop_event.is_set():
            for config in self._state.schedules:
                if self._stop_event.is_set():
                    break

                if self._should_run(config):
                    self._run_job(config)

            # Check ogni 30 secondi
            self._stop_event.wait(30)

        print("Scheduler fermato")

    def start(self) -> None:
        """Avvia scheduler (blocca il processo)"""
        self._state.running = True
        self._state.start_time = datetime.now().isoformat()
        self._stop_event.clear()

        # Gestisci SIGINT/SIGTERM
        def signal_handler(sig, frame):
            print("\nRicevuto segnale di stop...")
            self.stop()

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        self._loop()

    def start_background(self) -> None:
        """Avvia scheduler in background"""
        if self._thread and self._thread.is_alive():
            print("Scheduler gia in esecuzione")
            return

        self._state.running = True
        self._state.start_time = datetime.now().isoformat()
        self._stop_event.clear()

        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Ferma scheduler"""
        self._stop_event.set()
        self._state.running = False

        if self._thread:
            self._thread.join(timeout=5)

    def is_running(self) -> bool:
        """Controlla se scheduler e attivo"""
        return self._state.running

    def get_status(self) -> Dict[str, Any]:
        """Ritorna stato corrente"""
        return {
            "running": self._state.running,
            "current_job": self._state.current_job,
            "start_time": self._state.start_time,
            "schedules_count": len(self._state.schedules),
            "enabled_count": sum(1 for s in self._state.schedules if s.enabled)
        }


@dataclass
class WorkerConfig:
    """Configurazione worker distribuito"""
    worker_id: str
    host: str = "localhost"
    port: int = 5000
    max_parallel: int = 3
    projects: List[str] = field(default_factory=list)  # Progetti assegnati


class DistributedCoordinator:
    """
    Coordinatore per esecuzione distribuita.

    Permette di distribuire test su piu macchine.

    Usage:
        coordinator = DistributedCoordinator()

        # Registra worker
        coordinator.register_worker(WorkerConfig(
            worker_id="worker-1",
            host="192.168.1.10",
            projects=["my-chatbot"]
        ))

        # Distribuisci test
        coordinator.distribute_tests(tests, project="my-chatbot")
    """

    def __init__(self, config_path: Path = None):
        self._config_path = config_path or Path("config/workers.json")
        self._workers: Dict[str, WorkerConfig] = {}
        self._load_workers()

    def _load_workers(self) -> None:
        """Carica configurazione worker"""
        if self._config_path.exists():
            try:
                with open(self._config_path) as f:
                    data = json.load(f)
                for w in data.get("workers", []):
                    self._workers[w["worker_id"]] = WorkerConfig(**w)
            except Exception as e:
                print(f"! Errore caricamento workers: {e}")

    def _save_workers(self) -> None:
        """Salva configurazione worker"""
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "workers": [
                {
                    "worker_id": w.worker_id,
                    "host": w.host,
                    "port": w.port,
                    "max_parallel": w.max_parallel,
                    "projects": w.projects
                }
                for w in self._workers.values()
            ]
        }
        with open(self._config_path, 'w') as f:
            json.dump(data, f, indent=2)

    def register_worker(self, config: WorkerConfig) -> None:
        """Registra un worker"""
        self._workers[config.worker_id] = config
        self._save_workers()

    def unregister_worker(self, worker_id: str) -> bool:
        """Rimuove un worker"""
        if worker_id in self._workers:
            del self._workers[worker_id]
            self._save_workers()
            return True
        return False

    def list_workers(self) -> List[WorkerConfig]:
        """Lista tutti i worker"""
        return list(self._workers.values())

    def get_workers_for_project(self, project: str) -> List[WorkerConfig]:
        """Trova worker disponibili per un progetto"""
        return [
            w for w in self._workers.values()
            if not w.projects or project in w.projects
        ]

    def distribute_tests(self,
                         tests: List[Any],
                         project: str) -> Dict[str, List[Any]]:
        """
        Distribuisce test ai worker disponibili.

        Returns:
            Dict[worker_id -> tests assegnati]
        """
        workers = self.get_workers_for_project(project)

        if not workers:
            # Nessun worker: esegui tutto localmente
            return {"local": tests}

        # Distribuisci round-robin
        distribution: Dict[str, List[Any]] = {w.worker_id: [] for w in workers}

        for i, test in enumerate(tests):
            worker_idx = i % len(workers)
            worker_id = workers[worker_idx].worker_id
            distribution[worker_id].append(test)

        return distribution

    def check_worker_health(self, worker_id: str) -> bool:
        """Controlla se un worker e raggiungibile"""
        if worker_id not in self._workers:
            return False

        worker = self._workers[worker_id]

        # Per ora: ping semplice (in futuro: HTTP health check)
        try:
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex((worker.host, worker.port))
            sock.close()
            return result == 0
        except Exception:
            return False

    def get_cluster_status(self) -> Dict[str, Any]:
        """Ritorna stato del cluster"""
        workers_status = []

        for worker_id, config in self._workers.items():
            workers_status.append({
                "worker_id": worker_id,
                "host": config.host,
                "port": config.port,
                "healthy": self.check_worker_health(worker_id),
                "projects": config.projects,
                "max_parallel": config.max_parallel
            })

        return {
            "total_workers": len(self._workers),
            "workers": workers_status
        }


def create_default_schedules(project: str) -> List[ScheduleConfig]:
    """Crea schedule di default per un progetto"""
    return [
        ScheduleConfig(
            name=f"{project}-daily",
            project=project,
            schedule_type=ScheduleType.DAILY,
            mode="auto",
            tests="pending",
            cron_hour=6,
            cron_minute=0
        ),
        ScheduleConfig(
            name=f"{project}-weekly-full",
            project=project,
            schedule_type=ScheduleType.WEEKLY,
            mode="auto",
            tests="all",
            new_run=True,
            cron_hour=2,
            cron_minute=0,
            cron_day_of_week=0  # Lunedi
        )
    ]
