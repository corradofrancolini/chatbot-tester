"""
Thread-Safe Wrappers - Thread-safe wrappers for parallel test execution

Contains:
- ThreadSafeSheetsClient: Wraps GoogleSheetsClient for parallel writes
- ParallelResultsCollector: In-memory collector for parallel results
"""

import threading
from pathlib import Path
from typing import Optional, List, Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from ..sheets_client import GoogleSheetsClient, TestResult, ScreenshotUrls


class ThreadSafeSheetsClient:
    """
    Wrapper thread-safe per GoogleSheetsClient.

    Accumula risultati in memoria durante l'esecuzione parallela
    e li scrive in batch alla fine, evitando race conditions.

    Usage:
        # Wrap client esistente
        safe_client = ThreadSafeSheetsClient(sheets_client)

        # Da worker paralleli (thread-safe)
        safe_client.queue_result(result)
        safe_client.queue_screenshot(file_path, test_id)

        # Alla fine (scrivi tutto)
        safe_client.flush()
    """

    def __init__(self, client: 'GoogleSheetsClient'):
        """
        Args:
            client: GoogleSheetsClient gia autenticato e configurato
        """
        self._client = client
        self._results_queue: List['TestResult'] = []
        self._screenshots_queue: List[tuple] = []  # (file_path, test_id)
        self._lock = threading.RLock()
        self._upload_lock = threading.RLock()  # Lock separato per upload Drive

        # Mapping test_id -> screenshot_urls per associazione post-upload
        self._screenshot_urls: Dict[str, 'ScreenshotUrls'] = {}

    @property
    def client(self) -> 'GoogleSheetsClient':
        """Accesso al client sottostante"""
        return self._client

    @property
    def queued_count(self) -> int:
        """Numero risultati in coda"""
        with self._lock:
            return len(self._results_queue)

    def queue_result(self, result: 'TestResult') -> None:
        """
        Accoda un risultato per scrittura batch.
        Thread-safe.

        Args:
            result: TestResult da accodare
        """
        with self._lock:
            self._results_queue.append(result)

    def queue_screenshot(self, file_path: Path, test_id: str) -> None:
        """
        Accoda uno screenshot per upload batch.
        Thread-safe.

        Args:
            file_path: Path al file screenshot
            test_id: ID del test
        """
        with self._lock:
            self._screenshots_queue.append((file_path, test_id))

    def upload_screenshot_now(self, file_path: Path, test_id: str) -> Optional['ScreenshotUrls']:
        """
        Upload screenshot immediatamente (thread-safe).
        Utile se vuoi fare upload durante l'esecuzione.

        Args:
            file_path: Path al file screenshot
            test_id: ID del test

        Returns:
            ScreenshotUrls o None
        """
        with self._upload_lock:
            urls = self._client.upload_screenshot(file_path, test_id)
            if urls:
                with self._lock:
                    self._screenshot_urls[test_id] = urls
            return urls

    def get_screenshot_urls(self, test_id: str) -> Optional['ScreenshotUrls']:
        """Ottiene URL screenshot gia uploadato"""
        with self._lock:
            return self._screenshot_urls.get(test_id)

    def flush_screenshots(self) -> int:
        """
        Upload tutti gli screenshot in coda.

        Returns:
            Numero screenshot uploadati
        """
        with self._lock:
            screenshots_to_upload = self._screenshots_queue.copy()
            self._screenshots_queue.clear()

        uploaded = 0
        for file_path, test_id in screenshots_to_upload:
            urls = self.upload_screenshot_now(file_path, test_id)
            if urls:
                uploaded += 1

        return uploaded

    def flush_results(self) -> int:
        """
        Scrive tutti i risultati in coda su Google Sheets.

        Returns:
            Numero risultati scritti
        """
        with self._lock:
            if not self._results_queue:
                return 0

            results_to_write = self._results_queue.copy()
            self._results_queue.clear()

        # Associa screenshot_urls ai risultati se disponibili
        for result in results_to_write:
            if result.test_id in self._screenshot_urls:
                result.screenshot_urls = self._screenshot_urls[result.test_id]

        # Scrivi batch
        return self._client.append_results(results_to_write)

    def flush(self) -> tuple:
        """
        Flush completo: prima screenshot, poi risultati.

        Returns:
            (screenshots_uploaded, results_written)
        """
        screenshots = self.flush_screenshots()
        results = self.flush_results()
        return screenshots, results

    def is_test_completed(self, test_id: str) -> bool:
        """
        Verifica se un test e gia completato (nella RUN o in coda).
        Thread-safe.
        """
        with self._lock:
            # Check coda locale
            if any(r.test_id == test_id for r in self._results_queue):
                return True

        # Check foglio remoto
        return self._client.is_test_completed(test_id)

    def get_completed_tests(self) -> set:
        """
        Ottiene tutti i test completati (remoti + in coda).
        Thread-safe.
        """
        with self._lock:
            queued = {r.test_id for r in self._results_queue}

        remote = self._client.get_completed_tests()
        return remote | queued


class ParallelResultsCollector:
    """
    Collector per risultati da esecuzione parallela.

    Versione piu leggera di ThreadSafeSheetsClient che
    accumula solo in memoria senza dipendere da Sheets.
    Utile se vuoi gestire la scrittura separatamente.

    Usage:
        collector = ParallelResultsCollector()

        # Da worker paralleli
        collector.add(result)

        # Alla fine
        all_results = collector.get_all()
        sheets_client.append_results(all_results)
    """

    def __init__(self):
        self._results: List['TestResult'] = []
        self._lock = threading.RLock()
        self._completed_ids: set = set()

    def add(self, result: 'TestResult') -> None:
        """Aggiunge risultato (thread-safe)"""
        with self._lock:
            self._results.append(result)
            self._completed_ids.add(result.test_id)

    def get_all(self) -> List['TestResult']:
        """Ottiene tutti i risultati (copia)"""
        with self._lock:
            return self._results.copy()

    def clear(self) -> None:
        """Svuota il collector"""
        with self._lock:
            self._results.clear()
            self._completed_ids.clear()

    def is_completed(self, test_id: str) -> bool:
        """Verifica se test e gia nel collector"""
        with self._lock:
            return test_id in self._completed_ids

    @property
    def count(self) -> int:
        """Numero risultati raccolti"""
        with self._lock:
            return len(self._results)

    def get_summary(self) -> Dict[str, int]:
        """Statistiche sui risultati raccolti"""
        with self._lock:
            passed = sum(1 for r in self._results if r.result == "PASS")
            failed = sum(1 for r in self._results if r.result == "FAIL")
            errors = sum(1 for r in self._results if r.result == "ERROR")
            skipped = sum(1 for r in self._results if r.result == "SKIP")

            return {
                "total": len(self._results),
                "passed": passed,
                "failed": failed,
                "errors": errors,
                "skipped": skipped
            }
