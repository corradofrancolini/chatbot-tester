"""
CLI Utilities - clig.dev compliant helpers

Funzionalita:
- Exit codes significativi
- Suggerimenti "did you mean"
- Next steps dopo operazioni
- Conferma azioni distruttive
- Feedback immediato
"""

import sys
import difflib
from enum import IntEnum
from typing import List, Optional, Callable
from pathlib import Path


# ═══════════════════════════════════════════════════════════════════════════════
# EXIT CODES (clig.dev compliant)
# ═══════════════════════════════════════════════════════════════════════════════

class ExitCode(IntEnum):
    """
    Exit codes standardizzati.

    0 = success
    1 = general error
    2 = misuse (bad args)
    64-78 = BSD sysexits.h
    """
    SUCCESS = 0
    ERROR = 1
    MISUSE = 2          # Bad command line args

    # Errori specifici (64-78 da sysexits.h)
    USAGE_ERROR = 64    # Command line usage error
    DATA_ERROR = 65     # Data format error
    NO_INPUT = 66       # Cannot open input
    NO_USER = 67        # Addressee unknown
    NO_HOST = 68        # Host name unknown
    UNAVAILABLE = 69    # Service unavailable
    SOFTWARE = 70       # Internal software error
    OS_ERROR = 71       # System error
    OS_FILE = 72        # Critical OS file missing
    CANT_CREATE = 73    # Cannot create output file
    IO_ERROR = 74       # Input/output error
    TEMP_FAIL = 75      # Temporary failure
    PROTOCOL = 76       # Remote protocol error
    NO_PERM = 77        # Permission denied
    CONFIG = 78         # Configuration error

    # Custom (100+)
    PROJECT_NOT_FOUND = 100
    TEST_FAILED = 101
    HEALTH_CHECK_FAILED = 102
    BROWSER_ERROR = 103
    NETWORK_ERROR = 104
    CANCELLED = 130     # Ctrl+C (128 + SIGINT)


def exit_with_code(code: ExitCode, message: str = None) -> None:
    """Esce con codice e messaggio opzionale."""
    if message:
        stream = sys.stderr if code != ExitCode.SUCCESS else sys.stdout
        print(message, file=stream)
    sys.exit(code)


# ═══════════════════════════════════════════════════════════════════════════════
# DID YOU MEAN (suggerimenti errori)
# ═══════════════════════════════════════════════════════════════════════════════

def suggest_similar(input_value: str, valid_options: List[str],
                    cutoff: float = 0.6) -> Optional[str]:
    """
    Trova opzione simile a input errato.

    Args:
        input_value: Valore inserito dall'utente
        valid_options: Lista opzioni valide
        cutoff: Soglia similarita (0-1, default 0.6)

    Returns:
        Opzione piu simile o None
    """
    matches = difflib.get_close_matches(
        input_value.lower(),
        [o.lower() for o in valid_options],
        n=1,
        cutoff=cutoff
    )

    if matches:
        # Ritorna l'opzione originale (con case corretto)
        for opt in valid_options:
            if opt.lower() == matches[0]:
                return opt
    return None


def format_did_you_mean(input_value: str, suggestion: str) -> str:
    """Formatta messaggio 'did you mean'."""
    return f"'{input_value}' non riconosciuto. Intendevi '{suggestion}'?"


def suggest_project(input_name: str, projects_dir: Path) -> Optional[str]:
    """Suggerisce progetto simile se nome non trovato."""
    if not projects_dir.exists():
        return None

    # Progetti sono directory con project.yaml dentro
    valid_projects = [
        p.name for p in projects_dir.iterdir()
        if p.is_dir() and (p / "project.yaml").exists()
    ]
    return suggest_similar(input_name, valid_projects)


def suggest_command(input_cmd: str) -> Optional[str]:
    """Suggerisce comando simile se non riconosciuto."""
    valid_commands = [
        'train', 'assisted', 'auto',
        'compare', 'export', 'notify',
        'health-check', 'scheduler',
        'new-project', 'new-run'
    ]
    return suggest_similar(input_cmd, valid_commands)


# ═══════════════════════════════════════════════════════════════════════════════
# NEXT STEPS (suggerimenti post-operazione)
# ═══════════════════════════════════════════════════════════════════════════════

