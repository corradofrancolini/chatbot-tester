"""
Performance Metrics - Chatbot Tester v1.6.0

Modulo per la raccolta e analisi delle metriche di performance:
- Timing: durata run, media per test, breakdown per fase
- Throughput: test/minuto, confronto con run precedenti
- Affidabilità: retry, timeout, error rate, flakiness
- Servizi Esterni: latenza chatbot, Google Sheets, LangSmith
- Confronto Local vs Cloud: differenze tempi e risultati
"""

import json
import time
import statistics
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum


class MetricPhase(Enum):
    """Fasi di esecuzione di un test"""
    SETUP = "setup"
    SEND_QUESTION = "send_question"
    WAIT_RESPONSE = "wait_response"
    SCREENSHOT = "screenshot"
    SAVE_RESULTS = "save_results"
    TOTAL = "total"


class ExecutionEnvironment(Enum):
    """Ambiente di esecuzione"""
    LOCAL = "local"
    CLOUD = "cloud"


@dataclass
class PhaseMetric:
    """Metrica per una singola fase"""
    phase: str
    duration_ms: float
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    success: bool = True
    error: Optional[str] = None


@dataclass
class ExternalServiceMetric:
    """Metrica per un servizio esterno"""
    service: str  # chatbot, google_sheets, langsmith
    operation: str  # send, write, trace
    duration_ms: float
    success: bool = True
    error: Optional[str] = None
    timestamp: Optional[datetime] = None


@dataclass
class TestMetrics:
    """Metriche complete per un singolo test"""
    test_id: str
    environment: str = "local"
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    # Timing per fase
    phases: List[PhaseMetric] = field(default_factory=list)
    total_duration_ms: float = 0

    # Affidabilità
    retry_count: int = 0
    timeout_occurred: bool = False
    error_occurred: bool = False
    error_message: str = ""

    # Servizi esterni
    external_services: List[ExternalServiceMetric] = field(default_factory=list)

    # Risultato
    status: str = ""  # PASS, FAIL, ERROR, SKIP

    def add_phase(self, phase: str, duration_ms: float, success: bool = True, error: str = None):
        """Aggiunge metrica per una fase"""
        self.phases.append(PhaseMetric(
            phase=phase,
            duration_ms=duration_ms,
            success=success,
            error=error
        ))

    def add_service_call(self, service: str, operation: str, duration_ms: float,
                         success: bool = True, error: str = None):
        """Aggiunge metrica per chiamata a servizio esterno"""
        self.external_services.append(ExternalServiceMetric(
            service=service,
            operation=operation,
            duration_ms=duration_ms,
            success=success,
            error=error,
            timestamp=datetime.now()
        ))

    def get_phase_duration(self, phase: str) -> float:
        """Ottiene durata di una fase specifica"""
        for p in self.phases:
            if p.phase == phase:
                return p.duration_ms
        return 0

    def get_service_latency(self, service: str) -> float:
        """Ottiene latenza media per un servizio"""
        latencies = [s.duration_ms for s in self.external_services if s.service == service]
        return statistics.mean(latencies) if latencies else 0


