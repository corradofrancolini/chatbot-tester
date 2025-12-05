"""
Health Check Module - Verifica disponibilità servizi

Fornisce:
- Health checks per tutti i servizi (Ollama, LangSmith, Google, Chatbot URL)
- Circuit breaker per gestire fallimenti
- Auto-retry con backoff esponenziale
- Graceful degradation quando servizi non disponibili

Usage:
    health = HealthChecker(config)

    # Check singolo servizio
    result = health.check_ollama()

    # Check tutti i servizi
    status = health.check_all()
    if not status.can_run:
        print(status.blocking_issues)

    # Con circuit breaker
    with health.circuit_breaker("google_sheets"):
        sheets_client.append_row(...)
"""

import time
import requests
from enum import Enum
from typing import Optional, Dict, List, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import wraps


class ServiceStatus(Enum):
    """Stato di un servizio"""
    HEALTHY = "healthy"       # Funzionante
    DEGRADED = "degraded"     # Funziona con limitazioni
    UNHEALTHY = "unhealthy"   # Non funziona
    UNKNOWN = "unknown"       # Non verificato
    DISABLED = "disabled"     # Disabilitato dall'utente


@dataclass
class HealthCheckResult:
    """Risultato di un singolo health check"""
    service: str
    status: ServiceStatus
    message: str = ""
    latency_ms: int = 0
    details: Dict[str, Any] = field(default_factory=dict)
    checked_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def is_healthy(self) -> bool:
        return self.status in (ServiceStatus.HEALTHY, ServiceStatus.DISABLED)

    @property
    def is_usable(self) -> bool:
        """Il servizio può essere usato (anche se degradato)"""
        return self.status in (ServiceStatus.HEALTHY, ServiceStatus.DEGRADED, ServiceStatus.DISABLED)


@dataclass
class SystemHealth:
    """Stato complessivo del sistema"""
    checks: Dict[str, HealthCheckResult] = field(default_factory=dict)
    checked_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def all_healthy(self) -> bool:
        """Tutti i servizi sono healthy"""
        return all(c.is_healthy for c in self.checks.values())

    @property
    def can_run(self) -> bool:
        """Il sistema può eseguire test (servizi critici OK)"""
        critical = ["chatbot_url", "browser"]
        return all(
            self.checks.get(s, HealthCheckResult(s, ServiceStatus.UNKNOWN)).is_usable
            for s in critical
        )

    @property
    def blocking_issues(self) -> List[str]:
        """Lista problemi che bloccano l'esecuzione"""
        issues = []
        for name, check in self.checks.items():
            if not check.is_usable:
                issues.append(f"{name}: {check.message}")
        return issues

    @property
    def warnings(self) -> List[str]:
        """Lista warning (servizi degradati)"""
        warnings = []
        for name, check in self.checks.items():
            if check.status == ServiceStatus.DEGRADED:
                warnings.append(f"{name}: {check.message}")
        return warnings

    def get_summary(self) -> Dict[str, str]:
        """Riepilogo per UI"""
        return {
            name: check.status.value
            for name, check in self.checks.items()
        }


class CircuitState(Enum):
    """Stati del circuit breaker"""
    CLOSED = "closed"       # Normale, lascia passare
    OPEN = "open"           # Aperto, blocca chiamate
    HALF_OPEN = "half_open" # Test se il servizio è tornato


@dataclass
class CircuitBreaker:
    """
    Circuit breaker per un singolo servizio.

    Previene cascate di errori aprendo il circuito dopo
    troppi fallimenti consecutivi.
    """
    name: str
    failure_threshold: int = 3      # Fallimenti prima di aprire
    recovery_timeout: int = 30      # Secondi prima di riprovare
    half_open_max_calls: int = 1    # Chiamate test in half-open

    # Stato interno
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: Optional[datetime] = None
    half_open_calls: int = 0

    def record_success(self):
        """Registra una chiamata riuscita"""
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.half_open_max_calls:
                self._close()
        else:
            self.failure_count = 0
            self.success_count += 1

    def record_failure(self):
        """Registra un fallimento"""
        self.failure_count += 1
        self.last_failure_time = datetime.now()

        if self.state == CircuitState.HALF_OPEN:
            self._open()
        elif self.failure_count >= self.failure_threshold:
            self._open()

    def can_execute(self) -> bool:
        """Verifica se è possibile eseguire una chiamata"""
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            # Controlla se è passato il timeout
            if self.last_failure_time:
                elapsed = (datetime.now() - self.last_failure_time).total_seconds()
                if elapsed >= self.recovery_timeout:
                    self._half_open()
                    return True
            return False

        if self.state == CircuitState.HALF_OPEN:
            return self.half_open_calls < self.half_open_max_calls

        return False

    def _open(self):
        """Apre il circuito"""
        self.state = CircuitState.OPEN
        self.half_open_calls = 0

    def _close(self):
        """Chiude il circuito"""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.half_open_calls = 0

    def _half_open(self):
        """Mette il circuito in half-open"""
        self.state = CircuitState.HALF_OPEN
        self.half_open_calls = 0
        self.success_count = 0


