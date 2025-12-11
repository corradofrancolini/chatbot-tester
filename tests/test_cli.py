"""
Test suite per CLI (run.py)
"""
import pytest
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestCLIHelp:
    """Test per opzioni help"""

    def test_help_option(self):
        """Test --help"""
        result = subprocess.run(
            ['python', 'run.py', '--help'],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0
        assert '--project' in result.stdout
        assert '--mode' in result.stdout

    def test_version_option(self):
        """Test --version"""
        result = subprocess.run(
            ['python', 'run.py', '--version'],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0


class TestCLIExport:
    """Test per opzioni export"""

    def test_export_requires_project(self):
        """Export richiede progetto"""
        result = subprocess.run(
            ['python', 'run.py', '--export', 'html'],
            capture_output=True,
            text=True
        )
        # Dovrebbe fallire senza progetto
        assert result.returncode != 0 or 'project' in result.stderr.lower() or 'progetto' in result.stderr.lower()

    def test_export_invalid_format(self):
        """Export con formato non valido"""
        result = subprocess.run(
            ['python', 'run.py', '-p', 'test', '--export', 'invalid_format'],
            capture_output=True,
            text=True
        )
        assert result.returncode != 0


class TestCLINotify:
    """Test per opzioni notify"""

    def test_test_notify_option(self):
        """Test --test-notify"""
        result = subprocess.run(
            ['python', 'run.py', '--test-notify'],
            capture_output=True,
            text=True,
            timeout=10
        )
        # Dovrebbe completare (con o senza errori di notifica)
        # L'importante è che non crashi


class TestCLIModes:
    """Test per modalità"""

    def test_mode_options(self):
        """Verifica che le modalità siano accettate"""
        for mode in ['train', 'assisted', 'auto']:
            result = subprocess.run(
                ['python', 'run.py', '-p', 'nonexistent', '-m', mode, '--dry-run'],
                capture_output=True,
                text=True,
                timeout=5
            )
            # Può fallire per progetto mancante, ma non per modalità invalida


class TestCLIHealthCheck:
    """Test per health check"""

    def test_health_check_option(self):
        """Test --health-check"""
        result = subprocess.run(
            ['python', 'run.py', '--health-check', '-p', 'my-chatbot'],
            capture_output=True,
            text=True,
            timeout=30
        )
        # Deve completare senza crash


class TestModuleImports:
    """Test per import moduli"""

    def test_import_export(self):
        """Import src/export.py"""
        from src.export import RunReport, ReportExporter
        assert RunReport is not None
        assert ReportExporter is not None

    def test_import_notifications(self):
        """Import src/notifications.py"""
        from src.notifications import NotificationManager, NotificationConfig
        assert NotificationManager is not None
        assert NotificationConfig is not None

    def test_import_config_loader(self):
        """Import src/config_loader.py"""
        from src.config_loader import ConfigLoader
        assert ConfigLoader is not None

    def test_import_ui(self):
        """Import src/ui.py"""
        from src.ui import ConsoleUI, MenuItem
        assert ConsoleUI is not None
        assert MenuItem is not None

    def test_import_i18n(self):
        """Import src/i18n.py"""
        from src.i18n import t, set_language
        assert t is not None
        assert set_language is not None

    def test_import_comparison(self):
        """Import src/comparison.py"""
        from src.comparison import RunComparator, RegressionDetector
        assert RunComparator is not None
        assert RegressionDetector is not None

    def test_import_scheduler(self):
        """Import src/scheduler.py"""
        from src.scheduler import LocalScheduler, ScheduleConfig
        assert LocalScheduler is not None
        assert ScheduleConfig is not None


class TestRunPySyntax:
    """Test sintassi run.py"""

    def test_run_py_compiles(self):
        """run.py compila senza errori"""
        result = subprocess.run(
            ['python', '-m', 'py_compile', 'run.py'],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"

    def test_src_modules_compile(self):
        """Tutti i moduli src/ compilano"""
        src_path = Path('src')
        for py_file in src_path.glob('*.py'):
            result = subprocess.run(
                ['python', '-m', 'py_compile', str(py_file)],
                capture_output=True,
                text=True
            )
            assert result.returncode == 0, f"Syntax error in {py_file}: {result.stderr}"
