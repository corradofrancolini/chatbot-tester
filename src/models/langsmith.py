from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any

@dataclass
class ToolCall:
    """Chiamata a un tool nel trace"""
    name: str
    input: Dict[str, Any]
    output: Optional[Any] = None
    duration_ms: int = 0
    error: Optional[str] = None


@dataclass
class TraceInfo:
    """Informazioni su un trace LangSmith"""
    id: str
    name: str
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_ms: int = 0
    status: str = ""
    input: str = ""
    output: str = ""
    tool_calls: List[ToolCall] = field(default_factory=list)
    tokens_used: int = 0
    model: str = ""
    url: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WaterfallStep:
    """Singolo step nel waterfall tree"""
    name: str
    run_type: str  # llm, tool, chain, retriever, etc.
    duration_ms: int = 0
    start_offset_ms: int = 0  # Offset dall'inizio del trace
    status: str = ""
    error: Optional[str] = None
    depth: int = 0  # Livello di nesting


@dataclass
class SourceDocument:
    """Documento fonte recuperato durante la ricerca"""
    title: str = ""
    source: str = ""  # URL o path
    content_preview: str = ""  # Troncato per display (max 300 char)
    full_content: str = ""     # Contenuto completo per evaluation
    score: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LangSmithReport:
    """Report strutturato per un trace LangSmith"""
    trace_url: str = ""
    duration_ms: int = 0
    status: str = ""
    model: str = ""
    model_provider: str = ""
    vector_store: str = ""  # Vector store provider (es. Qdrant, FAISS)
    tokens_input: int = 0
    tokens_output: int = 0
    tokens_total: int = 0
    tools_used: List[str] = field(default_factory=list)
    tool_count: int = 0
    failed_tools: int = 0
    first_token_ms: int = 0
    error: str = ""
    # Campi estesi
    query: str = ""  # Query/input eseguita
    response: str = ""  # Risposta/output
    waterfall: List[WaterfallStep] = field(default_factory=list)  # Tree della run
    sources: List[SourceDocument] = field(default_factory=list)  # Fonti consultate
    # Metriche timing dettagliate
    llm_duration_ms: int = 0  # Tempo totale LLM
    llm_calls: int = 0  # Numero chiamate LLM
    tool_duration_ms: int = 0  # Tempo totale tool
    retriever_duration_ms: int = 0  # Tempo retriever/RAG
    chain_duration_ms: int = 0  # Tempo chain/orchestration
    queue_time_ms: int = 0  # Tempo in coda (se disponibile)
    streaming_duration_ms: int = 0  # Durata streaming
    tokens_per_second: float = 0.0  # Velocità generazione token

    def format_for_sheets(self) -> str:
        """Formatta il report per inserimento in Google Sheets (colonna LS REPORT)"""
        lines = []

        # === TIMING (prima, più importante) ===
        lines.append("=== TIMING ===")

        # Tempo totale
        if self.duration_ms:
            duration_sec = self.duration_ms / 1000
            lines.append(f"⏱️ Total: {self._format_duration(self.duration_ms)}")

        # Time to first token
        if self.first_token_ms:
            lines.append(f"⚡ TTFT: {self._format_duration(self.first_token_ms)}")

        # Breakdown per componente
        breakdown = []
        if self.llm_duration_ms:
            pct = (self.llm_duration_ms / self.duration_ms * 100) if self.duration_ms else 0
            breakdown.append(f"  • LLM: {self._format_duration(self.llm_duration_ms)} ({pct:.0f}%)")
        if self.tool_duration_ms:
            pct = (self.tool_duration_ms / self.duration_ms * 100) if self.duration_ms else 0
            breakdown.append(f"  • Tools: {self._format_duration(self.tool_duration_ms)} ({pct:.0f}%)")
        if self.retriever_duration_ms:
            pct = (self.retriever_duration_ms / self.duration_ms * 100) if self.duration_ms else 0
            breakdown.append(f"  • RAG/Retriever: {self._format_duration(self.retriever_duration_ms)} ({pct:.0f}%)")
        if self.chain_duration_ms:
            pct = (self.chain_duration_ms / self.duration_ms * 100) if self.duration_ms else 0
            breakdown.append(f"  • Chain: {self._format_duration(self.chain_duration_ms)} ({pct:.0f}%)")

        if breakdown:
            lines.append("Breakdown:")
            lines.extend(breakdown)

        # Token speed
        if self.tokens_per_second > 0:
            lines.append(f"🚀 Speed: {self.tokens_per_second:.1f} tok/s")
        elif self.tokens_output and self.llm_duration_ms:
            # Calcola se non fornito
            tps = self.tokens_output / (self.llm_duration_ms / 1000)
            lines.append(f"🚀 Speed: {tps:.1f} tok/s")

        # === MODEL ===
        if self.model:
            lines.append("")
            lines.append("=== MODEL ===")
            model_str = self.model
            if self.model_provider:
                model_str = f"{self.model_provider}/{self.model}"
            lines.append(f"🤖 {model_str}")
            if self.llm_calls > 1:
                lines.append(f"   ({self.llm_calls} LLM calls)")

        # === TOKENS ===
        if self.tokens_total or self.tokens_input or self.tokens_output:
            lines.append("")
            lines.append("=== TOKENS ===")
            lines.append(f"📊 Input: {self.tokens_input:,}")
            lines.append(f"📊 Output: {self.tokens_output:,}")
            lines.append(f"📊 Total: {self.tokens_total:,}")
            # Stima costo (prezzi GPT-4 Turbo)
            if self.tokens_total > 0:
                cost_estimate = (self.tokens_input * 0.00001) + (self.tokens_output * 0.00003)
                if cost_estimate > 0.0001:
                    lines.append(f"💰 Est. cost: ${cost_estimate:.4f}")

        # === TOOLS ===
        if self.tools_used:
            lines.append("")
            lines.append(f"=== TOOLS ({self.tool_count} calls) ===")
            lines.append(", ".join(self.tools_used))
            if self.failed_tools:
                lines.append(f"❌ Failed: {self.failed_tools}")

        # === WATERFALL TIMING ===
        if self.waterfall:
            lines.append("")
            lines.append(f"=== WATERFALL ({len(self.waterfall)} steps) ===")
            # Mostra solo gli step principali (depth <= 1) con timing
            main_steps = [s for s in self.waterfall if s.depth <= 1]
            for step in main_steps[:10]:  # Max 10 step
                status_icon = "✓" if step.status == "success" else "✗" if step.error else "→"
                duration_str = f"{step.duration_ms}ms" if step.duration_ms < 1000 else f"{step.duration_ms/1000:.1f}s"
                lines.append(f"  {status_icon} {step.name} ({step.run_type}): {duration_str}")
            if len(main_steps) > 10:
                lines.append(f"  ... +{len(main_steps) - 10} more steps")

        # === SOURCES ===
        if self.sources:
            lines.append("")
            lines.append(f"=== SOURCES ({len(self.sources)}) ===")
            for src in self.sources[:5]:  # Max 5 sources
                title = src.title or src.source or "Unknown"
                score_str = f" [{src.score:.2f}]" if src.score else ""
                lines.append(f"• {title}{score_str}")
            if len(self.sources) > 5:
                lines.append(f"  ... +{len(self.sources) - 5} more sources")

        # === QUERY (breve) ===
        if self.query:
            lines.append("")
            lines.append("=== QUERY ===")
            query_preview = self.query[:150] + "..." if len(self.query) > 150 else self.query
            lines.append(query_preview)

        # === RESPONSE (breve) ===
        if self.response:
            lines.append("")
            lines.append("=== RESPONSE ===")
            response_preview = self.response[:200] + "..." if len(self.response) > 200 else self.response
            lines.append(response_preview)

        # === ERRORS ===
        has_errors = self.error or self.failed_tools or (self.status and self.status != "success")
        waterfall_errors = [s for s in self.waterfall if s.error]

        if has_errors or waterfall_errors:
            lines.append("")
            lines.append("=== ERRORS ===")
            if self.status and self.status != "success":
                lines.append(f"Status: {self.status}")
            if self.error:
                lines.append(f"Error: {self.error[:150]}")
            for step in waterfall_errors[:3]:  # Max 3 errori
                lines.append(f"• {step.name}: {step.error[:80]}")

        # === TRACE URL ===
        if self.trace_url:
            lines.append("")
            lines.append("=== TRACE ===")
            lines.append(self.trace_url)

        return "\n".join(lines) if lines else ""

    def _format_duration(self, ms: int) -> str:
        """Formatta durata in modo leggibile"""
        if ms < 1000:
            return f"{ms}ms"
        elif ms < 60000:
            return f"{ms/1000:.2f}s"
        else:
            mins = ms // 60000
            secs = (ms % 60000) / 1000
            return f"{mins}m {secs:.1f}s"

    def get_model_version(self) -> str:
        """Restituisce stringa model version per il report"""
        if self.model_provider and self.model:
            return f"{self.model_provider}/{self.model}"
        return self.model or ""

    def get_rag_context(self, max_docs: int = 5, max_chars: int = 10000) -> Optional[str]:
        """
        Restituisce contesto RAG concatenato dai documenti recuperati.

        Utile per passare automaticamente il contesto all'Evaluator
        senza richiedere file manuali.

        Args:
            max_docs: Numero massimo di documenti da includere
            max_chars: Lunghezza massima totale del contesto

        Returns:
            Stringa con contesto concatenato, o None se nessun documento
        """
        if not self.sources:
            return None

        context_parts = []
        total_chars = 0

        for doc in self.sources[:max_docs]:
            # Usa full_content se disponibile, altrimenti content_preview
            content = doc.full_content or doc.content_preview
            if not content:
                continue

            # Aggiungi source come header se disponibile
            if doc.source:
                header = f"[Source: {doc.source}]\n"
            else:
                header = ""

            part = f"{header}{content}\n\n---\n\n"

            # Verifica limite caratteri
            if total_chars + len(part) > max_chars:
                # Tronca l'ultimo documento se necessario
                remaining = max_chars - total_chars
                if remaining > 100:
                    context_parts.append(part[:remaining] + "...")
                break

            context_parts.append(part)
            total_chars += len(part)

        return "".join(context_parts).strip() if context_parts else None
