"""
Training System - Pattern Learning per Chatbot Tester

Gestisce:
- Riconoscimento pattern nelle risposte del bot
- Apprendimento risposte utente
- Suggerimenti basati su training precedente
- Persistenza in training_data.json
"""

import re
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field, asdict


@dataclass
class LearnedResponse:
    """Una risposta appresa per un pattern"""
    text: str
    count: int = 1
    last_used: str = ""
    
    def __post_init__(self):
        if not self.last_used:
            self.last_used = datetime.utcnow().isoformat()
    
    def use(self):
        """Incrementa contatore e aggiorna timestamp"""
        self.count += 1
        self.last_used = datetime.utcnow().isoformat()


@dataclass
class Pattern:
    """Pattern riconosciuto nelle domande del bot"""
    id: str
    name: str  # Nome human-readable (es. "country", "email", "confirmation")
    bot_patterns: List[str]  # Regex patterns per riconoscere la domanda
    responses: List[LearnedResponse] = field(default_factory=list)
    
    def matches(self, bot_message: str) -> bool:
        """Verifica se il messaggio del bot matcha questo pattern"""
        msg_lower = bot_message.lower()
        for pattern in self.bot_patterns:
            if re.search(pattern, msg_lower):
                return True
        return False
    
    def get_suggestions(self, limit: int = 5) -> List[LearnedResponse]:
        """Ritorna le risposte più usate"""
        sorted_responses = sorted(
            self.responses, 
            key=lambda r: r.count, 
            reverse=True
        )
        return sorted_responses[:limit]
    
    def add_response(self, text: str) -> LearnedResponse:
        """Aggiunge o aggiorna una risposta"""
        # Cerca risposta esistente
        for resp in self.responses:
            if resp.text.lower() == text.lower():
                resp.use()
                return resp
        
        # Nuova risposta
        new_resp = LearnedResponse(text=text)
        self.responses.append(new_resp)
        return new_resp


@dataclass
class ConversationTurn:
    """Singolo turno di una conversazione registrata"""
    bot: str
    user: Optional[str] = None
    pattern_id: Optional[str] = None


@dataclass
class RecordedConversation:
    """Conversazione completa registrata"""
    test_id: str
    question: str
    turns: List[ConversationTurn] = field(default_factory=list)
    timestamp: str = ""
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat()


