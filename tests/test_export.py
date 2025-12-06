"""
Test suite per src/export.py
"""
import pytest
from pathlib import Path
from datetime import datetime
import tempfile
import json

# Importa moduli da testare
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.export import (
    RunReport, TestResult, ReportExporter,
    PDFExporter, ExcelExporter, HTMLExporter
)


class TestRunReport:
    """Test per la classe RunReport"""

    def test_create_empty_report(self):
        """Crea report vuoto"""
        report = RunReport(
            project="test-project",
            run_number=1,
            timestamp=datetime.now().isoformat(),
            results=[]
        )
        assert report.project == "test-project"
        assert report.run_number == 1
        assert len(report.results) == 0

    def test_create_report_with_results(self):
        """Crea report con risultati"""
        results = [
            TestResult(
                test_id="TEST_001",
                question="Test question?",
                expected="Expected answer",
                actual="Actual answer",
                status="PASS",
                score=0.9,
                duration_ms=1500
            ),
            TestResult(
                test_id="TEST_002",
                question="Another question?",
                expected="Expected",
                actual="Different",
                status="FAIL",
                score=0.3,
                duration_ms=2000
            )
        ]

        report = RunReport(
            project="test-project",
            run_number=5,
            timestamp=datetime.now().isoformat(),
            results=results
        )

        assert len(report.results) == 2
        assert report.results[0].status == "PASS"
        assert report.results[1].status == "FAIL"

    def test_report_statistics(self):
        """Verifica calcolo statistiche"""
        results = [
            TestResult("T1", "Q1", "E1", "A1", "PASS", 0.9, 1000),
            TestResult("T2", "Q2", "E2", "A2", "PASS", 0.8, 1000),
            TestResult("T3", "Q3", "E3", "A3", "FAIL", 0.2, 1000),
        ]

        report = RunReport(
            project="test",
            run_number=1,
            timestamp=datetime.now().isoformat(),
            results=results
        )

        # Calcola statistiche
        passed = sum(1 for r in report.results if r.status == "PASS")
        failed = sum(1 for r in report.results if r.status == "FAIL")

        assert passed == 2
        assert failed == 1


class TestExporters:
    """Test per gli exporter"""

    @pytest.fixture
    def sample_report(self):
        """Report di esempio per i test"""
        return RunReport(
            project="test-project",
            run_number=10,
            timestamp="2024-01-15T10:30:00",
            results=[
                TestResult("TEST_001", "Question 1?", "Expected 1", "Actual 1", "PASS", 0.95, 1200),
                TestResult("TEST_002", "Question 2?", "Expected 2", "Actual 2", "FAIL", 0.40, 1800),
                TestResult("TEST_003", "Question 3?", "Expected 3", "Actual 3", "PASS", 0.88, 900),
            ]
        )

    def test_csv_export_via_facade(self, sample_report):
        """Test export CSV via ReportExporter"""
        with tempfile.TemporaryDirectory() as tmpdir:
            exporter = ReportExporter(sample_report)
            result_path = exporter.to_csv(Path(tmpdir) / "report.csv")

            assert result_path.exists()

            # Verifica contenuto
            content = result_path.read_text()
            assert "TEST_001" in content
            assert "PASS" in content
            assert "FAIL" in content

    def test_html_exporter(self, sample_report):
        """Test export HTML"""
        with tempfile.NamedTemporaryFile(suffix='.html', delete=False) as f:
            output_path = Path(f.name)

        try:
            exporter = HTMLExporter(sample_report)
            result_path = exporter.export(output_path)

            assert result_path.exists()

            # Verifica contenuto HTML
            content = result_path.read_text()
            assert "<html" in content.lower()
            assert "test-project" in content
            assert "TEST_001" in content
        finally:
            output_path.unlink(missing_ok=True)

    def test_report_exporter_facade(self, sample_report):
        """Test ReportExporter facade"""
        exporter = ReportExporter(sample_report)

        with tempfile.TemporaryDirectory() as tmpdir:
            # Test CSV
            csv_path = Path(tmpdir) / "report.csv"
            result = exporter.to_csv(csv_path)
            assert result.exists()

            # Test HTML
            html_path = Path(tmpdir) / "report.html"
            result = exporter.to_html(html_path)
            assert result.exists()


class TestReportLoading:
    """Test per caricamento report esistenti"""

    def test_from_summary_json(self):
        """Test caricamento da summary.json"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Crea summary.json di test
            summary_data = {
                "project": "test-project",
                "run_number": 15,
                "timestamp": "2024-01-20T14:00:00",
                "total_tests": 3,
                "passed": 2,
                "failed": 1,
                "pass_rate": 66.7
            }

            summary_path = Path(tmpdir) / "summary.json"
            summary_path.write_text(json.dumps(summary_data))

            # Prova a caricare
            report = RunReport.from_summary_and_csv(summary_path)

            assert report.project == "test-project"
            assert report.run_number == 15
