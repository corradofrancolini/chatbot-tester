"""
Ollama Client - Integrazione con LLM locale

Gestisce:
- Comunicazione con Ollama API
- Generazione risposte per modalità Assisted/Auto
- Analisi conversazioni e decisioni followup
- Valutazione qualità risposte
- Utilizzo training data per in-context learning
"""

import json
import requests
from typing import Optional, Generator, List, Dict, Any, TYPE_CHECKING
from dataclasses import dataclass

if TYPE_CHECKING:
    from .training import TrainingData


@dataclass
class OllamaResponse:
    """Risposta da Ollama"""
    text: str
    model: str
    done: bool
    total_duration: Optional[int] = None
    eval_count: Optional[int] = None


class OllamaClient:
    """
    Client per comunicazione con Ollama.

    Features:
    - Generazione risposte streaming
    - Prompt specializzati per testing chatbot
    - Valutazione automatica risposte
    - Decisione followup intelligente
    - In-context learning da training data

    Usage:
        client = OllamaClient(model="mistral")

        # Verifica disponibilità
        if client.is_available():
            # Imposta training context
            client.set_training_context(training_data)
            
            # Decidi risposta basata su training
            response = client.decide_response(bot_message, conversation)
    """

    def __init__(self,
                 model: str = "mistral",
                 url: str = "http://localhost:11434/api/generate",
                 timeout: int = 120):
        """
        Inizializza il client Ollama.

        Args:
            model: Nome modello (default: mistral)
            url: URL endpoint Ollama
            timeout: Timeout richieste in secondi
        """
        self.model = model
        self.url = url
        self.timeout = timeout
        self.base_url = url.replace("/api/generate", "")
        
        # Training context per in-context learning
        self._training: Optional['TrainingData'] = None

    def set_training_context(self, training: 'TrainingData') -> None:
        """
        Imposta il training data per in-context learning.
        
        Args:
            training: TrainingData con pattern e risposte apprese
        """
        self._training = training

    def is_available(self) -> bool:
        """
        Verifica se Ollama è raggiungibile e il modello è disponibile.

        Returns:
            True se Ollama è pronto
        """
        try:
            # Check server
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if response.status_code != 200:
                return False

            # Check modello
            models = response.json().get('models', [])
            model_names = [m.get('name', '') for m in models]

            return self.model in model_names
        except:
            return False

    def get_available_models(self) -> list[str]:
        """Ritorna lista modelli disponibili in Ollama"""
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
        Genera una risposta.

        Args:
            prompt: Prompt utente
            system: System prompt opzionale
            temperature: Creatività (0-1)
            max_tokens: Lunghezza massima risposta

        Returns:
            Testo generato o None se errore
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
                print(f"Errore Ollama: {response.status_code}")
                return None
        except Exception as e:
            print(f"Errore connessione Ollama: {e}")
            return None

    def generate_stream(self,
                        prompt: str,
                        system: Optional[str] = None,
                        temperature: float = 0.7) -> Generator[str, None, None]:
        """
        Genera risposta in streaming.

        Args:
            prompt: Prompt utente
            system: System prompt opzionale
            temperature: Creatività (0-1)

        Yields:
            Chunks di testo
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
            print(f"Errore streaming Ollama: {e}")

    # ========== IN-CONTEXT LEARNING DA TRAINING ==========

    def _build_training_context(self) -> str:
        """
        Costruisce il contesto di training per il prompt.
        
        Returns:
            Stringa con esempi appresi formattati
        """
        if not self._training:
            return ""
        
        lines = ["RISPOSTE APPRESE DA TRAINING:"]
        
        for pattern in self._training.patterns:
            if pattern.responses:
                # Prendi le top 3 risposte più usate
                top_responses = sorted(
                    pattern.responses, 
                    key=lambda r: r.count, 
                    reverse=True
                )[:3]
                
                responses_str = ", ".join([
                    f'"{r.text}" (usato {r.count}x)' 
                    for r in top_responses
                ])
                
                lines.append(f"- Quando il bot chiede '{pattern.name}' → rispondi con: {responses_str}")
        
        if len(lines) == 1:
            return ""  # Nessun pattern con risposte
        
        return "\n".join(lines)

    def _is_final_response(self, bot_message: str) -> bool:
        """
        Euristica per capire se il bot ha dato una risposta finale.
        
        Indicators:
        - Contiene "Source:" (citazione)
        - Messaggio lungo (>300 chars)
        - Contiene URL
        - Frasi di chiusura tipiche
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
        
        # Se contiene source + è lungo, è sicuramente finale
        if "source:" in msg_lower and len(bot_message) > 200:
            return True
        
        # Altrimenti se almeno 2 indicatori
        return sum(indicators) >= 2

    def decide_response(self,
                        bot_message: str,
                        conversation: List[Dict[str, str]],
                        followups: Optional[List[str]] = None,
                        test_context: Optional[str] = None) -> Optional[str]:
        """
        Decide la risposta da dare al bot usando training context.
        
        Questo è il metodo principale per Auto/Assisted mode.
        Usa in-context learning con gli esempi dal training.
        
        Args:
            bot_message: Ultimo messaggio del bot
            conversation: Conversazione finora [{role, content}, ...]
            followups: Followup predefiniti disponibili (opzionale)
            test_context: Contesto/categoria del test (opzionale)
            
        Returns:
            Risposta da inviare, o None se conversazione completata
        """
        # Check se il bot ha dato una risposta finale
        if self._is_final_response(bot_message):
            return None
        
        # Prima controlla se c'è un pattern match nel training
        if self._training:
            suggestions = self._training.get_suggestions(bot_message, limit=1)
            if suggestions:
                # Pattern riconosciuto - usa la risposta più comune
                return suggestions[0]['text']
        
        # Altrimenti usa LLM con training context
        training_context = self._build_training_context()
        
        system = """Sei un tester automatico di chatbot. Il tuo compito è rispondere alle domande del bot per completare il test.

REGOLE:
1. Rispondi in modo conciso e realistico
2. Se il bot chiede informazioni specifiche (paese, email, data), usa i pattern appresi
3. Se la conversazione sembra completa, rispondi con "DONE"
4. Non fare domande, rispondi direttamente

Rispondi SOLO con il testo da inviare, oppure "DONE" se il test è completato."""

        # Formatta conversazione recente
        conv_text = "\n".join([
            f"{'USER' if m['role'] == 'user' else 'BOT'}: {m['content'][:200]}"
            for m in conversation[-6:]
        ])
        
        # Costruisci prompt
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
            
            # Check se conversazione completata
            if response.upper() == "DONE":
                return None
            
            # Rimuovi virgolette se presenti
            if response.startswith('"') and response.endswith('"'):
                response = response[1:-1]
            
            # Impara la risposta se c'è un pattern match
            if self._training:
                self._training.learn(bot_message, response)
            
            return response
        
        # Fallback: usa primo followup se disponibile
        if followups:
            return followups[0]
        
        return None

    def should_continue(self,
                        bot_message: str,
                        conversation: List[Dict[str, str]],
                        turn: int,
                        max_turns: int = 15) -> bool:
        """
        Decide se continuare la conversazione o terminare.
        
        Args:
            bot_message: Ultimo messaggio del bot
            conversation: Conversazione finora
            turn: Turno corrente
            max_turns: Massimo turni
            
        Returns:
            True se continuare, False se terminare
        """
        # Limiti hard
        if turn >= max_turns:
            return False
        
        if not bot_message:
            return False
        
        # Euristica: se il bot ha dato una risposta lunga e informativa, probabilmente è finito
        if len(bot_message) > 500 and turn > 2:
            # Chiedi a LLM
            prompt = f"""Il bot ha risposto:
"{bot_message[:300]}..."

La conversazione ha {turn} turni. Sembra una risposta finale o serve continuare?
Rispondi SOLO con "CONTINUE" o "DONE"."""
            
            response = self.generate(prompt, temperature=0.2, max_tokens=10)
            if response and "DONE" in response.upper():
                return False
        
        return True

    # ========== PROMPT SPECIALIZZATI PER TESTING ==========

    def analyze_response(self,
                         question: str,
                         bot_response: str,
                         expected_behavior: Optional[str] = None) -> dict:
        """
        Analizza la risposta del chatbot.

        Args:
            question: Domanda posta
            bot_response: Risposta del chatbot
            expected_behavior: Comportamento atteso (opzionale)

        Returns:
            Dict con analisi: {quality, issues, suggestions}
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
                # Pulisci eventuale markdown
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

        return {"quality": "error", "issues": ["Errore analisi LLM"]}

    def decide_followup(self,
                        conversation: list[dict],
                        available_followups: list[str],
                        test_context: Optional[str] = None) -> Optional[str]:
        """
        Decide quale followup inviare basandosi sulla conversazione.

        Args:
            conversation: Lista messaggi [{role, content}, ...]
            available_followups: Lista possibili followup
            test_context: Contesto del test (opzionale)

        Returns:
            Followup da inviare o None se conversazione completata
        """
        if not available_followups:
            return None

        system = """Sei un tester di chatbot. Decidi il prossimo messaggio da inviare per testare il bot.
