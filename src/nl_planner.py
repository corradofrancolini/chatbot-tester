"""
Action Planner - Pianificatore multi-step per l'agente.

Scompone richieste complesse in sequenze di azioni atomiche.
Gestisce dipendenze tra azioni e chiarimenti.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any, Union
from enum import Enum
import json

from .nl_processor import NLProcessor, NLConfig, ActionType, Intent
from .nl_memory import ConversationMemory
from .nl_confirmation import ActionPreview


class ActionStatus(Enum):
    """Stati possibili di un'azione"""
    PENDING = "pending"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class PlannedAction:
    """Singola azione nel piano"""
    step_number: int
    action_type: str
    parameters: Dict[str, Any]
    description: str
    depends_on: Optional[int] = None
    status: ActionStatus = ActionStatus.PENDING
    result_message: Optional[str] = None

    def to_intent(self) -> Intent:
        """Converte in Intent per esecuzione"""
        return Intent(
            action=ActionType(self.action_type),
            project=self.parameters.get("project"),
            mode=self.parameters.get("mode"),
            test_filter=self.parameters.get("test_filter"),
            test_id=self.parameters.get("test_id"),
            test_ids=self.parameters.get("test_ids"),
            run_number=self.parameters.get("run_number"),
            run_a=self.parameters.get("run_a"),
            run_b=self.parameters.get("run_b"),
            export_format=self.parameters.get("export_format"),
            cloud=self.parameters.get("cloud", False),
            new_run=self.parameters.get("new_run", False),
            single_turn=self.parameters.get("single_turn", False),
            test_limit=self.parameters.get("test_limit"),
            raw_text=""
        )

    def to_preview(self, total_steps: int = 1) -> ActionPreview:
        """Converte in ActionPreview per conferma"""
        warnings = []
        if self.parameters.get("cloud"):
            warnings.append("Esecuzione nel cloud (CircleCI)")
        if self.parameters.get("new_run"):
            warnings.append("Creera' una nuova RUN")

        return ActionPreview(
            action_type=self.action_type,
            description=self.description,
            parameters=self.parameters,
            warnings=warnings,
            step_number=self.step_number,
            total_steps=total_steps
        )


@dataclass
class ExecutionPlan:
    """Piano di esecuzione multi-step"""
    goal: str
    actions: List[PlannedAction]
    created_at: datetime = field(default_factory=datetime.now)
    needs_clarification: bool = False
    clarification_question: Optional[str] = None

    def get_next_action(self) -> Optional[PlannedAction]:
        """Ritorna prossima azione pending"""
        for action in self.actions:
            if action.status == ActionStatus.PENDING:
                return action
        return None

    def get_action(self, step: int) -> Optional[PlannedAction]:
        """Ritorna azione per numero step"""
        for action in self.actions:
            if action.step_number == step:
                return action
        return None

    def mark_completed(self, step: int, message: str) -> None:
        """Marca step come completato"""
        action = self.get_action(step)
        if action:
            action.status = ActionStatus.COMPLETED
            action.result_message = message

    def mark_failed(self, step: int, error: str) -> None:
        """Marca step come fallito"""
        action = self.get_action(step)
        if action:
            action.status = ActionStatus.FAILED
            action.result_message = error

    def mark_skipped(self, step: int, reason: str = "") -> None:
        """Marca step come saltato"""
        action = self.get_action(step)
        if action:
            action.status = ActionStatus.SKIPPED
            action.result_message = reason or "Saltato dall'utente"

    def is_complete(self) -> bool:
        """True se tutte le azioni sono complete, fallite o saltate"""
        return all(
            a.status in (ActionStatus.COMPLETED, ActionStatus.FAILED, ActionStatus.SKIPPED)
            for a in self.actions
        )

    def get_previews(self) -> List[ActionPreview]:
        """Ritorna lista preview per conferma"""
        total = len(self.actions)
        return [a.to_preview(total) for a in self.actions]

    def __len__(self) -> int:
        return len(self.actions)