@dataclass
class RunMetrics:
    """Metriche aggregate per un run completo"""
    run_id: str
    project: str
    environment: str = "local"
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    # Test metrics
    test_metrics: List[TestMetrics] = field(default_factory=list)

    # Aggregati
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    error_tests: int = 0
    skipped_tests: int = 0

    # Timing aggregati
    total_duration_ms: float = 0
    avg_test_duration_ms: float = 0
    min_test_duration_ms: float = 0
    max_test_duration_ms: float = 0

    # Throughput
    tests_per_minute: float = 0

    # Affidabilità
    total_retries: int = 0
    total_timeouts: int = 0
    total_errors: int = 0
    error_rate: float = 0

    # Servizi esterni - latenze medie
    chatbot_avg_latency_ms: float = 0
    sheets_avg_latency_ms: float = 0
    langsmith_avg_latency_ms: float = 0

    def calculate_aggregates(self):
        """Calcola tutte le metriche aggregate"""
        if not self.test_metrics:
            return

        # Conteggi
        self.total_tests = len(self.test_metrics)
        self.passed_tests = sum(1 for t in self.test_metrics if t.status == "PASS")
        self.failed_tests = sum(1 for t in self.test_metrics if t.status == "FAIL")
        self.error_tests = sum(1 for t in self.test_metrics if t.status == "ERROR")
        self.skipped_tests = sum(1 for t in self.test_metrics if t.status == "SKIP")

        # Timing
        durations = [t.total_duration_ms for t in self.test_metrics if t.total_duration_ms > 0]
        if durations:
            self.total_duration_ms = sum(durations)
            self.avg_test_duration_ms = statistics.mean(durations)
            self.min_test_duration_ms = min(durations)
            self.max_test_duration_ms = max(durations)

        # Throughput
        if self.start_time and self.end_time:
            elapsed = (self.end_time - self.start_time).total_seconds()
            if elapsed > 0:
                self.tests_per_minute = (self.total_tests / elapsed) * 60

        # Affidabilità
        self.total_retries = sum(t.retry_count for t in self.test_metrics)
        self.total_timeouts = sum(1 for t in self.test_metrics if t.timeout_occurred)
        self.total_errors = sum(1 for t in self.test_metrics if t.error_occurred)
        self.error_rate = (self.total_errors / self.total_tests * 100) if self.total_tests > 0 else 0

        # Servizi esterni
        chatbot_latencies = []
        sheets_latencies = []
        langsmith_latencies = []

        for t in self.test_metrics:
            for s in t.external_services:
                if s.service == "chatbot":
                    chatbot_latencies.append(s.duration_ms)
                elif s.service == "google_sheets":
                    sheets_latencies.append(s.duration_ms)
                elif s.service == "langsmith":
                    langsmith_latencies.append(s.duration_ms)

        self.chatbot_avg_latency_ms = statistics.mean(chatbot_latencies) if chatbot_latencies else 0
        self.sheets_avg_latency_ms = statistics.mean(sheets_latencies) if sheets_latencies else 0
        self.langsmith_avg_latency_ms = statistics.mean(langsmith_latencies) if langsmith_latencies else 0


@dataclass
class PerformanceComparison:
    """Confronto performance tra due run (es. local vs cloud)"""
    run_a: str
    run_b: str
    environment_a: str
    environment_b: str

    # Differenze timing
    duration_diff_ms: float = 0
    duration_diff_percent: float = 0
    avg_test_diff_ms: float = 0
    avg_test_diff_percent: float = 0

    # Differenze throughput
    throughput_diff: float = 0
    throughput_diff_percent: float = 0

    # Differenze risultati
    pass_rate_diff: float = 0
    result_differences: List[Dict[str, Any]] = field(default_factory=list)

    # Differenze servizi
    chatbot_latency_diff_ms: float = 0
    sheets_latency_diff_ms: float = 0


