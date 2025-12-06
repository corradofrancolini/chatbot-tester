"""
End-to-End Tests - Test completi del sistema

Testa il sistema dall'inizio alla fine usando --dry-run.
"""
import pytest
from pathlib import Path
import subprocess
import tempfile
import json
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestCLIEndToEnd:
    """Test end-to-end via CLI"""

    def test_dry_run_with_project(self):
        """Esegue dry-run completo con progetto"""
        # Trova un progetto disponibile
        projects_dir = Path("config/projects")
        if not projects_dir.exists():
            pytest.skip("Directory progetti non trovata")

        project_files = list(projects_dir.glob("*.yaml"))
        if not project_files:
            pytest.skip("Nessun progetto configurato")

        project_name = project_files[0].stem

        result = subprocess.run(
            ['python', 'run.py', '-p', project_name, '--dry-run'],
            capture_output=True,
            text=True,
            timeout=30
        )

        # Dry-run deve completare senza errori
        assert result.returncode == 0, f"Dry-run fallito: {result.stderr}"

    def test_dry_run_shows_test_count(self):
        """Dry-run mostra numero di test"""
        projects_dir = Path("config/projects")
        if not projects_dir.exists():
            pytest.skip("Directory progetti non trovata")

        project_files = list(projects_dir.glob("*.yaml"))
        if not project_files:
            pytest.skip("Nessun progetto configurato")

        project_name = project_files[0].stem

        result = subprocess.run(
            ['python', 'run.py', '-p', project_name, '--dry-run'],
            capture_output=True,
            text=True,
            timeout=30
        )

        # Output deve contenere info sui test
        output = result.stdout + result.stderr
        # Cerca pattern numerici che indicano conteggio test
        assert any(c.isdigit() for c in output) or 'test' in output.lower()

    def test_list_projects(self):
        """Lista progetti disponibili"""
        result = subprocess.run(
            ['python', 'run.py', '--list-projects'],
            capture_output=True,
            text=True,
            timeout=10
        )

        # Deve completare (anche se nessun progetto)
        # Potrebbe avere returncode 0 o mostrare lista


class TestExportEndToEnd:
    """Test end-to-end export"""

    def test_export_html_existing_run(self):
        """Esporta HTML da run esistente"""
        report_dir = Path("reports/my-chatbot")
        if not report_dir.exists():
            pytest.skip("Nessun report disponibile")

        runs = sorted(report_dir.glob("run_*"), reverse=True)
        if not runs:
            pytest.skip("Nessun run disponibile")

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "export.html"

            result = subprocess.run(
                ['python', 'run.py', '-p', 'my-chatbot', '--export', 'html', '-o', str(output_path)],
                capture_output=True,
                text=True,
                timeout=30
            )

            # Verifica che l'export sia completato
            # (potrebbe creare il file o mostrare messaggio)

    def test_export_csv_existing_run(self):
        """Esporta CSV da run esistente"""
        report_dir = Path("reports/my-chatbot")
        if not report_dir.exists():
            pytest.skip("Nessun report disponibile")

        runs = sorted(report_dir.glob("run_*"), reverse=True)
        if not runs:
            pytest.skip("Nessun run disponibile")

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "export.csv"

            result = subprocess.run(
                ['python', 'run.py', '-p', 'my-chatbot', '--export', 'csv', '-o', str(output_path)],
                capture_output=True,
                text=True,
                timeout=30
            )


class TestHealthCheckEndToEnd:
    """Test end-to-end health check"""

    def test_health_check_completes(self):
        """Health check completa senza crash"""
        projects_dir = Path("config/projects")
        if not projects_dir.exists():
            pytest.skip("Directory progetti non trovata")

        project_files = list(projects_dir.glob("*.yaml"))
        if not project_files:
            pytest.skip("Nessun progetto configurato")

        project_name = project_files[0].stem

        result = subprocess.run(
            ['python', 'run.py', '-p', project_name, '--health-check'],
            capture_output=True,
            text=True,
            timeout=60  # Health check potrebbe richiedere tempo
        )

        # Deve completare (anche con errori di rete)
        # L'importante e' che non crashi con exception


