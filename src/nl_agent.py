"""
Conversational Agent - Orchestratore principale per l'agente avanzato.

Coordina memoria, pianificatore, conferma e esecuzione per
offrire un'esperienza conversazionale completa.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum

from .nl_processor import NLProcessor, NLConfig, ActionType, get_provider_instructions
from .nl_executor import ActionExecutor, ExecutionResult
from .nl_memory import ConversationMemory, TurnRole
from .nl_planner import ActionPlanner, ExecutionPlan, ActionStatus, PlannedAction
from .nl_confirmation import ConfirmationUI, ConfirmationChoice, ActionPreview
from .ui import ConsoleUI, get_ui
from .config_loader import ConfigLoader


class AgentState(Enum):
    """Stati dell'agente"""
    IDLE = "idle"
    UNDERSTANDING = "understanding"
    PLANNING = "planning"
    CONFIRMING = "confirming"
    EXECUTING = "executing"
    REPORTING = "reporting"


@dataclass
class AgentResponse:
    """Risposta dell'agente"""
    message: str
    state: AgentState
    plan: Optional[ExecutionPlan] = None
    needs_input: bool = False
    prompt: Optional[str] = None


class ConversationalAgent:
    """
    Agente conversazionale completo.

    Orchestrazione:
    1. Riceve input utente
    2. Salva in memoria
    3. Crea piano di esecuzione
    4. Chiede conferma
    5. Esegue azioni
    6. Riporta risultati

    Features:
    - Memoria conversazionale (ultimi N turni)
    - Pianificazione multi-step
    - Conferma sempre prima di eseguire
    - Gestione dipendenze tra azioni
    """

    WELCOME_MESSAGE = """
========================================
   Chatbot Tester - Agent Mode
========================================

Sono il tuo assistente per il testing. Ricordo il contesto
e posso eseguire sequenze di azioni.

Esempi:
  - "lancia test silicon-b in auto"
  - "testa e poi esportami il pdf"
  - "confronta le ultime due run"
  - "quali test sono falliti?"

Digita 'exit' per uscire, 'history' per la cronologia.

"""

    def __init__(self, config: NLConfig = None, ui: ConsoleUI = None):
        """
        Inizializza agente conversazionale.

        Args:
            config: Configurazione NL (provider, model, etc.)
            ui: Console UI per output
        """
        self.ui = ui or get_ui()
        self.loader = ConfigLoader()
        self.projects = self.loader.list_projects()

        # Load config from settings if not provided
        if config is None:
            config = self._load_config_from_settings()

        self.config = config
        self.processor = NLProcessor(config, self.projects)
        self.memory = ConversationMemory(max_turns=20)
        self.planner = ActionPlanner(self.processor, self.memory, self.projects)
        self.executor = ActionExecutor(self.ui)
        self.confirmer = ConfirmationUI(self.ui)

        self.state = AgentState.IDLE
        self.current_plan: Optional[ExecutionPlan] = None

    def _load_config_from_settings(self) -> NLConfig:
        """Load NL config from settings.yaml"""
        try:
            import yaml
            from pathlib import Path

            settings_path = Path(__file__).parent.parent / "config" / "settings.yaml"
            if settings_path.exists():
                with open(settings_path) as f:
                    settings = yaml.safe_load(f)

                nl = settings.get('natural_language', {})
                return NLConfig(
                    provider=nl.get('provider', 'ollama'),
                    model=nl.get('model', 'llama3.2:3b'),
                    api_key_env=nl.get('api_key_env', ''),
                    ollama_url=nl.get('ollama_url', 'http://localhost:11434'),
                    temperature=nl.get('temperature', 0.1)
                )
        except Exception:
            pass

        return NLConfig()

    async def start_session(self):
        """Avvia sessione interattiva"""
        self.ui.print(self.WELCOME_MESSAGE)

        # Check provider availability
        if not self.processor.is_available():
            self.ui.warning(f"Provider '{self.config.provider}' non disponibile.")
            self.ui.print(get_provider_instructions(self.config.provider))
            return

        self.ui.success(f"Connesso a {self.config.provider} ({self.config.model})")

        if self.projects:
            self.ui.muted(f"Progetti: {', '.join(self.projects)}")
        else:
            self.ui.warning("Nessun progetto configurato")

        self.ui.print("")

        # Main loop
        while True:
            try:
                try:
                    user_input = input("\n> ").strip()
                except EOFError:
                    break

                if not user_input:
                    continue

                # Handle special commands
                if user_input.lower() in ('exit', 'quit', 'esci', 'q'):
                    self.ui.print("\nArrivederci!")
                    break

                if user_input.lower() in ('history', 'cronologia', 'storia'):
                    self._show_history()
                    continue

                if user_input.lower() in ('status', 'stato'):
                    self._show_status()
                    continue

                if user_input.lower() in ('clear', 'reset', 'pulisci'):
                    self.memory.clear()
                    self.ui.success("Memoria cancellata")
                    continue

                if user_input.lower() in ('help', 'aiuto', '?'):
                    self._show_help()
                    continue

                # Process input through agent pipeline
                await self.process_input(user_input)

            except KeyboardInterrupt:
                self.ui.print("\n\nInterrotto. Digita 'exit' per uscire.")
            except Exception as e:
                self.ui.error(f"Errore: {e}")
                self.state = AgentState.IDLE

    async def process_input(self, user_input: str) -> AgentResponse:
        """
        Processa input utente attraverso pipeline agente.

        Args:
            user_input: Richiesta in linguaggio naturale

        Returns:
            AgentResponse con risultato elaborazione
        """
        # 1. Salva in memoria
        self.memory.add_user_message(user_input)
        self.state = AgentState.UNDERSTANDING

        # 2. Crea piano
        self.state = AgentState.PLANNING
        self.ui.muted("  [Analizzando richiesta...]")

        plan = self.planner.create_plan(user_input)
        self.current_plan = plan

        # 3. Gestisci chiarimenti
        if plan.needs_clarification:
            self.ui.print(f"\n  {plan.clarification_question}")
            self.memory.add_assistant_message(plan.clarification_question)
            self.state = AgentState.IDLE
            return AgentResponse(
                message=plan.clarification_question,
                state=AgentState.IDLE,
                needs_input=True,
                prompt=plan.clarification_question
            )

        # 4. Piano vuoto?
        if not plan.actions:
            msg = "Non ho capito cosa vuoi fare. Puoi riformulare?"
            self.ui.warning(f"  {msg}")
            self.memory.add_assistant_message(msg)
            self.state = AgentState.IDLE
            return AgentResponse(
                message=msg,
                state=AgentState.IDLE,
                needs_input=True
            )

        # 5. Mostra piano e chiedi conferma
        self.state = AgentState.CONFIRMING
        previews = plan.get_previews()

        if len(plan.actions) > 1:
            # Piano multi-step: conferma globale prima
            choice, _ = self.confirmer.confirm_plan(previews)
        else:
            # Singola azione: conferma diretta
            choice, modified_params = self.confirmer.confirm_action(previews[0])
            if choice == ConfirmationChoice.MODIFY and modified_params:
                # Aggiorna parametri azione
                plan.actions[0].parameters.update(modified_params)

        # 6. Gestisci scelta
        if choice == ConfirmationChoice.ABORT:
            msg = "Operazione annullata."
            self.ui.print(f"\n  {msg}")
            self.memory.add_assistant_message(msg)
            self.state = AgentState.IDLE
            return AgentResponse(
                message=msg,
                state=AgentState.IDLE,
                plan=plan
            )

        if choice == ConfirmationChoice.SKIP:
            msg = "Azione saltata."
            self.ui.print(f"\n  {msg}")
            self.memory.add_assistant_message(msg)
            self.state = AgentState.IDLE
            return AgentResponse(
                message=msg,
                state=AgentState.IDLE,
                plan=plan
            )

        # 7. Esegui piano
        self.state = AgentState.EXECUTING
        results = await self._execute_plan(plan)

        # 8. Report finale
        self.state = AgentState.REPORTING
        summary = self._generate_summary(plan, results)
        self.memory.add_assistant_message(summary)

        self.state = AgentState.IDLE
        return AgentResponse(
            message=summary,
            state=AgentState.IDLE,
            plan=plan
        )

    async def _execute_plan(self, plan: ExecutionPlan) -> List[ExecutionResult]:
        """
        Esegue piano step by step.

        Args:
            plan: Piano da eseguire

        Returns:
            Lista risultati per ogni step
        """
        results = []
        total_steps = len(plan.actions)

        for i, action in enumerate(plan.actions, 1):
            # Check dipendenze
            if action.depends_on:
                dep_action = plan.get_action(action.depends_on)
                if dep_action and dep_action.status != ActionStatus.COMPLETED:
                    plan.mark_skipped(action.step_number, "Dipendenza fallita")
                    results.append(ExecutionResult(
                        success=False,
                        message=f"Saltato: dipendenza step {action.depends_on} non completata"
                    ))
                    continue

            # Mostra progresso
            action_name = self.confirmer.ACTION_NAMES.get(action.action_type, action.action_type)
            self.confirmer.show_execution_progress(i, total_steps, action_name)

            # Esegui
            action.status = ActionStatus.EXECUTING
            intent = action.to_intent()
            result = await self.executor.execute(intent)
            results.append(result)

            # Aggiorna stato
            if result.success:
                plan.mark_completed(action.step_number, result.message)
                self.confirmer.show_execution_result(True, result.message)

                # Aggiorna stato sessione se rilevante
                if action.action_type == "run_tests" and action.parameters.get("project"):
                    self.memory.update_state(
                        active_project=action.parameters["project"],
                        last_action="run_tests",
                        last_action_success=True,
                        last_action_result=result.message
                    )
            else:
                plan.mark_failed(action.step_number, result.message)
                self.confirmer.show_execution_result(False, result.message)

                # Chiedi se continuare
                if i < total_steps:
                    if not self.confirmer.ask_continue_after_failure(i, result.message):
                        # Marca rimanenti come saltati
                        for remaining in plan.actions[i:]:
                            plan.mark_skipped(remaining.step_number, "Annullato dopo errore")
                        break

        return results

    def _generate_summary(self, plan: ExecutionPlan, results: List[ExecutionResult]) -> str:
        """Genera riassunto esecuzione"""
        completed = sum(1 for a in plan.actions if a.status == ActionStatus.COMPLETED)
        failed = sum(1 for a in plan.actions if a.status == ActionStatus.FAILED)
        skipped = sum(1 for a in plan.actions if a.status == ActionStatus.SKIPPED)
        total = len(plan.actions)

        if completed == total:
            summary = f"Completato: {completed}/{total} azioni eseguite con successo."
        elif failed > 0:
            summary = f"Completato con errori: {completed} OK, {failed} fallite, {skipped} saltate."
        else:
            summary = f"Completato parzialmente: {completed} OK, {skipped} saltate."

        return summary

    def _show_history(self):
        """Mostra cronologia conversazione"""
        if not self.memory.turns:
            self.ui.muted("  Nessuna cronologia")
            return

        self.ui.print("\n  Cronologia conversazione:")
        self.ui.print("  " + "-" * 40)

        for turn in self.memory.turns[-10:]:  # Ultimi 10
            role_icon = {
                TurnRole.USER: ">",
                TurnRole.ASSISTANT: "<",
                TurnRole.SYSTEM: "!"
            }.get(turn.role, "?")

            # Tronca messaggi lunghi
            content = turn.content[:60] + "..." if len(turn.content) > 60 else turn.content
            self.ui.print(f"  {role_icon} {content}")

        self.ui.print("  " + "-" * 40)

    def _show_status(self):
        """Mostra stato sessione"""
        self.ui.print("\n  Stato sessione:")
        self.ui.print("  " + "-" * 40)

        if self.memory.state.active_project:
            self.ui.print(f"  Progetto attivo: {self.memory.state.active_project}")
        else:
            self.ui.muted("  Nessun progetto attivo")

        if self.memory.state.last_run_number:
            self.ui.print(f"  Ultimo run: {self.memory.state.last_run_number}")

        if self.memory.state.last_action:
            status = "OK" if self.memory.state.last_action_success else "FALLITO"
            self.ui.print(f"  Ultima azione: {self.memory.state.last_action} ({status})")

        self.ui.print(f"  Turni in memoria: {len(self.memory)}")
        self.ui.print("  " + "-" * 40)

    def _show_help(self):
        """Mostra aiuto"""
        help_text = """
  Comandi disponibili:
  ─────────────────────────────────────────
  TEST
    "lancia test [progetto]"        - Esegui test
    "testa [progetto] in auto"      - Test automatici
    "testa solo i failed"           - Solo test falliti
    "lancia nel cloud"              - Esegui su CircleCI

  REPORT
    "esporta pdf"                   - Export PDF
    "esportami excel del run 15"    - Export specifico

  ANALISI
    "confronta run 15 e 16"         - Confronto A/B
    "mostra regressioni"            - Test regrediti
    "trova test flaky"              - Test instabili

  STATO
    "stato progetto"                - Info progetto
    "lista progetti"                - Progetti disponibili
    "health check"                  - Verifica servizi

  SPECIALI
    history / cronologia            - Mostra cronologia
    status / stato                  - Stato sessione
    clear / reset                   - Pulisci memoria
    exit / quit                     - Esci

  MULTI-STEP
    "testa e poi esporta pdf"       - Sequenza azioni
    "confronta e mostra regressioni"
  ─────────────────────────────────────────
"""
        self.ui.print(help_text)


async def run_agent_mode(config: NLConfig = None):
    """Entry point per modalita' agente"""
    agent = ConversationalAgent(config)
    await agent.start_session()


async def run_agent_single(command: str, config: NLConfig = None) -> AgentResponse:
    """
    Esegue singolo comando in modalita' agente.

    A differenza di run_single_command(), gestisce:
    - Conferma prima dell'esecuzione
    - Supporto multi-step
    """
    agent = ConversationalAgent(config)

    if not agent.processor.is_available():
        return AgentResponse(
            message=f"Provider '{agent.config.provider}' non disponibile",
            state=AgentState.IDLE
        )

    return await agent.process_input(command)