class PerformanceCollector:
    """Raccoglie metriche durante l'esecuzione dei test"""

    def __init__(self, run_id: str, project: str, environment: str = "local"):
        self.run_metrics = RunMetrics(
            run_id=run_id,
            project=project,
            environment=environment,
            start_time=datetime.now()
        )
        self._current_test: Optional[TestMetrics] = None
        self._phase_start: Optional[float] = None
        self._phase_name: Optional[str] = None

    def start_test(self, test_id: str):
        """Inizia raccolta metriche per un test"""
        self._current_test = TestMetrics(
            test_id=test_id,
            environment=self.run_metrics.environment,
            start_time=datetime.now()
        )

    def start_phase(self, phase: str):
        """Inizia misurazione di una fase"""
        self._phase_name = phase
        self._phase_start = time.perf_counter()

    def end_phase(self, success: bool = True, error: str = None):
        """Termina misurazione di una fase"""
        if self._phase_start and self._phase_name and self._current_test:
            duration_ms = (time.perf_counter() - self._phase_start) * 1000
            self._current_test.add_phase(
                phase=self._phase_name,
                duration_ms=duration_ms,
                success=success,
                error=error
            )
        self._phase_start = None
        self._phase_name = None

    def record_service_call(self, service: str, operation: str, duration_ms: float,
                           success: bool = True, error: str = None):
        """Registra chiamata a servizio esterno"""
        if self._current_test:
            self._current_test.add_service_call(
                service=service,
                operation=operation,
                duration_ms=duration_ms,
                success=success,
                error=error
            )

    def record_retry(self):
        """Registra un retry"""
        if self._current_test:
            self._current_test.retry_count += 1

    def record_timeout(self):
        """Registra un timeout"""
        if self._current_test:
            self._current_test.timeout_occurred = True

    def record_error(self, message: str):
        """Registra un errore"""
        if self._current_test:
            self._current_test.error_occurred = True
            self._current_test.error_message = message

    def end_test(self, status: str):
        """Termina raccolta metriche per un test"""
        if self._current_test:
            self._current_test.end_time = datetime.now()
            self._current_test.status = status

            # Calcola durata totale
            if self._current_test.start_time and self._current_test.end_time:
                delta = self._current_test.end_time - self._current_test.start_time
                self._current_test.total_duration_ms = delta.total_seconds() * 1000

            self.run_metrics.test_metrics.append(self._current_test)
            self._current_test = None

    def finalize(self) -> RunMetrics:
        """Finalizza e calcola aggregati"""
        self.run_metrics.end_time = datetime.now()
        self.run_metrics.calculate_aggregates()
        return self.run_metrics

    def save(self, output_dir: Path) -> Path:
        """Salva metriche su file JSON"""
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / f"performance_{self.run_metrics.run_id}.json"

        # Converti a dict serializzabile
        data = self._to_serializable(self.run_metrics)

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        return output_file

    def _to_serializable(self, obj) -> Any:
        """Converte oggetto in formato serializzabile JSON"""
        if hasattr(obj, '__dataclass_fields__'):
            result = {}
            for field_name in obj.__dataclass_fields__:
                value = getattr(obj, field_name)
                result[field_name] = self._to_serializable(value)
            return result
        elif isinstance(obj, list):
            return [self._to_serializable(item) for item in obj]
        elif isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, Enum):
            return obj.value
        else:
            return obj


