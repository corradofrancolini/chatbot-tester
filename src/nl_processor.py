"""
Natural Language Processor - LLM-based intent extraction

Supports multiple providers:
- Ollama (local, free, default)
- Anthropic Claude API
- OpenAI GPT API
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Generator
from enum import Enum
import json
import os

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


class ActionType(Enum):
    """Supported action types"""
    RUN_TESTS = "run_tests"
    EXPORT_REPORT = "export_report"
    COMPARE_RUNS = "compare_runs"
    SHOW_STATUS = "show_status"
    LIST_PROJECTS = "list_projects"
    CREATE_PROJECT = "create_project"
    SHOW_REGRESSIONS = "show_regressions"
    DETECT_FLAKY = "detect_flaky"
    HEALTH_CHECK = "health_check"
    SHOW_PERFORMANCE = "show_performance"
    CANCEL_PIPELINE = "cancel_pipeline"
    HELP = "help"
    UNKNOWN = "unknown"


@dataclass
class Intent:
    """Parsed intent from natural language"""
    action: ActionType
    project: Optional[str] = None
    mode: Optional[str] = None  # train, assisted, auto
    test_filter: Optional[str] = None  # all, pending, failed
    test_id: Optional[str] = None
    test_ids: Optional[List[str]] = None
    run_number: Optional[int] = None
    run_a: Optional[int] = None
    run_b: Optional[int] = None
    export_format: Optional[str] = None  # pdf, excel, html, csv
    cloud: bool = False
    new_run: bool = False
    single_turn: bool = False
    test_limit: Optional[int] = None
    confidence: float = 0.0
    raw_text: str = ""
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'action': self.action.value,
            'project': self.project,
            'mode': self.mode,
            'test_filter': self.test_filter,
            'test_id': self.test_id,
            'test_ids': self.test_ids,
            'run_number': self.run_number,
            'run_a': self.run_a,
            'run_b': self.run_b,
            'export_format': self.export_format,
            'cloud': self.cloud,
            'new_run': self.new_run,
            'single_turn': self.single_turn,
            'test_limit': self.test_limit,
            'confidence': self.confidence,
        }


@dataclass
class NLConfig:
    """Configuration for NL processor"""
    provider: str = "ollama"  # ollama | anthropic | openai
    model: str = "llama3.2:3b"
    api_key_env: str = ""
    ollama_url: str = "http://localhost:11434"
    temperature: float = 0.1
    max_tokens: int = 500


class LLMProvider:
    """Base class for LLM providers"""

    def is_available(self) -> bool:
        raise NotImplementedError

    def generate(self, prompt: str, system: str) -> Optional[str]:
        raise NotImplementedError


class OllamaProvider(LLMProvider):
    """Ollama local LLM provider"""

    def __init__(self, model: str, url: str, temperature: float = 0.1):
        self.model = model
        self.base_url = url
        self.url = f"{url}/api/generate"
        self.temperature = temperature

    def is_available(self) -> bool:
        if not REQUESTS_AVAILABLE:
            return False
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=3)
            if resp.status_code != 200:
                return False
            # Check if model is available
            models = resp.json().get('models', [])
            model_names = [m.get('name', '') for m in models]
            # Match model name (with or without tag)
            return any(self.model in name or name in self.model for name in model_names)
        except:
            return False

    def generate(self, prompt: str, system: str) -> Optional[str]:
        if not REQUESTS_AVAILABLE:
            return None
        try:
            payload = {
                "model": self.model,
                "prompt": prompt,
                "system": system,
                "stream": False,
                "options": {"temperature": self.temperature}
            }
            resp = requests.post(self.url, json=payload, timeout=60)
            if resp.status_code == 200:
                return resp.json().get('response', '')
        except Exception as e:
            pass
        return None


class AnthropicProvider(LLMProvider):
    """Anthropic Claude API provider"""

    def __init__(self, api_key: str, model: str = "claude-3-haiku-20240307"):
        self.api_key = api_key
        self.model = model
        self.url = "https://api.anthropic.com/v1/messages"

    def is_available(self) -> bool:
        return bool(self.api_key) and REQUESTS_AVAILABLE

    def generate(self, prompt: str, system: str) -> Optional[str]:
        if not self.is_available():
            return None
        try:
            headers = {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            }
            payload = {
                "model": self.model,
                "max_tokens": 500,
                "system": system,
                "messages": [{"role": "user", "content": prompt}]
            }
            resp = requests.post(self.url, json=payload, headers=headers, timeout=30)
            if resp.status_code == 200:
                return resp.json()['content'][0]['text']
        except:
            pass
        return None


class OpenAIProvider(LLMProvider):
    """OpenAI GPT API provider"""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self.api_key = api_key
        self.model = model
        self.url = "https://api.openai.com/v1/chat/completions"

    def is_available(self) -> bool:
        return bool(self.api_key) and REQUESTS_AVAILABLE

    def generate(self, prompt: str, system: str) -> Optional[str]:
        if not self.is_available():
            return None
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.1
            }
            resp = requests.post(self.url, json=payload, headers=headers, timeout=30)
            if resp.status_code == 200:
                return resp.json()['choices'][0]['message']['content']
        except:
            pass
        return None


class NLProcessor:
    """
    Natural Language Processor for chatbot-tester commands.

    Usage:
        processor = NLProcessor(config, available_projects)
        intent = processor.parse_intent("lancia test silicon-b in auto")
        # intent.action = ActionType.RUN_TESTS
        # intent.project = "silicon-b"
        # intent.mode = "auto"
    """

    SYSTEM_PROMPT = """Sei un parser di comandi per un tool di testing chatbot chiamato "chatbot-tester".
