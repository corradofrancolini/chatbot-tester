"""
Diagnostic Engine - Diagnosi intelligente dei fallimenti prompt

Analizza test falliti, genera ipotesi basate su knowledge base,
verifica le ipotesi e suggerisce fix.

Usage:
    engine = DiagnosticEngine()
    diagnosis = engine.diagnose(prompt, test_failure)

    # Interactive mode
    session = InteractiveDiagnostic(ui)
    diagnosis = session.run(prompt, test_failure)

    # Batch diagnosis
    engine = DiagnosticEngine()
    diagnoses = engine.diagnose_batch(prompt, failures)
"""

import re
import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable, Tuple
from enum import Enum


# =============================================================================
# Data Classes
# =============================================================================

class FailureType(Enum):
    """Tipi di fallimento classificabili."""
    FORMAT_VIOLATION = "format_violation"
    CONTENT_INCORRECT = "content_incorrect"
    PRIORITY_CONFLICT = "priority_conflict"
    LANGUAGE_MISMATCH = "language_mismatch"
    SCOPE_VIOLATION = "scope_violation"
    REASONING_FAILURE = "reasoning_failure"
    CONSISTENCY_FAILURE = "consistency_failure"
    UNKNOWN = "unknown"


@dataclass
class Hypothesis:
    """Una ipotesi sulla causa del fallimento."""
    id: str
    cause: str
    confidence: float
    check: str
    source: str
    verified: Optional[bool] = None
    verification_details: Optional[str] = None


@dataclass
class Fix:
    """Un fix suggerito."""
    hypothesis_id: str
    description: str
    template: str
    model_specific: Optional[str] = None
    confidence: float = 0.0


@dataclass
class Diagnosis:
    """Risultato completo della diagnosi."""
    failure_type: FailureType
    hypotheses: List[Hypothesis]
    verified_hypotheses: List[Hypothesis] = field(default_factory=list)
    suggested_fixes: List[Fix] = field(default_factory=list)
    questions_asked: List[Dict[str, str]] = field(default_factory=list)
    confidence: float = 0.0

    def summary(self) -> str:
        """Genera sommario della diagnosi."""
        lines = [
            f"Failure Type: {self.failure_type.value}",
            f"Confidence: {self.confidence:.0%}",
            "",
            "Hypotheses:"
        ]
        for h in self.hypotheses[:3]:
            status = ""
            if h.verified is True:
                status = " [VERIFIED]"
            elif h.verified is False:
                status = " [REJECTED]"
            lines.append(f"  [{h.confidence:.0%}] {h.cause}{status}")

        if self.suggested_fixes:
            lines.append("")
            lines.append("Suggested Fixes:")
            for fix in self.suggested_fixes[:2]:
                lines.append(f"  - {fix.description}")

        return "\n".join(lines)


@dataclass
class TestFailure:
    """Rappresentazione di un test fallito."""
    test_id: str
    question: str
    expected: Optional[str]
    actual: str
    error_type: Optional[str] = None
    notes: Optional[str] = None


# =============================================================================
# Knowledge Base Loader
# =============================================================================