class PerformanceReporter:
    """Genera report di performance"""

    def __init__(self, run_metrics: RunMetrics):
        self.metrics = run_metrics

    def generate_summary(self) -> str:
        """Genera summary testuale delle performance"""
        lines = [
            f"\n{'='*60}",
            f"  PERFORMANCE REPORT - {self.metrics.project}",
            f"  Run: {self.metrics.run_id} ({self.metrics.environment})",
            f"{'='*60}\n",
        ]

        # Timing
        lines.append("📊 TIMING")
        lines.append(f"   Durata totale: {self._format_duration(self.metrics.total_duration_ms)}")
        lines.append(f"   Media per test: {self._format_duration(self.metrics.avg_test_duration_ms)}")
        lines.append(f"   Min/Max: {self._format_duration(self.metrics.min_test_duration_ms)} / {self._format_duration(self.metrics.max_test_duration_ms)}")
        lines.append("")

        # Breakdown per fase
        phase_stats = self._calculate_phase_stats()
        if phase_stats:
            lines.append("   Breakdown per fase:")
            for phase, stats in phase_stats.items():
                lines.append(f"     • {phase}: {self._format_duration(stats['avg'])} (avg)")
        lines.append("")

        # Throughput
        lines.append("⚡ THROUGHPUT")
        lines.append(f"   Test completati: {self.metrics.total_tests}")
        lines.append(f"   Velocità: {self.metrics.tests_per_minute:.2f} test/minuto")
        lines.append("")

        # Affidabilità
        lines.append("🔒 AFFIDABILITÀ")
        lines.append(f"   Pass rate: {self._pass_rate():.1f}%")
        lines.append(f"   Retry totali: {self.metrics.total_retries}")
        lines.append(f"   Timeout: {self.metrics.total_timeouts}")
        lines.append(f"   Error rate: {self.metrics.error_rate:.1f}%")
        lines.append("")

        # Servizi esterni
        lines.append("🌐 SERVIZI ESTERNI (latenza media)")
        if self.metrics.chatbot_avg_latency_ms > 0:
            lines.append(f"   Chatbot: {self._format_duration(self.metrics.chatbot_avg_latency_ms)}")
        if self.metrics.sheets_avg_latency_ms > 0:
            lines.append(f"   Google Sheets: {self._format_duration(self.metrics.sheets_avg_latency_ms)}")
        if self.metrics.langsmith_avg_latency_ms > 0:
            lines.append(f"   LangSmith: {self._format_duration(self.metrics.langsmith_avg_latency_ms)}")
        lines.append("")

        lines.append(f"{'='*60}")

        return "\n".join(lines)

    def generate_html_report(self) -> str:
        """Genera report HTML dettagliato"""
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Performance Report - {self.metrics.project}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 20px; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        .card {{ background: white; border-radius: 8px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; border-radius: 8px; margin-bottom: 20px; }}
        h1 {{ margin: 0; font-size: 24px; }}
        h2 {{ color: #333; margin-top: 0; border-bottom: 2px solid #eee; padding-bottom: 10px; }}
        .metric {{ display: inline-block; margin: 10px 20px 10px 0; }}
        .metric-value {{ font-size: 32px; font-weight: bold; color: #667eea; }}
        .metric-label {{ font-size: 12px; color: #666; text-transform: uppercase; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #eee; }}
        th {{ background: #f8f9fa; font-weight: 600; }}
        .pass {{ color: #28a745; }}
        .fail {{ color: #dc3545; }}
        .bar {{ background: #e9ecef; border-radius: 4px; height: 8px; }}
        .bar-fill {{ background: #667eea; height: 100%; border-radius: 4px; }}
        .timestamp {{ color: #666; font-size: 14px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Performance Report</h1>
            <p>Progetto: {self.metrics.project} | Run: {self.metrics.run_id} | Ambiente: {self.metrics.environment}</p>
            <p class="timestamp">
                {self.metrics.start_time.strftime('%Y-%m-%d %H:%M:%S') if self.metrics.start_time else 'N/A'} -
                {self.metrics.end_time.strftime('%H:%M:%S') if self.metrics.end_time else 'N/A'}
            </p>
        </div>

        <div class="grid">
            <div class="card">
                <h2>📊 Timing</h2>
                <div class="metric">
                    <div class="metric-value">{self._format_duration(self.metrics.total_duration_ms)}</div>
                    <div class="metric-label">Durata Totale</div>
                </div>
                <div class="metric">
                    <div class="metric-value">{self._format_duration(self.metrics.avg_test_duration_ms)}</div>
                    <div class="metric-label">Media per Test</div>
                </div>
            </div>

            <div class="card">
                <h2>⚡ Throughput</h2>
                <div class="metric">
                    <div class="metric-value">{self.metrics.tests_per_minute:.1f}</div>
                    <div class="metric-label">Test/Minuto</div>
                </div>
                <div class="metric">
                    <div class="metric-value">{self.metrics.total_tests}</div>
                    <div class="metric-label">Test Totali</div>
                </div>
            </div>

            <div class="card">
                <h2>🔒 Affidabilità</h2>
                <div class="metric">
                    <div class="metric-value">{self._pass_rate():.1f}%</div>
                    <div class="metric-label">Pass Rate</div>
                </div>
                <div class="metric">
                    <div class="metric-value">{self.metrics.error_rate:.1f}%</div>
                    <div class="metric-label">Error Rate</div>
                </div>
            </div>

            <div class="card">
                <h2>🌐 Servizi Esterni</h2>
                <div class="metric">
                    <div class="metric-value">{self._format_duration(self.metrics.chatbot_avg_latency_ms)}</div>
                    <div class="metric-label">Chatbot Latency</div>
                </div>
                <div class="metric">
                    <div class="metric-value">{self._format_duration(self.metrics.sheets_avg_latency_ms)}</div>
                    <div class="metric-label">Sheets Latency</div>
                </div>
            </div>
        </div>

        <div class="card">
            <h2>📋 Dettaglio Test</h2>
            <table>
                <thead>
                    <tr>
                        <th>Test ID</th>
                        <th>Status</th>
                        <th>Durata</th>
                        <th>Retry</th>
                        <th>Chatbot</th>
                        <th>Sheets</th>
                    </tr>
                </thead>
                <tbody>
                    {self._generate_test_rows()}
                </tbody>
            </table>
        </div>

        <div class="card">
            <h2>📈 Breakdown per Fase</h2>
            {self._generate_phase_chart()}
        </div>
    </div>
</body>
</html>
"""
        return html

    def _generate_test_rows(self) -> str:
        """Genera righe tabella test"""
        rows = []
        for t in self.metrics.test_metrics:
            status_class = "pass" if t.status == "PASS" else "fail"
            chatbot_lat = t.get_service_latency("chatbot")
            sheets_lat = t.get_service_latency("google_sheets")

            rows.append(f"""
                <tr>
                    <td>{t.test_id}</td>
                    <td class="{status_class}">{t.status}</td>
                    <td>{self._format_duration(t.total_duration_ms)}</td>
                    <td>{t.retry_count}</td>
                    <td>{self._format_duration(chatbot_lat)}</td>
                    <td>{self._format_duration(sheets_lat)}</td>
                </tr>
            """)
        return "\n".join(rows)

    def _generate_phase_chart(self) -> str:
        """Genera grafico breakdown fasi"""
        phase_stats = self._calculate_phase_stats()
        if not phase_stats:
            return "<p>Nessun dato disponibile</p>"

        total = sum(s['avg'] for s in phase_stats.values())
        if total == 0:
            return "<p>Nessun dato disponibile</p>"

        bars = []
        for phase, stats in phase_stats.items():
            pct = (stats['avg'] / total) * 100 if total > 0 else 0
            bars.append(f"""
                <div style="margin: 10px 0;">
                    <div style="display: flex; justify-content: space-between;">
                        <span>{phase}</span>
                        <span>{self._format_duration(stats['avg'])} ({pct:.1f}%)</span>
                    </div>
                    <div class="bar"><div class="bar-fill" style="width: {pct}%"></div></div>
                </div>
            """)
        return "\n".join(bars)

    def _calculate_phase_stats(self) -> Dict[str, Dict[str, float]]:
        """Calcola statistiche per fase"""
        phase_durations: Dict[str, List[float]] = {}

        for t in self.metrics.test_metrics:
            for p in t.phases:
                if p.phase not in phase_durations:
                    phase_durations[p.phase] = []
                phase_durations[p.phase].append(p.duration_ms)

        stats = {}
        for phase, durations in phase_durations.items():
            if durations:
                stats[phase] = {
                    'avg': statistics.mean(durations),
                    'min': min(durations),
                    'max': max(durations),
                    'count': len(durations)
                }
        return stats

    def _pass_rate(self) -> float:
        """Calcola pass rate"""
        if self.metrics.total_tests == 0:
            return 0
        return (self.metrics.passed_tests / self.metrics.total_tests) * 100

    def _format_duration(self, ms: float) -> str:
        """Formatta durata in modo leggibile"""
        if ms == 0:
            return "-"
        if ms < 1000:
            return f"{ms:.0f}ms"
        elif ms < 60000:
            return f"{ms/1000:.1f}s"
        else:
            minutes = int(ms / 60000)
            seconds = (ms % 60000) / 1000
            return f"{minutes}m {seconds:.0f}s"


class PerformanceHistory:
    """Gestisce storico performance per dashboard"""

    def __init__(self, project: str, data_dir: Path):
        self.project = project
        self.data_dir = data_dir / project / "performance"
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def save_run(self, metrics: RunMetrics):
        """Salva metriche di un run"""
        filename = f"run_{metrics.run_id}_{metrics.environment}.json"
        filepath = self.data_dir / filename

        collector = PerformanceCollector(metrics.run_id, metrics.project, metrics.environment)
        collector.run_metrics = metrics
        collector.save(self.data_dir)

    def load_history(self, last_n: int = 10, environment: Optional[str] = None) -> List[RunMetrics]:
        """Carica ultimi N run"""
        files = sorted(self.data_dir.glob("performance_*.json"), reverse=True)

        history = []
        for f in files[:last_n * 2]:  # Carica di più per filtrare
            try:
                with open(f, 'r', encoding='utf-8') as fp:
                    data = json.load(fp)

                if environment and data.get('environment') != environment:
                    continue

                metrics = self._dict_to_run_metrics(data)
                history.append(metrics)

                if len(history) >= last_n:
                    break
            except Exception:
                continue

        return history

    def get_trends(self, last_n: int = 10) -> Dict[str, Any]:
        """Calcola trend delle metriche"""
        history = self.load_history(last_n)

        if len(history) < 2:
            return {"message": "Dati insufficienti per calcolare trend"}

        # Ordina per data
        history.sort(key=lambda x: x.start_time or datetime.min)

        trends = {
            "duration": self._calculate_trend([m.total_duration_ms for m in history]),
            "throughput": self._calculate_trend([m.tests_per_minute for m in history]),
            "pass_rate": self._calculate_trend([
                (m.passed_tests / m.total_tests * 100) if m.total_tests > 0 else 0
                for m in history
            ]),
            "error_rate": self._calculate_trend([m.error_rate for m in history]),
            "chatbot_latency": self._calculate_trend([m.chatbot_avg_latency_ms for m in history]),
            "sheets_latency": self._calculate_trend([m.sheets_avg_latency_ms for m in history]),
        }

        return trends

    def _calculate_trend(self, values: List[float]) -> Dict[str, Any]:
        """Calcola trend per una serie di valori"""
        if len(values) < 2:
            return {"trend": "stable", "change": 0}

        # Confronta media prima metà vs seconda metà
        mid = len(values) // 2
        first_half = statistics.mean(values[:mid]) if values[:mid] else 0
        second_half = statistics.mean(values[mid:]) if values[mid:] else 0

        if first_half == 0:
            change_pct = 0
        else:
            change_pct = ((second_half - first_half) / first_half) * 100

        if abs(change_pct) < 5:
            trend = "stable"
        elif change_pct > 0:
            trend = "increasing"
        else:
            trend = "decreasing"

        return {
            "trend": trend,
            "change_percent": round(change_pct, 1),
            "current": round(values[-1], 2) if values else 0,
            "average": round(statistics.mean(values), 2) if values else 0
        }

    def _dict_to_run_metrics(self, data: Dict) -> RunMetrics:
        """Converte dict in RunMetrics"""
        metrics = RunMetrics(
            run_id=data.get('run_id', ''),
            project=data.get('project', ''),
            environment=data.get('environment', 'local'),
            total_tests=data.get('total_tests', 0),
            passed_tests=data.get('passed_tests', 0),
            failed_tests=data.get('failed_tests', 0),
            total_duration_ms=data.get('total_duration_ms', 0),
            avg_test_duration_ms=data.get('avg_test_duration_ms', 0),
            tests_per_minute=data.get('tests_per_minute', 0),
            error_rate=data.get('error_rate', 0),
            chatbot_avg_latency_ms=data.get('chatbot_avg_latency_ms', 0),
            sheets_avg_latency_ms=data.get('sheets_avg_latency_ms', 0),
            langsmith_avg_latency_ms=data.get('langsmith_avg_latency_ms', 0),
        )

        # Parse dates
        if data.get('start_time'):
            try:
                metrics.start_time = datetime.fromisoformat(data['start_time'])
            except:
                pass
        if data.get('end_time'):
            try:
                metrics.end_time = datetime.fromisoformat(data['end_time'])
            except:
                pass

        return metrics


class PerformanceAlerter:
    """Sistema di alerting per degradazione performance"""

    def __init__(self, thresholds: Optional[Dict[str, float]] = None):
        self.thresholds = thresholds or {
            "duration_increase_percent": 20,  # Alert se durata aumenta >20%
            "throughput_decrease_percent": 15,  # Alert se throughput cala >15%
            "error_rate_threshold": 10,  # Alert se error rate >10%
            "pass_rate_threshold": 80,  # Alert se pass rate <80%
            "chatbot_latency_ms": 30000,  # Alert se chatbot >30s
            "sheets_latency_ms": 5000,  # Alert se sheets >5s
        }
        self.alerts: List[Dict[str, Any]] = []

    def check(self, current: RunMetrics, baseline: Optional[RunMetrics] = None) -> List[Dict[str, Any]]:
        """Controlla metriche e genera alert"""
        self.alerts = []

        # Check valori assoluti
        if current.error_rate > self.thresholds["error_rate_threshold"]:
            self.alerts.append({
                "type": "error_rate",
                "severity": "warning",
                "message": f"Error rate alto: {current.error_rate:.1f}% (soglia: {self.thresholds['error_rate_threshold']}%)",
                "value": current.error_rate
            })

        pass_rate = (current.passed_tests / current.total_tests * 100) if current.total_tests > 0 else 0
        if pass_rate < self.thresholds["pass_rate_threshold"]:
            self.alerts.append({
                "type": "pass_rate",
                "severity": "warning",
                "message": f"Pass rate basso: {pass_rate:.1f}% (soglia: {self.thresholds['pass_rate_threshold']}%)",
                "value": pass_rate
            })

        if current.chatbot_avg_latency_ms > self.thresholds["chatbot_latency_ms"]:
            self.alerts.append({
                "type": "chatbot_latency",
                "severity": "info",
                "message": f"Latenza chatbot alta: {current.chatbot_avg_latency_ms/1000:.1f}s",
                "value": current.chatbot_avg_latency_ms
            })

        if current.sheets_avg_latency_ms > self.thresholds["sheets_latency_ms"]:
            self.alerts.append({
                "type": "sheets_latency",
                "severity": "info",
                "message": f"Latenza Google Sheets alta: {current.sheets_avg_latency_ms/1000:.1f}s",
                "value": current.sheets_avg_latency_ms
            })

        # Check confronto con baseline
        if baseline:
            # Durata
            if baseline.total_duration_ms > 0:
                duration_change = ((current.total_duration_ms - baseline.total_duration_ms) / baseline.total_duration_ms) * 100
                if duration_change > self.thresholds["duration_increase_percent"]:
                    self.alerts.append({
                        "type": "duration_regression",
                        "severity": "warning",
                        "message": f"Durata aumentata del {duration_change:.1f}% rispetto a baseline",
                        "value": duration_change
                    })

            # Throughput
            if baseline.tests_per_minute > 0:
                throughput_change = ((baseline.tests_per_minute - current.tests_per_minute) / baseline.tests_per_minute) * 100
                if throughput_change > self.thresholds["throughput_decrease_percent"]:
                    self.alerts.append({
                        "type": "throughput_regression",
                        "severity": "warning",
                        "message": f"Throughput calato del {throughput_change:.1f}%",
                        "value": throughput_change
                    })

        return self.alerts

    def has_critical_alerts(self) -> bool:
        """Verifica se ci sono alert critici"""
        return any(a["severity"] == "critical" for a in self.alerts)

    def has_warnings(self) -> bool:
        """Verifica se ci sono warning"""
        return any(a["severity"] == "warning" for a in self.alerts)

    def format_alerts(self) -> str:
        """Formatta alert per output"""
        if not self.alerts:
            return "✅ Nessun alert di performance"

        lines = ["⚠️  PERFORMANCE ALERTS:"]
        for alert in self.alerts:
            icon = "🔴" if alert["severity"] == "critical" else "🟡" if alert["severity"] == "warning" else "🔵"
            lines.append(f"   {icon} {alert['message']}")

        return "\n".join(lines)


def compare_environments(local_metrics: RunMetrics, cloud_metrics: RunMetrics) -> PerformanceComparison:
    """Confronta performance tra local e cloud"""
    comparison = PerformanceComparison(
        run_a=local_metrics.run_id,
        run_b=cloud_metrics.run_id,
        environment_a=local_metrics.environment,
        environment_b=cloud_metrics.environment
    )

    # Timing
    comparison.duration_diff_ms = cloud_metrics.total_duration_ms - local_metrics.total_duration_ms
    if local_metrics.total_duration_ms > 0:
        comparison.duration_diff_percent = (comparison.duration_diff_ms / local_metrics.total_duration_ms) * 100

    comparison.avg_test_diff_ms = cloud_metrics.avg_test_duration_ms - local_metrics.avg_test_duration_ms
    if local_metrics.avg_test_duration_ms > 0:
        comparison.avg_test_diff_percent = (comparison.avg_test_diff_ms / local_metrics.avg_test_duration_ms) * 100

    # Throughput
    comparison.throughput_diff = cloud_metrics.tests_per_minute - local_metrics.tests_per_minute
    if local_metrics.tests_per_minute > 0:
        comparison.throughput_diff_percent = (comparison.throughput_diff / local_metrics.tests_per_minute) * 100

    # Pass rate
    local_pass_rate = (local_metrics.passed_tests / local_metrics.total_tests * 100) if local_metrics.total_tests > 0 else 0
    cloud_pass_rate = (cloud_metrics.passed_tests / cloud_metrics.total_tests * 100) if cloud_metrics.total_tests > 0 else 0
    comparison.pass_rate_diff = cloud_pass_rate - local_pass_rate

    # Servizi
    comparison.chatbot_latency_diff_ms = cloud_metrics.chatbot_avg_latency_ms - local_metrics.chatbot_avg_latency_ms
    comparison.sheets_latency_diff_ms = cloud_metrics.sheets_avg_latency_ms - local_metrics.sheets_avg_latency_ms

    # Differenze risultati test
    local_results = {t.test_id: t.status for t in local_metrics.test_metrics}
    cloud_results = {t.test_id: t.status for t in cloud_metrics.test_metrics}

    for test_id in set(local_results.keys()) | set(cloud_results.keys()):
        local_status = local_results.get(test_id, "N/A")
        cloud_status = cloud_results.get(test_id, "N/A")
        if local_status != cloud_status:
            comparison.result_differences.append({
                "test_id": test_id,
                "local": local_status,
                "cloud": cloud_status
            })

    return comparison


def format_comparison_report(comparison: PerformanceComparison) -> str:
    """Formatta report confronto environment"""
    lines = [
        f"\n{'='*60}",
        f"  CONFRONTO {comparison.environment_a.upper()} vs {comparison.environment_b.upper()}",
        f"  Run: {comparison.run_a} vs {comparison.run_b}",
        f"{'='*60}\n",
    ]

    # Timing
    lines.append("📊 TIMING")
    sign = "+" if comparison.duration_diff_ms > 0 else ""
    lines.append(f"   Durata totale: {sign}{comparison.duration_diff_ms/1000:.1f}s ({sign}{comparison.duration_diff_percent:.1f}%)")
    sign = "+" if comparison.avg_test_diff_ms > 0 else ""
    lines.append(f"   Media per test: {sign}{comparison.avg_test_diff_ms/1000:.1f}s ({sign}{comparison.avg_test_diff_percent:.1f}%)")
    lines.append("")

    # Throughput
    lines.append("⚡ THROUGHPUT")
    sign = "+" if comparison.throughput_diff > 0 else ""
    lines.append(f"   Differenza: {sign}{comparison.throughput_diff:.2f} test/min ({sign}{comparison.throughput_diff_percent:.1f}%)")
    lines.append("")

    # Risultati
    lines.append("📋 RISULTATI")
    sign = "+" if comparison.pass_rate_diff > 0 else ""
    lines.append(f"   Pass rate: {sign}{comparison.pass_rate_diff:.1f}%")
    if comparison.result_differences:
        lines.append(f"   Test con risultati diversi: {len(comparison.result_differences)}")
        for diff in comparison.result_differences[:5]:  # Mostra primi 5
            lines.append(f"     • {diff['test_id']}: {diff['local']} → {diff['cloud']}")
        if len(comparison.result_differences) > 5:
            lines.append(f"     ... e altri {len(comparison.result_differences) - 5}")
    lines.append("")

    # Latenze servizi
    lines.append("🌐 LATENZE SERVIZI")
    sign = "+" if comparison.chatbot_latency_diff_ms > 0 else ""
    lines.append(f"   Chatbot: {sign}{comparison.chatbot_latency_diff_ms/1000:.1f}s")
    sign = "+" if comparison.sheets_latency_diff_ms > 0 else ""
    lines.append(f"   Sheets: {sign}{comparison.sheets_latency_diff_ms/1000:.1f}s")

    lines.append(f"\n{'='*60}")

    return "\n".join(lines)
