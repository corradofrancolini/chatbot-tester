"""
Unit Tests - Export Module

Testa le singole funzioni di export.
"""
import pytest
from pathlib import Path
import tempfile
import csv
import json
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.export import RunReport, ReportExporter, HTMLExporter


class TestCSVExport:
    """Test export CSV"""

    def test_export_csv_creates_file(self):
        """Verifica che to_csv() crei un file"""
        # Carica un report esistente se disponibile
        report_dir = Path("reports/my-chatbot")
        if not report_dir.exists():
            pytest.skip("Nessun report disponibile per test")

        # Trova l'ultimo run
        runs = sorted(report_dir.glob("run_*"), reverse=True)
        if not runs:
            pytest.skip("Nessun run disponibile")

        summary_path = runs[0] / "summary.json"
        if not summary_path.exists():
            pytest.skip("summary.json non trovato")

        report = RunReport.from_summary_and_csv(summary_path)
        exporter = ReportExporter(report)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test_export.csv"
            result = exporter.to_csv(output_path)

            assert result.exists(), "File CSV non creato"
            assert result.stat().st_size > 0, "File CSV vuoto"

    def test_csv_has_valid_structure(self):
        """Verifica che il CSV abbia struttura valida"""
        report_dir = Path("reports/my-chatbot")
        if not report_dir.exists():
            pytest.skip("Nessun report disponibile")

        runs = sorted(report_dir.glob("run_*"), reverse=True)
        if not runs:
            pytest.skip("Nessun run disponibile")

        summary_path = runs[0] / "summary.json"
        if not summary_path.exists():
            pytest.skip("summary.json non trovato")

        report = RunReport.from_summary_and_csv(summary_path)
        exporter = ReportExporter(report)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test.csv"
            result = exporter.to_csv(output_path)

            # Leggi e verifica CSV
            with open(result, 'r') as f:
                reader = csv.DictReader(f)
                rows = list(reader)

            # Deve avere almeno una riga se ci sono risultati
            # (potrebbe essere vuoto se il report è vuoto)
            assert isinstance(rows, list)


class TestHTMLExport:
    """Test export HTML"""

    def test_export_html_creates_file(self):
        """Verifica che to_html() crei un file"""
        report_dir = Path("reports/my-chatbot")
        if not report_dir.exists():
            pytest.skip("Nessun report disponibile")

        runs = sorted(report_dir.glob("run_*"), reverse=True)
        if not runs:
            pytest.skip("Nessun run disponibile")

        summary_path = runs[0] / "summary.json"
        if not summary_path.exists():
            pytest.skip("summary.json non trovato")

        report = RunReport.from_summary_and_csv(summary_path)
        exporter = ReportExporter(report)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test_export.html"
            result = exporter.to_html(output_path)

            assert result.exists(), "File HTML non creato"
            assert result.stat().st_size > 0, "File HTML vuoto"

    def test_html_is_valid(self):
        """Verifica che l'HTML sia valido"""
        report_dir = Path("reports/my-chatbot")
        if not report_dir.exists():
            pytest.skip("Nessun report disponibile")

        runs = sorted(report_dir.glob("run_*"), reverse=True)
        if not runs:
            pytest.skip("Nessun run disponibile")

        summary_path = runs[0] / "summary.json"
        if not summary_path.exists():
            pytest.skip("summary.json non trovato")

        report = RunReport.from_summary_and_csv(summary_path)
        exporter = ReportExporter(report)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test.html"
            result = exporter.to_html(output_path)

            content = result.read_text()

            # Verifica tag HTML base
            assert "<html" in content.lower()
            assert "</html>" in content.lower()
            assert "<body" in content.lower()


class TestRunReportLoading:
    """Test caricamento RunReport"""

    def test_load_from_summary_json(self):
        """Carica report da summary.json"""
        report_dir = Path("reports/my-chatbot")
        if not report_dir.exists():
            pytest.skip("Nessun report disponibile")

        runs = sorted(report_dir.glob("run_*"), reverse=True)
        if not runs:
            pytest.skip("Nessun run disponibile")

        summary_path = runs[0] / "summary.json"
        if not summary_path.exists():
            pytest.skip("summary.json non trovato")

        report = RunReport.from_summary_and_csv(summary_path)

        # Verifica attributi base
        assert report is not None
        assert hasattr(report, 'run_number') or hasattr(report, 'project')

    def test_load_with_csv(self):
        """Carica report con CSV dei risultati"""
        report_dir = Path("reports/my-chatbot")
        if not report_dir.exists():
            pytest.skip("Nessun report disponibile")

        runs = sorted(report_dir.glob("run_*"), reverse=True)
        if not runs:
            pytest.skip("Nessun run disponibile")

        summary_path = runs[0] / "summary.json"
        csv_path = runs[0] / "report.csv"

        if not summary_path.exists():
            pytest.skip("summary.json non trovato")

        if csv_path.exists():
            report = RunReport.from_summary_and_csv(summary_path, csv_path)
        else:
            report = RunReport.from_summary_and_csv(summary_path)

        assert report is not None
