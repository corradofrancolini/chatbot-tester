"""
Notifications Module - Sistema di Notifiche

Supporta:
- Email (SMTP)
- Desktop (macOS native)
- Microsoft Teams (webhook)

Configurabile via settings.yaml
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from enum import Enum
from pathlib import Path
import json
import os
import subprocess
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import urllib.request
import urllib.error


class NotificationType(Enum):
    """Tipi di notifica"""
    RUN_COMPLETE = "run_complete"
    REGRESSION = "regression"
    FLAKY_TESTS = "flaky_tests"
    ERROR = "error"


class NotificationPriority(Enum):
    """Priorita notifica"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class NotificationConfig:
    """Configurazione notifiche"""
    # Email
    email_enabled: bool = False
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password_env: str = "SMTP_PASSWORD"  # Nome variabile ambiente
    email_from: str = ""
    email_recipients: List[str] = field(default_factory=list)

    # Desktop (macOS)
    desktop_enabled: bool = True
    desktop_sound: bool = True

    # Teams
    teams_enabled: bool = False
    teams_webhook_url_env: str = "TEAMS_WEBHOOK_URL"

    # Triggers
    on_complete: bool = True
    on_failure: bool = True
    on_regression: bool = True
    on_flaky: bool = False

    @classmethod
    def from_dict(cls, data: Dict) -> 'NotificationConfig':
        return cls(
            email_enabled=data.get('email', {}).get('enabled', False),
            smtp_host=data.get('email', {}).get('smtp_host', 'smtp.gmail.com'),
            smtp_port=data.get('email', {}).get('smtp_port', 587),
            smtp_user=data.get('email', {}).get('smtp_user', ''),
            smtp_password_env=data.get('email', {}).get('smtp_password_env', 'SMTP_PASSWORD'),
            email_from=data.get('email', {}).get('from', ''),
            email_recipients=data.get('email', {}).get('recipients', []),
            desktop_enabled=data.get('desktop', {}).get('enabled', True),
            desktop_sound=data.get('desktop', {}).get('sound', True),
            teams_enabled=data.get('teams', {}).get('enabled', False),
            teams_webhook_url_env=data.get('teams', {}).get('webhook_url_env', 'TEAMS_WEBHOOK_URL'),
            on_complete=data.get('triggers', {}).get('on_complete', True),
            on_failure=data.get('triggers', {}).get('on_failure', True),
            on_regression=data.get('triggers', {}).get('on_regression', True),
            on_flaky=data.get('triggers', {}).get('on_flaky', False),
        )


@dataclass
class TestRunSummary:
    """Riepilogo di un test run per notifiche"""
    project: str
    run_number: int
    total_tests: int
    passed: int
    failed: int
    skipped: int = 0
    regressions: int = 0
    flaky_tests: int = 0
    duration_seconds: float = 0
    error_message: Optional[str] = None

    @property
    def pass_rate(self) -> float:
        if self.total_tests == 0:
            return 0.0
        return (self.passed / self.total_tests) * 100

    @property
    def status(self) -> str:
        if self.error_message:
            return "ERROR"
        if self.failed > 0:
            return "FAILED"
        return "PASSED"

    @property
    def status_emoji(self) -> str:
        if self.error_message:
            return "X"
        if self.failed > 0:
            return "!"
        return "OK"