class KnowledgeBase:
    """Carica e gestisce la knowledge base."""

    def __init__(self, path: Optional[Path] = None):
        if path is None:
            path = Path(__file__).parent.parent / "knowledge" / "failure_patterns.yaml"
        self.path = path
        self._data: Optional[Dict] = None

    @property
    def data(self) -> Dict:
        if self._data is None:
            self._data = self._load()
        return self._data

    def _load(self) -> Dict:
        """Carica knowledge base da YAML."""
        if not self.path.exists():
            return self._default_kb()

        with open(self.path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    def _default_kb(self) -> Dict:
        """Knowledge base minimale di fallback."""
        return {
            'failure_patterns': {},
            'verification_strategies': {},
            'fix_templates': {},
            'symptom_mapping': {}
        }

    def get_pattern(self, pattern_id: str) -> Optional[Dict]:
        """Ottiene un failure pattern."""
        return self.data.get('failure_patterns', {}).get(pattern_id)

    def get_verification(self, hypothesis_id: str) -> Optional[Dict]:
        """Ottiene strategia di verifica per ipotesi."""
        return self.data.get('verification_strategies', {}).get(hypothesis_id)

    def get_fix(self, hypothesis_id: str, model: str = 'generic') -> Optional[str]:
        """Ottiene template fix per ipotesi."""
        templates = self.data.get('fix_templates', {}).get(hypothesis_id, {})
        return templates.get(model) or templates.get('generic')

    def get_patterns_for_symptom(self, symptom: str) -> List[str]:
        """Trova pattern rilevanti per un sintomo."""
        mapping = self.data.get('symptom_mapping', {})
        symptom_lower = symptom.lower()

        # Cerca match esatto
        if symptom_lower in mapping:
            return mapping[symptom_lower]

        # Cerca match parziale
        for key, patterns in mapping.items():
            if key in symptom_lower or symptom_lower in key:
                return patterns

        return []


# =============================================================================
# Failure Classifier
# =============================================================================

class FailureClassifier:
    """Classifica il tipo di fallimento."""

    # Keywords per ogni tipo di fallimento (IT + EN)
    KEYWORDS = {
        FailureType.FORMAT_VIOLATION: [
            'json', 'xml', 'format', 'structure', 'schema', 'field', 'missing',
            'invalid', 'parse', 'syntax', 'formato', 'struttura', 'campo'
        ],
        FailureType.CONTENT_INCORRECT: [
            'wrong', 'incorrect', 'hallucin', 'invented', 'fake', 'not found',
            'does not exist', 'made up', 'inaccurate', 'sbagliato', 'errato',
            'inventato', 'non esiste', 'falso'
        ],
        FailureType.PRIORITY_CONFLICT: [
            'priority', 'order', 'rank', 'first', 'prefer', 'chose wrong',
            'ignored', 'should have', 'instead of', 'but not', 'non ha',
            'ha ignorato', 'ha scelto', 'invece di', 'priorita', 'ordine',
            'prezzo', 'colore', 'economico', 'costoso', 'attributo'
        ],
        FailureType.LANGUAGE_MISMATCH: [
            'language', 'lingua', 'english', 'italian', 'italiano', 'wrong language',
            'different language', 'mixed', 'inglese', 'francese', 'tedesco'
        ],
        FailureType.SCOPE_VIOLATION: [
            'too long', 'too short', 'verbose', 'terse', 'missing details',
            'extra', 'unrequested', 'scope', 'out of scope', 'troppo lungo',
            'troppo corto', 'manca', 'dettagli'
        ],
        FailureType.REASONING_FAILURE: [
            'logic', 'reasoning', 'step', 'conclusion', 'wrong calculation',
            'skipped', 'circular', 'logica', 'ragionamento', 'calcolo'
        ],
        FailureType.CONSISTENCY_FAILURE: [
            'inconsistent', 'different', 'varies', 'flaky', 'sometimes',
            'unpredictable', 'inconsistente', 'diverso', 'a volte'
        ]
    }

    def classify(self, failure: TestFailure) -> FailureType:
        """Classifica il tipo di fallimento."""
        # Combina tutti i testi disponibili
        text = " ".join(filter(None, [
            failure.error_type,
            failure.notes,
            failure.actual,
            failure.expected
        ])).lower()

        # Conta match per ogni tipo
        scores = {}
        for ftype, keywords in self.KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in text)
            if score > 0:
                scores[ftype] = score

        if not scores:
            return FailureType.UNKNOWN

        # Ritorna tipo con più match
        return max(scores, key=scores.get)


# =============================================================================
# Hypothesis Generator
# =============================================================================

