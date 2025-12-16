"""
Confirmation UI - Sistema di conferma azioni per l'agente.

Mostra le azioni proposte all'utente e chiede conferma prima di eseguirle.
Supporta modifica parametri inline.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Tuple, Dict, Any
from enum import Enum

from .ui import ConsoleUI, get_ui


class ConfirmationChoice(Enum):
    """Scelte possibili per conferma"""
    CONFIRM = "confirm"      # Procedi con l'azione
    MODIFY = "modify"        # Modifica parametri
    SKIP = "skip"            # Salta questa azione
    ABORT = "abort"          # Annulla tutto


@dataclass
class ActionPreview:
    """Preview di un'azione per conferma"""
    action_type: str
    description: str
    parameters: Dict[str, Any]
    warnings: List[str] = field(default_factory=list)
    step_number: Optional[int] = None
    total_steps: Optional[int] = None

    def format_parameters(self) -> List[Tuple[str, str]]:
        """Formatta parametri per display"""
        result = []
        param_names = {
            "project": "Progetto",
            "mode": "Modalita",
            "test_filter": "Test",
            "cloud": "Cloud",
            "new_run": "Nuovo run",
            "single_turn": "Single turn",
            "test_limit": "Limite test",
            "export_format": "Formato",
            "run_number": "Run",
            "run_a": "Run A",
            "run_b": "Run B",
            "test_id": "Test ID",
            "test_ids": "Test IDs",
        }

        for key, value in self.parameters.items():
            if value is not None and value != "" and value != False:
                name = param_names.get(key, key.replace("_", " ").title())
                if isinstance(value, bool):
                    display = "Si" if value else "No"
                elif isinstance(value, list):
                    display = ", ".join(str(v) for v in value)
                else:
                    display = str(value)
                result.append((name, display))

        return result


