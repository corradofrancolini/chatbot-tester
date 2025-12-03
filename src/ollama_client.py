"""
Ollama Client - Integrazione con LLM locale

Gestisce:
- Comunicazione con Ollama API
- Generazione risposte per modalità Assisted/Auto
- Analisi conversazioni e decisioni followup
- Valutazione qualità risposte
"""

import json
import requests
from typing import Optional, Generator
from dataclasses import dataclass


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
    
    Usage:
        client = OllamaClient(model="mistral")
        
        # Verifica disponibilità
        if client.is_available():
            response = client.generate("Analizza questa risposta...")
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
            model_names = [m.get('name', '').split(':')[0] for m in models]
            
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
        system = "Genera dati di test realistici. Rispondi SOLO con il valore, senza spiegazioni."
        
        type_hints = {
            "email": "un indirizzo email aziendale realistico",
            "date": "una data nel formato richiesto",
            "number": "un numero appropriato",
            "phone": "un numero di telefono italiano",
            "name": "un nome e cognome italiani",
            "address": "un indirizzo italiano completo",
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
