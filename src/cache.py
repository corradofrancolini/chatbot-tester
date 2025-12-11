"""
Cache Module - Caching intelligente per ottimizzazione performance

Fornisce:
- Cache in memoria con TTL
- Cache su disco per persistenza
- Decoratori per caching automatico
- Invalidazione intelligente
"""

import json
import hashlib
import time
import threading
from pathlib import Path
from typing import Optional, Any, Callable, TypeVar, Generic
from dataclasses import dataclass, field
from functools import wraps
from datetime import datetime, timedelta


T = TypeVar('T')


@dataclass
class CacheEntry(Generic[T]):
    """Entry singola nella cache"""
    key: str
    value: T
    created_at: float
    expires_at: float
    hits: int = 0
    last_accessed: float = field(default_factory=time.time)


class MemoryCache:
    """
    Cache in memoria con TTL e LRU eviction.

    Features:
    - TTL configurabile per entry
    - Limite dimensione con LRU eviction
    - Thread-safe
    - Statistiche accessi

    Usage:
        cache = MemoryCache(max_size=1000, default_ttl_seconds=300)

        # Set/Get
        cache.set("key", value, ttl=60)
        value = cache.get("key")

        # Con decoratore
        @cache.cached(ttl=120)
        def expensive_function(x):
            return compute(x)
    """

    def __init__(self,
                 max_size: int = 1000,
                 default_ttl_seconds: int = 300):
        self.max_size = max_size
        self.default_ttl = default_ttl_seconds
        self._cache: dict[str, CacheEntry] = {}
        self._lock = threading.RLock()
        self._stats = {
            'hits': 0,
            'misses': 0,
            'evictions': 0
        }

    def get(self, key: str) -> Optional[Any]:
        """
        Ottiene valore dalla cache.

        Args:
            key: Chiave

        Returns:
            Valore o None se non trovato/scaduto
        """
        with self._lock:
            entry = self._cache.get(key)

            if not entry:
                self._stats['misses'] += 1
                return None

            # Check TTL
            if time.time() > entry.expires_at:
                del self._cache[key]
                self._stats['misses'] += 1
                return None

            # Update access stats
            entry.hits += 1
            entry.last_accessed = time.time()
            self._stats['hits'] += 1

            return entry.value

    def set(self,
            key: str,
            value: Any,
            ttl: Optional[int] = None) -> None:
        """
        Salva valore nella cache.

        Args:
            key: Chiave
            value: Valore
            ttl: TTL in secondi (default: default_ttl)
        """
        with self._lock:
            # Evict se necessario
            if len(self._cache) >= self.max_size:
                self._evict_lru()

            ttl_seconds = ttl if ttl is not None else self.default_ttl
            now = time.time()

            self._cache[key] = CacheEntry(
                key=key,
                value=value,
                created_at=now,
                expires_at=now + ttl_seconds
            )

    def delete(self, key: str) -> bool:
        """Elimina entry dalla cache"""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def clear(self) -> None:
        """Svuota la cache"""
        with self._lock:
            self._cache.clear()

    def _evict_lru(self) -> None:
        """Rimuove le entry meno usate di recente"""
        if not self._cache:
            return

        # Trova entry con last_accessed piu vecchio
        oldest_key = min(
            self._cache.keys(),
            key=lambda k: self._cache[k].last_accessed
        )

        del self._cache[oldest_key]
        self._stats['evictions'] += 1

    def cached(self, ttl: Optional[int] = None):
        """
        Decoratore per caching automatico.

        Args:
            ttl: TTL in secondi

        Usage:
            @cache.cached(ttl=60)
            def fetch_data(id):
                return api_call(id)
        """
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args, **kwargs):
                # Genera chiave dalla funzione e argomenti
                key = self._make_key(func.__name__, args, kwargs)

                # Check cache
                cached_value = self.get(key)
                if cached_value is not None:
                    return cached_value

                # Execute e cache
                result = func(*args, **kwargs)
                self.set(key, result, ttl)

                return result

            return wrapper
        return decorator

    def _make_key(self, func_name: str, args: tuple, kwargs: dict) -> str:
        """Genera chiave cache da funzione e argomenti"""
        key_data = {
            'func': func_name,
            'args': str(args),
            'kwargs': str(sorted(kwargs.items()))
        }
        key_str = json.dumps(key_data, sort_keys=True)
        return hashlib.md5(key_str.encode()).hexdigest()

    def get_stats(self) -> dict:
        """Statistiche cache"""
        with self._lock:
            total = self._stats['hits'] + self._stats['misses']
            hit_rate = self._stats['hits'] / total if total > 0 else 0

            return {
                'size': len(self._cache),
                'max_size': self.max_size,
                'hits': self._stats['hits'],
                'misses': self._stats['misses'],
                'hit_rate': f"{hit_rate:.1%}",
                'evictions': self._stats['evictions']
            }

    def cleanup_expired(self) -> int:
        """Rimuove entry scadute. Ritorna numero rimosso."""
        with self._lock:
            now = time.time()
            expired = [k for k, v in self._cache.items() if v.expires_at < now]

            for key in expired:
                del self._cache[key]

            return len(expired)


