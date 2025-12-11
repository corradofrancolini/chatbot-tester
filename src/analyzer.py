"""
Analyzer - Analisi automatica dei test falliti

Funzionalita:
- Generazione debug package da test falliti
- Integrazione Claude API per analisi
- Integrazione Groq API per analisi
- Modalita manuale (clipboard)
- Suggerimenti per fix prompt

Providers supportati:
- manual: genera debug package e copia in clipboard
- claude: analisi via Claude API (Anthropic)
- groq: analisi via Groq API (modelli open-source veloci)

Usage:
    analyzer = create_analyzer("claude")
    results = analyzer.analyze_failures(project, run_number)
"""

import os
import json
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any, Literal
from enum import Enum


# ═══════════════════════════════════════════════════════════════════════════════
# Data Classes
# ═══════════════════════════════════════════════════════════════════════════════

class AnalyzerProvider(str, Enum):
    """Provider disponibili per l'analisi."""
    MANUAL = "manual"
    CLAUDE = "claude"
    GROQ = "groq"


@dataclass
class TestFailure:
    """Rappresenta un test fallito."""
    test_id: str
    test_name: str
    question: str
    expected: str
    actual: str
    notes: Optional[str] = None
    langsmith_url: Optional[str] = None
    langsmith_trace: Optional[Dict[str, Any]] = None
    screenshot_path: Optional[str] = None


@dataclass
class DebugPackage:
    """Pacchetto di debug per analisi."""
    project: str
    run_number: int
    timestamp: str
    prompt_version: Optional[str]
    prompt_content: Optional[str]
    failures: List[TestFailure]
    total_tests: int
    passed_tests: int
    failed_tests: int

    def to_markdown(self) -> str:
        """Genera rappresentazione Markdown del pacchetto."""
        lines = [
            f"# Debug Package - {self.project}",
            f"",
            f"**Run:** {self.run_number}",
            f"**Data:** {self.timestamp}",
            f"**Test totali:** {self.total_tests}",
            f"**Passati:** {self.passed_tests}",
            f"**Falliti:** {self.failed_tests}",
            f"",
        ]

        # Prompt section
        if self.prompt_content:
            lines.extend([
                f"## Prompt Attuale (v{self.prompt_version or 'unknown'})",
                f"",
                f"```",
                self.prompt_content,
                f"```",
                f"",
            ])

        # Failures section
        lines.extend([
            f"## Test Falliti ({len(self.failures)})",
            f"",
        ])

        for i, failure in enumerate(self.failures, 1):
            lines.extend([
                f"### {i}. {failure.test_name} (ID: {failure.test_id})",
                f"",
                f"**Domanda:**",
                f"> {failure.question}",
                f"",
                f"**Risposta attesa:**",
                f"> {failure.expected}",
                f"",
                f"**Risposta ricevuta:**",
                f"> {failure.actual}",
                f"",
            ])

            if failure.notes:
                lines.extend([
                    f"**Note:**",
                    f"> {failure.notes}",
                    f"",
                ])

            if failure.langsmith_url:
                lines.extend([
                    f"**LangSmith Trace:** [{failure.langsmith_url}]({failure.langsmith_url})",
                    f"",
                ])

            if failure.langsmith_trace:
                lines.extend([
                    f"**LangSmith Details:**",
                    f"```json",
                    json.dumps(failure.langsmith_trace, indent=2, ensure_ascii=False)[:2000],
                    f"```",
                    f"",
                ])

            lines.append("---")
            lines.append("")

        return "\n".join(lines)

    def to_analysis_prompt(self) -> str:
        """Genera prompt per l'analisi LLM."""
        return f"""Sei un esperto di prompt engineering. Analizza i seguenti test falliti di un chatbot e suggerisci modifiche al prompt per risolvere i problemi.

{self.to_markdown()}

## Istruzioni per l'analisi

Per ogni test fallito:
1. Identifica il PROBLEMA: perche' il bot ha risposto in modo errato?
2. Trova la CAUSA nel prompt: cosa manca o e' ambiguo?
3. Suggerisci un FIX: modifica specifica al prompt

Alla fine, fornisci:
- Un RIEPILOGO dei problemi comuni
- Una VERSIONE CORRETTA del prompt (se possibile)
- PRIORITA' dei fix (da piu' critico a meno critico)

Rispondi in italiano."""


