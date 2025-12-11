"""
Ollama Client - Local LLM integration

Handles:
- Ollama API communication
- Response generation for Assisted/Auto modes
- Conversation analysis and followup decisions
- Response quality evaluation
- Training data usage for in-context learning
"""

import json
import requests
from typing import Optional, Generator, List, Dict, Any, TYPE_CHECKING
from dataclasses import dataclass

if TYPE_CHECKING:
    from .training import TrainingData


@dataclass
class OllamaResponse:
    """Response from Ollama"""
    text: str
    model: str
    done: bool
    total_duration: Optional[int] = None
    eval_count: Optional[int] = None


class OllamaClient:
    """
    Client for Ollama communication.

    Features:
    - Streaming response generation
    - Specialized prompts for chatbot testing
    - Automatic response evaluation
    - Intelligent followup decision
    - In-context learning from training data

    Usage:
        client = OllamaClient(model="mistral")

        # Check availability
        if client.is_available():
            # Set training context
            client.set_training_context(training_data)

            # Decide response based on training
            response = client.decide_response(bot_message, conversation)
    """

    def __init__(self,
                 model: str = "mistral",
                 url: str = "http://localhost:11434/api/generate",
                 timeout: int = 120):
        """
        Initialize the Ollama client.

        Args:
            model: Model name (default: mistral)
            url: Ollama endpoint URL
            timeout: Request timeout in seconds
        """
        self.model = model
        self.url = url
        self.timeout = timeout
        self.base_url = url.replace("/api/generate", "")

        # Training context for in-context learning
        self._training: Optional['TrainingData'] = None

    def set_training_context(self, training: 'TrainingData') -> None:
        """
        Set training data for in-context learning.

        Args:
            training: TrainingData with learned patterns and responses
        """
        self._training = training

    def is_available(self) -> bool:
        """
        Check if Ollama is reachable and the model is available.

        Returns:
            True if Ollama is ready
        """
        try:
            # Check server
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if response.status_code != 200:
                return False

            # Check model
            models = response.json().get('models', [])
            model_names = [m.get('name', '') for m in models]

            return self.model in model_names
        except:
            return False

    def get_available_models(self) -> list[str]:
        """Return list of available models in Ollama"""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if response.status_code == 200:
                models = response.json().get('models', [])
                return [m.get('name', '') for m in models]
        except:
            pass
        return []

    def generate(self,
                 prompt: str,
                 system: Optional[str] = None,
                 temperature: float = 0.7,
                 max_tokens: int = 1000) -> Optional[str]:
        """
        Generate a response.

        Args:
            prompt: User prompt
            system: Optional system prompt
            temperature: Creativity (0-1)
            max_tokens: Maximum response length

        Returns:
            Generated text or None if error
        """
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens
            }
        }

        if system:
            payload["system"] = system

        try:
            response = requests.post(
                self.url,
                json=payload,
                timeout=self.timeout
            )

            if response.status_code == 200:
                data = response.json()
                return data.get('response', '')
            else:
                print(f"Ollama error: {response.status_code}")
                return None
        except Exception as e:
            print(f"Ollama connection error: {e}")
            return None

    def generate_stream(self,
                        prompt: str,
                        system: Optional[str] = None,
                        temperature: float = 0.7) -> Generator[str, None, None]:
        """
        Generate response in streaming mode.

        Args:
            prompt: User prompt
            system: Optional system prompt
            temperature: Creativity (0-1)

        Yields:
            Text chunks
        """
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": temperature
            }
        }

        if system:
            payload["system"] = system

        try:
            response = requests.post(
                self.url,
                json=payload,
                stream=True,
                timeout=self.timeout
            )

            for line in response.iter_lines():
                if line:
                    data = json.loads(line)
                    if 'response' in data:
                        yield data['response']
                    if data.get('done', False):
                        break
        except Exception as e:
            print(f"Ollama streaming error: {e}")

    # ========== IN-CONTEXT LEARNING FROM TRAINING ==========

    def _build_training_context(self) -> str:
        """
        Build training context for the prompt.

        Returns:
            String with formatted learned examples
        """
        if not self._training:
            return ""

        lines = ["LEARNED RESPONSES FROM TRAINING:"]

        for pattern in self._training.patterns:
            if pattern.responses:
                # Get top 3 most used responses
                top_responses = sorted(
                    pattern.responses,
                    key=lambda r: r.count,
                    reverse=True
                )[:3]

                responses_str = ", ".join([
                    f'"{r.text}" (used {r.count}x)'
                    for r in top_responses
                ])

                lines.append(f"- When the bot asks '{pattern.name}' → respond with: {responses_str}")

        if len(lines) == 1:
            return ""  # No patterns with responses

        return "\n".join(lines)

    def _is_final_response(self, bot_message: str) -> bool:
        """
        Heuristic to determine if the bot gave a final response.

        Indicators:
        - Contains "Source:" (citation)
        - Long message (>300 chars)
        - Contains URL
        - Typical closing phrases
        """
        msg_lower = bot_message.lower()

        indicators = [
            "source:" in msg_lower,
            len(bot_message) > 300,
            "http" in msg_lower,
            "please let me know if" in msg_lower,
            "hope this helps" in msg_lower,
            "is there anything else" in msg_lower,
            "feel free to ask" in msg_lower,
            "let me know if you" in msg_lower,
        ]

        # If contains source + is long, it's definitely final
        if "source:" in msg_lower and len(bot_message) > 200:
            return True

        # Otherwise if at least 2 indicators
        return sum(indicators) >= 2

    def decide_response(self,
                        bot_message: str,
                        conversation: List[Dict[str, str]],
                        followups: Optional[List[str]] = None,
                        test_context: Optional[str] = None) -> Optional[str]:
        """
        Decide the response to give to the bot using training context.

        This is the main method for Auto/Assisted mode.
        Uses in-context learning with examples from training.

        Args:
            bot_message: Last bot message
            conversation: Conversation so far [{role, content}, ...]
            followups: Available predefined followups (optional)
            test_context: Test context/category (optional)

        Returns:
            Response to send, or None if conversation completed
        """
        # Check if the bot gave a final response
        if self._is_final_response(bot_message):
            return None

        # First check if there's a pattern match in training
        if self._training:
            suggestions = self._training.get_suggestions(bot_message, limit=1)
            if suggestions:
                # Pattern recognized - use most common response
                return suggestions[0]['text']

        # Otherwise use LLM with training context
        training_context = self._build_training_context()

        system = """Sei un tester automatico di chatbot. Il tuo compito è rispondere alle domande del bot per completare il test.

REGOLE:
1. Rispondi in modo conciso e realistico
2. Se il bot chiede informazioni specifiche (paese, email, data), usa i pattern appresi
3. Se la conversazione sembra completa, rispondi con "DONE"
4. Non fare domande, rispondi direttamente

Rispondi SOLO con il testo da inviare, oppure "DONE" se il test è completato."""

        # Format recent conversation
        conv_text = "\n".join([
            f"{'USER' if m['role'] == 'user' else 'BOT'}: {m['content'][:200]}"
            for m in conversation[-6:]
        ])

        # Build prompt
        prompt_parts = []

        if training_context:
            prompt_parts.append(training_context)
            prompt_parts.append("")

        if test_context:
            prompt_parts.append(f"CONTESTO TEST: {test_context}")
            prompt_parts.append("")

        prompt_parts.append("CONVERSAZIONE FINORA:")
        prompt_parts.append(conv_text)
        prompt_parts.append("")
        prompt_parts.append(f"ULTIMO MESSAGGIO BOT:\n{bot_message[:500]}")
        prompt_parts.append("")

        if followups:
            prompt_parts.append("FOLLOWUP DISPONIBILI:")
            for i, f in enumerate(followups, 1):
                prompt_parts.append(f"  {i}. {f}")
            prompt_parts.append("")

        prompt_parts.append("Cosa rispondo? (testo o DONE)")

        prompt = "\n".join(prompt_parts)

        response = self.generate(prompt, system=system, temperature=0.3, max_tokens=150)

        if response:
            response = response.strip()

            # Check if conversation completed
            if response.upper() == "DONE":
                return None

            # Remove quotes if present
            if response.startswith('"') and response.endswith('"'):
                response = response[1:-1]

            # Learn the response if there's a pattern match
            if self._training:
                self._training.learn(bot_message, response)

            return response

        # Fallback: use first followup if available
        if followups:
            return followups[0]

        return None

    def should_continue(self,
                        bot_message: str,
                        conversation: List[Dict[str, str]],
                        turn: int,
                        max_turns: int = 15) -> bool:
        """
        Decide whether to continue the conversation or terminate.

        Args:
            bot_message: Last bot message
            conversation: Conversation so far
            turn: Current turn
            max_turns: Maximum turns

        Returns:
            True to continue, False to terminate
        """
        # Hard limits
        if turn >= max_turns:
            return False

        if not bot_message:
            return False

        # Heuristic: if the bot gave a long informative response, it's probably done
        if len(bot_message) > 500 and turn > 2:
            # Ask LLM
            prompt = f"""The bot responded:
"{bot_message[:300]}..."

The conversation has {turn} turns. Does this look like a final response or should we continue?
Reply ONLY with "CONTINUE" or "DONE"."""

            response = self.generate(prompt, temperature=0.2, max_tokens=10)
            if response and "DONE" in response.upper():
                return False

        return True

    # ========== SPECIALIZED PROMPTS FOR TESTING ==========

    def analyze_response(self,
                         question: str,
                         bot_response: str,
                         expected_behavior: Optional[str] = None) -> dict:
        """
        Analyze the chatbot response.

        Args:
            question: Question asked
            bot_response: Chatbot response
            expected_behavior: Expected behavior (optional)

        Returns:
            Dict with analysis: {quality, issues, suggestions}
        """
        system = """Sei un analista QA esperto. Analizza le risposte dei chatbot in modo conciso.
Rispondi SOLO in formato JSON valido, senza markdown o altro testo."""

        prompt = f"""Analizza questa interazione chatbot:

DOMANDA: {question}

RISPOSTA CHATBOT:
{bot_response}

{f'COMPORTAMENTO ATTESO: {expected_behavior}' if expected_behavior else ''}

Rispondi con questo JSON:
{{
    "quality": "buona|accettabile|scarsa",
    "is_complete": true/false,
    "is_relevant": true/false,
    "issues": ["lista problemi se presenti"],
    "suggestions": ["suggerimenti miglioramento"]
}}"""

        response = self.generate(prompt, system=system, temperature=0.3)

        if response:
            try:
                # Clean possible markdown
                clean = response.strip()
                if clean.startswith("```"):
                    clean = clean.split("```")[1]
                    if clean.startswith("json"):
                        clean = clean[4:]

                return json.loads(clean)
            except:
                return {
                    "quality": "unknown",
                    "is_complete": True,
                    "is_relevant": True,
                    "issues": [],
                    "suggestions": [],
                    "raw_response": response
                }

        return {"quality": "error", "issues": ["LLM analysis error"]}

    def decide_followup(self,
                        conversation: list[dict],
                        available_followups: list[str],
                        test_context: Optional[str] = None) -> Optional[str]:
        """
        Decide which followup to send based on the conversation.

        Args:
            conversation: Message list [{role, content}, ...]
            available_followups: List of possible followups
            test_context: Test context (optional)

        Returns:
            Followup to send or None if conversation completed
        """
        if not available_followups:
            return None

        system = """Sei un tester di chatbot. Decidi il prossimo messaggio da inviare per testare il bot.
Rispondi SOLO con il numero del followup scelto, o "DONE" se la conversazione è completa."""

        # Format conversation
        conv_text = "\n".join([
            f"{'USER' if m['role'] == 'user' else 'BOT'}: {m['content']}"
            for m in conversation[-6:]  # Last 6 messages
        ])

        # Format followups
        followups_text = "\n".join([
            f"{i+1}. {f}" for i, f in enumerate(available_followups)
        ])

        prompt = f"""Conversazione attuale:
{conv_text}

{f'Contesto test: {test_context}' if test_context else ''}

Followup disponibili:
{followups_text}

Quale followup è più appropriato ora? Rispondi SOLO con il numero (1-{len(available_followups)}) o "DONE"."""

        response = self.generate(prompt, system=system, temperature=0.3, max_tokens=10)

        if response:
            response = response.strip().upper()

            if response == "DONE":
                return None

            try:
                idx = int(response) - 1
                if 0 <= idx < len(available_followups):
                    return available_followups[idx]
            except:
                pass

        # Default: first unused followup
        return available_followups[0] if available_followups else None

    def generate_test_input(self,
                            context: str,
                            input_type: str = "text",
                            constraints: Optional[dict] = None) -> str:
        """
        Generate realistic input for tests.

        Args:
            context: Context (e.g., "The bot asks for email")
            input_type: Input type (text, email, date, number, etc.)
            constraints: Optional constraints (min, max, pattern, etc.)

        Returns:
            Generated input
        """
        # First check if there's a pattern in training
        if self._training and input_type in ['country', 'email', 'confirmation', 'name']:
            for pattern in self._training.patterns:
                if pattern.id == input_type or pattern.name == input_type:
                    if pattern.responses:
                        # Use most common response
                        top = max(pattern.responses, key=lambda r: r.count)
                        return top.text

        system = "Genera dati di test realistici. Rispondi SOLO con il valore, senza spiegazioni."

        type_hints = {
            "email": "un indirizzo email aziendale realistico",
            "date": "una data nel formato richiesto",
            "number": "un numero appropriato",
            "phone": "un numero di telefono italiano",
            "name": "un nome e cognome italiani",
            "address": "un indirizzo italiano completo",
            "country": "un paese europeo",
            "text": "una risposta breve e appropriata"
        }

        hint = type_hints.get(input_type, "una risposta appropriata")

        prompt = f"""Contesto: {context}

Genera {hint}.
{f'Vincoli: {json.dumps(constraints)}' if constraints else ''}

Rispondi SOLO con il valore:"""

        response = self.generate(prompt, system=system, temperature=0.7, max_tokens=100)
        return response.strip() if response else ""

    def evaluate_test_result(self,
                             test_case: dict,
                             conversation: list[dict],
                             final_response: str) -> dict:
        """
        Evaluate the overall result of a test.

        Args:
            test_case: Test definition
            conversation: Complete conversation
            final_response: Last bot response

        Returns:
            Dict with: {passed, score, reason, details}
        """
        system = """Sei un QA tester. Valuta se il test è passato basandoti su:
- Completezza delle risposte
- Pertinenza
- Correttezza
- Gestione errori

Rispondi SOLO in JSON valido."""

        conv_text = "\n".join([
            f"{'USER' if m['role'] == 'user' else 'BOT'}: {m['content'][:200]}"
            for m in conversation
        ])

        prompt = f"""TEST: {test_case.get('question', 'N/A')}
CATEGORIA: {test_case.get('category', 'N/A')}
COMPORTAMENTO ATTESO: {test_case.get('expected', 'Risposta pertinente')}

CONVERSAZIONE:
{conv_text}

ULTIMA RISPOSTA BOT:
{final_response[:500]}

Valuta e rispondi con:
{{
    "passed": true/false,
    "score": 0-100,
    "reason": "spiegazione breve",
    "details": {{
        "completeness": 0-100,
        "relevance": 0-100,
        "correctness": 0-100
    }}
}}"""

        response = self.generate(prompt, system=system, temperature=0.2, max_tokens=300)

        if response:
            try:
                clean = response.strip()
                if clean.startswith("```"):
                    clean = clean.split("```")[1]
                    if clean.startswith("json"):
                        clean = clean[4:]
                return json.loads(clean)
            except:
                pass

        # Default: passed if there's a response
        return {
            "passed": bool(final_response),
            "score": 50 if final_response else 0,
            "reason": "Automatic evaluation failed",
            "details": {}
        }

    def suggest_followups(self,
                          question: str,
                          bot_response: str,
                          category: Optional[str] = None,
                          count: int = 3) -> list[str]:
        """
        Suggest possible followups for a test.

        Args:
            question: Original question
            bot_response: Bot response
            category: Test category (optional)
            count: Number of followups to generate

        Returns:
            List of suggested followups
        """
        system = """Sei un tester. Genera domande di followup per testare un chatbot.
Le domande devono:
- Approfondire l'argomento
- Testare edge cases
- Verificare la coerenza
Rispondi SOLO con le domande, una per riga."""

        prompt = f"""Domanda originale: {question}
{f'Categoria: {category}' if category else ''}

Risposta del bot:
{bot_response[:300]}

Genera {count} domande di followup per testare ulteriormente il bot:"""

        response = self.generate(prompt, system=system, temperature=0.8, max_tokens=300)

        if response:
            lines = [l.strip() for l in response.strip().split('\n') if l.strip()]
            # Remove numbering if present
            cleaned = []
            for line in lines:
                if line[0].isdigit() and (line[1] == '.' or line[1] == ')'):
                    line = line[2:].strip()
                cleaned.append(line)
            return cleaned[:count]

        return []


class OllamaInstaller:
    """Helper for Ollama installation on macOS"""

    @staticmethod
    def check_homebrew() -> bool:
        """Check if Homebrew is installed"""
        import subprocess
        try:
            result = subprocess.run(['which', 'brew'], capture_output=True)
            return result.returncode == 0
        except:
            return False

    @staticmethod
    def check_ollama_installed() -> bool:
        """Check if Ollama is installed"""
        import subprocess
        try:
            result = subprocess.run(['which', 'ollama'], capture_output=True)
            return result.returncode == 0
        except:
            return False

    @staticmethod
    def check_ollama_running() -> bool:
        """Check if Ollama server is running"""
        try:
            response = requests.get("http://localhost:11434/api/tags", timeout=2)
            return response.status_code == 200
        except:
            return False

    @staticmethod
    def get_install_command() -> str:
        """Command to install Ollama"""
        return "brew install ollama"

    @staticmethod
    def get_start_command() -> str:
        """Command to start Ollama"""
        return "ollama serve"

    @staticmethod
    def get_pull_model_command(model: str = "mistral") -> str:
        """Command to download a model"""
        return f"ollama pull {model}"
