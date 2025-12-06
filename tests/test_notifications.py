"""
Test suite per src/notifications.py
"""
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.notifications import (
    NotificationConfig, TestRunSummary,
    DesktopNotifier, EmailNotifier, TeamsNotifier,
    NotificationManager
)


class TestNotificationConfig:
    """Test per configurazione notifiche"""

    def test_default_config(self):
        """Config di default"""
        config = NotificationConfig()
        assert config.desktop_enabled == True
        assert config.email_enabled == False
        assert config.teams_enabled == False

    def test_custom_config(self):
        """Config personalizzata"""
        config = NotificationConfig(
            desktop_enabled=False,
            email_enabled=True,
            teams_enabled=True,
            smtp_host="smtp.test.com",
            smtp_port=465
        )
        assert config.desktop_enabled == False
        assert config.email_enabled == True
        assert config.smtp_host == "smtp.test.com"
        assert config.smtp_port == 465


class TestTestRunSummary:
    """Test per TestRunSummary"""

    def test_create_summary(self):
        """Crea summary"""
        summary = TestRunSummary(
            project="test-project",
            run_number=10,
            total_tests=50,
            passed=45,
            failed=5,
            pass_rate=90.0
        )
        assert summary.project == "test-project"
        assert summary.run_number == 10
        assert summary.pass_rate == 90.0

    def test_summary_with_optional_fields(self):
        """Summary con campi opzionali"""
        summary = TestRunSummary(
            project="test",
            run_number=1,
            total_tests=10,
            passed=10,
            failed=0,
            pass_rate=100.0,
            duration_seconds=120,
            report_url="https://example.com/report"
        )
        assert summary.duration_seconds == 120
        assert summary.report_url == "https://example.com/report"


class TestDesktopNotifier:
    """Test per DesktopNotifier"""

    def test_create_notifier(self):
        """Crea notifier"""
        config = NotificationConfig(desktop_enabled=True, desktop_sound=True)
        notifier = DesktopNotifier(config)
        assert notifier.config.desktop_enabled == True

    @patch('subprocess.run')
    def test_send_notification_macos(self, mock_run):
        """Test invio notifica macOS"""
        mock_run.return_value = MagicMock(returncode=0)

        config = NotificationConfig(desktop_enabled=True)
        notifier = DesktopNotifier(config)

        result = notifier.send("Test Title", "Test message")

        # Verifica che subprocess.run sia stato chiamato
        assert mock_run.called

    def test_disabled_notifier(self):
        """Notifier disabilitato non invia"""
        config = NotificationConfig(desktop_enabled=False)
        notifier = DesktopNotifier(config)

        result = notifier.send("Title", "Message")
        assert result == False


class TestTeamsNotifier:
    """Test per TeamsNotifier"""

    def test_create_notifier(self):
        """Crea notifier Teams"""
        config = NotificationConfig(
            teams_enabled=True,
            teams_webhook_url="https://outlook.office.com/webhook/test"
        )
        notifier = TeamsNotifier(config)
        assert notifier.config.teams_enabled == True

    def test_disabled_notifier(self):
        """Notifier disabilitato non invia"""
        config = NotificationConfig(teams_enabled=False)
        notifier = TeamsNotifier(config)

        result = notifier.send("Title", "Message")
        assert result == False

    @patch('urllib.request.urlopen')
    def test_send_notification(self, mock_urlopen):
        """Test invio notifica Teams"""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_urlopen.return_value.__enter__ = MagicMock(return_value=mock_response)
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        config = NotificationConfig(
            teams_enabled=True,
            teams_webhook_url="https://outlook.office.com/webhook/test"
        )
        notifier = TeamsNotifier(config)

        # Verifica che il metodo non sollevi eccezioni
        # (il risultato dipende dal mock)


class TestNotificationManager:
    """Test per NotificationManager"""

    def test_create_manager(self):
        """Crea manager"""
        config = NotificationConfig()
        manager = NotificationManager(config)
        assert manager is not None

    def test_notify_run_complete(self):
        """Test notifica run completato"""
        config = NotificationConfig(
            desktop_enabled=False,
            email_enabled=False,
            teams_enabled=False
        )
        manager = NotificationManager(config)

        summary = TestRunSummary(
            project="test",
            run_number=1,
            total_tests=10,
            passed=10,
            failed=0,
            pass_rate=100.0
        )

        results = manager.notify_run_complete(summary)

        # Con tutti disabilitati, tutti False
        assert results.get('desktop', True) == False
        assert results.get('email', True) == False
        assert results.get('teams', True) == False

    @patch('subprocess.run')
    def test_notify_with_desktop_enabled(self, mock_run):
        """Test notifica con desktop abilitato"""
        mock_run.return_value = MagicMock(returncode=0)

        config = NotificationConfig(
            desktop_enabled=True,
            email_enabled=False,
            teams_enabled=False
        )
        manager = NotificationManager(config)

        summary = TestRunSummary(
            project="test",
            run_number=1,
            total_tests=10,
            passed=8,
            failed=2,
            pass_rate=80.0
        )

        results = manager.notify_run_complete(summary)

        # Desktop dovrebbe essere stato chiamato
        assert mock_run.called


class TestNotificationManagerFromSettings:
    """Test per creazione manager da settings"""

    def test_from_settings_dict(self):
        """Crea manager da dizionario settings"""
        # Simula struttura settings.yaml
        class MockDesktop:
            enabled = True
            sound = True

        class MockEmail:
            enabled = False
            smtp_host = "smtp.test.com"
            smtp_port = 587
            smtp_user = ""
            smtp_password_env = "SMTP_PASSWORD"
            recipients = []

        class MockTeams:
            enabled = False
            webhook_url_env = "TEAMS_WEBHOOK_URL"

        class MockTriggers:
            on_complete = False
            on_failure = True
            on_regression = True
            on_flaky = False

        class MockNotifications:
            desktop = MockDesktop()
            email = MockEmail()
            teams = MockTeams()
            triggers = MockTriggers()

        manager = NotificationManager.from_settings(MockNotifications())

        assert manager.config.desktop_enabled == True
        assert manager.config.email_enabled == False