@dataclass
class AnalysisResult:
    """Risultato dell'analisi."""
    provider: str
    timestamp: str
    debug_package: DebugPackage
    analysis: str
    suggestions: List[str] = field(default_factory=list)
    estimated_cost: Optional[float] = None

    def to_markdown(self) -> str:
        """Genera report Markdown."""
        lines = [
            f"# Analisi Test Falliti - {self.debug_package.project}",
            f"",
            f"**Provider:** {self.provider}",
            f"**Data:** {self.timestamp}",
            f"**Run analizzata:** {self.debug_package.run_number}",
            f"**Test falliti analizzati:** {len(self.debug_package.failures)}",
        ]

        if self.estimated_cost:
            lines.append(f"**Costo stimato:** ${self.estimated_cost:.4f}")

        lines.extend([
            f"",
            f"---",
            f"",
            f"## Analisi",
            f"",
            self.analysis,
            f"",
        ])

        if self.suggestions:
            lines.extend([
                f"## Suggerimenti Rapidi",
                f"",
            ])
            for i, suggestion in enumerate(self.suggestions, 1):
                lines.append(f"{i}. {suggestion}")
            lines.append("")

        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# Debug Package Generator
# ═══════════════════════════════════════════════════════════════════════════════

class DebugPackageGenerator:
    """Genera debug package da una run di test."""

    def __init__(self, project_name: str, base_dir: Optional[Path] = None):
        self.project_name = project_name

        if base_dir:
            self.base_dir = Path(base_dir)
        else:
            self.base_dir = Path(__file__).parent.parent

        self.reports_dir = self.base_dir / "reports" / project_name

    def get_available_runs(self) -> List[int]:
        """Ritorna lista delle run disponibili."""
        if not self.reports_dir.exists():
            return []

        runs = []
        for d in self.reports_dir.iterdir():
            if d.is_dir() and d.name.startswith("run_"):
                try:
                    run_num = int(d.name.replace("run_", ""))
                    runs.append(run_num)
                except ValueError:
                    pass

        return sorted(runs, reverse=True)

    def get_latest_run(self) -> Optional[int]:
        """Ritorna il numero dell'ultima run."""
        runs = self.get_available_runs()
        return runs[0] if runs else None

    def generate(self, run_number: Optional[int] = None) -> Optional[DebugPackage]:
        """
        Genera debug package per una run specifica.

        Args:
            run_number: Numero run (default: ultima)

        Returns:
            DebugPackage o None se errore
        """
        if run_number is None:
            run_number = self.get_latest_run()

        if run_number is None:
            return None

        run_dir = self.reports_dir / f"run_{run_number:03d}"
        if not run_dir.exists():
            # Prova formato senza zero padding
            run_dir = self.reports_dir / f"run_{run_number}"
            if not run_dir.exists():
                return None

        # Carica summary
        summary_path = run_dir / "summary.json"
        if not summary_path.exists():
            return None

        with open(summary_path, 'r', encoding='utf-8') as f:
            summary = json.load(f)

        # Carica report CSV per dettagli test
        failures = self._extract_failures(run_dir, summary)

        # Carica prompt corrente
        prompt_content, prompt_version = self._load_current_prompt()

        return DebugPackage(
            project=self.project_name,
            run_number=run_number,
            timestamp=datetime.now().isoformat(),
            prompt_version=prompt_version,
            prompt_content=prompt_content,
            failures=failures,
            total_tests=summary.get('total_tests', 0),
            passed_tests=summary.get('passed', 0),
            failed_tests=summary.get('failed', 0)
        )

    def _extract_failures(self, run_dir: Path, summary: Dict) -> List[TestFailure]:
        """Estrae i test falliti dalla run."""
        failures = []

        # Prova a caricare da report.csv
        report_csv = run_dir / "report.csv"
        if report_csv.exists():
            failures = self._parse_report_csv(report_csv)
        else:
            # Fallback: estrai da summary se disponibile
            for test in summary.get('tests', []):
                if test.get('esito') == 'FAIL':
                    failures.append(TestFailure(
                        test_id=test.get('id', 'unknown'),
                        test_name=test.get('name', 'Unknown Test'),
                        question=test.get('question', ''),
                        expected=test.get('expected', ''),
                        actual=test.get('actual', ''),
                        notes=test.get('notes'),
                        langsmith_url=test.get('langsmith_url'),
                        langsmith_trace=test.get('langsmith_trace')
                    ))

        return failures

    def _parse_report_csv(self, csv_path: Path) -> List[TestFailure]:
        """Parsa report.csv per estrarre fallimenti."""
        import csv

        failures = []

        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Cerca colonne con esito FAIL
                esito = row.get('esito', row.get('Esito', row.get('result', '')))
                if esito.upper() == 'FAIL':
                    failures.append(TestFailure(
                        test_id=row.get('id', row.get('ID', row.get('test_id', 'unknown'))),
                        test_name=row.get('name', row.get('Nome', row.get('test_name', 'Unknown'))),
                        question=row.get('question', row.get('Domanda', row.get('input', ''))),
                        expected=row.get('expected', row.get('Atteso', row.get('expected_output', ''))),
                        actual=row.get('actual', row.get('Ricevuto', row.get('actual_output', ''))),
                        notes=row.get('notes', row.get('Note', None)),
                        langsmith_url=row.get('langsmith_url', row.get('LangSmith', None))
                    ))

        return failures

    def _load_current_prompt(self) -> tuple[Optional[str], Optional[str]]:
        """Carica il prompt corrente del progetto."""
        from src.prompt_manager import PromptManager

        try:
            manager = PromptManager(self.project_name, self.base_dir)
            content = manager.get_current()
            version = manager.get_current_version()
            return content, str(version.version) if version else None
        except Exception:
            return None, None


