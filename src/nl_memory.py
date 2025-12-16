"""
Conversation Memory - Gestione memoria conversazionale per l'agente.

Mantiene il contesto della conversazione tra i turni:
- Ultimi N messaggi (sliding window)
- Stato della sessione (progetto attivo, ultimo run, etc.)
- Compressione turni vecchi in summary
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum


class TurnRole(Enum):
    """Ruoli nei turni di conversazione"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


@dataclass
class ConversationTurn:
    """Singolo turno di conversazione"""
    role: TurnRole
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role.value,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ConversationTurn':
        return cls(
            role=TurnRole(data["role"]),
            content=data["content"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            metadata=data.get("metadata", {})
        )


@dataclass
class SessionState:
    """Stato della sessione corrente"""
    active_project: Optional[str] = None
    last_run_number: Optional[int] = None
    last_action: Optional[str] = None
    last_action_result: Optional[str] = None
    last_action_success: Optional[bool] = None
    pending_clarification: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "active_project": self.active_project,
            "last_run_number": self.last_run_number,
            "last_action": self.last_action,
            "last_action_result": self.last_action_result,
            "last_action_success": self.last_action_success,
            "pending_clarification": self.pending_clarification
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SessionState':
        return cls(**data)

    def update(self, **kwargs) -> None:
        """Aggiorna stato con i valori forniti"""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)


class ConversationMemory:
    """
    Gestisce la memoria della conversazione.

    Features:
    - Sliding window degli ultimi N turni
    - Tracking dello stato sessione
    - Formattazione contesto per LLM
    """

    def __init__(self, max_turns: int = 20):
        """
        Inizializza memoria conversazionale.

        Args:
            max_turns: Numero massimo di turni da mantenere
        """
        self.max_turns = max_turns
        self.turns: List[ConversationTurn] = []
        self.state = SessionState()

    def add_user_message(self, content: str, metadata: Dict = None) -> None:
        """Aggiunge messaggio utente"""
        self._add_turn(TurnRole.USER, content, metadata)

    def add_assistant_message(self, content: str, metadata: Dict = None) -> None:
        """Aggiunge messaggio assistente"""
        self._add_turn(TurnRole.ASSISTANT, content, metadata)

    def add_system_message(self, content: str, metadata: Dict = None) -> None:
        """Aggiunge messaggio di sistema"""
        self._add_turn(TurnRole.SYSTEM, content, metadata)

    def _add_turn(self, role: TurnRole, content: str, metadata: Dict = None) -> None:
        """Aggiunge un turno, rimuove i più vecchi se necessario"""
        turn = ConversationTurn(
            role=role,
            content=content,
            metadata=metadata or {}
        )
        self.turns.append(turn)

        # Mantieni solo ultimi max_turns
        if len(self.turns) > self.max_turns:
            self.turns = self.turns[-self.max_turns:]

    def update_state(self, **kwargs) -> None:
        """Aggiorna stato sessione"""
        self.state.update(**kwargs)

    def get_context_for_llm(self, include_state: bool = True) -> str:
        """
        Formatta contesto per prompt LLM.

        Args:
            include_state: Includere stato sessione

        Returns:
            Stringa formattata con contesto conversazionale
        """
        parts = []

        # Stato sessione
        if include_state:
            state_parts = []
            if self.state.active_project:
                state_parts.append(f"Progetto attivo: {self.state.active_project}")
            if self.state.last_run_number:
                state_parts.append(f"Ultimo run: {self.state.last_run_number}")
            if self.state.last_action:
                result = "successo" if self.state.last_action_success else "fallito"
                state_parts.append(f"Ultima azione: {self.state.last_action} ({result})")
            if state_parts:
                parts.append("STATO SESSIONE:\n" + "\n".join(f"  - {s}" for s in state_parts))

        # Conversazione recente (ultimi 10 turni per non sovraccaricare)
        recent_turns = self.turns[-10:] if len(self.turns) > 10 else self.turns
        if recent_turns:
            conv_parts = []
            for turn in recent_turns:
                role_name = {
                    TurnRole.USER: "Utente",
                    TurnRole.ASSISTANT: "Assistente",
                    TurnRole.SYSTEM: "Sistema"
                }.get(turn.role, "?")
                conv_parts.append(f"{role_name}: {turn.content}")

            parts.append("CONVERSAZIONE RECENTE:\n" + "\n".join(conv_parts))

        return "\n\n".join(parts) if parts else "Nessun contesto precedente."

    def get_last_user_message(self) -> Optional[str]:
        """Ritorna ultimo messaggio utente"""
        for turn in reversed(self.turns):
            if turn.role == TurnRole.USER:
                return turn.content
        return None

    def get_last_assistant_message(self) -> Optional[str]:
        """Ritorna ultimo messaggio assistente"""
        for turn in reversed(self.turns):
            if turn.role == TurnRole.ASSISTANT:
                return turn.content
        return None

    def clear(self) -> None:
        """Reset completo"""
        self.turns = []
        self.state = SessionState()

    def clear_turns(self) -> None:
        """Reset solo turni, mantiene stato"""
        self.turns = []

    def to_dict(self) -> Dict[str, Any]:
        """Per persistenza"""
        return {
            "max_turns": self.max_turns,
            "turns": [t.to_dict() for t in self.turns],
            "state": self.state.to_dict()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ConversationMemory':
        """Ripristina da persistenza"""
        memory = cls(max_turns=data.get("max_turns", 20))
        memory.turns = [ConversationTurn.from_dict(t) for t in data.get("turns", [])]
        memory.state = SessionState.from_dict(data.get("state", {}))
        return memory

    def __len__(self) -> int:
        return len(self.turns)

    def __bool__(self) -> bool:
        return len(self.turns) > 0 or self.state.active_project is not None