class EmailNotifier:
    """Notifiche via Email SMTP"""

    def __init__(self, config: NotificationConfig):
        self.config = config

    def send(self,
             subject: str,
             body: str,
             html_body: Optional[str] = None,
             attachments: List[Path] = None) -> bool:
        """Invia email"""
        if not self.config.email_enabled:
            return False

        if not self.config.email_recipients:
            print("! Email: nessun destinatario configurato")
            return False

        password = os.environ.get(self.config.smtp_password_env, '')
        if not password:
            print(f"! Email: variabile {self.config.smtp_password_env} non configurata")
            return False

        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.config.email_from or self.config.smtp_user
            msg['To'] = ', '.join(self.config.email_recipients)

            # Corpo testo
            msg.attach(MIMEText(body, 'plain'))

            # Corpo HTML (opzionale)
            if html_body:
                msg.attach(MIMEText(html_body, 'html'))

            # Allegati
            if attachments:
                for file_path in attachments:
                    if file_path.exists():
                        with open(file_path, 'rb') as f:
                            part = MIMEBase('application', 'octet-stream')
                            part.set_payload(f.read())
                            encoders.encode_base64(part)
                            part.add_header(
                                'Content-Disposition',
                                f'attachment; filename={file_path.name}'
                            )
                            msg.attach(part)

            # Invio
            with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port) as server:
                server.starttls()
                server.login(self.config.smtp_user, password)
                server.sendmail(
                    self.config.email_from or self.config.smtp_user,
                    self.config.email_recipients,
                    msg.as_string()
                )

            print(f"+ Email inviata a {len(self.config.email_recipients)} destinatari")
            return True

        except Exception as e:
            print(f"! Email error: {e}")
            return False

    def send_run_summary(self, summary: TestRunSummary) -> bool:
        """Invia riepilogo run"""
        subject = f"[{summary.status}] Chatbot Test - {summary.project} RUN {summary.run_number}"

        body = f"""
Chatbot Tester - Riepilogo Run

Progetto: {summary.project}
Run: #{summary.run_number}
Stato: {summary.status}

Risultati:
- Totale test: {summary.total_tests}
- Passati: {summary.passed}
- Falliti: {summary.failed}
- Pass rate: {summary.pass_rate:.1f}%

{"Regressioni: " + str(summary.regressions) if summary.regressions > 0 else ""}
{"Errore: " + summary.error_message if summary.error_message else ""}
        """.strip()

        html_body = f"""
<html>
<body style="font-family: Arial, sans-serif; padding: 20px;">
    <h2 style="color: {'#dc3545' if summary.status == 'FAILED' else '#28a745'};">
        {summary.status_emoji} {summary.project} - RUN {summary.run_number}
    </h2>

    <table style="border-collapse: collapse; width: 100%; max-width: 400px;">
        <tr>
            <td style="padding: 8px; border-bottom: 1px solid #ddd;"><strong>Totale test</strong></td>
            <td style="padding: 8px; border-bottom: 1px solid #ddd;">{summary.total_tests}</td>
        </tr>
        <tr style="background-color: #d4edda;">
            <td style="padding: 8px; border-bottom: 1px solid #ddd;"><strong>Passati</strong></td>
            <td style="padding: 8px; border-bottom: 1px solid #ddd;">{summary.passed}</td>
        </tr>
        <tr style="background-color: {'#f8d7da' if summary.failed > 0 else '#fff'};">
            <td style="padding: 8px; border-bottom: 1px solid #ddd;"><strong>Falliti</strong></td>
            <td style="padding: 8px; border-bottom: 1px solid #ddd;">{summary.failed}</td>
        </tr>
        <tr>
            <td style="padding: 8px; border-bottom: 1px solid #ddd;"><strong>Pass rate</strong></td>
            <td style="padding: 8px; border-bottom: 1px solid #ddd;">{summary.pass_rate:.1f}%</td>
        </tr>
    </table>

    {f'<p style="color: #dc3545;"><strong>Regressioni:</strong> {summary.regressions}</p>' if summary.regressions > 0 else ''}
    {f'<p style="color: #dc3545;"><strong>Errore:</strong> {summary.error_message}</p>' if summary.error_message else ''}

    <p style="color: #6c757d; font-size: 12px; margin-top: 20px;">
        Generato da Chatbot Tester
    </p>
</body>
</html>
        """

        return self.send(subject, body, html_body)