# ═══════════════════════════════════════════════════════════════════════════════
# Analyzer Base Class
# ═══════════════════════════════════════════════════════════════════════════════

class BaseAnalyzer(ABC):
    """Classe base per gli analyzer."""

    provider: AnalyzerProvider

    @abstractmethod
    def analyze(self, package: DebugPackage) -> AnalysisResult:
        """Esegue l'analisi del debug package."""
        pass

    @abstractmethod
    def estimate_cost(self, package: DebugPackage) -> float:
        """Stima il costo dell'analisi."""
        pass

    def save_result(self, result: AnalysisResult, output_dir: Path) -> Path:
        """Salva il risultato dell'analisi."""
        analysis_dir = output_dir / "analysis"
        analysis_dir.mkdir(exist_ok=True)

        # Salva markdown
        md_path = analysis_dir / f"analysis_{result.provider}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(result.to_markdown())

        # Salva anche il debug package
        pkg_path = analysis_dir / "debug_package.md"
        with open(pkg_path, 'w', encoding='utf-8') as f:
            f.write(result.debug_package.to_markdown())

        return md_path


# ═══════════════════════════════════════════════════════════════════════════════
# Manual Analyzer (Clipboard)
# ═══════════════════════════════════════════════════════════════════════════════

class ManualAnalyzer(BaseAnalyzer):
    """Analyzer manuale: genera package e copia in clipboard."""

    provider = AnalyzerProvider.MANUAL

    def analyze(self, package: DebugPackage) -> AnalysisResult:
        """Genera package e copia in clipboard."""
        content = package.to_analysis_prompt()

        # Copia in clipboard
        self._copy_to_clipboard(content)

        return AnalysisResult(
            provider=self.provider.value,
            timestamp=datetime.now().isoformat(),
            debug_package=package,
            analysis="[Contenuto copiato in clipboard - incolla su Claude per l'analisi]",
            suggestions=["Incolla il contenuto su Claude o altro LLM per ottenere l'analisi"],
            estimated_cost=0.0
        )

    def estimate_cost(self, package: DebugPackage) -> float:
        """Modalita manuale e' gratuita."""
        return 0.0

    def _copy_to_clipboard(self, content: str) -> bool:
        """Copia contenuto in clipboard (macOS/Linux/Windows)."""
        import sys

        try:
            if sys.platform == 'darwin':
                # macOS
                process = subprocess.Popen(['pbcopy'], stdin=subprocess.PIPE)
                process.communicate(content.encode('utf-8'))
                return process.returncode == 0
            elif sys.platform.startswith('linux'):
                # Linux (richiede xclip)
                process = subprocess.Popen(['xclip', '-selection', 'clipboard'],
                                           stdin=subprocess.PIPE)
                process.communicate(content.encode('utf-8'))
                return process.returncode == 0
            elif sys.platform == 'win32':
                # Windows
                process = subprocess.Popen(['clip'], stdin=subprocess.PIPE, shell=True)
                process.communicate(content.encode('utf-8'))
                return process.returncode == 0
        except Exception:
            pass

        return False