class HypothesisGenerator:
    """Genera ipotesi basate su failure type e knowledge base."""

    def __init__(self, kb: KnowledgeBase):
        self.kb = kb

    def generate(self, failure_type: FailureType, failure: TestFailure) -> List[Hypothesis]:
        """Genera ipotesi ordinate per confidence."""
        pattern = self.kb.get_pattern(failure_type.value)
        if not pattern:
            return []

        hypotheses = []
        for h_data in pattern.get('hypotheses', []):
            hypotheses.append(Hypothesis(
                id=h_data['id'],
                cause=h_data['cause'],
                confidence=h_data['confidence'],
                check=h_data.get('check', ''),
                source=h_data.get('source', 'unknown')
            ))

        # Ordina per confidence decrescente
        hypotheses.sort(key=lambda h: h.confidence, reverse=True)
        return hypotheses


# =============================================================================
# Verification Engine
# =============================================================================

class VerificationEngine:
    """Verifica ipotesi contro il prompt."""

    def __init__(self, kb: KnowledgeBase):
        self.kb = kb

    def verify(self, hypothesis: Hypothesis, prompt: str) -> Hypothesis:
        """Verifica una singola ipotesi."""
        strategy = self.kb.get_verification(hypothesis.id)
        if not strategy:
            return hypothesis

        # Esegui verifiche automatiche
        auto_checks = strategy.get('automated', [])
        for check in auto_checks:
            if 'pattern' in check:
                pattern = check['pattern']
                expect = check.get('expect', 'present')
                found = bool(re.search(pattern, prompt, re.IGNORECASE))

                if expect == 'present' and not found:
                    hypothesis.verified = True
                    hypothesis.verification_details = f"Pattern '{pattern}' not found in prompt"
                    return hypothesis
                elif expect == 'absent' and found:
                    hypothesis.verified = True
                    hypothesis.verification_details = f"Pattern '{pattern}' found (should be absent)"
                    return hypothesis

        # Se nessuna verifica automatica ha confermato, lascia unverified
        return hypothesis

    def verify_all(self, hypotheses: List[Hypothesis], prompt: str) -> List[Hypothesis]:
        """Verifica tutte le ipotesi."""
        return [self.verify(h, prompt) for h in hypotheses]


# =============================================================================
# Fix Suggester
# =============================================================================

class FixSuggester:
    """Suggerisce fix basati su ipotesi verificate."""

    def __init__(self, kb: KnowledgeBase):
        self.kb = kb

    def suggest(self, hypotheses: List[Hypothesis], model: str = 'generic') -> List[Fix]:
        """Genera fix per le ipotesi."""
        fixes = []

        for h in hypotheses:
            # Solo ipotesi verificate o ad alta confidence
            if h.verified is False:
                continue
            if h.verified is None and h.confidence < 0.6:
                continue

            template = self.kb.get_fix(h.id, model)
            if template:
                model_specific = None
                if model != 'generic':
                    model_specific = self.kb.get_fix(h.id, model)

                fixes.append(Fix(
                    hypothesis_id=h.id,
                    description=h.cause,
                    template=template,
                    model_specific=model_specific,
                    confidence=h.confidence if h.verified is None else 0.9
                ))

        # Ordina per confidence
        fixes.sort(key=lambda f: f.confidence, reverse=True)
        return fixes


# =============================================================================
# Diagnostic Engine (Main Class)
# =============================================================================