class ConfirmationUI:
    """
    Gestisce conferma azioni con l'utente.

    Features:
    - Mostra azione proposta con parametri
    - Permette modifica parametri inline
    - Opzioni: conferma, modifica, salta, annulla
    """

    ACTION_NAMES = {
        "run_tests": "Esegui test",
        "export_report": "Esporta report",
        "compare_runs": "Confronta run",
        "show_status": "Mostra stato",
        "list_projects": "Lista progetti",
        "show_regressions": "Mostra regressioni",
        "detect_flaky": "Rileva test flaky",
        "health_check": "Health check",
        "show_performance": "Mostra performance",
    }

    def __init__(self, ui: ConsoleUI = None):
        self.ui = ui or get_ui()

    def show_plan_summary(self, actions: List[ActionPreview]) -> None:
        """
        Mostra riassunto del piano completo.

        Args:
            actions: Lista di azioni nel piano
        """
        self.ui.print("\n  Piano di esecuzione:")
        self.ui.print("  " + "-" * 40)

        for i, action in enumerate(actions, 1):
            action_name = self.ACTION_NAMES.get(action.action_type, action.action_type)
            params_str = ", ".join(f"{k}={v}" for k, v in action.format_parameters())
            self.ui.print(f"  {i}. {action_name}")
            if params_str:
                self.ui.muted(f"     {params_str}")

        self.ui.print("  " + "-" * 40)
        self.ui.print("")

    def confirm_action(self, preview: ActionPreview) -> Tuple[ConfirmationChoice, Optional[Dict]]:
        """
        Chiede conferma per singola azione.

        Args:
            preview: Preview dell'azione

        Returns:
            Tupla (scelta, parametri_modificati o None)
        """
        self._show_action_box(preview)

        while True:
            self.ui.print("  [c] Conferma  [m] Modifica  [s] Salta  [a] Annulla tutto")
            try:
                choice = input("\n  > ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                return ConfirmationChoice.ABORT, None

            if choice in ('c', 'conferma', 'y', 'yes', 'si', ''):
                return ConfirmationChoice.CONFIRM, None

            elif choice in ('m', 'modifica', 'mod'):
                new_params = self._handle_modification(preview)
                if new_params:
                    return ConfirmationChoice.MODIFY, new_params
                # Se modifica annullata, rimostra box
                self._show_action_box(preview)

            elif choice in ('s', 'salta', 'skip'):
                return ConfirmationChoice.SKIP, None

            elif choice in ('a', 'annulla', 'abort', 'q'):
                return ConfirmationChoice.ABORT, None

            else:
                self.ui.warning("  Scelta non valida. Usa: c, m, s, a")

    def confirm_plan(self, actions: List[ActionPreview]) -> Tuple[ConfirmationChoice, Optional[int]]:
        """
        Chiede conferma per piano completo.

        Args:
            actions: Lista di azioni nel piano

        Returns:
            Tupla (scelta, step_da_cui_partire o None)
        """
        self.show_plan_summary(actions)

        self.ui.print("  [c] Conferma tutto  [v] Vedi dettagli  [a] Annulla")

        while True:
            try:
                choice = input("\n  > ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                return ConfirmationChoice.ABORT, None

            if choice in ('c', 'conferma', 'y', 'yes', 'si', ''):
                return ConfirmationChoice.CONFIRM, None

            elif choice in ('v', 'vedi', 'dettagli'):
                # Mostra dettagli di ogni azione
                for action in actions:
                    self._show_action_box(action)
                    self.ui.print("")
                self.show_plan_summary(actions)
                self.ui.print("  [c] Conferma tutto  [v] Vedi dettagli  [a] Annulla")

            elif choice in ('a', 'annulla', 'abort', 'q'):
                return ConfirmationChoice.ABORT, None

            else:
                self.ui.warning("  Scelta non valida. Usa: c, v, a")

    def _show_action_box(self, preview: ActionPreview) -> None:
        """Mostra box con dettagli azione"""
        action_name = self.ACTION_NAMES.get(preview.action_type, preview.action_type)

        # Header
        if preview.step_number and preview.total_steps:
            header = f"Step {preview.step_number}/{preview.total_steps}: {action_name}"
        else:
            header = f"Azione: {action_name}"

        self.ui.print("")
        self.ui.print("  " + "+" + "-" * 50 + "+")
        self.ui.print(f"  | {header:<48} |")
        self.ui.print("  |" + "-" * 50 + "|")

        # Parametri
        for name, value in preview.format_parameters():
            line = f"{name}:".ljust(15) + value
            self.ui.print(f"  |   {line:<46} |")

        # Warnings
        if preview.warnings:
            self.ui.print("  |" + "-" * 50 + "|")
            for warning in preview.warnings:
                self.ui.print(f"  | [yellow]! {warning:<46}[/yellow] |")

        self.ui.print("  " + "+" + "-" * 50 + "+")

    def _handle_modification(self, preview: ActionPreview) -> Optional[Dict]:
        """
        Gestisce modifica parametri.

        Args:
            preview: Preview azione corrente

        Returns:
            Dict con nuovi parametri o None se annullato
        """
        self.ui.print("\n  Modifica parametri (INVIO per mantenere, 'q' per annullare)")
        self.ui.print("")

        new_params = {}
        editable_params = ["project", "mode", "test_filter", "cloud", "new_run", "export_format"]

        for key in editable_params:
            if key in preview.parameters:
                current = preview.parameters[key]

                # Mostra valore corrente
                if isinstance(current, bool):
                    current_display = "si" if current else "no"
                    hint = " (si/no)"
                else:
                    current_display = str(current) if current else "(vuoto)"
                    hint = ""

                try:
                    new_value = input(f"  {key} [{current_display}]{hint}: ").strip()
                except (EOFError, KeyboardInterrupt):
                    return None

                if new_value.lower() == 'q':
                    return None

                if new_value:
                    # Converti tipo
                    if isinstance(current, bool):
                        new_params[key] = new_value.lower() in ('si', 'yes', 'true', '1')
                    elif isinstance(current, int):
                        try:
                            new_params[key] = int(new_value)
                        except ValueError:
                            self.ui.warning(f"  Valore non valido per {key}, mantengo originale")
                    else:
                        new_params[key] = new_value

        return new_params if new_params else None

    def show_execution_progress(self, step: int, total: int, action_name: str) -> None:
        """Mostra progresso esecuzione"""
        self.ui.print(f"\n  Step {step}/{total}: {action_name}...")

    def show_execution_result(self, success: bool, message: str) -> None:
        """Mostra risultato esecuzione"""
        if success:
            self.ui.success(f"  {message}")
        else:
            self.ui.error(f"  {message}")

    def ask_continue_after_failure(self, step: int, error: str) -> bool:
        """
        Chiede se continuare dopo un fallimento.

        Args:
            step: Numero step fallito
            error: Messaggio errore

        Returns:
            True se continuare, False se annullare
        """
        self.ui.error(f"\n  Step {step} fallito: {error}")
        self.ui.print("  [c] Continua con prossimo step  [a] Annulla tutto")

        try:
            choice = input("\n  > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return False

        return choice in ('c', 'continua', 'y', 'yes')