class ActionPlanner:
    """
    Scompone richieste complesse in azioni atomiche.

    Esempi:
    - "testa e poi esporta pdf" -> [run_tests, export_report(pdf)]
    - "confronta le ultime due run e mostra regressioni" -> [compare_runs, show_regressions]
    """

    PLANNING_PROMPT = '''Sei un pianificatore di azioni per chatbot-tester.
Analizza la richiesta dell'utente e scomponila in azioni atomiche.

CONTESTO SESSIONE:
{context}

PROGETTI DISPONIBILI: {projects}

AZIONI DISPONIBILI:
- run_tests: Esegue test
  Parametri: project (obbligatorio), mode (auto|assisted|train), test_filter (pending|failed|all), cloud (bool), new_run (bool), test_limit (int)

- export_report: Esporta report
  Parametri: project (obbligatorio), export_format (pdf|excel|html|csv), run_number (int)

- compare_runs: Confronta due run
  Parametri: project (obbligatorio), run_a (int), run_b (int)

- show_regressions: Mostra regressioni
  Parametri: project (obbligatorio), run_number (int)

- detect_flaky: Rileva test instabili
  Parametri: project (obbligatorio)

- show_status: Mostra stato progetto
  Parametri: project

- list_projects: Lista progetti disponibili
  Nessun parametro

- health_check: Verifica servizi
  Parametri: project (opzionale)

- show_performance: Metriche performance
  Parametri: project, run_number (int)

REGOLE:
1. Se manca un parametro OBBLIGATORIO e non puoi dedurlo dal contesto, chiedi chiarimento
2. Se l'utente usa pronomi ("quello", "l'ultimo"), cerca nel contesto sessione
3. Se la richiesta implica piu' azioni, scomponile in sequenza
4. Indica dipendenze: se un'azione dipende dal risultato di un'altra, usa depends_on

RICHIESTA UTENTE: {user_input}

Rispondi SOLO con JSON valido:
{{
    "understood": true/false,
    "needs_clarification": true/false,
    "clarification_question": "domanda se serve, altrimenti null",
    "goal": "obiettivo dell'utente in una frase",
    "actions": [
        {{
            "step": 1,
            "action": "nome_azione",
            "parameters": {{}},
            "description": "descrizione breve per l'utente",
            "depends_on": null o numero step precedente
        }}
    ]
}}'''

    def __init__(self, processor: NLProcessor, memory: ConversationMemory, projects: List[str] = None):
        """
        Inizializza pianificatore.

        Args:
            processor: NLProcessor per chiamate LLM
            memory: Memoria conversazionale per contesto
            projects: Lista progetti disponibili
        """
        self.processor = processor
        self.memory = memory
        self.projects = projects or []

    def create_plan(self, user_input: str) -> ExecutionPlan:
        """
        Crea piano di esecuzione da richiesta utente.

        Args:
            user_input: Richiesta in linguaggio naturale

        Returns:
            ExecutionPlan (potrebbe richiedere chiarimento)
        """
        # Prepara prompt con contesto
        context = self.memory.get_context_for_llm()
        projects_str = ", ".join(self.projects) if self.projects else "nessuno"

        prompt = self.PLANNING_PROMPT.format(
            context=context,
            projects=projects_str,
            user_input=user_input
        )

        # Chiama LLM
        system = "Sei un pianificatore preciso. Rispondi sempre in JSON valido."
        response = self.processor.provider.generate(prompt, system)

        if not response:
            return ExecutionPlan(
                goal=user_input,
                actions=[],
                needs_clarification=True,
                clarification_question="Non sono riuscito a capire. Puoi riformulare?"
            )

        return self._parse_plan_response(response, user_input)

    def _parse_plan_response(self, response: str, original_input: str) -> ExecutionPlan:
        """Parse risposta LLM in piano strutturato"""
        try:
            # Pulisci risposta
            clean = response.strip()

            # Rimuovi markdown code blocks
            if "```" in clean:
                lines = clean.split("\n")
                json_lines = []
                in_block = False
                for line in lines:
                    if line.startswith("```"):
                        in_block = not in_block
                        continue
                    if in_block or not clean.startswith("```"):
                        json_lines.append(line)
                clean = "\n".join(json_lines)

            # Trova JSON
            start = clean.find('{')
            end = clean.rfind('}')
            if start != -1 and end != -1:
                clean = clean[start:end + 1]

            data = json.loads(clean)

            # Verifica se serve chiarimento
            if data.get("needs_clarification", False):
                return ExecutionPlan(
                    goal=data.get("goal", original_input),
                    actions=[],
                    needs_clarification=True,
                    clarification_question=data.get("clarification_question", "Puoi specificare meglio?")
                )

            # Costruisci azioni
            actions = []
            for action_data in data.get("actions", []):
                action = PlannedAction(
                    step_number=action_data.get("step", len(actions) + 1),
                    action_type=action_data.get("action", "unknown"),
                    parameters=action_data.get("parameters", {}),
                    description=action_data.get("description", ""),
                    depends_on=action_data.get("depends_on")
                )
                actions.append(action)

            return ExecutionPlan(
                goal=data.get("goal", original_input),
                actions=actions
            )

        except json.JSONDecodeError:
            # Fallback: prova parsing singola azione
            return self._fallback_single_action(original_input)
        except Exception as e:
            return ExecutionPlan(
                goal=original_input,
                actions=[],
                needs_clarification=True,
                clarification_question=f"Ho avuto un problema a capire. Puoi riformulare?"
            )

    def _fallback_single_action(self, user_input: str) -> ExecutionPlan:
        """Fallback: usa parser singola azione esistente"""
        intent = self.processor.parse_intent(user_input)

        if intent.action == ActionType.UNKNOWN:
            return ExecutionPlan(
                goal=user_input,
                actions=[],
                needs_clarification=True,
                clarification_question=intent.error or "Non ho capito. Puoi riformulare?"
            )

        # Converti Intent in PlannedAction
        params = {}
        if intent.project:
            params["project"] = intent.project
        if intent.mode:
            params["mode"] = intent.mode
        if intent.test_filter:
            params["test_filter"] = intent.test_filter
        if intent.cloud:
            params["cloud"] = intent.cloud
        if intent.new_run:
            params["new_run"] = intent.new_run
        if intent.export_format:
            params["export_format"] = intent.export_format
        if intent.run_number:
            params["run_number"] = intent.run_number
        if intent.run_a:
            params["run_a"] = intent.run_a
        if intent.run_b:
            params["run_b"] = intent.run_b
        if intent.test_limit:
            params["test_limit"] = intent.test_limit

        action = PlannedAction(
            step_number=1,
            action_type=intent.action.value,
            parameters=params,
            description=self._generate_description(intent)
        )

        return ExecutionPlan(
            goal=user_input,
            actions=[action]
        )

    def _generate_description(self, intent: Intent) -> str:
        """Genera descrizione leggibile per un Intent"""
        action_desc = {
            ActionType.RUN_TESTS: "Eseguire test",
            ActionType.EXPORT_REPORT: "Esportare report",
            ActionType.COMPARE_RUNS: "Confrontare run",
            ActionType.SHOW_STATUS: "Mostrare stato",
            ActionType.LIST_PROJECTS: "Elencare progetti",
            ActionType.SHOW_REGRESSIONS: "Mostrare regressioni",
            ActionType.DETECT_FLAKY: "Rilevare test flaky",
            ActionType.HEALTH_CHECK: "Verificare servizi",
            ActionType.SHOW_PERFORMANCE: "Mostrare performance",
        }

        base = action_desc.get(intent.action, str(intent.action.value))

        if intent.project:
            base += f" su {intent.project}"
        if intent.mode:
            base += f" in modalita' {intent.mode}"
        if intent.cloud:
            base += " (cloud)"

        return base