Rispondi SOLO con il numero del followup scelto, o "DONE" se la conversazione è completa."""

        # Formatta conversazione
        conv_text = "\n".join([
            f"{'USER' if m['role'] == 'user' else 'BOT'}: {m['content']}"
            for m in conversation[-6:]  # Ultimi 6 messaggi
        ])

        # Formatta followups
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

        # Default: primo followup non ancora usato
        return available_followups[0] if available_followups else None

    def generate_test_input(self,
                            context: str,
                            input_type: str = "text",
                            constraints: Optional[dict] = None) -> str:
        """
        Genera input realistico per test.

        Args:
            context: Contesto (es. "Il bot chiede l'email")
            input_type: Tipo input (text, email, date, number, etc.)
            constraints: Vincoli opzionali (min, max, pattern, etc.)

        Returns:
            Input generato
        """
        # Prima controlla se c'è un pattern nel training
        if self._training and input_type in ['country', 'email', 'confirmation', 'name']:
            for pattern in self._training.patterns:
                if pattern.id == input_type or pattern.name == input_type:
                    if pattern.responses:
                        # Usa la risposta più comune
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
        Valuta il risultato complessivo di un test.

        Args:
            test_case: Definizione del test
            conversation: Conversazione completa
            final_response: Ultima risposta del bot

        Returns:
            Dict con: {passed, score, reason, details}
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

        # Default: passato se c'è una risposta
        return {
            "passed": bool(final_response),
            "score": 50 if final_response else 0,
            "reason": "Valutazione automatica fallita",
            "details": {}
        }

    def suggest_followups(self,
                          question: str,
                          bot_response: str,
                          category: Optional[str] = None,
                          count: int = 3) -> list[str]:
        """
        Suggerisce possibili followup per un test.

        Args:
            question: Domanda originale
            bot_response: Risposta del bot
            category: Categoria test (opzionale)
            count: Numero followup da generare

        Returns:
            Lista di followup suggeriti
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
            # Rimuovi numerazione se presente
            cleaned = []
            for line in lines:
                if line[0].isdigit() and (line[1] == '.' or line[1] == ')'):
                    line = line[2:].strip()
                cleaned.append(line)
            return cleaned[:count]

        return []


class OllamaInstaller:
    """Helper per installazione Ollama su macOS"""

    @staticmethod
    def check_homebrew() -> bool:
        """Verifica se Homebrew è installato"""
        import subprocess
        try:
            result = subprocess.run(['which', 'brew'], capture_output=True)
            return result.returncode == 0
        except:
            return False

    @staticmethod
    def check_ollama_installed() -> bool:
        """Verifica se Ollama è installato"""
        import subprocess
        try:
            result = subprocess.run(['which', 'ollama'], capture_output=True)
            return result.returncode == 0
        except:
            return False

    @staticmethod
    def check_ollama_running() -> bool:
        """Verifica se Ollama server è in esecuzione"""
        try:
            response = requests.get("http://localhost:11434/api/tags", timeout=2)
            return response.status_code == 200
        except:
            return False

    @staticmethod
    def get_install_command() -> str:
        """Comando per installare Ollama"""
        return "brew install ollama"

    @staticmethod
    def get_start_command() -> str:
        """Comando per avviare Ollama"""
        return "ollama serve"

    @staticmethod
    def get_pull_model_command(model: str = "mistral") -> str:
        """Comando per scaricare un modello"""
        return f"ollama pull {model}"
