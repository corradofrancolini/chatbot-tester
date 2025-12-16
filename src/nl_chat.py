"""
Natural Language Chat Mode - Interactive session

Provides a conversational interface for chatbot-tester.
"""

import asyncio
from typing import Optional, List, Tuple
from .nl_processor import NLProcessor, NLConfig, Intent, ActionType, get_provider_instructions
from .nl_executor import ActionExecutor, ExecutionResult
from .ui import ConsoleUI, get_ui
from .config_loader import ConfigLoader


class NLChatSession:
    """
    Interactive chat session for natural language commands.

    Usage:
        session = NLChatSession()
        await session.start()
    """

    WELCOME_MESSAGE = """
========================================
   Chatbot Tester - Chat Mode
========================================

Puoi darmi comandi in linguaggio naturale:
  - "lancia test silicon-b in auto"
  - "esporta pdf dell'ultima run"
  - "confronta run 15 e 16"

Digita 'exit' o 'quit' per uscire.
Digita 'help' per i comandi disponibili.

"""

    def __init__(self, config: NLConfig = None, ui: ConsoleUI = None):
        self.ui = ui or get_ui()
        self.loader = ConfigLoader()
        self.projects = self.loader.list_projects()

        # Load config from settings if not provided
        if config is None:
            config = self._load_config_from_settings()

        self.config = config
        self.processor = NLProcessor(config, self.projects)
        self.executor = ActionExecutor(self.ui)
        self.history: List[Tuple[str, Intent, ExecutionResult]] = []

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

    async def start(self):
        """Start interactive chat session"""
        self.ui.print(self.WELCOME_MESSAGE)

        # Check if provider is available
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

        while True:
            try:
                # Get user input
                try:
                    user_input = input("\n> ").strip()
                except EOFError:
                    break

                if not user_input:
                    continue

                # Check for exit commands
                if user_input.lower() in ('exit', 'quit', 'esci', 'q'):
                    self.ui.print("\nArrivederci!")
                    break

                # Process command
                await self._process_command(user_input)

            except KeyboardInterrupt:
                self.ui.print("\n\nInterrotto. Digita 'exit' per uscire.")
            except Exception as e:
                self.ui.error(f"Errore: {e}")

    async def _process_command(self, user_input: str):
        """Process a single command"""
        # Parse intent
        self.ui.muted(f"  [Parsing...]")
        intent = self.processor.parse_intent(user_input)

        # Show what was understood
        if intent.action != ActionType.UNKNOWN:
            parts = [f"Azione: {intent.action.value}"]
            if intent.project:
                parts.append(f"progetto={intent.project}")
            if intent.mode:
                parts.append(f"mode={intent.mode}")
            if intent.cloud:
                parts.append("cloud=true")
            if intent.test_filter and intent.test_filter != 'pending':
                parts.append(f"test={intent.test_filter}")
            if intent.new_run:
                parts.append("new_run=true")

            self.ui.muted(f"  [{', '.join(parts)}]")

        # Execute
        result = await self.executor.execute(intent)

        # Store in history
        self.history.append((user_input, intent, result))

        # Show result
        if result.success:
            self.ui.success(result.message)
        else:
            self.ui.error(result.message)

    def get_history(self) -> List[Tuple[str, Intent, ExecutionResult]]:
        """Get command history"""
        return self.history


async def run_chat_mode(config: NLConfig = None):
    """Entry point for chat mode"""
    session = NLChatSession(config)
    await session.start()


async def run_single_command(command: str, config: NLConfig = None) -> ExecutionResult:
    """
    Execute a single natural language command.

    Args:
        command: Natural language command string
        config: Optional NL configuration

    Returns:
        ExecutionResult with success status and message
    """
    ui = get_ui()
    loader = ConfigLoader()
    projects = loader.list_projects()

    # Load config from settings if not provided
    if config is None:
        try:
            import yaml
            from pathlib import Path

            settings_path = Path(__file__).parent.parent / "config" / "settings.yaml"
            if settings_path.exists():
                with open(settings_path) as f:
                    settings = yaml.safe_load(f)

                nl = settings.get('natural_language', {})
                config = NLConfig(
                    provider=nl.get('provider', 'ollama'),
                    model=nl.get('model', 'llama3.2:3b'),
                    api_key_env=nl.get('api_key_env', ''),
                    ollama_url=nl.get('ollama_url', 'http://localhost:11434'),
                    temperature=nl.get('temperature', 0.1)
                )
        except Exception:
            config = NLConfig()

    processor = NLProcessor(config, projects)

    # Check provider availability
    if not processor.is_available():
        ui.error(f"Provider '{config.provider}' non disponibile")
        ui.print(get_provider_instructions(config.provider))
        return ExecutionResult(
            success=False,
            message=f"Provider '{config.provider}' non disponibile"
        )

    # Parse intent
    ui.muted(f"  Parsing: {command}")
    intent = processor.parse_intent(command)

    if intent.action == ActionType.UNKNOWN:
        ui.error(f"Comando non riconosciuto: {intent.error or command}")
        return ExecutionResult(
            success=False,
            message=intent.error or "Comando non riconosciuto"
        )

    # Show what was understood
    ui.print(f"\n  Azione: {intent.action.value}")
    if intent.project:
        ui.print(f"  Progetto: {intent.project}")
    if intent.mode:
        ui.print(f"  Modalita: {intent.mode}")
    if intent.cloud:
        ui.print(f"  Cloud: Si")
    if intent.test_filter:
        ui.print(f"  Test filter: {intent.test_filter}")
    if intent.new_run:
        ui.print(f"  Nuovo run: Si")
    ui.print("")

    # Execute
    executor = ActionExecutor(ui)
    result = await executor.execute(intent)

    if result.success:
        ui.success(result.message)
    else:
        ui.error(result.message)

    return result