Il tuo compito e' estrarre l'intento e i parametri da comandi in linguaggio naturale (italiano o inglese).

PROGETTI DISPONIBILI: {projects}

AZIONI POSSIBILI:

1. run_tests - Esegue test su un progetto
   - project: nome progetto (OBBLIGATORIO)
   - mode: train | assisted | auto (default: auto)
   - test_filter: all | pending | failed (default: pending)
   - test_id: ID singolo test (es: TEST_001)
   - test_ids: lista ID test separati da virgola
   - cloud: true se vuole eseguire nel cloud/CircleCI
   - new_run: true se vuole forzare una nuova RUN
   - single_turn: true se vuole solo domanda iniziale
   - test_limit: numero massimo di test

2. export_report - Esporta report
   - project: nome progetto (OBBLIGATORIO)
   - export_format: pdf | excel | html | csv | all (default: html)
   - run_number: numero RUN da esportare

3. compare_runs - Confronta due RUN
   - project: nome progetto (OBBLIGATORIO)
   - run_a: primo numero RUN
   - run_b: secondo numero RUN

4. show_regressions - Mostra regressioni
   - project: nome progetto (OBBLIGATORIO)
   - run_number: numero RUN (default: ultimo)

5. detect_flaky - Rileva test instabili
   - project: nome progetto (OBBLIGATORIO)

6. show_status - Mostra stato/risultati
   - project: nome progetto
   - run_number: numero RUN

7. list_projects - Lista progetti disponibili

8. health_check - Verifica servizi
   - project: nome progetto (opzionale)

9. show_performance - Mostra metriche performance
   - project: nome progetto
   - run_number: numero RUN

10. help - Mostra aiuto

ESEMPI:
- "lancia test silicon-b in auto" -> run_tests, project=silicon-b, mode=auto
- "esegui silicon-a nel cloud" -> run_tests, project=silicon-a, cloud=true
- "testa silicon-b con nuova run" -> run_tests, project=silicon-b, new_run=true
- "esegui solo TEST_001 di silicon-b" -> run_tests, project=silicon-b, test_id=TEST_001
- "esporta pdf di silicon-b" -> export_report, project=silicon-b, export_format=pdf
- "confronta run 15 e 16 di silicon-b" -> compare_runs, project=silicon-b, run_a=15, run_b=16
- "regressioni silicon-prod" -> show_regressions, project=silicon-prod
- "test flaky su silicon-a" -> detect_flaky, project=silicon-a
- "quali progetti ho?" -> list_projects
- "lista progetti" -> list_projects
- "health check" -> health_check
- "esegui primi 5 test" -> run_tests, test_limit=5
- "run all tests on silicon-b in cloud" -> run_tests, project=silicon-b, test_filter=all, cloud=true