class NextSteps:
    """Genera suggerimenti per prossimi passi."""

    @staticmethod
    def after_test_run(project: str, run_number: int,
                       passed: int, failed: int) -> List[str]:
        """Suggerimenti dopo esecuzione test."""
        steps = []

        if failed > 0:
            steps.append(f"Vedi dettagli: chatbot-tester -p {project} --compare")
            steps.append(f"Riesegui falliti: chatbot-tester -p {project} --tests failed")

        steps.append(f"Esporta report: chatbot-tester -p {project} --export html")

        if passed > 0 and failed == 0:
            steps.append(f"Confronta con run precedente: chatbot-tester -p {project} --compare")

        return steps

    @staticmethod
    def after_export(output_path: Path) -> List[str]:
        """Suggerimenti dopo export."""
        steps = [f"Apri file: open {output_path}"]

        if output_path.suffix == '.html':
            steps.append(f"Visualizza in browser: open {output_path}")

        return steps

    @staticmethod
    def after_new_project(project_name: str) -> List[str]:
        """Suggerimenti dopo creazione progetto."""
        return [
            f"Configura test: config/projects/{project_name}/tests.yaml",
            f"Esegui health check: chatbot-tester -p {project_name} --health-check",
            f"Avvia in train mode: chatbot-tester -p {project_name} -m train"
        ]

    @staticmethod
    def after_compare(has_regressions: bool, project: str) -> List[str]:
        """Suggerimenti dopo confronto."""
        steps = []

        if has_regressions:
            steps.append(f"Riesegui test falliti: chatbot-tester -p {project} --tests failed")
            steps.append(f"Analizza flaky: chatbot-tester -p {project} --flaky")
        else:
            steps.append(f"Esporta report: chatbot-tester -p {project} --export html")

        return steps

    @staticmethod
    def format(steps: List[str], title: str = "Prossimi passi") -> str:
        """Formatta lista suggerimenti."""
        if not steps:
            return ""

        lines = [f"\n{title}:"]
        for i, step in enumerate(steps, 1):
            lines.append(f"  {i}. {step}")
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# CONFIRM (conferma azioni distruttive)
# ═══════════════════════════════════════════════════════════════════════════════

class ConfirmLevel:
    """Livelli di conferma per azioni."""
    MILD = "mild"           # Singolo file/azione reversibile
    MODERATE = "moderate"   # Piu file/azione importante
    SEVERE = "severe"       # Azione irreversibile/distruttiva


def confirm_action(message: str, level: str = ConfirmLevel.MILD,
                   force: bool = False, no_interactive: bool = False) -> bool:
    """
    Chiede conferma per azione.

    Args:
        message: Descrizione azione
        level: Livello gravita (mild/moderate/severe)
        force: Se True, salta conferma
        no_interactive: Se True, rifiuta automaticamente

    Returns:
        True se confermato
    """
    if force:
        return True

    if no_interactive:
        print(f"Azione richiede conferma ma --no-interactive attivo: {message}",
              file=sys.stderr)
        return False

    if not sys.stdin.isatty():
        print(f"Azione richiede conferma interattiva: {message}",
              file=sys.stderr)
        return False

    if level == ConfirmLevel.MILD:
        prompt = f"{message} [y/N] "
        response = input(prompt).strip().lower()
        return response in ('y', 'yes', 'si', 's')

    elif level == ConfirmLevel.MODERATE:
        prompt = f"{message}\nSei sicuro? [y/N] "
        response = input(prompt).strip().lower()
        return response in ('y', 'yes', 'si', 's')

    elif level == ConfirmLevel.SEVERE:
        confirm_word = "CONFERMA"
        prompt = f"{message}\nDigita '{confirm_word}' per procedere: "
        response = input(prompt).strip()
        return response == confirm_word

    return False


def confirm_delete(item: str, count: int = 1) -> bool:
    """Conferma eliminazione."""
    if count == 1:
        return confirm_action(
            f"Eliminare '{item}'?",
            level=ConfirmLevel.MILD
        )
    else:
        return confirm_action(
            f"Eliminare {count} elementi in '{item}'?",
            level=ConfirmLevel.MODERATE
        )


def confirm_overwrite(path: Path) -> bool:
    """Conferma sovrascrittura file."""
    if path.exists():
        return confirm_action(
            f"Il file '{path}' esiste. Sovrascrivere?",
            level=ConfirmLevel.MILD
        )
    return True


# ═══════════════════════════════════════════════════════════════════════════════
# FEEDBACK IMMEDIATO
# ═══════════════════════════════════════════════════════════════════════════════

def print_startup_feedback(version: str = "1.4.0") -> None:
    """Stampa feedback immediato all'avvio (<100ms)."""
    # Questo deve essere chiamato il prima possibile
    print(f"chatbot-tester v{version}", flush=True)


def print_loading(message: str = "Caricamento...") -> Callable:
    """
    Stampa messaggio loading e ritorna funzione per completamento.

    Usage:
        done = print_loading("Connessione...")
        # ... operazione lunga ...
        done()  # o done("Connesso")
    """
    import sys

    sys.stdout.write(f"\r{message}")
    sys.stdout.flush()

    def complete(final_message: str = None):
        if final_message:
            sys.stdout.write(f"\r{final_message}\n")
        else:
            sys.stdout.write("\r" + " " * len(message) + "\r")
        sys.stdout.flush()

    return complete


# ═══════════════════════════════════════════════════════════════════════════════
# ERROR FORMATTING
# ═══════════════════════════════════════════════════════════════════════════════

def format_error(message: str, suggestion: str = None,
                 code: ExitCode = None) -> str:
    """
    Formatta messaggio errore user-friendly.

    Args:
        message: Messaggio errore principale
        suggestion: Suggerimento per risolvere
        code: Exit code per riferimento
    """
    lines = [f"Errore: {message}"]

    if suggestion:
        lines.append(f"Suggerimento: {suggestion}")

    if code:
        lines.append(f"(exit code: {code})")

    return "\n".join(lines)


def handle_keyboard_interrupt() -> None:
    """Gestisce Ctrl+C in modo pulito."""
    print("\n\nOperazione annullata (Ctrl+C)")
    sys.exit(ExitCode.CANCELLED)