class DesktopNotifier:
    """Notifiche Desktop native (macOS)"""

    def __init__(self, config: NotificationConfig):
        self.config = config

    def send(self,
             title: str,
             message: str,
             subtitle: Optional[str] = None,
             sound: bool = None) -> bool:
        """Invia notifica desktop macOS"""
        if not self.config.desktop_enabled:
            return False

        # Usa osascript per notifiche native macOS
        script_parts = [
            f'display notification "{self._escape(message)}"',
            f'with title "{self._escape(title)}"'
        ]

        if subtitle:
            script_parts.append(f'subtitle "{self._escape(subtitle)}"')

        if sound if sound is not None else self.config.desktop_sound:
            script_parts.append('sound name "default"')

        script = ' '.join(script_parts)

        try:
            subprocess.run(
                ['osascript', '-e', script],
                check=True,
                capture_output=True
            )
            return True
        except subprocess.CalledProcessError as e:
            print(f"! Desktop notification error: {e}")
            return False
        except FileNotFoundError:
            # Non siamo su macOS
            print("! Desktop notifications disponibili solo su macOS")
            return False

    def _escape(self, text: str) -> str:
        """Escape per AppleScript"""
        return text.replace('"', '\\"').replace('\n', ' ')

    def send_run_summary(self, summary: TestRunSummary) -> bool:
        """Invia riepilogo run come notifica desktop"""
        title = f"{summary.status_emoji} {summary.project}"
        subtitle = f"RUN {summary.run_number} - {summary.status}"
        message = f"{summary.passed}/{summary.total_tests} test passati ({summary.pass_rate:.0f}%)"

        if summary.regressions > 0:
            message += f" - {summary.regressions} regressioni!"

        return self.send(title, message, subtitle)


class TeamsNotifier:
    """Notifiche Microsoft Teams via Webhook"""

    def __init__(self, config: NotificationConfig):
        self.config = config

    def send(self,
             title: str,
             message: str,
             color: str = "0078D7",
             facts: List[Dict[str, str]] = None) -> bool:
        """Invia messaggio a Teams via webhook"""
        if not self.config.teams_enabled:
            return False

        webhook_url = os.environ.get(self.config.teams_webhook_url_env, '')
        if not webhook_url:
            print(f"! Teams: variabile {self.config.teams_webhook_url_env} non configurata")
            return False

        # Formato Adaptive Card per Teams
        payload = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "themeColor": color,
            "summary": title,
            "sections": [{
                "activityTitle": title,
                "text": message,
                "facts": facts or [],
                "markdown": True
            }]
        }

        try:
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(
                webhook_url,
                data=data,
                headers={'Content-Type': 'application/json'}
            )

            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status == 200:
                    print("+ Teams notification inviata")
                    return True
                else:
                    print(f"! Teams error: HTTP {response.status}")
                    return False

        except urllib.error.URLError as e:
            print(f"! Teams error: {e}")
            return False
        except Exception as e:
            print(f"! Teams error: {e}")
            return False

    def send_run_summary(self, summary: TestRunSummary) -> bool:
        """Invia riepilogo run a Teams"""
        # Colore basato su stato
        if summary.status == "PASSED":
            color = "28a745"  # Verde
        elif summary.status == "FAILED":
            color = "dc3545"  # Rosso
        else:
            color = "ffc107"  # Giallo

        title = f"{summary.status_emoji} Chatbot Test - {summary.project} RUN {summary.run_number}"

        message = f"**Stato:** {summary.status}"
        if summary.error_message:
            message += f"\n\n**Errore:** {summary.error_message}"

        facts = [
            {"name": "Totale test", "value": str(summary.total_tests)},
            {"name": "Passati", "value": str(summary.passed)},
            {"name": "Falliti", "value": str(summary.failed)},
            {"name": "Pass rate", "value": f"{summary.pass_rate:.1f}%"},
        ]

        if summary.regressions > 0:
            facts.append({"name": "Regressioni", "value": str(summary.regressions)})

        if summary.flaky_tests > 0:
            facts.append({"name": "Test flaky", "value": str(summary.flaky_tests)})

        return self.send(title, message, color, facts)