class DiagnosticEngine:
    """
    Engine principale per diagnosi dei fallimenti prompt.

    Combina classifier, hypothesis generator, verification engine
    e fix suggester in un flusso integrato.
    """

    def __init__(self, kb_path: Optional[Path] = None, interactive: bool = False):
        self.kb = KnowledgeBase(kb_path)
        self.classifier = FailureClassifier()
        self.hypothesis_gen = HypothesisGenerator(self.kb)
        self.verifier = VerificationEngine(self.kb)
        self.fix_suggester = FixSuggester(self.kb)
        self.interactive = interactive

    def diagnose(
        self,
        prompt: str,
        failure: TestFailure,
        model: str = 'generic',
        ui: Optional[Any] = None
    ) -> Diagnosis:
        """
        Esegue diagnosi completa.

        Args:
            prompt: Il prompt da analizzare
            failure: Il test failure da diagnosticare
            model: Modello target (per fix model-specific)
            ui: UI per modalità interattiva

        Returns:
            Diagnosis con ipotesi, verifiche e fix suggeriti
        """
        # 1. Classifica il fallimento
        failure_type = self.classifier.classify(failure)

        # 2. Genera ipotesi
        hypotheses = self.hypothesis_gen.generate(failure_type, failure)

        # 3. Verifica ipotesi
        hypotheses = self.verifier.verify_all(hypotheses, prompt)

        # 4. Modalità interattiva: chiedi conferma
        questions_asked = []
        if self.interactive and ui:
            hypotheses, questions_asked = self._interactive_verification(
                hypotheses, failure_type, ui
            )

        # 5. Genera fix
        verified = [h for h in hypotheses if h.verified is True]
        fixes = self.fix_suggester.suggest(hypotheses, model)

        # 6. Calcola confidence complessiva
        if verified:
            overall_confidence = max(h.confidence for h in verified)
        elif hypotheses:
            overall_confidence = hypotheses[0].confidence * 0.7
        else:
            overall_confidence = 0.0

        return Diagnosis(
            failure_type=failure_type,
            hypotheses=hypotheses,
            verified_hypotheses=verified,
            suggested_fixes=fixes,
            questions_asked=questions_asked,
            confidence=overall_confidence
        )

    def _interactive_verification(
        self,
        hypotheses: List[Hypothesis],
        failure_type: FailureType,
        ui: Any
    ) -> tuple:
        """Verifica interattiva con domande all'utente."""
        questions_asked = []

        # Ottieni domande per questo tipo di fallimento
        pattern = self.kb.get_pattern(failure_type.value)
        if not pattern:
            return hypotheses, questions_asked

        pattern_questions = pattern.get('questions', [])

        # Chiedi conferma per ipotesi top
        for h in hypotheses[:2]:
            if h.verified is None:
                response = ui.ask(
                    f"Ipotesi: {h.cause}\n"
                    f"(Confidence: {h.confidence:.0%})\n"
                    f"E' plausibile?",
                    options=["Si", "No", "Non so"]
                )
                questions_asked.append({
                    'question': h.cause,
                    'response': response
                })

                if response == "Si":
                    h.verified = True
                    h.verification_details = "Confirmed by user"
                elif response == "No":
                    h.verified = False
                    h.verification_details = "Rejected by user"

        return hypotheses, questions_asked

    def diagnose_batch(
        self,
        prompt: str,
        failures: List[TestFailure],
        model: str = 'generic'
    ) -> List[Diagnosis]:
        """Diagnosi batch per più fallimenti."""
        return [
            self.diagnose(prompt, failure, model)
            for failure in failures
        ]


# =============================================================================
# Interactive Diagnostic Session
# =============================================================================

@dataclass
class UserContext:
    """Contesto raccolto dall'utente prima della diagnosi."""
    observed_behavior: str = ""
    expected_behavior: str = ""
    frequency: str = ""  # always, sometimes, rare
    model_used: str = ""
    additional_notes: str = ""
    suspected_cause: Optional[str] = None


