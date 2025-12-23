"""
Baselines (Golden Answers) - Cache e gestione delle risposte di riferimento.

Le baseline sono risposte "golden" marcate manualmente su Google Sheets
che servono come riferimento per la valutazione automatica dei test.

Funzionalità:
- Cache in-memory con TTL configurabile
- Fetch da Google Sheets (colonna BASELINE = ✓)
- Lookup per test_id
- Auto-refresh quando la cache scade
"""

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, TYPE_CHECKING
from pathlib import Path

if TYPE_CHECKING:
    from .sheets_client import GoogleSheetsClient


@dataclass
class Baseline:
    """Una baseline (golden answer) per un test."""
    test_id: str
    question: str
    conversation: str  # Risposta golden (conversazione completa)
    run_number: int  # RUN da cui proviene
    date: str  # Data del test originale
    prompt_version: str = ""
    model_version: str = ""
    notes: str = ""

    @property
    def answer(self) -> str:
        """Estrae solo la risposta del bot dalla conversazione."""
        lines = self.conversation.split('\n')
        bot_responses = []
        for line in lines:
            if line.startswith('BOT:'):
                bot_responses.append(line[4:].strip())
        return '\n'.join(bot_responses) if bot_responses else self.conversation


@dataclass
class BaselinesCache:
    """
    Cache delle baseline con TTL (Time To Live).

    Uso:
        cache = BaselinesCache(ttl_seconds=300)  # 5 minuti
        cache.load(sheets_client, project_name)

        baseline = cache.get("TEST_001")
        if baseline:
            print(f"Golden answer: {baseline.answer}")
    """
    ttl_seconds: int = 300  # Default: 5 minuti
    _baselines: Dict[str, Baseline] = field(default_factory=dict)
    _loaded_at: float = 0.0
    _project: str = ""

    @property
    def is_expired(self) -> bool:
        """True se la cache è scaduta o mai caricata."""
        if self._loaded_at == 0:
            return True
        return (time.time() - self._loaded_at) > self.ttl_seconds

    @property
    def age_seconds(self) -> float:
        """Età della cache in secondi."""
        if self._loaded_at == 0:
            return float('inf')
        return time.time() - self._loaded_at

    @property
    def count(self) -> int:
        """Numero di baseline in cache."""
        return len(self._baselines)

    def get(self, test_id: str) -> Optional[Baseline]:
        """
        Ottiene la baseline per un test_id.

        Args:
            test_id: ID del test (es. "TEST_001")

        Returns:
            Baseline se esiste, None altrimenti
        """
        return self._baselines.get(test_id)

    def has(self, test_id: str) -> bool:
        """True se esiste una baseline per questo test_id."""
        return test_id in self._baselines

    def all(self) -> Dict[str, Baseline]:
        """Ritorna tutte le baseline (copia)."""
        return dict(self._baselines)

    def clear(self) -> None:
        """Svuota la cache."""
        self._baselines.clear()
        self._loaded_at = 0.0
        self._project = ""

    def load(
        self,
        sheets_client: "GoogleSheetsClient",
        project_name: str,
        force: bool = False
    ) -> int:
        """
        Carica le baseline da Google Sheets.

        Cerca in tutte le RUN del progetto le righe con BASELINE = ✓
        e le memorizza in cache.

        Args:
            sheets_client: Client Google Sheets autenticato
            project_name: Nome progetto
            force: Se True, ricarica anche se cache non scaduta

        Returns:
            Numero di baseline caricate
        """
        # Skip se cache valida e stesso progetto
        if not force and not self.is_expired and self._project == project_name:
            return self.count

        self._baselines.clear()
        self._project = project_name

        try:
            # Usa il metodo del sheets_client per ottenere tutte le baseline
            baselines_data = sheets_client.get_all_baselines()

            for data in baselines_data:
                baseline = Baseline(
                    test_id=data.get('test_id', ''),
                    question=data.get('question', ''),
                    conversation=data.get('conversation', ''),
                    run_number=data.get('run_number', 0),
                    date=data.get('date', ''),
                    prompt_version=data.get('prompt_version', ''),
                    model_version=data.get('model_version', ''),
                    notes=data.get('notes', '')
                )

                if baseline.test_id:
                    # Se esistono più baseline per lo stesso test, tieni la più recente
                    existing = self._baselines.get(baseline.test_id)
                    if not existing or baseline.run_number > existing.run_number:
                        self._baselines[baseline.test_id] = baseline

            self._loaded_at = time.time()
            return self.count

        except Exception as e:
            print(f"Errore caricamento baseline: {e}")
            self._loaded_at = time.time()  # Evita retry continui
            return 0

    def refresh_if_needed(
        self,
        sheets_client: "GoogleSheetsClient",
        project_name: str
    ) -> bool:
        """
        Ricarica la cache solo se scaduta.

        Args:
            sheets_client: Client Google Sheets
            project_name: Nome progetto

        Returns:
            True se la cache è stata ricaricata
        """
        if self.is_expired or self._project != project_name:
            self.load(sheets_client, project_name, force=True)
            return True
        return False

    def summary(self) -> str:
        """Ritorna un riepilogo della cache."""
        if not self._baselines:
            return "Cache baseline vuota"

        age = self.age_seconds
        if age == float('inf'):
            age_str = "mai caricata"
        elif age < 60:
            age_str = f"{age:.0f}s fa"
        else:
            age_str = f"{age/60:.1f}min fa"

        expired = " (SCADUTA)" if self.is_expired else ""

        return f"Cache: {self.count} baseline, caricata {age_str}{expired}"


# Singleton globale per uso semplificato
_global_cache: Optional[BaselinesCache] = None


def get_baselines_cache(ttl_seconds: int = 300) -> BaselinesCache:
    """
    Ottiene l'istanza globale della cache baseline.

    Args:
        ttl_seconds: TTL in secondi (usato solo alla prima chiamata)

    Returns:
        Istanza singleton di BaselinesCache
    """
    global _global_cache
    if _global_cache is None:
        _global_cache = BaselinesCache(ttl_seconds=ttl_seconds)
    return _global_cache


def get_baseline(
    test_id: str,
    sheets_client: "GoogleSheetsClient",
    project_name: str,
    ttl_seconds: int = 300
) -> Optional[Baseline]:
    """
    Funzione di convenienza per ottenere una baseline.

    Gestisce automaticamente la cache e il refresh.

    Args:
        test_id: ID del test
        sheets_client: Client Google Sheets
        project_name: Nome progetto
        ttl_seconds: TTL cache in secondi

    Returns:
        Baseline se esiste, None altrimenti

    Esempio:
        baseline = get_baseline("TEST_001", sheets_client, "silicon-b")
        if baseline:
            expected_answer = baseline.answer
    """
    cache = get_baselines_cache(ttl_seconds)
    cache.refresh_if_needed(sheets_client, project_name)
    return cache.get(test_id)


def preload_baselines(
    sheets_client: "GoogleSheetsClient",
    project_name: str,
    ttl_seconds: int = 300
) -> int:
    """
    Pre-carica tutte le baseline in cache.

    Utile all'inizio di una sessione di test per evitare
    chiamate API durante l'esecuzione.

    Args:
        sheets_client: Client Google Sheets
        project_name: Nome progetto
        ttl_seconds: TTL cache

    Returns:
        Numero di baseline caricate
    """
    cache = get_baselines_cache(ttl_seconds)
    return cache.load(sheets_client, project_name, force=True)
