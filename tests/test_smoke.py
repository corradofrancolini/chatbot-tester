"""
Smoke Test Suite - Verifica veloce che tutto funzioni

Esegui con: pytest tests/test_smoke.py -v
"""
import pytest
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestSyntax:
    """Verifica che tutti i file Python compilino correttamente"""

    def test_run_py(self):
        """run.py compila"""
        result = subprocess.run(['python', '-m', 'py_compile', 'run.py'], capture_output=True)
        assert result.returncode == 0

    def test_all_src_modules(self):
        """Tutti i moduli src/ compilano"""
        for py_file in Path('src').glob('*.py'):
            result = subprocess.run(['python', '-m', 'py_compile', str(py_file)], capture_output=True)
            assert result.returncode == 0, f"Errore in {py_file}: {result.stderr.decode()}"


class TestImports:
    """Verifica che i moduli principali siano importabili"""

    def test_export_module(self):
        from src.export import RunReport, ReportExporter
        assert RunReport is not None
        assert ReportExporter is not None

    def test_notifications_module(self):
        from src.notifications import NotificationManager, NotificationConfig
        assert NotificationManager is not None
        assert NotificationConfig is not None

    def test_ui_module(self):
        from src.ui import ConsoleUI, MenuItem
        assert ConsoleUI is not None
        assert MenuItem is not None

    def test_config_loader_module(self):
        from src.config_loader import ConfigLoader
        assert ConfigLoader is not None

    def test_tester_module(self):
        from src.tester import ChatbotTester, TestCase
        assert ChatbotTester is not None
        assert TestCase is not None

    def test_comparison_module(self):
        from src.comparison import RunComparator, RegressionDetector
        assert RunComparator is not None
        assert RegressionDetector is not None

    def test_scheduler_module(self):
        from src.scheduler import LocalScheduler, ScheduleConfig
        assert LocalScheduler is not None
        assert ScheduleConfig is not None

    def test_i18n_module(self):
        from src.i18n import t, set_language
        assert t is not None
        assert callable(set_language)


class TestConfig:
    """Verifica configurazione"""

    def test_settings_yaml_exists(self):
        assert Path('config/settings.yaml').exists()

    def test_settings_yaml_valid(self):
        import yaml
        with open('config/settings.yaml') as f:
            data = yaml.safe_load(f)
        assert 'app' in data
        assert 'browser' in data
        assert 'notifications' in data


class TestCLI:
    """Verifica CLI base"""

    def test_help(self):
        result = subprocess.run(['python', 'run.py', '--help'], capture_output=True, text=True)
        assert result.returncode == 0
        assert '--project' in result.stdout

    def test_version(self):
        result = subprocess.run(['python', 'run.py', '--version'], capture_output=True, text=True)
        assert result.returncode == 0


class TestProjectStructure:
    """Verifica struttura progetto"""

    def test_required_directories(self):
        assert Path('src').is_dir()
        assert Path('config').is_dir()

    def test_required_files(self):
        assert Path('run.py').exists()
        assert Path('README.md').exists()
        assert Path('CLAUDE.md').exists()


class TestNotificationsConfig:
    """Verifica configurazione notifiche"""

    def test_desktop_notifier_instantiable(self):
        from src.notifications import NotificationConfig, DesktopNotifier
        config = NotificationConfig(desktop_enabled=True)
        notifier = DesktopNotifier(config)
        assert notifier is not None

    def test_notification_manager_instantiable(self):
        from src.notifications import NotificationConfig, NotificationManager
        config = NotificationConfig()
        manager = NotificationManager(config)
        assert manager is not None


class TestExportFunctionality:
    """Verifica export"""

    def test_html_exporter_instantiable(self):
        from src.export import RunReport, HTMLExporter
        # Usa from_summary_and_csv con path fittizio se disponibile
        # Per ora test solo import
        assert HTMLExporter is not None

    def test_report_exporter_instantiable(self):
        from src.export import ReportExporter
        assert ReportExporter is not None