class NotificationManager:
    """
    Gestore centralizzato notifiche.

    Usage:
        config = NotificationConfig.from_dict(settings['notifications'])
        notifier = NotificationManager(config)

        # Invia a tutti i canali configurati
        notifier.notify_run_complete(summary)

        # Oppure canale specifico
        notifier.send_desktop("Titolo", "Messaggio")
    """

    def __init__(self, config: NotificationConfig):
        self.config = config
        self.email = EmailNotifier(config)
        self.desktop = DesktopNotifier(config)
        self.teams = TeamsNotifier(config)

    def notify_run_complete(self, summary: TestRunSummary) -> Dict[str, bool]:
        """Notifica completamento run su tutti i canali"""
        results = {}

        # Determina se notificare
        should_notify = self.config.on_complete
        if summary.status == "FAILED" and self.config.on_failure:
            should_notify = True
        if summary.regressions > 0 and self.config.on_regression:
            should_notify = True

        if not should_notify:
            return results

        # Invia su tutti i canali abilitati
        if self.config.email_enabled:
            results['email'] = self.email.send_run_summary(summary)

        if self.config.desktop_enabled:
            results['desktop'] = self.desktop.send_run_summary(summary)

        if self.config.teams_enabled:
            results['teams'] = self.teams.send_run_summary(summary)

        return results

    def notify_regression(self,
                          project: str,
                          run_number: int,
                          regressions: List[str]) -> Dict[str, bool]:
        """Notifica regressioni rilevate"""
        if not self.config.on_regression:
            return {}

        results = {}
        title = f"! Regressioni in {project} RUN {run_number}"
        message = f"Rilevate {len(regressions)} regressioni:\n" + "\n".join(f"- {r}" for r in regressions[:10])

        if len(regressions) > 10:
            message += f"\n... e altre {len(regressions) - 10}"

        if self.config.desktop_enabled:
            results['desktop'] = self.desktop.send(title, message[:200])

        if self.config.teams_enabled:
            results['teams'] = self.teams.send(
                title,
                message,
                color="dc3545",
                facts=[{"name": "Test regrediti", "value": str(len(regressions))}]
            )

        if self.config.email_enabled:
            results['email'] = self.email.send(
                f"[REGRESSION] {project} RUN {run_number}",
                message
            )

        return results

    def notify_error(self,
                     project: str,
                     error: str) -> Dict[str, bool]:
        """Notifica errore critico"""
        results = {}
        title = f"X Errore in {project}"

        if self.config.desktop_enabled:
            results['desktop'] = self.desktop.send(title, error[:200], sound=True)

        if self.config.teams_enabled:
            results['teams'] = self.teams.send(title, error, color="dc3545")

        if self.config.email_enabled:
            results['email'] = self.email.send(f"[ERROR] {project}", error)

        return results

    # Metodi di convenienza per canali singoli
    def send_desktop(self, title: str, message: str, subtitle: str = None) -> bool:
        """Invia solo notifica desktop"""
        return self.desktop.send(title, message, subtitle)

    def send_email(self, subject: str, body: str, html: str = None) -> bool:
        """Invia solo email"""
        return self.email.send(subject, body, html)

    def send_teams(self, title: str, message: str) -> bool:
        """Invia solo a Teams"""
        return self.teams.send(title, message)


def test_notifications():
    """Test rapido delle notifiche"""
    config = NotificationConfig(
        desktop_enabled=True,
        desktop_sound=True
    )

    manager = NotificationManager(config)

    # Test desktop
    print("Testing desktop notification...")
    manager.send_desktop(
        "Chatbot Tester",
        "Test notification",
        "This is a test"
    )

    # Test summary
    summary = TestRunSummary(
        project="test-project",
        run_number=1,
        total_tests=10,
        passed=8,
        failed=2
    )

    print(f"Summary: {summary.status} - {summary.pass_rate:.1f}%")


if __name__ == "__main__":
    test_notifications()