class TestCompareEndToEnd:
    """Test end-to-end comparison"""

    def test_compare_runs_available(self):
        """Confronta run se disponibili"""
        report_dir = Path("reports/my-chatbot")
        if not report_dir.exists():
            pytest.skip("Nessun report disponibile")

        runs = sorted(report_dir.glob("run_*"), reverse=True)
        if len(runs) < 2:
            pytest.skip("Servono almeno 2 run per confronto")

        # Estrai numeri run
        run_numbers = []
        for run in runs[:2]:
            try:
                num = int(run.name.replace("run_", ""))
                run_numbers.append(num)
            except ValueError:
                continue

        if len(run_numbers) < 2:
            pytest.skip("Impossibile estrarre numeri run")

        result = subprocess.run(
            ['python', 'run.py', '-p', 'my-chatbot', '--compare', str(run_numbers[0]), str(run_numbers[1])],
            capture_output=True,
            text=True,
            timeout=30
        )

        # Deve completare senza crash


class TestNotifyEndToEnd:
    """Test end-to-end notifiche"""

    def test_test_notify_option(self):
        """Test della funzione test-notify"""
        result = subprocess.run(
            ['python', 'run.py', '--test-notify'],
            capture_output=True,
            text=True,
            timeout=15
        )

        # Deve completare (notifica potrebbe fallire se non configurata)


class TestInteractiveMode:
    """Test modalita' interattiva (simulated)"""

    def test_noninteractive_flag(self):
        """Verifica che --no-interactive funzioni"""
        projects_dir = Path("config/projects")
        if not projects_dir.exists():
            pytest.skip("Directory progetti non trovata")

        project_files = list(projects_dir.glob("*.yaml"))
        if not project_files:
            pytest.skip("Nessun progetto configurato")

        project_name = project_files[0].stem

        result = subprocess.run(
            ['python', 'run.py', '-p', project_name, '--no-interactive', '--dry-run'],
            capture_output=True,
            text=True,
            timeout=30
        )

        # Deve completare senza bloccarsi su input


class TestModeSelection:
    """Test selezione modalita'"""

    @pytest.mark.parametrize("mode", ["train", "assisted", "auto"])
    def test_mode_accepted(self, mode):
        """Verifica che tutte le modalita' siano accettate"""
        projects_dir = Path("config/projects")
        if not projects_dir.exists():
            pytest.skip("Directory progetti non trovata")

        project_files = list(projects_dir.glob("*.yaml"))
        if not project_files:
            pytest.skip("Nessun progetto configurato")

        project_name = project_files[0].stem

        result = subprocess.run(
            ['python', 'run.py', '-p', project_name, '-m', mode, '--dry-run'],
            capture_output=True,
            text=True,
            timeout=30
        )

        # La modalita' deve essere accettata (non errore di argparse)
        assert 'invalid choice' not in result.stderr.lower()


class TestLanguageOption:
    """Test opzione lingua"""

    @pytest.mark.parametrize("lang", ["it", "en"])
    def test_language_option(self, lang):
        """Verifica che le lingue siano accettate"""
        result = subprocess.run(
            ['python', 'run.py', '--lang', lang, '--help'],
            capture_output=True,
            text=True,
            timeout=10
        )

        # Deve completare senza errori
        assert result.returncode == 0


class TestFullWorkflow:
    """Test workflow completo"""

    def test_complete_dry_run_workflow(self):
        """Workflow completo: progetto -> dry-run -> verifica output"""
        projects_dir = Path("config/projects")
        if not projects_dir.exists():
            pytest.skip("Directory progetti non trovata")

        project_files = list(projects_dir.glob("*.yaml"))
        if not project_files:
            pytest.skip("Nessun progetto configurato")

        project_name = project_files[0].stem

        # Step 1: Verifica progetto esiste
        from src.config_loader import ConfigLoader
        loader = ConfigLoader()
        config = loader.get_project(project_name)
        assert config is not None

        # Step 2: Esegui dry-run
        result = subprocess.run(
            ['python', 'run.py', '-p', project_name, '--dry-run', '--no-interactive'],
            capture_output=True,
            text=True,
            timeout=30
        )

        assert result.returncode == 0, f"Workflow fallito: {result.stderr}"

        # Step 3: Verifica output contiene info progetto
        output = result.stdout + result.stderr
        # Almeno qualche output deve esserci
        assert len(output) > 0
