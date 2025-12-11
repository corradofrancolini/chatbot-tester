"""
Comparison Module - A/B Testing e Regression Detection

Permette di:
- Confrontare risultati tra due RUN
- Rilevare regressioni (test che passavano e ora falliscono)
- Rilevare miglioramenti (test che fallivano e ora passano)
- Analizzare coverage dei test
- Identificare flaky tests
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Set, Tuple
from datetime import datetime
from enum import Enum
from pathlib import Path
import json


class ChangeType(Enum):
    """Tipo di cambiamento tra due run"""
    REGRESSION = "regression"      # PASS -> FAIL
    IMPROVEMENT = "improvement"    # FAIL -> PASS
    STABLE_PASS = "stable_pass"    # PASS -> PASS
    STABLE_FAIL = "stable_fail"    # FAIL -> FAIL
    NEW_TEST = "new_test"          # Non esisteva -> qualsiasi
    REMOVED_TEST = "removed_test"  # Esisteva -> non esiste piu
    FLAKY = "flaky"                # Risultati inconsistenti


@dataclass
class TestChange:
    """Rappresenta un cambiamento in un singolo test"""
    test_id: str
    change_type: ChangeType
    old_result: Optional[str] = None  # PASS, FAIL, ERROR, SKIP
    new_result: Optional[str] = None
    old_notes: str = ""
    new_notes: str = ""
    category: str = ""
    question: str = ""


@dataclass
class ComparisonResult:
    """Risultato del confronto tra due RUN"""
    run_a: int  # Numero RUN base (vecchia)
    run_b: int  # Numero RUN nuova
    timestamp: str = ""

    # Statistiche
    total_tests_a: int = 0
    total_tests_b: int = 0

    passed_a: int = 0
    passed_b: int = 0
    failed_a: int = 0
    failed_b: int = 0

    # Cambiamenti
    regressions: List[TestChange] = field(default_factory=list)
    improvements: List[TestChange] = field(default_factory=list)
    stable_pass: List[TestChange] = field(default_factory=list)
    stable_fail: List[TestChange] = field(default_factory=list)
    new_tests: List[TestChange] = field(default_factory=list)
    removed_tests: List[TestChange] = field(default_factory=list)

    # Metriche derivate
    @property
    def regression_count(self) -> int:
        return len(self.regressions)

    @property
    def improvement_count(self) -> int:
        return len(self.improvements)

    @property
    def pass_rate_a(self) -> float:
        if self.total_tests_a == 0:
            return 0.0
        return self.passed_a / self.total_tests_a

    @property
    def pass_rate_b(self) -> float:
        if self.total_tests_b == 0:
            return 0.0
        return self.passed_b / self.total_tests_b

    @property
    def pass_rate_delta(self) -> float:
        """Differenza percentuale (positivo = miglioramento)"""
        return self.pass_rate_b - self.pass_rate_a

    @property
    def has_regressions(self) -> bool:
        return len(self.regressions) > 0

    @property
    def is_improvement(self) -> bool:
        return self.pass_rate_delta > 0 and not self.has_regressions


@dataclass
class CoverageReport:
    """Report di coverage dei test"""
    total_tests: int = 0
    categories: Dict[str, int] = field(default_factory=dict)
    uncovered_categories: List[str] = field(default_factory=list)
    tests_per_category: Dict[str, List[str]] = field(default_factory=dict)

    # Suggerimenti
    suggested_tests: List[str] = field(default_factory=list)


@dataclass
class FlakyTestReport:
    """Report sui test flaky"""
    test_id: str
    total_runs: int = 0
    pass_count: int = 0
    fail_count: int = 0
    flaky_score: float = 0.0  # 0 = stabile, 1 = molto flaky
    history: List[Tuple[int, str]] = field(default_factory=list)  # (run_number, result)


class RunComparator:
    """
    Confronta risultati tra RUN diverse.

    Usage:
        comparator = RunComparator(sheets_client)

        # Confronto A/B
        result = comparator.compare(run_a=10, run_b=15)

        if result.has_regressions:
            print(f"ATTENZIONE: {result.regression_count} regressioni!")
            for reg in result.regressions:
                print(f"  - {reg.test_id}: {reg.old_result} -> {reg.new_result}")
    """

    def __init__(self, sheets_client=None, local_reports_path: Path = None):
        """
        Args:
            sheets_client: GoogleSheetsClient per leggere da Sheets
            local_reports_path: Path ai report locali (alternativo)
        """
        self._sheets = sheets_client
        self._local_path = local_reports_path
        self._cache: Dict[int, Dict[str, Any]] = {}

    def compare(self, run_a: int, run_b: int) -> ComparisonResult:
        """
        Confronta due RUN.

        Args:
            run_a: Numero RUN base (tipicamente la precedente)
            run_b: Numero RUN da confrontare (tipicamente la nuova)

        Returns:
            ComparisonResult con tutti i dettagli
        """
        # Carica dati
        data_a = self._load_run_data(run_a)
        data_b = self._load_run_data(run_b)

        result = ComparisonResult(
            run_a=run_a,
            run_b=run_b,
            timestamp=datetime.now().isoformat()
        )

        # Set di test ID
        tests_a = set(data_a.keys())
        tests_b = set(data_b.keys())

        # Statistiche base
        result.total_tests_a = len(tests_a)
        result.total_tests_b = len(tests_b)
        result.passed_a = sum(1 for t in data_a.values() if t.get('esito') == 'PASS')
        result.passed_b = sum(1 for t in data_b.values() if t.get('esito') == 'PASS')
        result.failed_a = sum(1 for t in data_a.values() if t.get('esito') == 'FAIL')
        result.failed_b = sum(1 for t in data_b.values() if t.get('esito') == 'FAIL')

        # Test comuni
        common_tests = tests_a & tests_b

        for test_id in common_tests:
            old = data_a[test_id]
            new = data_b[test_id]

            old_result = old.get('esito', '')
            new_result = new.get('esito', '')

            change = TestChange(
                test_id=test_id,
                change_type=ChangeType.STABLE_PASS,  # Default
                old_result=old_result,
                new_result=new_result,
                old_notes=old.get('notes', ''),
                new_notes=new.get('notes', ''),
                category=new.get('category', ''),
                question=new.get('question', '')
            )

            # Determina tipo di cambiamento
            if old_result == 'PASS' and new_result == 'FAIL':
                change.change_type = ChangeType.REGRESSION
                result.regressions.append(change)
            elif old_result == 'FAIL' and new_result == 'PASS':
                change.change_type = ChangeType.IMPROVEMENT
                result.improvements.append(change)
            elif old_result == 'PASS' and new_result == 'PASS':
                change.change_type = ChangeType.STABLE_PASS
                result.stable_pass.append(change)
            elif old_result == 'FAIL' and new_result == 'FAIL':
                change.change_type = ChangeType.STABLE_FAIL
                result.stable_fail.append(change)

        # Test nuovi (in B ma non in A)
        for test_id in (tests_b - tests_a):
            new = data_b[test_id]
            change = TestChange(
                test_id=test_id,
                change_type=ChangeType.NEW_TEST,
                new_result=new.get('esito', ''),
                new_notes=new.get('notes', ''),
                category=new.get('category', ''),
                question=new.get('question', '')
            )
            result.new_tests.append(change)

        # Test rimossi (in A ma non in B)
        for test_id in (tests_a - tests_b):
            old = data_a[test_id]
            change = TestChange(
                test_id=test_id,
                change_type=ChangeType.REMOVED_TEST,
                old_result=old.get('esito', ''),
                old_notes=old.get('notes', ''),
                category=old.get('category', ''),
                question=old.get('question', '')
            )
            result.removed_tests.append(change)

        return result

    def compare_latest(self) -> Optional[ComparisonResult]:
        """
        Confronta le ultime due RUN.

        Returns:
            ComparisonResult o None se non ci sono abbastanza RUN
        """
        runs = self._get_all_run_numbers()

        if len(runs) < 2:
            return None

        return self.compare(runs[-2], runs[-1])

    def _load_run_data(self, run_number: int) -> Dict[str, Dict]:
        """
        Carica dati di una RUN.

        Returns:
            Dict[test_id -> {esito, notes, category, question, ...}]
        """
        # Check cache
        if run_number in self._cache:
            return self._cache[run_number]

        data = {}

        # Prova da Sheets
        if self._sheets:
            try:
                worksheet = self._sheets.get_run_sheet(run_number)
                if worksheet:
                    records = worksheet.get_all_records()
                    for record in records:
                        test_id = record.get('TEST ID', '')
                        if test_id:
                            data[test_id] = {
                                'esito': record.get('ESITO', ''),
                                'notes': record.get('NOTES', ''),
                                'question': record.get('QUESTION', ''),
                                'category': '',  # Non sempre presente
                                'date': record.get('DATE', '')
                            }
            except Exception as e:
                print(f"! Errore caricamento RUN {run_number} da Sheets: {e}")

        # Prova da report locali
        if not data and self._local_path:
            report_path = self._local_path / f"run_{run_number}" / "results.json"
            if report_path.exists():
                try:
                    with open(report_path) as f:
                        results = json.load(f)
                    for result in results:
                        test_id = result.get('test_id', '')
                        if test_id:
                            data[test_id] = result
                except Exception as e:
                    print(f"! Errore caricamento RUN {run_number} locale: {e}")

        self._cache[run_number] = data
        return data

    def _get_all_run_numbers(self) -> List[int]:
        """Ottiene tutti i numeri RUN disponibili"""
        if self._sheets:
            return self._sheets.get_all_run_numbers()

        if self._local_path:
            runs = []
            for d in self._local_path.iterdir():
                if d.is_dir() and d.name.startswith('run_'):
                    try:
                        run_num = int(d.name.split('_')[1])
                        runs.append(run_num)
                    except:
                        pass
            return sorted(runs)

        return []


class RegressionDetector:
    """
    Rileva regressioni automaticamente.

    Usage:
        detector = RegressionDetector(comparator)

        # Check dopo ogni run
        regressions = detector.check_for_regressions(new_run=15)

        if regressions:
            send_alert(regressions)
    """

    def __init__(self, comparator: RunComparator):
        self._comparator = comparator

    def check_for_regressions(self,
                               new_run: int,
                               baseline_run: Optional[int] = None) -> List[TestChange]:
        """
        Verifica se ci sono regressioni rispetto a una baseline.

        Args:
            new_run: RUN da verificare
            baseline_run: RUN di riferimento (default: precedente)

        Returns:
            Lista di regressioni trovate
        """
        if baseline_run is None:
            # Usa la RUN precedente
            runs = self._comparator._get_all_run_numbers()
            if new_run not in runs:
                return []

            idx = runs.index(new_run)
            if idx == 0:
                return []  # Prima RUN, niente da confrontare

            baseline_run = runs[idx - 1]

        result = self._comparator.compare(baseline_run, new_run)
        return result.regressions

    def get_regression_trend(self,
                              last_n_runs: int = 5) -> Dict[str, Any]:
        """
        Analizza trend delle regressioni nelle ultime N run.

        Returns:
            Statistiche sul trend
        """
        runs = self._comparator._get_all_run_numbers()[-last_n_runs:]

        if len(runs) < 2:
            return {'error': 'Serve almeno 2 RUN per analisi trend'}

        regression_counts = []
        improvement_counts = []
        pass_rates = []

        for i in range(1, len(runs)):
            result = self._comparator.compare(runs[i-1], runs[i])
            regression_counts.append(result.regression_count)
            improvement_counts.append(result.improvement_count)
            pass_rates.append(result.pass_rate_b)

        return {
            'runs_analyzed': len(runs),
            'total_regressions': sum(regression_counts),
            'total_improvements': sum(improvement_counts),
            'avg_regressions_per_run': sum(regression_counts) / len(regression_counts),
            'pass_rate_trend': pass_rates,
            'is_improving': pass_rates[-1] > pass_rates[0] if pass_rates else False
        }


class CoverageAnalyzer:
    """
    Analizza la coverage dei test.

    Usage:
        analyzer = CoverageAnalyzer(tests_config, categories_config)

        report = analyzer.analyze(executed_tests)
        print(f"Coverage: {report.total_tests} test")
        print(f"Categorie coperte: {len(report.categories)}")
    """

    # Categorie standard per chatbot
    DEFAULT_CATEGORIES = [
        "product_search",
        "product_details",
        "pricing",
        "availability",
        "comparison",
        "recommendations",
        "order_status",
        "returns",
        "support",
        "general_info",
        "error_handling",
        "edge_cases"
    ]

    def __init__(self,
                 expected_categories: Optional[List[str]] = None,
                 min_tests_per_category: int = 3):
        """
        Args:
            expected_categories: Categorie che dovrebbero avere test
            min_tests_per_category: Minimo test per categoria
        """
        self._categories = expected_categories or self.DEFAULT_CATEGORIES
        self._min_tests = min_tests_per_category

    def analyze(self,
                tests: List[Dict[str, Any]],
                test_config: Optional[Dict] = None) -> CoverageReport:
        """
        Analizza coverage dei test.

        Args:
            tests: Lista test eseguiti con categoria
            test_config: Configurazione test con categorie

        Returns:
            CoverageReport
        """
        report = CoverageReport()
        report.total_tests = len(tests)

        # Conta test per categoria
        for test in tests:
            category = test.get('category', 'uncategorized')

            if category not in report.categories:
                report.categories[category] = 0
                report.tests_per_category[category] = []

            report.categories[category] += 1
            report.tests_per_category[category].append(test.get('test_id', ''))

        # Trova categorie non coperte
        covered = set(report.categories.keys())
        expected = set(self._categories)
        report.uncovered_categories = list(expected - covered)

        # Suggerisci test mancanti
        for category in report.uncovered_categories:
            report.suggested_tests.append(
                f"Aggiungere test per categoria: {category}"
            )

        for category, count in report.categories.items():
            if count < self._min_tests:
                report.suggested_tests.append(
                    f"Categoria '{category}' ha solo {count} test "
                    f"(minimo suggerito: {self._min_tests})"
                )

        return report


class FlakyTestDetector:
    """
    Rileva test flaky (risultati inconsistenti).

    Un test e' flaky se:
    - Passa e fallisce in run diverse senza modifiche
    - Ha un'alta varianza nei risultati

    Usage:
        detector = FlakyTestDetector(comparator)

        flaky_tests = detector.detect_flaky_tests(last_n_runs=10)

        for test in flaky_tests:
            print(f"{test.test_id}: flaky score {test.flaky_score:.2f}")
    """

    def __init__(self, comparator: RunComparator):
        self._comparator = comparator

    def detect_flaky_tests(self,
                           last_n_runs: int = 10,
                           flaky_threshold: float = 0.3) -> List[FlakyTestReport]:
        """
        Rileva test flaky nelle ultime N run.

        Args:
            last_n_runs: Numero RUN da analizzare
            flaky_threshold: Soglia flaky score (0-1)

        Returns:
            Lista di FlakyTestReport per test flaky
        """
        runs = self._comparator._get_all_run_numbers()[-last_n_runs:]

        if len(runs) < 3:
            return []  # Servono almeno 3 run per rilevare flakiness

        # Raccogli storia di ogni test
        test_history: Dict[str, List[Tuple[int, str]]] = {}

        for run_num in runs:
            data = self._comparator._load_run_data(run_num)

            for test_id, test_data in data.items():
                if test_id not in test_history:
                    test_history[test_id] = []

                test_history[test_id].append(
                    (run_num, test_data.get('esito', ''))
                )

        # Calcola flaky score per ogni test
        flaky_tests = []

        for test_id, history in test_history.items():
            if len(history) < 3:
                continue  # Non abbastanza dati

            results = [r for _, r in history]
            pass_count = results.count('PASS')
            fail_count = results.count('FAIL')
            total = len(results)

            # Flaky score: quanto varia tra PASS e FAIL
            # 0 = sempre stesso risultato, 1 = 50/50
            if total == 0:
                continue

            pass_ratio = pass_count / total
            flaky_score = 2 * min(pass_ratio, 1 - pass_ratio)

            if flaky_score >= flaky_threshold:
                report = FlakyTestReport(
                    test_id=test_id,
                    total_runs=total,
                    pass_count=pass_count,
                    fail_count=fail_count,
                    flaky_score=flaky_score,
                    history=history
                )
                flaky_tests.append(report)

        # Ordina per flaky score decrescente
        flaky_tests.sort(key=lambda x: x.flaky_score, reverse=True)

        return flaky_tests

    def get_stability_report(self, last_n_runs: int = 10) -> Dict[str, Any]:
        """
        Report generale sulla stabilita dei test.

        Returns:
            Statistiche di stabilita
        """
        runs = self._comparator._get_all_run_numbers()[-last_n_runs:]

        if len(runs) < 2:
            return {'error': 'Serve almeno 2 RUN per analisi stabilita'}

        flaky = self.detect_flaky_tests(last_n_runs, flaky_threshold=0.2)

        # Conta test stabili
        test_history: Dict[str, List[str]] = {}

        for run_num in runs:
            data = self._comparator._load_run_data(run_num)
            for test_id, test_data in data.items():
                if test_id not in test_history:
                    test_history[test_id] = []
                test_history[test_id].append(test_data.get('esito', ''))

        stable_pass = 0
        stable_fail = 0

        for test_id, results in test_history.items():
            if len(results) >= 2:
                if all(r == 'PASS' for r in results):
                    stable_pass += 1
                elif all(r == 'FAIL' for r in results):
                    stable_fail += 1

        total_tests = len(test_history)

        return {
            'runs_analyzed': len(runs),
            'total_tests': total_tests,
            'stable_pass': stable_pass,
            'stable_fail': stable_fail,
            'flaky_tests': len(flaky),
            'stability_score': (stable_pass + stable_fail) / total_tests if total_tests > 0 else 0,
            'flaky_test_ids': [f.test_id for f in flaky]
        }


def format_comparison_report(result: ComparisonResult) -> str:
    """
    Formatta un ComparisonResult per output testuale.
    """
    lines = []
    lines.append(f"{'='*60}")
    lines.append(f"CONFRONTO RUN {result.run_a} vs RUN {result.run_b}")
    lines.append(f"{'='*60}")
    lines.append("")

    # Sommario
    lines.append("SOMMARIO")
    lines.append("-" * 40)
    lines.append(f"Pass rate RUN {result.run_a}: {result.pass_rate_a:.1%}")
    lines.append(f"Pass rate RUN {result.run_b}: {result.pass_rate_b:.1%}")

    delta = result.pass_rate_delta
    delta_str = f"+{delta:.1%}" if delta >= 0 else f"{delta:.1%}"
    lines.append(f"Delta: {delta_str}")
    lines.append("")

    # Regressioni
    if result.regressions:
        lines.append(f"REGRESSIONI ({len(result.regressions)})")
        lines.append("-" * 40)
        for reg in result.regressions:
            lines.append(f"  {reg.test_id}: {reg.old_result} -> {reg.new_result}")
            if reg.question:
                lines.append(f"    Q: {reg.question[:60]}...")
        lines.append("")

    # Miglioramenti
    if result.improvements:
        lines.append(f"MIGLIORAMENTI ({len(result.improvements)})")
        lines.append("-" * 40)
        for imp in result.improvements:
            lines.append(f"  {imp.test_id}: {imp.old_result} -> {imp.new_result}")
        lines.append("")

    # Nuovi test
    if result.new_tests:
        lines.append(f"NUOVI TEST ({len(result.new_tests)})")
        lines.append("-" * 40)
        for new in result.new_tests:
            lines.append(f"  {new.test_id}: {new.new_result}")
        lines.append("")

    # Test rimossi
    if result.removed_tests:
        lines.append(f"TEST RIMOSSI ({len(result.removed_tests)})")
        lines.append("-" * 40)
        for rem in result.removed_tests:
            lines.append(f"  {rem.test_id}")
        lines.append("")

    # Statistiche finali
    lines.append("STATISTICHE")
    lines.append("-" * 40)
    lines.append(f"Stabili PASS: {len(result.stable_pass)}")
    lines.append(f"Stabili FAIL: {len(result.stable_fail)}")
    lines.append(f"Regressioni: {result.regression_count}")
    lines.append(f"Miglioramenti: {result.improvement_count}")

    return "\n".join(lines)