# ═══════════════════════════════════════════════════════════════════════════════
# Claude Analyzer
# ═══════════════════════════════════════════════════════════════════════════════

class ClaudeAnalyzer(BaseAnalyzer):
    """Analyzer che usa Claude API."""

    provider = AnalyzerProvider.CLAUDE

    # Prezzi per 1M token (approssimati)
    INPUT_COST_PER_1M = 3.0   # $3 per 1M input tokens (Sonnet)
    OUTPUT_COST_PER_1M = 15.0  # $15 per 1M output tokens (Sonnet)

    def __init__(self, api_key: Optional[str] = None, model: str = "claude-sonnet-4-20250514"):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.model = model

        if not self.api_key:
            raise ValueError(
                "Claude API key non trovata. "
                "Imposta ANTHROPIC_API_KEY o passa api_key al costruttore."
            )

    def analyze(self, package: DebugPackage) -> AnalysisResult:
        """Esegue analisi via Claude API."""
        try:
            import anthropic
        except ImportError:
            raise ImportError(
                "anthropic non installato. Esegui: pip install anthropic"
            )

        client = anthropic.Anthropic(api_key=self.api_key)

        prompt = package.to_analysis_prompt()

        message = client.messages.create(
            model=self.model,
            max_tokens=4096,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        analysis_text = message.content[0].text

        # Calcola costo effettivo
        input_tokens = message.usage.input_tokens
        output_tokens = message.usage.output_tokens
        cost = (input_tokens * self.INPUT_COST_PER_1M / 1_000_000 +
                output_tokens * self.OUTPUT_COST_PER_1M / 1_000_000)

        return AnalysisResult(
            provider=self.provider.value,
            timestamp=datetime.now().isoformat(),
            debug_package=package,
            analysis=analysis_text,
            suggestions=self._extract_suggestions(analysis_text),
            estimated_cost=cost
        )

    def estimate_cost(self, package: DebugPackage) -> float:
        """Stima costo basato sulla lunghezza del contenuto."""
        content = package.to_analysis_prompt()
        # Stima approssimativa: 4 caratteri = 1 token
        estimated_input_tokens = len(content) / 4
        estimated_output_tokens = 2000  # Risposta media

        return (estimated_input_tokens * self.INPUT_COST_PER_1M / 1_000_000 +
                estimated_output_tokens * self.OUTPUT_COST_PER_1M / 1_000_000)

    def _extract_suggestions(self, analysis: str) -> List[str]:
        """Estrae suggerimenti dal testo dell'analisi."""
        suggestions = []
        lines = analysis.split('\n')

        in_suggestions = False
        for line in lines:
            line = line.strip()
            if 'suggerim' in line.lower() or 'priorit' in line.lower():
                in_suggestions = True
                continue
            if in_suggestions and line.startswith(('1.', '2.', '3.', '-', '*')):
                # Rimuovi bullet/numero
                suggestion = line.lstrip('0123456789.-*) ').strip()
                if suggestion and len(suggestion) > 10:
                    suggestions.append(suggestion)
                    if len(suggestions) >= 5:
                        break

        return suggestions


# ═══════════════════════════════════════════════════════════════════════════════
# Groq Analyzer
# ═══════════════════════════════════════════════════════════════════════════════

class GroqAnalyzer(BaseAnalyzer):
    """Analyzer che usa Groq API."""

    provider = AnalyzerProvider.GROQ

    # Groq e' molto piu' economico
    INPUT_COST_PER_1M = 0.05   # $0.05 per 1M input tokens
    OUTPUT_COST_PER_1M = 0.10  # $0.10 per 1M output tokens

    def __init__(self, api_key: Optional[str] = None,
                 model: str = "llama-3.1-70b-versatile"):
        self.api_key = api_key or os.environ.get("GROQ_API_KEY")
        self.model = model

        if not self.api_key:
            raise ValueError(
                "Groq API key non trovata. "
                "Imposta GROQ_API_KEY o passa api_key al costruttore."
            )

    def analyze(self, package: DebugPackage) -> AnalysisResult:
        """Esegue analisi via Groq API."""
        try:
            from groq import Groq
        except ImportError:
            raise ImportError(
                "groq non installato. Esegui: pip install groq"
            )

        client = Groq(api_key=self.api_key)

        prompt = package.to_analysis_prompt()

        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "user", "content": prompt}
            ],
            model=self.model,
            max_tokens=4096,
            temperature=0.3
        )

        analysis_text = chat_completion.choices[0].message.content

        # Calcola costo
        input_tokens = chat_completion.usage.prompt_tokens
        output_tokens = chat_completion.usage.completion_tokens
        cost = (input_tokens * self.INPUT_COST_PER_1M / 1_000_000 +
                output_tokens * self.OUTPUT_COST_PER_1M / 1_000_000)

        return AnalysisResult(
            provider=self.provider.value,
            timestamp=datetime.now().isoformat(),
            debug_package=package,
            analysis=analysis_text,
            suggestions=self._extract_suggestions(analysis_text),
            estimated_cost=cost
        )

    def estimate_cost(self, package: DebugPackage) -> float:
        """Stima costo (Groq e' molto economico)."""
        content = package.to_analysis_prompt()
        estimated_input_tokens = len(content) / 4
        estimated_output_tokens = 2000

        return (estimated_input_tokens * self.INPUT_COST_PER_1M / 1_000_000 +
                estimated_output_tokens * self.OUTPUT_COST_PER_1M / 1_000_000)

    def _extract_suggestions(self, analysis: str) -> List[str]:
        """Estrae suggerimenti dal testo dell'analisi."""
        # Stessa logica di Claude
        suggestions = []
        lines = analysis.split('\n')

        in_suggestions = False
        for line in lines:
            line = line.strip()
            if 'suggerim' in line.lower() or 'priorit' in line.lower():
                in_suggestions = True
                continue
            if in_suggestions and line.startswith(('1.', '2.', '3.', '-', '*')):
                suggestion = line.lstrip('0123456789.-*) ').strip()
                if suggestion and len(suggestion) > 10:
                    suggestions.append(suggestion)
                    if len(suggestions) >= 5:
                        break

        return suggestions