class TrainingData:
    """
    Gestisce i dati di training con pattern learning.
    
    Usage:
        training = TrainingData.load(path)
        
        # Riconosce pattern
        pattern = training.match_pattern("Which country are you in?")
        if pattern:
            suggestions = pattern.get_suggestions()
        
        # Impara nuova risposta
        training.learn("Which country?", "Italy")
        
        # Salva
        training.save(path)
    """
    
    # Pattern predefiniti (bootstrap iniziale)
    DEFAULT_PATTERNS = [
        Pattern(
            id="country",
            name="country",
            bot_patterns=[
                r"which country",
                r"what country", 
                r"country are you",
                r"where are you (based|located)",
                r"your (location|country)",
                r"select.{0,20}country"
            ]
        ),
        Pattern(
            id="email",
            name="email",
            bot_patterns=[
                r"(your )?(e-?mail|email address)",
                r"contact.{0,10}(address|info)",
                r"send.{0,10}(to|email)",
                r"provide.{0,10}email"
            ]
        ),
        Pattern(
            id="confirmation",
            name="yes/no",
            bot_patterns=[
                r"(yes|no)\??$",
                r"would you like",
                r"do you want",
                r"shall i",
                r"confirm",
                r"proceed\?",
                r"is (this|that) correct"
            ]
        ),
        Pattern(
            id="date",
            name="date",
            bot_patterns=[
                r"which date",
                r"what date",
                r"when (do|would|did)",
                r"(start|end|from|to) date",
                r"select.{0,10}date"
            ]
        ),
        Pattern(
            id="name",
            name="name",
            bot_patterns=[
                r"(your |the )?(full )?name",
                r"who (is|are)",
                r"employee.{0,10}name"
            ]
        )
    ]
    
    def __init__(self):
        self.patterns: List[Pattern] = []
        self.conversations: List[RecordedConversation] = []
        self._initialize_default_patterns()
    
    def _initialize_default_patterns(self):
        """Inizializza con pattern predefiniti se vuoto"""
        if not self.patterns:
            self.patterns = [
                Pattern(
                    id=p.id,
                    name=p.name,
                    bot_patterns=p.bot_patterns.copy(),
                    responses=[]
                )
                for p in self.DEFAULT_PATTERNS
            ]
    
    @classmethod
    def load(cls, file_path: Path) -> 'TrainingData':
        """Carica training data da file"""
        training = cls()
        
        if not file_path.exists():
            return training
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Carica patterns
            if 'patterns' in data:
                training.patterns = []
                for p in data['patterns']:
                    responses = [
                        LearnedResponse(
                            text=r.get('text', ''),
                            count=r.get('count', 1),
                            last_used=r.get('last_used', '')
                        )
                        for r in p.get('responses', [])
                    ]
                    training.patterns.append(Pattern(
                        id=p.get('id', ''),
                        name=p.get('name', ''),
                        bot_patterns=p.get('bot_patterns', []),
                        responses=responses
                    ))
                
                # Assicura che i pattern di default esistano
                existing_ids = {p.id for p in training.patterns}
                for default_p in cls.DEFAULT_PATTERNS:
                    if default_p.id not in existing_ids:
                        training.patterns.append(Pattern(
                            id=default_p.id,
                            name=default_p.name,
                            bot_patterns=default_p.bot_patterns.copy(),
                            responses=[]
                        ))
            
            # Carica conversazioni
            if 'conversations' in data:
                for c in data['conversations']:
                    turns = [
                        ConversationTurn(
                            bot=t.get('bot', ''),
                            user=t.get('user'),
                            pattern_id=t.get('pattern_id')
                        )
                        for t in c.get('turns', [])
                    ]
                    training.conversations.append(RecordedConversation(
                        test_id=c.get('test_id', ''),
                        question=c.get('question', ''),
                        turns=turns,
                        timestamp=c.get('timestamp', '')
                    ))
            
        except (json.JSONDecodeError, IOError) as e:
            print(f"! Errore caricamento training_data: {e}")
        
        return training
    
    def save(self, file_path: Path) -> bool:
        """Salva training data su file"""
        try:
            data = {
                'patterns': [
                    {
                        'id': p.id,
                        'name': p.name,
                        'bot_patterns': p.bot_patterns,
                        'responses': [
                            {
                                'text': r.text,
                                'count': r.count,
                                'last_used': r.last_used
                            }
                            for r in p.responses
                        ]
                    }
                    for p in self.patterns
                ],
                'conversations': [
                    {
                        'test_id': c.test_id,
                        'question': c.question,
                        'turns': [
                            {
                                'bot': t.bot,
                                'user': t.user,
                                'pattern_id': t.pattern_id
                            }
                            for t in c.turns
                        ],
                        'timestamp': c.timestamp
                    }
                    for c in self.conversations
                ],
                'meta': {
                    'version': '2.0',
                    'updated': datetime.utcnow().isoformat(),
                    'total_patterns': len(self.patterns),
                    'total_conversations': len(self.conversations)
                }
            }
            
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            return True
            
        except IOError as e:
            print(f"✗ Errore salvataggio training_data: {e}")
            return False
    
    def match_pattern(self, bot_message: str) -> Optional[Pattern]:
        """
        Trova il pattern che matcha il messaggio del bot.
        
        Args:
            bot_message: Messaggio del bot
            
        Returns:
            Pattern matchato o None
        """
        for pattern in self.patterns:
            if pattern.matches(bot_message):
                return pattern
        return None
    
    def learn(self, bot_message: str, user_response: str) -> Tuple[Optional[Pattern], bool]:
        """
        Impara una nuova risposta per un pattern.
        
        Args:
            bot_message: Messaggio del bot
            user_response: Risposta dell'utente
            
        Returns:
            (Pattern matchato, True se nuova risposta)
        """
        pattern = self.match_pattern(bot_message)
        
        if pattern:
            # Verifica se è nuova
            existing = any(
                r.text.lower() == user_response.lower() 
                for r in pattern.responses
            )
            
            pattern.add_response(user_response)
            return pattern, not existing
        
        return None, False
    
    def get_suggestions(self, bot_message: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Ottiene suggerimenti per rispondere al bot.
        
        Args:
            bot_message: Messaggio del bot
            limit: Numero massimo suggerimenti
            
        Returns:
            Lista di suggerimenti con formato:
            [{"text": "Italy", "count": 12, "pattern": "country"}, ...]
        """
        pattern = self.match_pattern(bot_message)
        
        if not pattern:
            return []
        
        suggestions = []
        for resp in pattern.get_suggestions(limit):
            suggestions.append({
                'text': resp.text,
                'count': resp.count,
                'pattern': pattern.name
            })
        
        return suggestions
    
    def record_conversation(self, 
                           test_id: str, 
                           question: str,
                           turns: List[Dict[str, str]]) -> None:
        """
        Registra una conversazione completa.
        
        Args:
            test_id: ID del test
            question: Domanda iniziale
            turns: Lista di {"bot": "...", "user": "..."}
        """
        recorded_turns = []
        
        for turn in turns:
            bot_msg = turn.get('bot', '')
            user_msg = turn.get('user')
            
            # Trova pattern per questo turno
            pattern = self.match_pattern(bot_msg) if bot_msg else None
            
            recorded_turns.append(ConversationTurn(
                bot=bot_msg,
                user=user_msg,
                pattern_id=pattern.id if pattern else None
            ))
        
        self.conversations.append(RecordedConversation(
            test_id=test_id,
            question=question,
            turns=recorded_turns
        ))
        
        # Limita storico
        if len(self.conversations) > 500:
            self.conversations = self.conversations[-300:]
    
    def get_stats(self) -> Dict[str, Any]:
        """Ritorna statistiche sul training"""
        total_responses = sum(
            len(p.responses) for p in self.patterns
        )
        total_uses = sum(
            sum(r.count for r in p.responses)
            for p in self.patterns
        )
        
        return {
            'patterns': len(self.patterns),
            'learned_responses': total_responses,
            'total_uses': total_uses,
            'conversations': len(self.conversations)
        }
    
    def add_custom_pattern(self, 
                          pattern_id: str,
                          name: str,
                          bot_patterns: List[str]) -> Pattern:
        """
        Aggiunge un pattern personalizzato.
        
        Args:
            pattern_id: ID univoco
            name: Nome human-readable
            bot_patterns: Lista regex
            
        Returns:
            Pattern creato
        """
        # Verifica se esiste già
        for p in self.patterns:
            if p.id == pattern_id:
                # Aggiorna patterns esistente
                p.bot_patterns = list(set(p.bot_patterns + bot_patterns))
                return p
        
        # Crea nuovo
        new_pattern = Pattern(
            id=pattern_id,
            name=name,
            bot_patterns=bot_patterns,
            responses=[]
        )
        self.patterns.append(new_pattern)
        return new_pattern


class TrainModeUI:
    """
    Helper per UI del Train Mode.
    
    Gestisce la visualizzazione minimalista con suggerimenti contestuali.
    """
    
    def __init__(self, training: TrainingData):
        self.training = training
    
    def format_suggestions(self, bot_message: str, followup: Optional[str] = None) -> str:
        """
        Formatta i suggerimenti per la risposta.
        
        Returns:
            Stringa formattata da stampare
        """
        suggestions = self.training.get_suggestions(bot_message)
        
        lines = []
        
        if suggestions:
            # Pattern riconosciuto
            pattern_name = suggestions[0]['pattern']
            parts = []
            
            for i, sug in enumerate(suggestions[:4], 1):
                count_str = f"×{sug['count']}" if sug['count'] > 1 else ""
                parts.append(f"[{i}] {sug['text']} {count_str}".strip())
            
            lines.append(f"  ~ {pattern_name}?  " + "  ".join(parts))
        
        if followup:
            lines.append(f"  [f] followup: \"{followup[:50]}{'...' if len(followup) > 50 else ''}\"")
        
        if not suggestions and not followup:
            lines.append("  [risposta...]")
        
        return "\n".join(lines)
    
    def format_learned(self, pattern: Optional[Pattern], response: str, is_new: bool) -> str:
        """Formatta feedback su cosa è stato imparato"""
        if pattern:
            if is_new:
                return f"  ✓ {response} (nuovo: {pattern.name} → {response})"
            else:
                return f"  ✓ {response}"
        else:
            return f"  ✓ {response}"
    
    def format_test_header(self, test_id: str, question: str, turn: int, max_turns: int) -> str:
        """Formatta header del test"""
        q_short = question[:60] + "..." if len(question) > 60 else question
        return f"{test_id} │ {q_short}"
    
    def format_message(self, role: str, content: str) -> str:
        """Formatta un messaggio della conversazione"""
        if role.lower() in ('user', 'you'):
            return f"YOU → {content}"
        else:
            return f"BOT ← {content}"
    
    def format_test_complete(self, test_id: str, turns: int, patterns_learned: int) -> str:
        """Formatta riepilogo fine test"""
        parts = [f"✓ {test_id} completato", f"{turns} turni"]
        if patterns_learned > 0:
            parts.append(f"+{patterns_learned} pattern appresi")
        return " │ ".join(parts)
