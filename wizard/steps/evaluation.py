"""
Step 8: Evaluation Configuration
Configures automatic evaluation of chatbot responses.
"""

from typing import Tuple
from rich.prompt import Prompt, Confirm
from rich.table import Table

from wizard.steps.base import BaseStep
from src.ui import console
from src.i18n import t


class EvaluationStep(BaseStep):
    """Step 8: Configure evaluation metrics and thresholds."""

    step_number = 8
    step_key = "step8"
    is_optional = True
    estimated_time = 3.0

    def _show_metrics_info(self):
        """Display information about available metrics."""
        console.print("\n  [bold]Metriche disponibili:[/bold]\n")

        table = Table(show_header=True, header_style="bold cyan", box=None, padding=(0, 2))
        table.add_column("Metrica", style="bold")
        table.add_column("Descrizione")
        table.add_column("Richiede")

        table.add_row(
            "SEMANTIC",
            "Similarita semantica con risposta attesa",
            "expected_answer nel test"
        )
        table.add_row(
            "JUDGE",
            "LLM-as-judge (GPT-4o-mini valuta la risposta)",
            "Solo la risposta"
        )
        table.add_row(
            "GROUND",
            "Groundedness - risposta basata sul contesto",
            "Contesto RAG"
        )
        table.add_row(
            "FAITH",
            "Faithfulness - fedelta al contesto recuperato",
            "Contesto RAG"
        )
        table.add_row(
            "RELEV",
            "Relevance - pertinenza della risposta",
            "Contesto RAG"
        )

        console.print(table)
        console.print()

    def _configure_thresholds(self) -> None:
        """Configure threshold values."""
        console.print("\n  [bold]Configurazione soglie[/bold]")
        console.print("  [dim]Le soglie determinano quando un test passa/fallisce.[/dim]")
        console.print("  [dim]Valori tra 0.0 e 1.0. Piu alto = piu severo.[/dim]\n")

        # Semantic threshold
        console.print(f"  Semantic (similarita semantica)")
        console.print(f"  [dim]Default: 0.7 - Richiede expected_answer nel test[/dim]")
        val = Prompt.ask("  Soglia", default=str(self.state.eval_semantic_threshold))
        try:
            self.state.eval_semantic_threshold = max(0.0, min(1.0, float(val)))
        except ValueError:
            pass

        # Judge threshold
        console.print(f"\n  Judge (LLM-as-judge)")
        console.print(f"  [dim]Default: 0.6 - GPT-4o-mini valuta qualita risposta[/dim]")
        val = Prompt.ask("  Soglia", default=str(self.state.eval_judge_threshold))
        try:
            self.state.eval_judge_threshold = max(0.0, min(1.0, float(val)))
        except ValueError:
            pass

        # RAG threshold
        console.print(f"\n  RAG (groundedness, faithfulness, relevance)")
        console.print(f"  [dim]Default: 0.5 - Richiede contesto da LangSmith o file[/dim]")
        val = Prompt.ask("  Soglia", default=str(self.state.eval_rag_threshold))
        try:
            self.state.eval_rag_threshold = max(0.0, min(1.0, float(val)))
        except ValueError:
            pass

    def _show_calibration_info(self):
        """Show information about calibration."""
        console.print("\n  [cyan]" + "-" * 50 + "[/cyan]")
        console.print("  [bold]Calibrazione soglie[/bold]")
        console.print("  [cyan]" + "-" * 50 + "[/cyan]")
        console.print("""
  Le soglie ottimali dipendono dal tipo di chatbot:
  - Chatbot informativo: soglie alte (0.7-0.8)
  - Chatbot creativo: soglie basse (0.4-0.5)
  - Assistente generico: soglie medie (0.5-0.6)

  Dopo alcune run con evaluation attivo, usa:

    [bold green]python run.py -p {project} --calibrate[/bold green]

  per analizzare le metriche e ottenere soglie ottimali
  basate sui dati reali del tuo chatbot.
""".format(project=self.state.project_name or "PROGETTO"))

    def run(self) -> Tuple[bool, str]:
        """Execute Evaluation configuration."""
        self.show()

        # Info about evaluation
        console.print("\n  [dim]L'evaluation analizza automaticamente le risposte del chatbot[/dim]")
        console.print("  [dim]usando metriche semantiche e LLM-as-judge.[/dim]")

        # Show metrics info
        self._show_metrics_info()

        # Ask to enable
        enable = Confirm.ask("\n  Abilitare evaluation automatico?", default=True)
        self.state.evaluation_enabled = enable

        if enable:
            # Auto RAG context (only if LangSmith enabled)
            if self.state.langsmith_enabled:
                console.print("\n  [bold]Auto RAG Context[/bold]")
                console.print("  [dim]Estrae automaticamente il contesto RAG da LangSmith[/dim]")
                console.print("  [dim]per abilitare le metriche GROUND/FAITH/RELEV.[/dim]")
                self.state.eval_auto_rag_context = Confirm.ask(
                    "\n  Abilitare Auto RAG Context?",
                    default=True
                )
            else:
                console.print("\n  [yellow]!  LangSmith non abilitato[/yellow]")
                console.print("  [dim]Le metriche RAG richiederanno file di contesto manuali.[/dim]")
                self.state.eval_auto_rag_context = False

            # Thresholds configuration
            console.print("\n  [bold]Configurazione soglie[/bold]")
            customize = Confirm.ask("  Personalizzare le soglie? (altrimenti usa default)", default=False)

            if customize:
                self._configure_thresholds()
            else:
                # Use sensible defaults
                self.state.eval_semantic_threshold = 0.7
                self.state.eval_judge_threshold = 0.6
                self.state.eval_rag_threshold = 0.5

            # Show calibration info
            self._show_calibration_info()

        # Summary
        console.print("\n  [cyan]" + "-" * 50 + "[/cyan]")
        console.print(f"  [bold]Riepilogo Evaluation[/bold]")
        console.print("  [cyan]" + "-" * 50 + "[/cyan]")
        console.print(f"  Evaluation: {'[green]Abilitato[/green]' if self.state.evaluation_enabled else '[yellow]Disabilitato[/yellow]'}")

        if self.state.evaluation_enabled:
            console.print(f"  Auto RAG Context: {'[green]Si[/green]' if self.state.eval_auto_rag_context else '[yellow]No[/yellow]'}")
            console.print(f"  Soglia Semantic: {self.state.eval_semantic_threshold}")
            console.print(f"  Soglia Judge: {self.state.eval_judge_threshold}")
            console.print(f"  Soglia RAG: {self.state.eval_rag_threshold}")

        console.print("  [cyan]" + "-" * 50 + "[/cyan]")

        # Navigation
        console.print("\n  [dim]Premi INVIO per continuare, 'b' per tornare indietro...[/dim]")
        nav = input("  ").strip().lower()

        if nav == 'b':
            return True, 'back'
        elif nav == 'q':
            return False, 'quit'

        self.state.mark_step_complete(self.step_number)
        return True, 'next'