class InteractiveDiagnostic:
    """
    Sessione interattiva per diagnosi dei fallimenti.

    Implementa un flusso a due fasi:
    - Fase A: Raccolta contesto dall'utente
    - Fase B: Verifica ipotesi con conferma utente

    Usage:
        from src.ui import ConsoleUI
        ui = ConsoleUI()
        session = InteractiveDiagnostic(ui)
        diagnosis = session.run(prompt, test_failure)
    """

    def __init__(self, ui: Any):
        self.ui = ui
        self.engine = DiagnosticEngine()
        self.context: Optional[UserContext] = None

    def run(
        self,
        prompt: str,
        failure: TestFailure,
        model: str = 'generic',
        skip_context: bool = False
    ) -> Diagnosis:
        """
        Esegue diagnosi interattiva completa.

        Args:
            prompt: Prompt da analizzare
            failure: Test failure da diagnosticare
            model: Modello target
            skip_context: Salta fase A (raccolta contesto)

        Returns:
            Diagnosis con ipotesi verificate e fix suggeriti
        """
        self.ui.section("Diagnostic Engine")
        self.ui.info(f"Analisi fallimento: {failure.test_id}")

        # Fase A: Raccolta contesto
        if not skip_context:
            self.context = self._collect_context(failure)

        # Classificazione iniziale
        failure_type = self.engine.classifier.classify(failure)
        self.ui.info(f"Tipo fallimento rilevato: {failure_type.value}")

        # Genera ipotesi
        hypotheses = self.engine.hypothesis_gen.generate(failure_type, failure)
        if not hypotheses:
            self.ui.warning("Nessuna ipotesi generata per questo tipo di fallimento")
            return Diagnosis(
                failure_type=failure_type,
                hypotheses=[],
                confidence=0.0
            )

        # Verifica automatica
        hypotheses = self.engine.verifier.verify_all(hypotheses, prompt)

        # Fase B: Conferma ipotesi con utente
        hypotheses, questions_asked = self._verify_with_user(
            hypotheses, failure_type
        )

        # Genera fix
        verified = [h for h in hypotheses if h.verified is True]
        fixes = self.engine.fix_suggester.suggest(hypotheses, model)

        # Calcola confidence
        if verified:
            confidence = max(h.confidence for h in verified)
        elif hypotheses:
            confidence = hypotheses[0].confidence * 0.7
        else:
            confidence = 0.0

        diagnosis = Diagnosis(
            failure_type=failure_type,
            hypotheses=hypotheses,
            verified_hypotheses=verified,
            suggested_fixes=fixes,
            questions_asked=questions_asked,
            confidence=confidence
        )

        # Mostra risultato
        self._show_diagnosis(diagnosis)

        return diagnosis

    def _collect_context(self, failure: TestFailure) -> UserContext:
        """Fase A: Raccoglie contesto dall'utente."""
        self.ui.section("Raccolta Contesto")
        self.ui.muted("Rispondi alle domande per migliorare la diagnosi")
        self.ui.print("")

        context = UserContext()

        # Comportamento osservato (pre-filled da failure)
        context.observed_behavior = failure.actual
        self.ui.info(f"Risposta ricevuta: {failure.actual[:100]}...")

        # Comportamento atteso
        if failure.expected:
            context.expected_behavior = failure.expected
            self.ui.info(f"Risposta attesa: {failure.expected[:100]}...")
        else:
            context.expected_behavior = self.ui.input(
                "Cosa ti aspettavi?",
                default=""
            )

        # Frequenza del problema
        from src.ui import MenuItem
        freq_choice = self.ui.menu([
            MenuItem("1", "Sempre", "Accade ogni volta"),
            MenuItem("2", "A volte", "Comportamento intermittente"),
            MenuItem("3", "Raramente", "Caso isolato")
        ], prompt="Frequenza del problema >")

        freq_map = {"1": "always", "2": "sometimes", "3": "rare"}
        context.frequency = freq_map.get(freq_choice, "unknown")

        # Modello usato
        context.model_used = self.ui.input(
            "Quale modello?",
            default="generic"
        )

        # Note aggiuntive (opzionale)
        if self.ui.confirm("Vuoi aggiungere note?", default=False):
            context.additional_notes = self.ui.input("Note")

        # Ipotesi utente (opzionale)
        if self.ui.confirm("Hai un'ipotesi sulla causa?", default=False):
            context.suspected_cause = self.ui.input("Ipotesi")

        return context

    def _verify_with_user(
        self,
        hypotheses: List[Hypothesis],
        failure_type: FailureType
    ) -> Tuple[List[Hypothesis], List[Dict[str, str]]]:
        """Fase B: Verifica ipotesi con conferma utente."""
        questions_asked = []

        self.ui.section("Verifica Ipotesi")
        self.ui.muted("Conferma o respingi le ipotesi proposte")
        self.ui.print("")

        # Mostra top 3 ipotesi per conferma
        for i, h in enumerate(hypotheses[:3]):
            if h.verified is not None:
                # Già verificata automaticamente
                status = "[VERIFICATA]" if h.verified else "[RESPINTA]"
                self.ui.info(f"{i+1}. {h.cause} {status}")
                continue

            # Chiedi conferma utente
            self.ui.print(f"\n[{i+1}] Ipotesi: {h.cause}")
            self.ui.muted(f"    Confidence: {h.confidence:.0%} | Fonte: {h.source}")

            from src.ui import MenuItem
            response = self.ui.menu([
                MenuItem("s", "Si", "Conferma questa ipotesi"),
                MenuItem("n", "No", "Respingi questa ipotesi"),
                MenuItem("?", "Non so", "Salta, non sono sicuro")
            ], prompt=f"Plausibile? >")

            questions_asked.append({
                'question': h.cause,
                'response': response
            })

            if response == "s":
                h.verified = True
                h.verification_details = "Confermata dall'utente"
                self.ui.success("Ipotesi confermata")
            elif response == "n":
                h.verified = False
                h.verification_details = "Respinta dall'utente"
                self.ui.warning("Ipotesi respinta")
            # "?" lascia h.verified = None

        return hypotheses, questions_asked

    def _show_diagnosis(self, diagnosis: Diagnosis) -> None:
        """Mostra risultato della diagnosi."""
        self.ui.divider()
        self.ui.section("Diagnosi Completata")

        # Summary
        self.ui.print(f"\nTipo: {diagnosis.failure_type.value}")
        self.ui.print(f"Confidence: {diagnosis.confidence:.0%}")

        # Ipotesi verificate
        if diagnosis.verified_hypotheses:
            self.ui.print("\nCause confermate:")
            for h in diagnosis.verified_hypotheses:
                self.ui.success(f"  {h.cause}")

        # Fix suggeriti
        if diagnosis.suggested_fixes:
            self.ui.section("Fix Suggeriti")
            for i, fix in enumerate(diagnosis.suggested_fixes[:3], 1):
                self.ui.print(f"\n[{i}] {fix.description}")
                self.ui.muted(f"    {fix.template[:200]}...")

    def quick_diagnose(
        self,
        prompt: str,
        failure: TestFailure,
        model: str = 'generic'
    ) -> Diagnosis:
        """
        Diagnosi rapida senza interazione.

        Esegue solo verifiche automatiche, utile per batch.
        """
        return self.engine.diagnose(prompt, failure, model)


# =============================================================================
# CLI Functions
# =============================================================================

def diagnose_cli(
    project_name: str,
    test_id: Optional[str] = None,
    run_number: Optional[int] = None,
    interactive: bool = False,
    model: str = 'generic'
) -> None:
    """CLI per diagnosi."""
    from src.ui import get_ui

    ui = get_ui()
    engine = DiagnosticEngine(interactive=interactive)

    # TODO: Caricare prompt e test failures dal progetto
    ui.info(f"Diagnostic Engine per {project_name}")
    ui.info(f"Interactive: {interactive}, Model: {model}")

    # Placeholder
    ui.warning("Implementazione completa in arrivo...")


if __name__ == "__main__":
    # Test rapido
    engine = DiagnosticEngine()

    test_failure = TestFailure(
        test_id="TEST_001",
        question="Cappelli rossi economici",
        expected="Prodotti sotto 10 euro",
        actual="Prodotti rossi da 50 euro",
        notes="Ha ignorato il criterio economici"
    )

    diagnosis = engine.diagnose(
        prompt="Sei un assistente e-commerce. Aiuta i clienti a trovare prodotti.",
        failure=test_failure
    )

    print(diagnosis.summary())