class CircuitBreakerOpen(Exception):
    """Eccezione quando il circuit breaker è aperto"""
    def __init__(self, service: str, retry_after: int):
        self.service = service
        self.retry_after = retry_after
        super().__init__(f"Circuit breaker open for {service}. Retry after {retry_after}s")


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    exponential_base: float = 2.0,
    retryable_exceptions: tuple = (requests.RequestException, TimeoutError, ConnectionError)
):
    """
    Decorator per retry con backoff esponenziale.

    Args:
        max_retries: Numero massimo di tentativi
        base_delay: Delay iniziale in secondi
        max_delay: Delay massimo in secondi
        exponential_base: Base per l'esponente
        retryable_exceptions: Eccezioni che triggerano retry
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exception = e

                    if attempt < max_retries:
                        delay = min(
                            base_delay * (exponential_base ** attempt),
                            max_delay
                        )
                        time.sleep(delay)
                    else:
                        raise

            raise last_exception
        return wrapper
    return decorator


class HealthChecker:
    """
    Health checker centralizzato per tutti i servizi.

    Gestisce:
    - Verifica disponibilità servizi
    - Circuit breaker per ogni servizio
    - Caching risultati health check
    """

    def __init__(self,
                 chatbot_url: str = "",
                 ollama_url: str = "http://localhost:11434",
                 langsmith_api_key: str = "",
                 google_credentials_path: str = "",
                 cache_ttl: int = 30):
        """
        Args:
            chatbot_url: URL del chatbot da testare
            ollama_url: URL di Ollama
            langsmith_api_key: API key LangSmith
            google_credentials_path: Path alle credenziali Google
            cache_ttl: Tempo di cache per i risultati (secondi)
        """
        self.chatbot_url = chatbot_url
        self.ollama_url = ollama_url
        self.langsmith_api_key = langsmith_api_key
        self.google_credentials_path = google_credentials_path
        self.cache_ttl = cache_ttl

        # Circuit breakers per servizio
        self.circuit_breakers: Dict[str, CircuitBreaker] = {
            "ollama": CircuitBreaker("ollama", failure_threshold=3, recovery_timeout=30),
            "langsmith": CircuitBreaker("langsmith", failure_threshold=5, recovery_timeout=60),
            "google_sheets": CircuitBreaker("google_sheets", failure_threshold=3, recovery_timeout=60),
            "chatbot": CircuitBreaker("chatbot", failure_threshold=5, recovery_timeout=30),
        }

        # Cache risultati
        self._cache: Dict[str, HealthCheckResult] = {}
        self._cache_time: Dict[str, datetime] = {}

    def _is_cached(self, service: str) -> bool:
        """Verifica se il risultato è in cache e valido"""
        if service not in self._cache_time:
            return False
        elapsed = (datetime.now() - self._cache_time[service]).total_seconds()
        return elapsed < self.cache_ttl

    def _cache_result(self, service: str, result: HealthCheckResult):
        """Salva risultato in cache"""
        self._cache[service] = result
        self._cache_time[service] = datetime.now()

    def check_chatbot_url(self, force: bool = False) -> HealthCheckResult:
        """
        Verifica raggiungibilità URL chatbot.
        """
        service = "chatbot_url"

        if not force and self._is_cached(service):
            return self._cache[service]

        if not self.chatbot_url:
            result = HealthCheckResult(
                service=service,
                status=ServiceStatus.UNHEALTHY,
                message="URL chatbot non configurato"
            )
            self._cache_result(service, result)
            return result

        start = time.time()
        try:
            response = requests.get(self.chatbot_url, timeout=10)
            latency = int((time.time() - start) * 1000)

            if response.status_code == 200:
                result = HealthCheckResult(
                    service=service,
                    status=ServiceStatus.HEALTHY,
                    message=f"OK ({latency}ms)",
                    latency_ms=latency
                )
            else:
                result = HealthCheckResult(
                    service=service,
                    status=ServiceStatus.DEGRADED,
                    message=f"HTTP {response.status_code}",
                    latency_ms=latency
                )
        except requests.Timeout:
            result = HealthCheckResult(
                service=service,
                status=ServiceStatus.UNHEALTHY,
                message="Timeout (>10s)"
            )
        except requests.RequestException as e:
            result = HealthCheckResult(
                service=service,
                status=ServiceStatus.UNHEALTHY,
                message=f"Errore: {str(e)[:50]}"
            )

        self._cache_result(service, result)
        return result

    def check_ollama(self, force: bool = False) -> HealthCheckResult:
        """
        Verifica disponibilità Ollama.
        """
        service = "ollama"

        if not force and self._is_cached(service):
            return self._cache[service]

        start = time.time()
        try:
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=5)
            latency = int((time.time() - start) * 1000)

            if response.status_code == 200:
                data = response.json()
                models = [m.get("name", "") for m in data.get("models", [])]
                result = HealthCheckResult(
                    service=service,
                    status=ServiceStatus.HEALTHY,
                    message=f"OK - {len(models)} modelli",
                    latency_ms=latency,
                    details={"models": models}
                )
            else:
                result = HealthCheckResult(
                    service=service,
                    status=ServiceStatus.UNHEALTHY,
                    message=f"HTTP {response.status_code}",
                    latency_ms=latency
                )
        except requests.RequestException:
            result = HealthCheckResult(
                service=service,
                status=ServiceStatus.UNHEALTHY,
                message="Non raggiungibile (ollama serve?)"
            )

        self._cache_result(service, result)
        return result

    def check_langsmith(self, force: bool = False) -> HealthCheckResult:
        """
        Verifica disponibilità LangSmith.
        """
        service = "langsmith"

        if not force and self._is_cached(service):
            return self._cache[service]

        if not self.langsmith_api_key:
            result = HealthCheckResult(
                service=service,
                status=ServiceStatus.DISABLED,
                message="API key non configurata"
            )
            self._cache_result(service, result)
            return result

        start = time.time()
        try:
            response = requests.get(
                "https://api.smith.langchain.com/api/v1/info",
                headers={"x-api-key": self.langsmith_api_key},
                timeout=10
            )
            latency = int((time.time() - start) * 1000)

            if response.status_code == 200:
                result = HealthCheckResult(
                    service=service,
                    status=ServiceStatus.HEALTHY,
                    message=f"OK ({latency}ms)",
                    latency_ms=latency
                )
            elif response.status_code == 401:
                result = HealthCheckResult(
                    service=service,
                    status=ServiceStatus.UNHEALTHY,
                    message="API key non valida"
                )
            else:
                result = HealthCheckResult(
                    service=service,
                    status=ServiceStatus.DEGRADED,
                    message=f"HTTP {response.status_code}"
                )
        except requests.RequestException as e:
            result = HealthCheckResult(
                service=service,
                status=ServiceStatus.UNHEALTHY,
                message=f"Errore: {str(e)[:50]}"
            )

        self._cache_result(service, result)
        return result

    def check_google_sheets(self, force: bool = False) -> HealthCheckResult:
        """
        Verifica disponibilità Google Sheets API.
        """
        service = "google_sheets"

        if not force and self._is_cached(service):
            return self._cache[service]

        if not self.google_credentials_path:
            result = HealthCheckResult(
                service=service,
                status=ServiceStatus.DISABLED,
                message="Credenziali non configurate"
            )
            self._cache_result(service, result)
            return result

        from pathlib import Path
        creds_path = Path(self.google_credentials_path)

        if not creds_path.exists():
            result = HealthCheckResult(
                service=service,
                status=ServiceStatus.UNHEALTHY,
                message=f"File non trovato: {creds_path.name}"
            )
            self._cache_result(service, result)
            return result

        # Verifica connettività Google API
        start = time.time()
        try:
            response = requests.get(
                "https://sheets.googleapis.com/$discovery/rest?version=v4",
                timeout=10
            )
            latency = int((time.time() - start) * 1000)

            if response.status_code == 200:
                result = HealthCheckResult(
                    service=service,
                    status=ServiceStatus.HEALTHY,
                    message=f"OK ({latency}ms)",
                    latency_ms=latency
                )
            else:
                result = HealthCheckResult(
                    service=service,
                    status=ServiceStatus.DEGRADED,
                    message=f"HTTP {response.status_code}"
                )
        except requests.RequestException:
            result = HealthCheckResult(
                service=service,
                status=ServiceStatus.UNHEALTHY,
                message="Google API non raggiungibile"
            )

        self._cache_result(service, result)
        return result

    def check_browser(self, force: bool = False) -> HealthCheckResult:
        """
        Verifica disponibilità Playwright/Chromium.
        """
        service = "browser"

        if not force and self._is_cached(service):
            return self._cache[service]

        try:
            import subprocess
            result_check = subprocess.run(
                ["playwright", "--version"],
                capture_output=True,
                timeout=5
            )

            if result_check.returncode == 0:
                version = result_check.stdout.decode().strip()
                result = HealthCheckResult(
                    service=service,
                    status=ServiceStatus.HEALTHY,
                    message=f"Playwright {version}",
                    details={"version": version}
                )
            else:
                result = HealthCheckResult(
                    service=service,
                    status=ServiceStatus.UNHEALTHY,
                    message="Playwright non installato"
                )
        except subprocess.TimeoutExpired:
            result = HealthCheckResult(
                service=service,
                status=ServiceStatus.UNHEALTHY,
                message="Timeout verifica Playwright"
            )
        except FileNotFoundError:
            result = HealthCheckResult(
                service=service,
                status=ServiceStatus.UNHEALTHY,
                message="Playwright non trovato nel PATH"
            )
        except Exception as e:
            result = HealthCheckResult(
                service=service,
                status=ServiceStatus.UNKNOWN,
                message=f"Errore: {str(e)[:50]}"
            )

        self._cache_result(service, result)
        return result

    def check_all(self, force: bool = False) -> SystemHealth:
        """
        Esegue tutti gli health check.

        Args:
            force: Ignora cache e ricontrolla tutto

        Returns:
            SystemHealth con tutti i risultati
        """
        health = SystemHealth()

        # Esegui tutti i check
        health.checks["browser"] = self.check_browser(force)
        health.checks["chatbot_url"] = self.check_chatbot_url(force)
        health.checks["ollama"] = self.check_ollama(force)
        health.checks["langsmith"] = self.check_langsmith(force)
        health.checks["google_sheets"] = self.check_google_sheets(force)

        return health

    def get_circuit_breaker(self, service: str) -> CircuitBreaker:
        """Ottiene il circuit breaker per un servizio"""
        if service not in self.circuit_breakers:
            self.circuit_breakers[service] = CircuitBreaker(service)
        return self.circuit_breakers[service]

    def execute_with_circuit_breaker(
        self,
        service: str,
        func: Callable,
        *args,
        **kwargs
    ) -> Any:
        """
        Esegue una funzione protetta dal circuit breaker.

        Args:
            service: Nome del servizio
            func: Funzione da eseguire
            *args, **kwargs: Argomenti per la funzione

        Returns:
            Risultato della funzione

        Raises:
            CircuitBreakerOpen: Se il circuito è aperto
        """
        cb = self.get_circuit_breaker(service)

        if not cb.can_execute():
            remaining = 0
            if cb.last_failure_time:
                elapsed = (datetime.now() - cb.last_failure_time).total_seconds()
                remaining = max(0, int(cb.recovery_timeout - elapsed))
            raise CircuitBreakerOpen(service, remaining)

        try:
            result = func(*args, **kwargs)
            cb.record_success()
            return result
        except Exception as e:
            cb.record_failure()
            raise


# Funzione helper per uso rapido
def quick_health_check(
    chatbot_url: str = "",
    use_ollama: bool = True,
    use_langsmith: bool = True,
    use_google: bool = True,
    langsmith_api_key: str = "",
    google_credentials_path: str = ""
) -> Dict[str, str]:
    """
    Health check rapido con output semplice.

    Returns:
        Dict con nome_servizio: stato
    """
    checker = HealthChecker(
        chatbot_url=chatbot_url,
        langsmith_api_key=langsmith_api_key if use_langsmith else "",
        google_credentials_path=google_credentials_path if use_google else ""
    )

    results = {}

    results["browser"] = checker.check_browser().status.value

    if chatbot_url:
        results["chatbot"] = checker.check_chatbot_url().status.value

    if use_ollama:
        results["ollama"] = checker.check_ollama().status.value

    if use_langsmith and langsmith_api_key:
        results["langsmith"] = checker.check_langsmith().status.value

    if use_google and google_credentials_path:
        results["google"] = checker.check_google_sheets().status.value

    return results
