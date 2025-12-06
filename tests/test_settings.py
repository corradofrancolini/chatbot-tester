"""
Test suite per Menu Settings e config
"""
import pytest
from pathlib import Path
import tempfile
import yaml

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestSettingsYaml:
    """Test per config/settings.yaml"""

    def test_settings_file_exists(self):
        """Verifica che settings.yaml esista"""
        settings_path = Path("config/settings.yaml")
        assert settings_path.exists(), "config/settings.yaml non trovato"

    def test_settings_valid_yaml(self):
        """Verifica che sia YAML valido"""
        settings_path = Path("config/settings.yaml")
        with open(settings_path) as f:
            data = yaml.safe_load(f)

        assert data is not None
        assert isinstance(data, dict)

    def test_settings_structure(self):
        """Verifica struttura settings"""
        settings_path = Path("config/settings.yaml")
        with open(settings_path) as f:
            data = yaml.safe_load(f)

        # Sezioni obbligatorie
        assert 'app' in data
        assert 'browser' in data
        assert 'notifications' in data
        assert 'logging' in data

    def test_app_section(self):
        """Verifica sezione app"""
        settings_path = Path("config/settings.yaml")
        with open(settings_path) as f:
            data = yaml.safe_load(f)

        app = data['app']
        assert 'language' in app
        assert app['language'] in ['it', 'en']

    def test_browser_section(self):
        """Verifica sezione browser"""
        settings_path = Path("config/settings.yaml")
        with open(settings_path) as f:
            data = yaml.safe_load(f)

        browser = data['browser']
        assert 'headless' in browser
        assert 'viewport' in browser
        assert 'width' in browser['viewport']
        assert 'height' in browser['viewport']

    def test_notifications_section(self):
        """Verifica sezione notifications"""
        settings_path = Path("config/settings.yaml")
        with open(settings_path) as f:
            data = yaml.safe_load(f)

        notifications = data['notifications']
        assert 'desktop' in notifications
        assert 'email' in notifications
        assert 'teams' in notifications
        assert 'triggers' in notifications

    def test_notifications_desktop(self):
        """Verifica desktop notifications"""
        settings_path = Path("config/settings.yaml")
        with open(settings_path) as f:
            data = yaml.safe_load(f)

        desktop = data['notifications']['desktop']
        assert 'enabled' in desktop
        assert 'sound' in desktop

    def test_notifications_email(self):
        """Verifica email notifications"""
        settings_path = Path("config/settings.yaml")
        with open(settings_path) as f:
            data = yaml.safe_load(f)

        email = data['notifications']['email']
        assert 'enabled' in email
        assert 'smtp_host' in email
        assert 'smtp_port' in email

    def test_notifications_teams(self):
        """Verifica Teams notifications"""
        settings_path = Path("config/settings.yaml")
        with open(settings_path) as f:
            data = yaml.safe_load(f)

        teams = data['notifications']['teams']
        assert 'enabled' in teams
        assert 'webhook_url_env' in teams

    def test_notifications_triggers(self):
        """Verifica triggers"""
        settings_path = Path("config/settings.yaml")
        with open(settings_path) as f:
            data = yaml.safe_load(f)

        triggers = data['notifications']['triggers']
        assert 'on_complete' in triggers
        assert 'on_failure' in triggers
        assert 'on_regression' in triggers
        assert 'on_flaky' in triggers


class TestUpdateSettingsYaml:
    """Test per funzione _update_settings_yaml"""

    def test_update_simple_value(self):
        """Test aggiornamento valore semplice"""
        with tempfile.NamedTemporaryFile(suffix='.yaml', delete=False, mode='w') as f:
            yaml.dump({'app': {'language': 'it'}}, f)
            temp_path = Path(f.name)

        try:
            # Importa funzione
            from run import _update_settings_yaml

            # Aggiorna
            _update_settings_yaml(temp_path, ['app', 'language'], 'en')

            # Verifica
            with open(temp_path) as f:
                data = yaml.safe_load(f)
            assert data['app']['language'] == 'en'
        finally:
            temp_path.unlink(missing_ok=True)

    def test_update_nested_value(self):
        """Test aggiornamento valore nested"""
        with tempfile.NamedTemporaryFile(suffix='.yaml', delete=False, mode='w') as f:
            yaml.dump({
                'notifications': {
                    'desktop': {'enabled': True, 'sound': True}
                }
            }, f)
            temp_path = Path(f.name)

        try:
            from run import _update_settings_yaml

            _update_settings_yaml(temp_path, ['notifications', 'desktop', 'enabled'], False)

            with open(temp_path) as f:
                data = yaml.safe_load(f)
            assert data['notifications']['desktop']['enabled'] == False
            assert data['notifications']['desktop']['sound'] == True  # Non modificato
        finally:
            temp_path.unlink(missing_ok=True)

    def test_update_boolean(self):
        """Test aggiornamento boolean"""
        with tempfile.NamedTemporaryFile(suffix='.yaml', delete=False, mode='w') as f:
            yaml.dump({'browser': {'headless': False}}, f)
            temp_path = Path(f.name)

        try:
            from run import _update_settings_yaml

            _update_settings_yaml(temp_path, ['browser', 'headless'], True)

            with open(temp_path) as f:
                data = yaml.safe_load(f)
            assert data['browser']['headless'] == True
        finally:
            temp_path.unlink(missing_ok=True)

    def test_update_integer(self):
        """Test aggiornamento intero"""
        with tempfile.NamedTemporaryFile(suffix='.yaml', delete=False, mode='w') as f:
            yaml.dump({'browser': {'viewport': {'width': 1280}}}, f)
            temp_path = Path(f.name)

        try:
            from run import _update_settings_yaml

            _update_settings_yaml(temp_path, ['browser', 'viewport', 'width'], 1920)

            with open(temp_path) as f:
                data = yaml.safe_load(f)
            assert data['browser']['viewport']['width'] == 1920
        finally:
            temp_path.unlink(missing_ok=True)

    def test_update_list(self):
        """Test aggiornamento lista"""
        with tempfile.NamedTemporaryFile(suffix='.yaml', delete=False, mode='w') as f:
            yaml.dump({
                'notifications': {
                    'email': {'recipients': []}
                }
            }, f)
            temp_path = Path(f.name)

        try:
            from run import _update_settings_yaml

            new_recipients = ['test@example.com', 'team@example.com']
            _update_settings_yaml(temp_path, ['notifications', 'email', 'recipients'], new_recipients)

            with open(temp_path) as f:
                data = yaml.safe_load(f)
            assert data['notifications']['email']['recipients'] == new_recipients
        finally:
            temp_path.unlink(missing_ok=True)
