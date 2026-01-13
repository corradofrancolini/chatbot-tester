"""
Test Data Extractor - Extracts test data from CSV reports

Parses test run reports and extracts structured test trace data.
"""

import re
import csv
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict


@dataclass
class TestTrace:
    """Trace di un singolo test."""
    test_id: str
    question: str
    response: str
    query_data: Optional[Dict] = None
    tools_used: List[str] = field(default_factory=list)
    sources: List[Dict[str, str]] = field(default_factory=list)
    model: Optional[str] = None
    duration_ms: int = 0
    first_token_ms: int = 0
    result: str = "UNKNOWN"
    notes: Optional[str] = None


class TestDataExtractor:
    """Estrae dati di test dal report CSV."""

    def __init__(self, project_name: str, base_dir: Optional[Path] = None):
        self.project_name = project_name
        if base_dir:
            self.base_dir = Path(base_dir)
        else:
            self.base_dir = Path(__file__).parent.parent.parent
        self.reports_dir = self.base_dir / "reports" / project_name

    def get_latest_run(self) -> Optional[int]:
        """Trova l'ultima run disponibile."""
        if not self.reports_dir.exists():
            return None

        run_dirs = list(self.reports_dir.glob("run_*"))
        if not run_dirs:
            return None

        run_numbers = []
        for d in run_dirs:
            try:
                num = int(d.name.split('_')[1])
                run_numbers.append(num)
            except (IndexError, ValueError):
                pass

        return max(run_numbers) if run_numbers else None

    def get_test(self, run_number: int, test_id: str) -> Optional[TestTrace]:
        """Estrae un singolo test dalla run."""
        report_path = self.reports_dir / f"run_{run_number:03d}" / "report.csv"
        if not report_path.exists():
            return None

        with open(report_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('test_id') == test_id:
                    return self._parse_row(row)

        return None

    def get_all_tests(self, run_number: int) -> List[TestTrace]:
        """Estrae tutti i test da una run."""
        report_path = self.reports_dir / f"run_{run_number:03d}" / "report.csv"
        if not report_path.exists():
            return []

        tests = []
        with open(report_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                trace = self._parse_row(row)
                if trace:
                    tests.append(trace)

        return tests

    def _parse_row(self, row: Dict[str, str]) -> Optional[TestTrace]:
        """Parsa una riga del CSV in TestTrace."""
        notes = row.get('notes', '')

        # Estrai sezioni strutturate dalle notes
        query_data = self._extract_section(notes, 'QUERY')
        response = self._extract_section(notes, 'RESPONSE')
        performance = self._extract_section(notes, 'PERFORMANCE')
        tools_section = self._extract_section(notes, 'TOOLS')
        sources_section = self._extract_section(notes, 'SOURCES')

        # Parse performance
        model = None
        duration = 0
        first_token = 0
        if performance:
            model_match = re.search(r'Model:\s*(.+)', performance)
            if model_match:
                model = model_match.group(1).strip()
            dur_match = re.search(r'Duration:\s*(\d+)ms', performance)
            if dur_match:
                duration = int(dur_match.group(1))
            ft_match = re.search(r'First Token:\s*(\d+)ms', performance)
            if ft_match:
                first_token = int(ft_match.group(1))

        # Parse tools
        tools = []
        if tools_section:
            tools = [t.strip() for t in tools_section.split('\n') if t.strip()]

        # Parse sources
        sources = []
        if sources_section:
            for line in sources_section.split('\n'):
                if line.strip().startswith('•'):
                    source_text = line.strip()[1:].strip()
                    sources.append({'path': source_text})

        return TestTrace(
            test_id=row.get('test_id', ''),
            question=row.get('question', ''),
            response=response or row.get('conversation', ''),
            query_data=self._parse_json_safe(query_data) if query_data else None,
            tools_used=tools,
            sources=sources,
            model=model,
            duration_ms=int(row.get('duration_ms', 0)) or duration,
            first_token_ms=first_token,
            result=row.get('esito', 'UNKNOWN'),
            notes=notes
        )

    def _extract_section(self, text: str, section_name: str) -> Optional[str]:
        """Estrae una sezione dal testo delle notes."""
        pattern = rf'=== {section_name}(?: \(\d+\))? ===\s*\n(.*?)(?===|$)'
        match = re.search(pattern, text, re.DOTALL)
        if match:
            return match.group(1).strip()
        return None

    def _parse_json_safe(self, text: str) -> Optional[Dict]:
        """Prova a parsare JSON, ritorna None se fallisce."""
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return None