class DiskCache:
    """
    Cache persistente su disco.

    Salva le entry come file JSON individuali.
    Utile per cache tra sessioni diverse.

    Usage:
        cache = DiskCache(Path("./cache"))
        cache.set("key", {"data": "value"}, ttl=3600)
        value = cache.get("key")
    """

    def __init__(self,
                 cache_dir: Path,
                 default_ttl_seconds: int = 3600):
        self.cache_dir = cache_dir
        self.default_ttl = default_ttl_seconds
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        """Crea directory cache se non esiste"""
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _key_to_path(self, key: str) -> Path:
        """Converte chiave in path file"""
        safe_key = hashlib.md5(key.encode()).hexdigest()
        return self.cache_dir / f"{safe_key}.json"

    def get(self, key: str) -> Optional[Any]:
        """Ottiene valore dalla cache"""
        path = self._key_to_path(key)

        if not path.exists():
            return None

        try:
            with open(path, 'r') as f:
                entry = json.load(f)

            # Check TTL
            if time.time() > entry['expires_at']:
                path.unlink()
                return None

            return entry['value']

        except (json.JSONDecodeError, KeyError):
            path.unlink(missing_ok=True)
            return None

    def set(self,
            key: str,
            value: Any,
            ttl: Optional[int] = None) -> None:
        """Salva valore nella cache"""
        path = self._key_to_path(key)
        ttl_seconds = ttl if ttl is not None else self.default_ttl

        entry = {
            'key': key,
            'value': value,
            'created_at': time.time(),
            'expires_at': time.time() + ttl_seconds
        }

        try:
            with open(path, 'w') as f:
                json.dump(entry, f)
        except (TypeError, ValueError) as e:
            # Valore non serializzabile
            print(f"Cache: impossibile salvare {key}: {e}")

    def delete(self, key: str) -> bool:
        """Elimina entry dalla cache"""
        path = self._key_to_path(key)
        if path.exists():
            path.unlink()
            return True
        return False

    def clear(self) -> None:
        """Svuota la cache"""
        for path in self.cache_dir.glob("*.json"):
            path.unlink()

    def cleanup_expired(self) -> int:
        """Rimuove entry scadute"""
        now = time.time()
        removed = 0

        for path in self.cache_dir.glob("*.json"):
            try:
                with open(path, 'r') as f:
                    entry = json.load(f)

                if entry.get('expires_at', 0) < now:
                    path.unlink()
                    removed += 1
            except:
                path.unlink(missing_ok=True)
                removed += 1

        return removed

    def get_size(self) -> tuple[int, int]:
        """Ritorna (numero file, dimensione totale bytes)"""
        files = list(self.cache_dir.glob("*.json"))
        total_bytes = sum(f.stat().st_size for f in files)
        return len(files), total_bytes


class LangSmithCache:
    """
    Cache specializzata per risposte LangSmith.

    Ottimizza le chiamate API memorizzando:
    - Trace info per ID
    - Report per question
    - Child runs per trace

    Usage:
        cache = LangSmithCache()

        # Wrappa client
        @cache.cache_trace
        def get_trace(trace_id):
            return client.get_trace_by_id(trace_id)
    """

    def __init__(self,
                 trace_ttl: int = 300,       # 5 minuti
                 report_ttl: int = 600,      # 10 minuti
                 child_runs_ttl: int = 300,  # 5 minuti
                 max_entries: int = 500):
        self._trace_cache = MemoryCache(max_entries, trace_ttl)
        self._report_cache = MemoryCache(max_entries, report_ttl)
        self._child_runs_cache = MemoryCache(max_entries, child_runs_ttl)

    def get_trace(self, trace_id: str) -> Optional[Any]:
        """Ottiene trace dalla cache"""
        return self._trace_cache.get(f"trace:{trace_id}")

    def set_trace(self, trace_id: str, trace: Any) -> None:
        """Salva trace nella cache"""
        self._trace_cache.set(f"trace:{trace_id}", trace)

    def get_report(self, question: str) -> Optional[Any]:
        """Ottiene report dalla cache"""
        key = hashlib.md5(question.encode()).hexdigest()
        return self._report_cache.get(f"report:{key}")

    def set_report(self, question: str, report: Any) -> None:
        """Salva report nella cache"""
        key = hashlib.md5(question.encode()).hexdigest()
        self._report_cache.set(f"report:{key}", report)

    def get_child_runs(self, trace_id: str) -> Optional[Any]:
        """Ottiene child runs dalla cache"""
        return self._child_runs_cache.get(f"children:{trace_id}")

    def set_child_runs(self, trace_id: str, runs: Any) -> None:
        """Salva child runs nella cache"""
        self._child_runs_cache.set(f"children:{trace_id}", runs)

    def invalidate_trace(self, trace_id: str) -> None:
        """Invalida tutte le cache per un trace"""
        self._trace_cache.delete(f"trace:{trace_id}")
        self._child_runs_cache.delete(f"children:{trace_id}")

    def clear_all(self) -> None:
        """Svuota tutte le cache"""
        self._trace_cache.clear()
        self._report_cache.clear()
        self._child_runs_cache.clear()

    def get_stats(self) -> dict:
        """Statistiche aggregate"""
        return {
            'trace_cache': self._trace_cache.get_stats(),
            'report_cache': self._report_cache.get_stats(),
            'child_runs_cache': self._child_runs_cache.get_stats()
        }


# Singleton per cache globale
_global_memory_cache: Optional[MemoryCache] = None
_global_langsmith_cache: Optional[LangSmithCache] = None


def get_memory_cache() -> MemoryCache:
    """Ottiene cache in memoria globale"""
    global _global_memory_cache
    if _global_memory_cache is None:
        _global_memory_cache = MemoryCache()
    return _global_memory_cache


def get_langsmith_cache() -> LangSmithCache:
    """Ottiene cache LangSmith globale"""
    global _global_langsmith_cache
    if _global_langsmith_cache is None:
        _global_langsmith_cache = LangSmithCache()
    return _global_langsmith_cache


def cached(ttl: int = 300):
    """
    Decoratore standalone per caching.

    Usage:
        @cached(ttl=60)
        def expensive_function(x):
            return compute(x)
    """
    cache = get_memory_cache()
    return cache.cached(ttl)