Rispondi SOLO con JSON valido:
{{
    "action": "nome_azione",
    "project": "nome_o_null",
    "mode": "modalita_o_null",
    "test_filter": "filtro_o_null",
    "test_id": "id_o_null",
    "test_ids": ["id1", "id2"] o null,
    "cloud": true_o_false,
    "new_run": true_o_false,
    "single_turn": true_o_false,
    "test_limit": numero_o_null,
    "export_format": "formato_o_null",
    "run_number": numero_o_null,
    "run_a": numero_o_null,
    "run_b": numero_o_null,
    "confidence": 0.0_a_1.0
}}"""

    def __init__(self, config: NLConfig, available_projects: List[str] = None):
        self.config = config
        self.projects = available_projects or []
        self.provider = self._create_provider()

    def _create_provider(self) -> LLMProvider:
        """Create the appropriate LLM provider"""
        if self.config.provider == "ollama":
            return OllamaProvider(
                self.config.model,
                self.config.ollama_url,
                self.config.temperature
            )
        elif self.config.provider == "anthropic":
            api_key = os.environ.get(self.config.api_key_env, "")
            return AnthropicProvider(api_key, self.config.model)
        elif self.config.provider == "openai":
            api_key = os.environ.get(self.config.api_key_env, "")
            return OpenAIProvider(api_key, self.config.model)
        else:
            # Default to Ollama
            return OllamaProvider(self.config.model, self.config.ollama_url)

    def is_available(self) -> bool:
        """Check if the provider is available"""
        return self.provider.is_available()

    def get_provider_name(self) -> str:
        """Get current provider name"""
        return self.config.provider

    def get_model_name(self) -> str:
        """Get current model name"""
        return self.config.model

    def parse_intent(self, text: str) -> Intent:
        """
        Parse natural language command into structured Intent.

        Args:
            text: Natural language command

        Returns:
            Intent object with parsed action and parameters
        """
        # Build system prompt with available projects
        projects_str = ", ".join(self.projects) if self.projects else "nessuno configurato"
        system = self.SYSTEM_PROMPT.format(projects=projects_str)

        prompt = f"Comando utente: {text}\n\nEstrai l'intento in JSON:"

        response = self.provider.generate(prompt, system)

        if not response:
            return Intent(
                action=ActionType.UNKNOWN,
                error="Errore comunicazione con LLM. Verifica che il provider sia attivo.",
                raw_text=text
            )

        try:
            # Clean response (remove markdown code blocks if present)
            clean = response.strip()
            if clean.startswith("```"):
                # Extract content between code fences
                lines = clean.split("\n")
                json_lines = []
                in_block = False
                for line in lines:
                    if line.startswith("```"):
                        in_block = not in_block
                        continue
                    if in_block:
                        json_lines.append(line)
                clean = "\n".join(json_lines)

            # Try to find JSON object in response
            start_idx = clean.find('{')
            end_idx = clean.rfind('}')
            if start_idx != -1 and end_idx != -1:
                clean = clean[start_idx:end_idx + 1]

            data = json.loads(clean)

            # Map action string to enum
            action_map = {
                "run_tests": ActionType.RUN_TESTS,
                "export_report": ActionType.EXPORT_REPORT,
                "compare_runs": ActionType.COMPARE_RUNS,
                "show_status": ActionType.SHOW_STATUS,
                "list_projects": ActionType.LIST_PROJECTS,
                "create_project": ActionType.CREATE_PROJECT,
                "show_regressions": ActionType.SHOW_REGRESSIONS,
                "detect_flaky": ActionType.DETECT_FLAKY,
                "health_check": ActionType.HEALTH_CHECK,
                "show_performance": ActionType.SHOW_PERFORMANCE,
                "cancel_pipeline": ActionType.CANCEL_PIPELINE,
                "help": ActionType.HELP,
            }

            action_str = data.get("action", "").lower()
            action = action_map.get(action_str, ActionType.UNKNOWN)

            # Parse test_ids if present
            test_ids = data.get("test_ids")
            if isinstance(test_ids, str):
                test_ids = [t.strip() for t in test_ids.split(",")]

            return Intent(
                action=action,
                project=data.get("project"),
                mode=data.get("mode"),
                test_filter=data.get("test_filter"),
                test_id=data.get("test_id"),
                test_ids=test_ids,
                cloud=data.get("cloud", False),
                new_run=data.get("new_run", False),
                single_turn=data.get("single_turn", False),
                test_limit=data.get("test_limit"),
                export_format=data.get("export_format"),
                run_number=data.get("run_number"),
                run_a=data.get("run_a"),
                run_b=data.get("run_b"),
                confidence=data.get("confidence", 0.5),
                raw_text=text
            )

        except json.JSONDecodeError as e:
            return Intent(
                action=ActionType.UNKNOWN,
                error=f"Risposta LLM non valida (JSON error): {str(e)[:50]}",
                raw_text=text
            )
        except Exception as e:
            return Intent(
                action=ActionType.UNKNOWN,
                error=f"Errore parsing: {str(e)[:50]}",
                raw_text=text
            )


def get_provider_instructions(provider: str) -> str:
    """Get setup instructions for a provider"""
    if provider == "ollama":
        return """
Per usare Ollama:
1. Installa Ollama: brew install ollama
2. Avvia il server: ollama serve
3. Scarica un modello: ollama pull llama3.2:3b
"""
    elif provider == "anthropic":
        return """
Per usare Anthropic Claude:
1. Ottieni API key da console.anthropic.com
2. Configura: export ANTHROPIC_API_KEY="sk-..."
3. Aggiorna settings.yaml con provider: "anthropic"
"""
    elif provider == "openai":
        return """
Per usare OpenAI:
1. Ottieni API key da platform.openai.com
2. Configura: export OPENAI_API_KEY="sk-..."
3. Aggiorna settings.yaml con provider: "openai"
"""
    return ""