# ═══════════════════════════════════════════════════════════════════════════════
# Factory
# ═══════════════════════════════════════════════════════════════════════════════

def create_analyzer(provider: str = "manual", **kwargs) -> BaseAnalyzer:
    """
    Crea un analyzer del tipo specificato.

    Args:
        provider: "manual", "claude", o "groq"
        **kwargs: Argomenti per il costruttore specifico

    Returns:
        Istanza di BaseAnalyzer

    Raises:
        ValueError: Se provider non riconosciuto
    """
    provider = provider.lower()

    if provider == "manual":
        return ManualAnalyzer()
    elif provider == "claude":
        return ClaudeAnalyzer(**kwargs)
    elif provider == "groq":
        return GroqAnalyzer(**kwargs)
    else:
        raise ValueError(
            f"Provider '{provider}' non riconosciuto. "
            f"Usa: manual, claude, groq"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# CLI Functions
# ═══════════════════════════════════════════════════════════════════════════════

def run_analysis(
    project_name: str,
    provider: str = "manual",
    run_number: Optional[int] = None,
    skip_confirm: bool = False,
    base_dir: Optional[Path] = None
) -> Optional[AnalysisResult]:
    """
    Esegue analisi dei test falliti.

    Args:
        project_name: Nome progetto
        provider: Provider da usare (manual/claude/groq)
        run_number: Numero run (default: ultima)
        skip_confirm: Salta conferma costi
        base_dir: Directory base

    Returns:
        AnalysisResult o None se annullato/errore
    """
    from src.ui import get_ui
    from src.cli_utils import ExitCode

    ui = get_ui()

    # Genera debug package
    generator = DebugPackageGenerator(project_name, base_dir)

    if run_number is None:
        run_number = generator.get_latest_run()
        if run_number is None:
            ui.error(f"Nessuna run trovata per {project_name}")
            return None

    ui.section(f"Analisi Test Falliti - {project_name}")
    ui.print(f"  Run: {run_number}")
    ui.print(f"  Provider: {provider}")

    package = generator.generate(run_number)
    if package is None:
        ui.error(f"Impossibile generare debug package per run {run_number}")
        return None

    if not package.failures:
        ui.success("Nessun test fallito da analizzare")
        return None

    ui.print(f"  Test falliti: {len(package.failures)}")

    # Crea analyzer
    try:
        analyzer = create_analyzer(provider)
    except ValueError as e:
        ui.error(str(e))
        return None
    except ImportError as e:
        ui.error(str(e))
        return None

    # Stima e conferma costi (se non manual)
    if provider != "manual" and not skip_confirm:
        estimated_cost = analyzer.estimate_cost(package)
        ui.print(f"  Costo stimato: ${estimated_cost:.4f}")

        confirm = input(f"\n  Procedere con l'analisi? [s/N] ").strip().lower()
        if confirm not in ('s', 'si', 'y', 'yes'):
            ui.info("Analisi annullata")
            return None

    # Esegui analisi
    ui.print("\n  Analisi in corso...")

    try:
        result = analyzer.analyze(package)
    except Exception as e:
        ui.error(f"Errore durante l'analisi: {e}")
        return None

    # Salva risultato
    if base_dir is None:
        base_dir = Path(__file__).parent.parent

    run_dir = base_dir / "reports" / project_name / f"run_{run_number:03d}"
    if not run_dir.exists():
        run_dir = base_dir / "reports" / project_name / f"run_{run_number}"

    saved_path = analyzer.save_result(result, run_dir)

    # Output
    ui.success(f"Analisi completata")
    ui.print(f"  Salvata in: {saved_path}")

    if provider == "manual":
        ui.info("\n  Debug package copiato in clipboard!")
        ui.muted("  Incolla su Claude per ottenere l'analisi")
    else:
        if result.estimated_cost:
            ui.print(f"  Costo effettivo: ${result.estimated_cost:.4f}")

        ui.section("Riepilogo Analisi")
        # Mostra primi 1000 caratteri
        preview = result.analysis[:1000]
        if len(result.analysis) > 1000:
            preview += "\n\n[...continua nel file salvato]"
        ui.print(preview)

        if result.suggestions:
            ui.section("Suggerimenti Principali")
            for i, suggestion in enumerate(result.suggestions[:3], 1):
                ui.print(f"  {i}. {suggestion}")

    # Next steps
    from src.cli_utils import NextSteps
    steps = [
        f"Vedi analisi completa: cat {saved_path}",
        f"Modifica prompt: chatbot-tester -p {project_name} --prompt-show",
    ]
    ui.muted(NextSteps.format(steps))

    return result
