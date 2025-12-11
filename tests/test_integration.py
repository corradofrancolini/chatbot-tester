"""
Integration Tests - Test moduli che lavorano insieme

Testa l'integrazione tra diversi componenti del sistema.
"""
import pytest
from pathlib import Path
import tempfile
import json
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config_loader import ConfigLoader
from src.notifications import NotificationManager, NotificationConfig
from src.export import RunReport, ReportExporter


class TestConfigAndNotifications:
    """Test integrazione ConfigLoader + NotificationManager"""

    def test_load_config_and_create_notification_manager(self):
        """Carica config e crea NotificationManager da YAML"""
        import yaml

        settings_path = Path("config/settings.yaml")
        if not settings_path.exists():
            pytest.skip("settings.yaml non trovato")

        with open(settings_path) as f:
            settings = yaml.safe_load(f)

        # Crea config notifiche da settings.notifications
        notif = settings.get('notifications', {})
        config = NotificationConfig(
            desktop_enabled=notif.get('desktop', {}).get('enabled', False),
            email_enabled=notif.get('email', {}).get('enabled', False),
            teams_enabled=notif.get('teams', {}).get('enabled', False)
        )

        manager = NotificationManager(config)
        assert manager is not None

    def test_notification_triggers_from_config(self):
        """Verifica che i trigger siano letti correttamente"""
        import yaml

        settings_path = Path("config/settings.yaml")
        if not settings_path.exists():
            pytest.skip("settings.yaml non trovato")

        with open(settings_path) as f:
            settings = yaml.safe_load(f)

        triggers = settings.get('notifications', {}).get('triggers', {})

        # Deve essere un dict con trigger
        assert isinstance(triggers, dict)


class TestConfigAndExport:
    """Test integrazione ConfigLoader + Export"""

    def test_load_project_config_for_report(self):
        """Carica config progetto per generare report"""
        loader = ConfigLoader()

        # Prova a caricare un progetto esistente
        projects_dir = Path("config/projects")
        if not projects_dir.exists():
            pytest.skip("Directory progetti non trovata")

        project_files = list(projects_dir.glob("*.yaml"))
        if not project_files:
            pytest.skip("Nessun progetto configurato")

        # Carica il primo progetto disponibile
        project_name = project_files[0].stem
        project_config = loader.load_project(project_name)

        assert project_config is not None
        # ProjectConfig e' un dataclass, verifica attributi
        assert hasattr(project_config, 'name') or hasattr(project_config, 'url')


class TestExportWorkflow:
    """Test workflow completo di export"""

    def test_full_export_workflow(self):
        """Workflow: carica report -> esporta CSV -> esporta HTML"""
        report_dir = Path("reports/my-chatbot")
        if not report_dir.exists():
            pytest.skip("Nessun report disponibile")

        runs = sorted(report_dir.glob("run_*"), reverse=True)
        if not runs:
            pytest.skip("Nessun run disponibile")

        summary_path = runs[0] / "summary.json"
        if not summary_path.exists():
            pytest.skip("summary.json non trovato")

        # Step 1: Carica report
        report = RunReport.from_summary_and_csv(summary_path)
        assert report is not None

        # Step 2: Crea exporter
        exporter = ReportExporter(report)

        with tempfile.TemporaryDirectory() as tmpdir:
            # Step 3: Export CSV
            csv_path = Path(tmpdir) / "report.csv"
            csv_result = exporter.to_csv(csv_path)
            assert csv_result.exists()

            # Step 4: Export HTML
            html_path = Path(tmpdir) / "report.html"
            html_result = exporter.to_html(html_path)
            assert html_result.exists()

            # Verifica che entrambi abbiano contenuto
            assert csv_result.stat().st_size > 0
            assert html_result.stat().st_size > 0


class TestNotificationWorkflow:
    """Test workflow notifiche"""

    def test_notification_dry_run(self):
        """Crea manager e verifica che non crashi"""
        config = NotificationConfig(
            desktop_enabled=True,
            email_enabled=False,
            teams_enabled=False
        )

        manager = NotificationManager(config)

        # Verifica che il manager abbia i metodi corretti
        assert hasattr(manager, 'notify_run_complete') or hasattr(manager, 'send_desktop')


class TestProjectWorkflow:
    """Test workflow caricamento progetto"""

    def test_load_and_validate_project(self):
        """Carica progetto e verifica struttura"""
        loader = ConfigLoader()

        projects_dir = Path("config/projects")
        if not projects_dir.exists():
            pytest.skip("Directory progetti non trovata")

        for project_file in projects_dir.glob("*.yaml"):
            project_name = project_file.stem
            config = loader.load_project(project_name)

            # Ogni progetto deve avere almeno questi campi
            assert config is not None

            # Verifica campi base (almeno uno deve esistere)
            has_name = hasattr(config, 'name')
            has_url = hasattr(config, 'url')

            assert has_name or has_url, f"Progetto {project_name} manca di name o url"


class TestI18nIntegration:
    """Test integrazione i18n"""

    def test_language_switching(self):
        """Verifica cambio lingua"""
        from src.i18n import t, set_language

        # Prova italiano
        set_language('it')
        result_it = t('menu.title')
        assert isinstance(result_it, str)

        # Prova inglese
        set_language('en')
        result_en = t('menu.title')
        assert isinstance(result_en, str)

        # Ripristina italiano (default)
        set_language('it')

    def test_translation_returns_string(self):
        """t() ritorna sempre una stringa"""
        from src.i18n import t

        result = t('menu.title')
        assert isinstance(result, str)

        # Anche per chiavi inesistenti
        result = t('nonexistent.key')
        assert isinstance(result, str)
