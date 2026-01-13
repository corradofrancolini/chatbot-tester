"""
Report Generator - Local HTML and CSV report generation

Handles:
- Navigable HTML report with statistics
- CSV export for analysis
- Summary JSON with run metadata
- Results aggregation
"""

import csv
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass, asdict
from collections import Counter


from .models import TestResult


@dataclass
class RunSummary:
    """Test run summary"""
    run_number: int
    project_name: str
    start_time: str
    end_time: str
    mode: str
    total_tests: int
    passed: int
    failed: int
    skipped: int
    errors: int
    duration_seconds: int
    avg_response_time_ms: int
    categories: Dict[str, Dict[str, int]]  # {category: {passed, failed}}


class ReportGenerator:
    """
    Local report generator.

    Features:
    - Interactive HTML report with filters
    - Excel-compatible CSV export
    - Summary JSON for automation
    - Statistics by category

    Usage:
        generator = ReportGenerator(output_dir)
        generator.add_result(result)
        generator.generate()
    """

    def __init__(self, output_dir: Path, project_name: str = ""):
        """
        Initialize the generator.

        Args:
            output_dir: Output directory (e.g., reports/project/run_001)
            project_name: Project name
        """
        self.output_dir = Path(output_dir)
        self.project_name = project_name
        self.screenshots_dir = self.output_dir / "screenshots"

        # Create directories
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.screenshots_dir.mkdir(exist_ok=True)

        # Results
        self.results: List[TestResult] = []

        # Timing
        self.start_time = datetime.utcnow()
        self.end_time: Optional[datetime] = None

        # Metadata
        self.mode = ""
        self.run_number = self._extract_run_number()

    def _extract_run_number(self) -> int:
        """Extract run number from path"""
        try:
            name = self.output_dir.name
            if name.startswith('run_'):
                return int(name.replace('run_', ''))
        except:
            pass
        return 0

    def add_result(self, result: TestResult) -> None:
        """Add a result"""
        self.results.append(result)

        # Set mode from first run
        if not self.mode and result.mode:
            self.mode = result.mode

    def add_results(self, results: List[TestResult]) -> None:
        """Add multiple results"""
        for r in results:
            self.add_result(r)

    def generate(self) -> Dict[str, Path]:
        """
        Generate all reports.

        Returns:
            Dict with paths: {html, csv, summary}
        """
        self.end_time = datetime.utcnow()

        paths = {
            'html': self._generate_html(),
            'csv': self._generate_csv(),
            'summary': self._generate_summary()
        }

        return paths

    def _generate_summary(self) -> Path:
        """Generate summary JSON"""
        # Calculate statistics
        esiti = Counter(r.result.upper() for r in self.results)

        # Statistics by category
        categories: Dict[str, Dict[str, int]] = {}
        for r in self.results:
            cat = r.category or 'uncategorized'
            if cat not in categories:
                categories[cat] = {'passed': 0, 'failed': 0, 'total': 0}
            categories[cat]['total'] += 1
            if r.result.upper() == 'PASS':
                categories[cat]['passed'] += 1
            elif r.result.upper() == 'FAIL':
                categories[cat]['failed'] += 1

        # Average response time
        durations = [r.duration_ms for r in self.results if r.duration_ms > 0]
        avg_duration = int(sum(durations) / len(durations)) if durations else 0

        summary = RunSummary(
            run_number=self.run_number,
            project_name=self.project_name,
            start_time=self.start_time.isoformat(),
            end_time=self.end_time.isoformat() if self.end_time else "",
            mode=self.mode,
            total_tests=len(self.results),
            passed=esiti.get('PASS', 0),
            failed=esiti.get('FAIL', 0),
            skipped=esiti.get('SKIP', 0),
            errors=esiti.get('ERROR', 0),
            duration_seconds=int((self.end_time - self.start_time).total_seconds()) if self.end_time else 0,
            avg_response_time_ms=avg_duration,
            categories=categories
        )

        path = self.output_dir / "summary.json"
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(asdict(summary), f, indent=2, ensure_ascii=False)

        return path

    def _generate_csv(self) -> Path:
        """Generate CSV report"""
        path = self.output_dir / "report.csv"

        fieldnames = [
            'test_id', 'date', 'mode', 'category', 'question',
            'result', 'duration_ms', 'followups_count', 'notes',
            'conversation', 'screenshot_path', 'langsmith_url',
            'prompt_version', 'model_version', 'environment'
        ]

        with open(path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for r in self.results:
                writer.writerow({
                    'test_id': r.test_id,
                    'date': r.date,
                    'mode': r.mode,
                    'category': r.category,
                    'question': r.question,
                    'result': r.result,
                    'duration_ms': r.duration_ms,
                    'followups_count': r.followups_count,
                    'notes': r.notes,
                    'conversation': r.conversation[:1000],  # Truncate
                    'screenshot_path': r.screenshot_path or "",
                    'langsmith_url': r.langsmith_url,
                    'prompt_version': r.prompt_version,
                    'model_version': r.model_version,
                    'environment': r.environment
                })

        return path

    def _generate_html(self) -> Path:
        """Generate interactive HTML report"""
        # Statistics for header
        esiti = Counter(r.result.upper() for r in self.results)
        total = len(self.results)
        passed = esiti.get('PASS', 0)
        failed = esiti.get('FAIL', 0)
        pass_rate = (passed / total * 100) if total > 0 else 0

        # Run duration
        duration = ""
        if self.end_time:
            secs = int((self.end_time - self.start_time).total_seconds())
            mins = secs // 60
            secs = secs % 60
            duration = f"{mins}m {secs}s"

        # Generate table rows
        rows_html = ""
        for r in self.results:
            esito_class = {
                'PASS': 'pass',
                'FAIL': 'fail',
                'SKIP': 'skip',
                'ERROR': 'error'
            }.get(r.result.upper(), '')

            # Format conversation (escape HTML)
            conv_escaped = (r.conversation
                .replace('&', '&amp;')
                .replace('<', '&lt;')
                .replace('>', '&gt;')
                .replace('\n', '<br>')
            )

            # Screenshot link
            screenshot_html = ""
            if r.screenshot_path:
                screenshot_html = f'<a href="{r.screenshot_path}" target="_blank">[img]</a>'

            # LangSmith link
            langsmith_html = ""
            if r.langsmith_url:
                langsmith_html = f'<a href="{r.langsmith_url}" target="_blank">[trace]</a>'

            rows_html += f"""
            <tr class="{esito_class}" data-category="{r.category}" data-esito="{r.result.upper()}">
                <td>{r.test_id}</td>
                <td>{r.category}</td>
                <td class="question">{r.question}</td>
                <td class="esito {esito_class}">{r.result}</td>
                <td>{r.duration_ms}ms</td>
                <td class="icons">{screenshot_html} {langsmith_html}</td>
                <td class="notes">{r.notes}</td>
                <td class="conversation">{conv_escaped}</td>
            </tr>
            """

        # Categories for filter
        categories = sorted(set(r.category for r in self.results if r.category))
        categories_options = "\n".join(f'<option value="{c}">{c}</option>' for c in categories)

        html = f"""<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Report Test - {self.project_name} - Run {self.run_number}</title>
    <style>
        :root {{
            --pass-color: #22c55e;
            --fail-color: #ef4444;
            --skip-color: #f59e0b;
            --error-color: #8b5cf6;
        }}

        * {{ box-sizing: border-box; margin: 0; padding: 0; }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f8fafc;
            color: #1e293b;
            line-height: 1.5;
        }}

        .container {{
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }}

        header {{
            background: white;
            padding: 20px;
            border-radius: 12px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }}

        h1 {{
            font-size: 1.5rem;
            margin-bottom: 10px;
        }}

        .meta {{
            color: #64748b;
            font-size: 0.9rem;
        }}

        .stats {{
            display: flex;
            gap: 20px;
            margin-top: 15px;
            flex-wrap: wrap;
        }}

        .stat {{
            background: #f1f5f9;
            padding: 15px 25px;
            border-radius: 8px;
            text-align: center;
        }}

        .stat-value {{
            font-size: 1.8rem;
            font-weight: 700;
        }}

        .stat-label {{
            font-size: 0.85rem;
            color: #64748b;
        }}

        .stat.pass .stat-value {{ color: var(--pass-color); }}
        .stat.fail .stat-value {{ color: var(--fail-color); }}

        .filters {{
            background: white;
            padding: 15px;
            border-radius: 12px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            margin-bottom: 20px;
            display: flex;
            gap: 15px;
            flex-wrap: wrap;
            align-items: center;
        }}

        .filters label {{ font-weight: 500; }}

        .filters select, .filters input {{
            padding: 8px 12px;
            border: 1px solid #e2e8f0;
            border-radius: 6px;
            font-size: 0.9rem;
        }}

        table {{
            width: 100%;
            background: white;
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            border-collapse: collapse;
        }}

        th {{
            background: #f8fafc;
            padding: 12px;
            text-align: left;
            font-weight: 600;
            border-bottom: 2px solid #e2e8f0;
        }}

        td {{
            padding: 12px;
            border-bottom: 1px solid #f1f5f9;
            vertical-align: top;
        }}

        tr:hover {{
            background: #f8fafc;
        }}

        .result {{
            font-weight: 600;
            padding: 4px 10px;
            border-radius: 4px;
            display: inline-block;
        }}

        .result.pass {{ background: #dcfce7; color: #166534; }}
        .result.fail {{ background: #fee2e2; color: #991b1b; }}
        .result.skip {{ background: #fef3c7; color: #92400e; }}
        .result.error {{ background: #ede9fe; color: #5b21b6; }}

        .question {{
            max-width: 300px;
            font-weight: 500;
        }}

        .conversation {{
            max-width: 400px;
            max-height: 100px;
            overflow-y: auto;
            font-size: 0.85rem;
            color: #64748b;
        }}

        .notes {{
            max-width: 200px;
            font-size: 0.85rem;
        }}

        .icons a {{
            text-decoration: none;
            margin-right: 5px;
        }}

        tr.hidden {{ display: none; }}

        @media (max-width: 768px) {{
            .stats {{ flex-direction: column; }}
            .filters {{ flex-direction: column; }}
            table {{ font-size: 0.85rem; }}
            td, th {{ padding: 8px; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Report Test - {self.project_name}</h1>
            <div class="meta">
                Run #{self.run_number} | {self.start_time.strftime('%Y-%m-%d %H:%M')} |
                Modalità: {self.mode} | Durata: {duration}
            </div>
            <div class="stats">
                <div class="stat">
                    <div class="stat-value">{total}</div>
                    <div class="stat-label">Totale Test</div>
                </div>
                <div class="stat pass">
                    <div class="stat-value">{passed}</div>
                    <div class="stat-label">Passati</div>
                </div>
                <div class="stat fail">
                    <div class="stat-value">{failed}</div>
                    <div class="stat-label">Falliti</div>
                </div>
                <div class="stat">
                    <div class="stat-value">{pass_rate:.1f}%</div>
                    <div class="stat-label">Pass Rate</div>
                </div>
            </div>
        </header>

        <div class="filters">
            <label>Filtra:</label>
            <select id="filterEsito">
                <option value="">Tutti gli esiti</option>
                <option value="PASS">PASS</option>
                <option value="FAIL">FAIL</option>
                <option value="SKIP">SKIP</option>
                <option value="ERROR">ERROR</option>
            </select>
            <select id="filterCategory">
                <option value="">Tutte le categorie</option>
                {categories_options}
            </select>
            <input type="text" id="searchText" placeholder="Cerca..." />
        </div>

        <table>
            <thead>
                <tr>
                    <th>ID</th>
                    <th>Categoria</th>
                    <th>Domanda</th>
                    <th>Esito</th>
                    <th>Tempo</th>
                    <th>Link</th>
                    <th>Note</th>
                    <th>Conversazione</th>
                </tr>
            </thead>
            <tbody id="resultsBody">
                {rows_html}
            </tbody>
        </table>
    </div>

    <script>
        const filterEsito = document.getElementById('filterEsito');
        const filterCategory = document.getElementById('filterCategory');
        const searchText = document.getElementById('searchText');
        const rows = document.querySelectorAll('#resultsBody tr');

        function applyFilters() {{
            const esito = filterEsito.value;
            const category = filterCategory.value;
            const search = searchText.value.toLowerCase();

            rows.forEach(row => {{
                const rowEsito = row.dataset.result;
                const rowCategory = row.dataset.category;
                const rowText = row.textContent.toLowerCase();

                let show = true;

                if (esito && rowEsito !== esito) show = false;
                if (category && rowCategory !== category) show = false;
                if (search && !rowText.includes(search)) show = false;

                row.classList.toggle('hidden', !show);
            }});
        }}

        filterEsito.addEventListener('change', applyFilters);
        filterCategory.addEventListener('change', applyFilters);
        searchText.addEventListener('input', applyFilters);
    </script>
</body>
</html>"""

        path = self.output_dir / "report.html"
        with open(path, 'w', encoding='utf-8') as f:
            f.write(html)

        return path

    def get_screenshot_path(self, test_id: str) -> Path:
        """Return path to save screenshot for a test"""
        return self.screenshots_dir / f"{test_id}.png"


def aggregate_reports(reports_dir: Path, project_name: str) -> Dict[str, Any]:
    """
    Aggregate statistics from all runs of a project.

    Args:
        reports_dir: Reports directory (e.g., reports/my-project/)
        project_name: Project name

    Returns:
        Aggregated statistics
    """
    runs = []

    for run_dir in sorted(reports_dir.iterdir()):
        if not run_dir.is_dir() or not run_dir.name.startswith('run_'):
            continue

        summary_file = run_dir / "summary.json"
        if summary_file.exists():
            with open(summary_file) as f:
                runs.append(json.load(f))

    if not runs:
        return {'error': 'No runs found'}

    # Calculate trend
    total_tests = sum(r['total_tests'] for r in runs)
    total_passed = sum(r['passed'] for r in runs)

    return {
        'project': project_name,
        'total_runs': len(runs),
        'total_tests': total_tests,
        'total_passed': total_passed,
        'overall_pass_rate': (total_passed / total_tests * 100) if total_tests > 0 else 0,
        'latest_run': runs[-1] if runs else None,
        'trend': [
            {
                'run': r['run_number'],
                'date': r['start_time'][:10],
                'pass_rate': (r['passed'] / r['total_tests'] * 100) if r['total_tests'] > 0 else 0
            }
            for r in runs[-10:]  # Last 10 runs
        ]
    }
