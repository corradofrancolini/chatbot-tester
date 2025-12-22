"""
Calibration Module - Threshold analysis for evaluation metrics

Analyzes test results to suggest optimal thresholds for each project.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime


@dataclass
class MetricStats:
    """Statistics for a single metric"""
    name: str
    count: int = 0
    min: float = 0.0
    max: float = 0.0
    mean: float = 0.0
    median: float = 0.0
    std: float = 0.0
    p10: float = 0.0  # 10th percentile
    p25: float = 0.0  # 25th percentile
    p75: float = 0.0  # 75th percentile
    p90: float = 0.0  # 90th percentile
    suggested_threshold: float = 0.0

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class CalibrationReport:
    """Complete calibration report for a project"""
    project: str
    run_numbers: List[int] = field(default_factory=list)
    total_tests: int = 0
    tests_with_metrics: int = 0
    timestamp: str = ""
    metrics: Dict[str, MetricStats] = field(default_factory=dict)
    suggested_config: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "project": self.project,
            "run_numbers": self.run_numbers,
            "total_tests": self.total_tests,
            "tests_with_metrics": self.tests_with_metrics,
            "timestamp": self.timestamp,
            "metrics": {k: v.to_dict() for k, v in self.metrics.items()},
            "suggested_config": self.suggested_config
        }


class CalibrationAnalyzer:
    """
    Analyzes evaluation metrics to suggest optimal thresholds.

    Usage:
        analyzer = CalibrationAnalyzer(sheets_client, project_config)
        report = analyzer.analyze(last_n_runs=5)
        analyzer.print_report(report)
        analyzer.save_report(report, output_path)
    """

    # Metric column mappings
    METRIC_COLUMNS = {
        "SEMANTIC": "semantic",
        "JUDGE": "judge",
        "GROUND": "groundedness",
        "FAITH": "faithfulness",
        "RELEV": "relevance",
        "OVERALL": "overall"
    }

    def __init__(self, sheets_client, project_config):
        """
        Initialize analyzer.

        Args:
            sheets_client: GoogleSheetsClient instance
            project_config: ProjectConfig with spreadsheet info
        """
        self.sheets = sheets_client
        self.project = project_config

    def analyze(self,
                last_n_runs: int = 5,
                run_numbers: Optional[List[int]] = None) -> CalibrationReport:
        """
        Analyze metrics from recent runs.

        Args:
            last_n_runs: Number of recent runs to analyze (default 5)
            run_numbers: Specific run numbers to analyze (overrides last_n_runs)

        Returns:
            CalibrationReport with statistics and suggested thresholds
        """
        report = CalibrationReport(
            project=self.project.name,
            timestamp=datetime.now().isoformat()
        )

        # Get run numbers to analyze
        if run_numbers:
            runs_to_analyze = run_numbers
        else:
            runs_to_analyze = self._get_recent_runs(last_n_runs)

        report.run_numbers = runs_to_analyze

        # Collect all metric values
        all_values: Dict[str, List[float]] = {
            metric: [] for metric in self.METRIC_COLUMNS.values()
        }

        for run_num in runs_to_analyze:
            run_data = self._read_run_data(run_num)
            if run_data:
                report.total_tests += len(run_data)
                self._extract_metrics(run_data, all_values)

        # Calculate statistics for each metric
        for col_name, metric_name in self.METRIC_COLUMNS.items():
            values = all_values.get(metric_name, [])
            if values:
                report.tests_with_metrics = max(report.tests_with_metrics, len(values))
                stats = self._calculate_stats(metric_name, values)
                report.metrics[metric_name] = stats

        # Generate suggested thresholds
        report.suggested_config = self._suggest_thresholds(report.metrics)

        return report

    def _get_recent_runs(self, n: int) -> List[int]:
        """Get the N most recent run numbers from the spreadsheet"""
        import re
        try:
            # Use gspread to list all worksheets
            run_numbers = []
            for worksheet in self.sheets._spreadsheet.worksheets():
                title = worksheet.title
                # Match pattern: "Run 001 [DEV] auto - 2025-12-04" or "RUN 001"
                match = re.match(r'^Run\s+(\d{3})', title, re.IGNORECASE)
                if match:
                    try:
                        num = int(match.group(1))
                        run_numbers.append(num)
                    except ValueError:
                        pass

            # Return last N runs
            run_numbers.sort(reverse=True)
            return run_numbers[:n]

        except Exception as e:
            print(f"Error getting run list: {e}")
            return []

    def _read_run_data(self, run_num: int) -> List[Dict]:
        """Read data from a specific run sheet"""
        import re
        try:
            # Find worksheet by run number (handles "Run 001 [DEV] auto - date" format)
            worksheet = None
            pattern = re.compile(rf'^Run\s+{run_num:03d}\b', re.IGNORECASE)

            for ws in self.sheets._spreadsheet.worksheets():
                if pattern.match(ws.title):
                    worksheet = ws
                    break

            if not worksheet:
                print(f"  Sheet for RUN {run_num:03d} not found")
                return []

            # Get all values using gspread
            rows = worksheet.get_all_values()
            if len(rows) < 2:
                return []

            # Parse header and data
            header = rows[0]
            data = []
            for row in rows[1:]:
                if any(cell.strip() for cell in row):  # Skip empty rows
                    row_dict = {}
                    for i, col in enumerate(header):
                        if i < len(row):
                            row_dict[col] = row[i]
                        else:
                            row_dict[col] = ""
                    data.append(row_dict)

            return data

        except Exception as e:
            print(f"Error reading RUN {run_num:03d}: {e}")
            return []

    def _extract_metrics(self, run_data: List[Dict], all_values: Dict[str, List[float]]):
        """Extract metric values from run data"""
        for row in run_data:
            for col_name, metric_name in self.METRIC_COLUMNS.items():
                value_str = row.get(col_name, "")
                if value_str and value_str not in ["", "No evaluation", "-"]:
                    try:
                        value = float(value_str)
                        if 0 <= value <= 1:  # Valid metric range
                            all_values[metric_name].append(value)
                    except ValueError:
                        pass

    def _calculate_stats(self, name: str, values: List[float]) -> MetricStats:
        """Calculate statistics for a list of values"""
        if not values:
            return MetricStats(name=name)

        sorted_values = sorted(values)
        n = len(values)

        # Calculate percentiles
        def percentile(p: float) -> float:
            k = (n - 1) * p
            f = int(k)
            c = f + 1 if f + 1 < n else f
            return sorted_values[f] + (k - f) * (sorted_values[c] - sorted_values[f])

        mean = sum(values) / n
        variance = sum((x - mean) ** 2 for x in values) / n
        std = variance ** 0.5

        stats = MetricStats(
            name=name,
            count=n,
            min=min(values),
            max=max(values),
            mean=round(mean, 3),
            median=round(percentile(0.5), 3),
            std=round(std, 3),
            p10=round(percentile(0.1), 3),
            p25=round(percentile(0.25), 3),
            p75=round(percentile(0.75), 3),
            p90=round(percentile(0.9), 3)
        )

        # Suggest threshold based on distribution
        # Use P25 as threshold (bottom 25% fails)
        stats.suggested_threshold = round(percentile(0.25), 2)

        return stats

    def _suggest_thresholds(self, metrics: Dict[str, MetricStats]) -> Dict[str, float]:
        """Generate suggested threshold configuration"""
        config = {}

        # Map metric names to config keys
        metric_to_config = {
            "semantic": "semantic_threshold",
            "judge": "judge_threshold",
            "groundedness": "rag_threshold",  # Use groundedness for RAG threshold
        }

        for metric_name, config_key in metric_to_config.items():
            if metric_name in metrics:
                stats = metrics[metric_name]
                if stats.count > 0:
                    # Use P25 as suggested threshold
                    config[config_key] = stats.suggested_threshold

        return config

    def print_report(self, report: CalibrationReport):
        """Print formatted report to console"""
        print("\n" + "=" * 60)
        print(f"  CALIBRATION REPORT - {report.project}")
        print("=" * 60)
        print(f"\nRuns analyzed: {report.run_numbers}")
        print(f"Total tests: {report.total_tests}")
        print(f"Tests with metrics: {report.tests_with_metrics}")

        if report.total_tests > 0 and report.tests_with_metrics == 0:
            print("\n⚠️  No evaluation metrics found in analyzed runs.")
            print("    Make sure evaluation is enabled in settings.yaml:")
            print("      evaluation:")
            print("        enabled: true")
            print("    And re-run tests with evaluation active.")

        print("\n" + "-" * 60)
        print("  METRIC STATISTICS")
        print("-" * 60)

        for name, stats in report.metrics.items():
            if stats.count > 0:
                print(f"\n{name.upper()} (n={stats.count})")
                print(f"  Range:    {stats.min:.2f} - {stats.max:.2f}")
                print(f"  Mean:     {stats.mean:.2f} (std: {stats.std:.2f})")
                print(f"  Median:   {stats.median:.2f}")
                print(f"  P10/P90:  {stats.p10:.2f} / {stats.p90:.2f}")
                print(f"  P25/P75:  {stats.p25:.2f} / {stats.p75:.2f}")
                print(f"  Suggested threshold: {stats.suggested_threshold:.2f}")

        print("\n" + "-" * 60)
        print("  SUGGESTED CONFIGURATION")
        print("-" * 60)
        print("\nAdd to config/settings.yaml:")
        print()
        print("evaluation:")
        for key, value in report.suggested_config.items():
            print(f"  {key}: {value}")

        print("\n" + "=" * 60)

    def save_report(self, report: CalibrationReport, output_path: Path):
        """Save report to JSON file"""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump(report.to_dict(), f, indent=2)
        print(f"\nReport saved to: {output_path}")


def run_calibration(project_name: str,
                    last_n_runs: int = 5,
                    run_numbers: Optional[List[int]] = None) -> Optional[CalibrationReport]:
    """
    Run calibration analysis for a project.

    Args:
        project_name: Name of the project
        last_n_runs: Number of recent runs to analyze
        run_numbers: Specific runs to analyze (optional)

    Returns:
        CalibrationReport or None on error
    """
    from .config_loader import ConfigLoader
    from .sheets_client import GoogleSheetsClient

    try:
        # Load configuration
        loader = ConfigLoader()
        project = loader.load_project(project_name)

        if not project.google_sheets.enabled:
            print(f"Google Sheets not enabled for project {project_name}")
            return None

        # Use credentials from project config (same as tester.py)
        creds_path = project.google_sheets.credentials_path

        # Token path should be in same directory as credentials
        token_path = str(Path(creds_path).parent / "token.json") if creds_path else ""

        # Initialize sheets client
        sheets = GoogleSheetsClient(
            spreadsheet_id=project.google_sheets.spreadsheet_id,
            credentials_path=creds_path,
            token_path=token_path,
            drive_folder_id=project.google_sheets.drive_folder_id
        )

        # Authenticate
        if not sheets.authenticate():
            print("Failed to authenticate with Google Sheets")
            return None

        # Run analysis
        analyzer = CalibrationAnalyzer(sheets, project)
        report = analyzer.analyze(last_n_runs=last_n_runs, run_numbers=run_numbers)

        # Print report
        analyzer.print_report(report)

        # Save report
        output_path = Path(f"reports/{project_name}/calibration_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        analyzer.save_report(report, output_path)

        return report

    except Exception as e:
        print(f"Calibration error: {e}")
        import traceback
        traceback.print_exc()
        return None
