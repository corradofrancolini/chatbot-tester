"""
LangSmith Client - Integrazione per debug e analisi chatbot

Gestisce:
- Recupero trace delle conversazioni
- Analisi tool routing
- Estrazione metriche performance
- Context envelope inspection
"""

import requests
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, field


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
    content_preview: str = ""
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

    def format_for_sheets(self) -> str:
        """Formatta il report per inserimento in Google Sheets (colonna NOTES)"""
        lines = []

        # === QUERY ===
        if self.query:
            lines.append("=== QUERY ===")
            query_preview = self.query[:200] + "..." if len(self.query) > 200 else self.query
            lines.append(query_preview)

        # === RESPONSE ===
        if self.response:
            lines.append("")
            lines.append("=== RESPONSE ===")
            response_preview = self.response[:300] + "..." if len(self.response) > 300 else self.response
            lines.append(response_preview)

        # === PERFORMANCE ===
        perf_lines = []
        if self.model:
            model_str = self.model
            if self.model_provider:
                model_str += f" ({self.model_provider})"
            perf_lines.append(f"Model: {model_str}")
        if self.duration_ms:
            perf_lines.append(f"Duration: {self.duration_ms}ms")
        if self.first_token_ms:
            perf_lines.append(f"First Token: {self.first_token_ms}ms")
        if self.tokens_total or self.tokens_input or self.tokens_output:
            perf_lines.append(f"Tokens: {self.tokens_input} in / {self.tokens_output} out")

        if perf_lines:
            lines.append("")
            lines.append("=== PERFORMANCE ===")
            lines.extend(perf_lines)

        # === TOOLS ===
        if self.tools_used:
            lines.append("")
            lines.append(f"=== TOOLS ({self.tool_count}) ===")
            lines.append(", ".join(self.tools_used))
            if self.failed_tools:
                lines.append(f"Failed: {self.failed_tools}")

        # === SOURCES ===
        if self.sources:
            lines.append("")
            lines.append(f"=== SOURCES ({len(self.sources)}) ===")
            for src in self.sources:
                title = src.title or src.source or "Unknown"
                score_str = f" [{src.score:.2f}]" if src.score else ""
                lines.append(f"• {title}{score_str}")
                if src.source and src.source != title:
                    lines.append(f"  {src.source}")
                if src.content_preview:
                    preview = src.content_preview[:120] + "..." if len(src.content_preview) > 120 else src.content_preview
                    lines.append(f"  \"{preview}\"")

        # === WATERFALL ===
        if self.waterfall:
            lines.append("")
            lines.append(f"=== WATERFALL ({len(self.waterfall)} steps) ===")
            for step in self.waterfall:
                indent = "  " * step.depth
                status_icon = "✓" if step.status == "success" else "✗" if step.error else "→"
                lines.append(f"{indent}{status_icon} {step.name} ({step.run_type}) {step.duration_ms}ms")

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
            for step in waterfall_errors:
                lines.append(f"• {step.name}: {step.error[:100]}")

        # === TRACE URL ===
        if self.trace_url:
            lines.append("")
            lines.append("=== TRACE ===")
            lines.append(self.trace_url)

        return "\n".join(lines) if lines else ""

    def get_model_version(self) -> str:
        """Restituisce stringa model version per il report"""
        if self.model_provider and self.model:
            return f"{self.model_provider}/{self.model}"
        return self.model or ""


class LangSmithClient:
    """
    Client per LangSmith API.
    
    Features:
    - Recupero trace per analisi
    - Estrazione tool calls
    - Metriche performance
    - Link diretto al trace
    
    Usage:
        client = LangSmithClient(
            api_key="lsv2_sk_...",
            project_id="xxx",
            org_id="yyy"
        )
        
        trace = client.get_latest_trace()
        tools = client.extract_tool_calls(trace)
    """
    
    BASE_URL = "https://api.smith.langchain.com/api/v1"
    
    def __init__(self,
                 api_key: str,
                 project_id: str,
                 org_id: str = "",
                 tool_names: Optional[List[str]] = None):
        """
        Inizializza il client.
        
        Args:
            api_key: API key LangSmith
            project_id: ID progetto LangSmith
            org_id: ID organizzazione (opzionale)
            tool_names: Lista nomi tool da tracciare (auto-detect se None)
        """
        self.api_key = api_key
        self.project_id = project_id
        self.org_id = org_id
        self.tool_names = tool_names or []
        
        self._session = requests.Session()
        self._session.headers.update({
            'x-api-key': api_key,
            'Content-Type': 'application/json'
        })
    
    @property
    def project_url(self) -> str:
        """URL del progetto in LangSmith"""
        base = "https://smith.langchain.com"
        if self.org_id:
            return f"{base}/o/{self.org_id}/projects/p/{self.project_id}"
        return f"{base}/projects/p/{self.project_id}"
    
    def is_available(self) -> bool:
        """
        Verifica se LangSmith è raggiungibile.
        
        Returns:
            True se connessione OK
        """
        try:
            response = self._session.get(
                f"{self.BASE_URL}/sessions/{self.project_id}",
                timeout=10
            )
            return response.status_code == 200
        except:
            return False
    
    def get_traces(self,
                   limit: int = 10,
                   start_time: Optional[datetime] = None,
                   end_time: Optional[datetime] = None) -> List[TraceInfo]:
        """Ottiene i trace recenti."""
        payload = {
            'session': [self.project_id],
            'limit': limit,
            'is_root': True
        }
        
        if start_time:
            payload['start_time'] = start_time.isoformat()
        if end_time:
            payload['end_time'] = end_time.isoformat()
        
        try:
            response = self._session.post(
                f"{self.BASE_URL}/runs/query",
                json=payload,
                timeout=30
            )
            
            if response.status_code != 200:
                print(f"! LangSmith API error: {response.status_code}")
                return []

            runs = response.json().get('runs', [])
            traces = []

            for run in runs:
                trace = self._parse_run(run)
                if trace:
                    traces.append(trace)

            return traces

        except Exception as e:
            print(f"! Errore recupero traces: {e}")
            return []
    
    def get_latest_trace(self, 
                         after: Optional[datetime] = None,
                         input_contains: Optional[str] = None) -> Optional[TraceInfo]:
        """
        Ottiene il trace più recente.
        
        Args:
            after: Solo trace dopo questa data
            input_contains: Filtra per contenuto input
            
        Returns:
            TraceInfo o None
        """
        start_time = after or (datetime.utcnow() - timedelta(hours=1))
        traces = self.get_traces(limit=20, start_time=start_time)
        
        for trace in traces:
            if input_contains:
                if input_contains.lower() in trace.input.lower():
                    return trace
            else:
                return trace
        
        return None
    
    def get_trace_by_id(self, trace_id: str) -> Optional[TraceInfo]:
        """
        Ottiene un trace specifico per ID.
        
        Args:
            trace_id: ID del trace
            
        Returns:
            TraceInfo o None
        """
        try:
            response = self._session.get(
                f"{self.BASE_URL}/runs/{trace_id}",
                timeout=30
            )
            
            if response.status_code == 200:
                return self._parse_run(response.json())
            
        except:
            pass
        
        return None
    
    def get_child_runs(self, parent_id: str) -> List[Dict]:
        """
        Ottiene tutti i run nel trace (tool calls, LLM, chain steps).
        
        Args:
            parent_id: ID del trace padre
            
        Returns:
            Lista di run nel trace
        """
        try:
            response = self._session.post(
                f"{self.BASE_URL}/runs/query",
                json={
                    'trace': parent_id,
                    'limit': 100
                },
                timeout=30
            )
            
            if response.status_code == 200:
                return response.json().get('runs', [])
            
        except:
            pass
        
        return []
    
    def extract_tool_calls(self, trace: TraceInfo) -> List[ToolCall]:
        """
        Estrae le chiamate ai tool da un trace.
        
        Args:
            trace: TraceInfo da analizzare
            
        Returns:
            Lista ToolCall
        """
        child_runs = self.get_child_runs(trace.id)
        
        tool_calls = []
        for run in child_runs:
            if run.get('run_type') == 'tool':
                tool = ToolCall(
                    name=run.get('name', 'unknown'),
                    input=run.get('inputs', {}),
                    output=run.get('outputs'),
                    duration_ms=self._calculate_duration(run),
                    error=run.get('error')
                )
                tool_calls.append(tool)
        
        return tool_calls
    
    def get_trace_url(self, trace_id: str) -> str:
        """
        Costruisce URL diretto al trace.
        
        Args:
            trace_id: ID del trace
            
        Returns:
            URL completo
        """
        base = "https://smith.langchain.com"
        if self.org_id:
            return f"{base}/o/{self.org_id}/projects/p/{self.project_id}/r/{trace_id}"
        return f"{base}/projects/p/{self.project_id}/r/{trace_id}"
    
    def auto_detect_tool_names(self, sample_size: int = 10) -> List[str]:
        """
        Auto-rileva i nomi dei tool usati nel progetto.
        
        Args:
            sample_size: Numero trace da analizzare
            
        Returns:
            Lista nomi tool unici
        """
        traces = self.get_traces(limit=sample_size)
        
        tool_names = set()
        for trace in traces:
            tools = self.extract_tool_calls(trace)
            for tool in tools:
                tool_names.add(tool.name)
        
        return sorted(list(tool_names))
    
    def analyze_trace(self, trace: TraceInfo) -> Dict[str, Any]:
        """
        Analisi completa di un trace.
        
        Args:
            trace: TraceInfo da analizzare
            
        Returns:
            Dict con analisi dettagliata
        """
        tool_calls = self.extract_tool_calls(trace)
        
        analysis = {
            'trace_id': trace.id,
            'trace_url': self.get_trace_url(trace.id),
            'duration_ms': trace.duration_ms,
            'status': trace.status,
            'model': trace.model,
            'tokens_used': trace.tokens_used,
            'tool_summary': {
                'total_calls': len(tool_calls),
                'tools_used': list(set(t.name for t in tool_calls)),
                'failed_calls': sum(1 for t in tool_calls if t.error)
            },
            'tool_details': [
                {
                    'name': t.name,
                    'duration_ms': t.duration_ms,
                    'has_error': bool(t.error),
                    'input_preview': str(t.input)[:200]
                }
                for t in tool_calls
            ],
            'input_preview': trace.input[:500] if trace.input else '',
            'output_preview': trace.output[:500] if trace.output else ''
        }
        
        return analysis
    
    def get_report_for_question(self,
                                 question: str,
                                 search_window_minutes: int = 30) -> LangSmithReport:
        """
        Ottiene report completo per una domanda, incluso modello.

        Args:
            question: Domanda inviata al chatbot
            search_window_minutes: Finestra temporale di ricerca

        Returns:
            LangSmithReport con tutti i dati estratti
        """
        start_time = datetime.utcnow() - timedelta(minutes=search_window_minutes)

        # Cerca il trace
        trace = self.get_latest_trace(
            after=start_time,
            input_contains=question[:50] if question else None
        )

        if not trace:
            return LangSmithReport(error=f"Trace non trovato per: {question[:50]}...")

        # Analizza il trace
        analysis = self.analyze_trace(trace)

        # Estrai info modello dai child runs
        model_info = self._extract_model_info(trace.id)

        # Estrai waterfall tree
        waterfall = self._extract_waterfall(trace.id, trace.start_time)

        # Estrai sources/documenti consultati
        sources = self._extract_sources(trace.id)

        return LangSmithReport(
            trace_url=analysis['trace_url'],
            duration_ms=analysis['duration_ms'],
            status=analysis['status'],
            model=model_info.get('model', '') or analysis.get('model', ''),
            model_provider=model_info.get('provider', ''),
            tokens_input=model_info.get('tokens_input', 0),
            tokens_output=model_info.get('tokens_output', 0),
            tokens_total=analysis['tokens_used'] or model_info.get('tokens_total', 0),
            tools_used=analysis['tool_summary']['tools_used'],
            tool_count=analysis['tool_summary']['total_calls'],
            failed_tools=analysis['tool_summary']['failed_calls'],
            first_token_ms=model_info.get('first_token_ms', 0),
            query=trace.input,
            response=trace.output,
            waterfall=waterfall,
            sources=sources
        )
    
    def _extract_model_info(self, trace_id: str) -> Dict[str, Any]:
        """
        Estrae informazioni sul modello dai child runs.
        
        Cerca run di tipo 'llm' o 'chat_model' per trovare:
        - Nome modello
        - Provider (OpenAI, Anthropic, etc.)
        - Token usage
        - Time to first token
        """
        child_runs = self.get_child_runs(trace_id)
        
        model_info = {
            'model': '',
            'provider': '',
            'tokens_input': 0,
            'tokens_output': 0,
            'tokens_total': 0,
            'first_token_ms': 0
        }
        
        for run in child_runs:
            run_type = run.get('run_type', '')
            
            # Cerca LLM runs
            if run_type in ['llm', 'chat_model']:
                # Estrai modello
                extra = run.get('extra', {})
                invocation = extra.get('invocation_params', {})
                metadata = extra.get('metadata', {})
                
                # Nome modello - cerca in vari posti
                model_name = (
                    invocation.get('model') or
                    invocation.get('model_name') or
                    metadata.get('model') or
                    metadata.get('ls_model_name') or
                    run.get('name', '')
                )
                
                if model_name and not model_info['model']:
                    model_info['model'] = model_name
                
                # Provider
                provider = (
                    metadata.get('ls_provider') or
                    invocation.get('_type', '').replace('_chat', '').replace('_llm', '') or
                    self._guess_provider(model_name)
                )
                
                if provider and not model_info['provider']:
                    model_info['provider'] = provider
                
                # Token usage
                outputs = run.get('outputs', {})
                usage = {}
                if isinstance(outputs, dict):
                    llm_output = outputs.get('llm_output', {})
                    if isinstance(llm_output, dict):
                        usage = llm_output.get('token_usage', {})
                
                if not usage and isinstance(outputs, dict):
                    usage = outputs.get('usage', {}) or run.get('metrics', {})
                
                if usage and isinstance(usage, dict):
                    model_info['tokens_input'] += usage.get('prompt_tokens', 0) or usage.get('input_tokens', 0)
                    model_info['tokens_output'] += usage.get('completion_tokens', 0) or usage.get('output_tokens', 0)
                    model_info['tokens_total'] += usage.get('total_tokens', 0)
                
                # First token time
                if run.get('first_token_time'):
                    start = run.get('start_time', '')
                    first_token = run.get('first_token_time', '')
                    if start and first_token:
                        try:
                            start_dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
                            first_dt = datetime.fromisoformat(first_token.replace('Z', '+00:00'))
                            model_info['first_token_ms'] = int((first_dt - start_dt).total_seconds() * 1000)
                        except:
                            pass
        
        # Se non trovato nei child, cerca nel run principale
        if not model_info['model']:
            try:
                response = self._session.get(
                    f"{self.BASE_URL}/runs/{trace_id}",
                    timeout=10
                )
                if response.status_code == 200:
                    run_data = response.json()
                    extra = run_data.get('extra', {})
                    metadata = extra.get('metadata', {})
                    
                    model_info['model'] = metadata.get('model', '') or metadata.get('ls_model_name', '')
                    model_info['provider'] = metadata.get('ls_provider', '')
            except:
                pass
        
        return model_info

    def _extract_waterfall(self, trace_id: str, trace_start: datetime) -> List[WaterfallStep]:
        """
        Estrae il waterfall tree (sequenza di step con timing).

        Args:
            trace_id: ID del trace
            trace_start: Timestamp di inizio del trace

        Returns:
            Lista di WaterfallStep ordinati per tempo
        """
        child_runs = self.get_child_runs(trace_id)

        if not child_runs:
            return []

        # Mappa parent_id -> depth per calcolare nesting
        id_to_depth = {trace_id: 0}
        steps = []

        # Prima passata: costruisci mappa depth
        for run in child_runs:
            run_id = run.get('id', '')
            parent_id = run.get('parent_run_id', '')

            if parent_id in id_to_depth:
                id_to_depth[run_id] = id_to_depth[parent_id] + 1
            else:
                id_to_depth[run_id] = 1

        # Seconda passata: estrai step
        for run in child_runs:
            run_id = run.get('id', '')
            run_type = run.get('run_type', 'unknown')
            name = run.get('name', 'unnamed')
            status = run.get('status', '')
            error = run.get('error')

            # Calcola offset dall'inizio
            start_offset_ms = 0
            duration_ms = 0
            try:
                run_start = run.get('start_time', '')
                if run_start:
                    run_start_dt = datetime.fromisoformat(run_start.replace('Z', '+00:00'))
                    # Rendi trace_start timezone-aware se necessario
                    if trace_start.tzinfo is None:
                        from datetime import timezone
                        trace_start_aware = trace_start.replace(tzinfo=timezone.utc)
                    else:
                        trace_start_aware = trace_start
                    start_offset_ms = int((run_start_dt - trace_start_aware).total_seconds() * 1000)

                run_end = run.get('end_time', '')
                if run_start and run_end:
                    run_start_dt = datetime.fromisoformat(run_start.replace('Z', '+00:00'))
                    run_end_dt = datetime.fromisoformat(run_end.replace('Z', '+00:00'))
                    duration_ms = int((run_end_dt - run_start_dt).total_seconds() * 1000)
            except:
                pass

            depth = id_to_depth.get(run_id, 1)

            steps.append(WaterfallStep(
                name=name,
                run_type=run_type,
                duration_ms=duration_ms,
                start_offset_ms=start_offset_ms,
                status=status,
                error=error,
                depth=depth
            ))

        # Ordina per start_offset_ms
        steps.sort(key=lambda s: s.start_offset_ms)

        return steps

    def _extract_sources(self, trace_id: str) -> List[SourceDocument]:
        """
        Estrae i documenti fonte consultati durante la ricerca.

        Cerca nei run di tipo 'retriever' o tool di ricerca per estrarre
        i documenti recuperati dal vector store o altri sistemi RAG.

        Args:
            trace_id: ID del trace

        Returns:
            Lista di SourceDocument
        """
        child_runs = self.get_child_runs(trace_id)
        sources = []
        seen_sources = set()  # Per evitare duplicati

        for run in child_runs:
            run_type = run.get('run_type', '')
            run_name = run.get('name', '').lower()

            # Cerca nei retriever runs
            if run_type == 'retriever' or 'retriev' in run_name or 'search' in run_name:
                outputs = run.get('outputs', {})

                # I documenti possono essere in vari formati
                docs = []

                # Formato LangChain standard: {'documents': [...]}
                if isinstance(outputs, dict):
                    docs = outputs.get('documents', [])
                    if not docs:
                        docs = outputs.get('output', [])
                    if not docs:
                        docs = outputs.get('results', [])

                # Se outputs è direttamente una lista
                if isinstance(outputs, list):
                    docs = outputs

                for doc in docs:
                    if isinstance(doc, dict):
                        # Estrai metadata
                        metadata = doc.get('metadata', {})
                        page_content = doc.get('page_content', '') or doc.get('content', '')

                        # Identifica source per evitare duplicati
                        source_id = metadata.get('source', '') or metadata.get('url', '') or page_content[:50]
                        if source_id in seen_sources:
                            continue
                        seen_sources.add(source_id)

                        source_doc = SourceDocument(
                            title=metadata.get('title', '') or metadata.get('name', ''),
                            source=metadata.get('source', '') or metadata.get('url', '') or metadata.get('file', ''),
                            content_preview=page_content[:300] if page_content else '',
                            score=float(metadata.get('score', 0) or doc.get('score', 0) or 0),
                            metadata=metadata
                        )
                        sources.append(source_doc)

                    elif isinstance(doc, str):
                        # Documento come stringa semplice
                        if doc[:50] not in seen_sources:
                            seen_sources.add(doc[:50])
                            sources.append(SourceDocument(
                                content_preview=doc[:300],
                                source="inline"
                            ))

            # Cerca anche nei tool che potrebbero restituire documenti
            if run_type == 'tool':
                tool_name = run.get('name', '').lower()
                if any(kw in tool_name for kw in ['search', 'retriev', 'lookup', 'query', 'get_doc', 'fetch']):
                    outputs = run.get('outputs', {})

                    if isinstance(outputs, dict):
                        # Tool output come dict
                        content = outputs.get('output', '') or outputs.get('result', '') or str(outputs)
                        if content and len(content) > 20:
                            source_key = f"{tool_name}:{content[:50]}"
                            if source_key not in seen_sources:
                                seen_sources.add(source_key)
                                sources.append(SourceDocument(
                                    title=f"Tool: {run.get('name', 'unknown')}",
                                    source=tool_name,
                                    content_preview=str(content)[:300]
                                ))

                    elif isinstance(outputs, str) and len(outputs) > 20:
                        source_key = f"{tool_name}:{outputs[:50]}"
                        if source_key not in seen_sources:
                            seen_sources.add(source_key)
                            sources.append(SourceDocument(
                                title=f"Tool: {run.get('name', 'unknown')}",
                                source=tool_name,
                                content_preview=outputs[:300]
                            ))

        return sources

    def _guess_provider(self, model_name: str) -> str:
        """Indovina il provider dal nome del modello"""
        if not model_name:
            return ""
        
        model_lower = model_name.lower()
        
        if 'gpt' in model_lower or 'o1' in model_lower or 'davinci' in model_lower:
            return 'openai'
        elif 'claude' in model_lower:
            return 'anthropic'
        elif 'gemini' in model_lower or 'palm' in model_lower:
            return 'google'
        elif 'mistral' in model_lower or 'mixtral' in model_lower:
            return 'mistral'
        elif 'llama' in model_lower:
            return 'meta'
        elif 'command' in model_lower:
            return 'cohere'
        
        return ""
    
    def _parse_run(self, run: Dict) -> Optional[TraceInfo]:
        """Converte un run API in TraceInfo"""
        try:
            start = datetime.fromisoformat(run.get('start_time', '').replace('Z', '+00:00'))
            end = None
            if run.get('end_time'):
                end = datetime.fromisoformat(run['end_time'].replace('Z', '+00:00'))
            
            # Estrai input/output
            inputs = run.get('inputs', {})
            outputs = run.get('outputs', {})
            
            input_str = ""
            if isinstance(inputs, dict):
                input_str = inputs.get('input', inputs.get('question', str(inputs)))
            
            output_str = ""
            if isinstance(outputs, dict):
                output_str = outputs.get('output', outputs.get('answer', str(outputs)))
            
            return TraceInfo(
                id=run.get('id', ''),
                name=run.get('name', ''),
                start_time=start,
                end_time=end,
                duration_ms=self._calculate_duration(run),
                status=run.get('status', ''),
                input=str(input_str),
                output=str(output_str),
                tokens_used=run.get('total_tokens', 0),
                model=run.get('extra', {}).get('metadata', {}).get('model', ''),
                url=self.get_trace_url(run.get('id', '')),
                metadata=run.get('extra', {}).get('metadata', {})
            )
        except Exception as e:
            print(f"! Errore parsing run: {e}")
            return None
    
    def _calculate_duration(self, run: Dict) -> int:
        """Calcola durata in millisecondi"""
        try:
            start = run.get('start_time', '')
            end = run.get('end_time', '')
            
            if not start or not end:
                return 0
            
            start_dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
            end_dt = datetime.fromisoformat(end.replace('Z', '+00:00'))
            
            return int((end_dt - start_dt).total_seconds() * 1000)
        except:
            return 0


class LangSmithDebugger:
    """
    Helper per debugging avanzato con LangSmith.
    
    Fornisce report dettagliati per analisi problemi.
    """
    
    def __init__(self, client: LangSmithClient):
        self.client = client
    
    def debug_conversation(self, 
                           question: str,
                           search_window_minutes: int = 5) -> Dict[str, Any]:
        """
        Debug completo di una conversazione.
        
        Args:
            question: Domanda inviata al chatbot
            search_window_minutes: Finestra temporale ricerca
            
        Returns:
            Report debug dettagliato
        """
        start_time = datetime.utcnow() - timedelta(minutes=search_window_minutes)
        
        trace = self.client.get_latest_trace(
            after=start_time,
            input_contains=question[:50]
        )
        
        if not trace:
            return {
                'found': False,
                'message': f'Trace non trovato per: {question[:50]}...'
            }
        
        analysis = self.client.analyze_trace(trace)
        
        return {
            'found': True,
            'trace_url': analysis['trace_url'],
            'duration_ms': analysis['duration_ms'],
            'status': analysis['status'],
            'tools_used': analysis['tool_summary']['tools_used'],
            'tool_count': analysis['tool_summary']['total_calls'],
            'failed_tools': analysis['tool_summary']['failed_calls'],
            'model': analysis['model'],
            'tokens': analysis['tokens_used'],
            'details': analysis
        }
    
    def get_performance_summary(self, 
                                 hours: int = 24,
                                 limit: int = 100) -> Dict[str, Any]:
        """
        Riassunto performance delle ultime ore.
        
        Args:
            hours: Ore da analizzare
            limit: Numero massimo trace
            
        Returns:
            Statistiche performance
        """
        start_time = datetime.utcnow() - timedelta(hours=hours)
        traces = self.client.get_traces(limit=limit, start_time=start_time)
        
        if not traces:
            return {'error': 'Nessun trace trovato'}
        
        durations = [t.duration_ms for t in traces if t.duration_ms > 0]
        statuses = [t.status for t in traces]
        
        return {
            'total_traces': len(traces),
            'time_period_hours': hours,
            'avg_duration_ms': sum(durations) / len(durations) if durations else 0,
            'min_duration_ms': min(durations) if durations else 0,
            'max_duration_ms': max(durations) if durations else 0,
            'success_rate': statuses.count('success') / len(statuses) if statuses else 0,
            'status_breakdown': {s: statuses.count(s) for s in set(statuses)}
        }
    
    def find_slow_traces(self, 
                          threshold_ms: int = 5000,
                          limit: int = 20) -> List[Dict]:
        """
        Trova trace lenti.
        
        Args:
            threshold_ms: Soglia in millisecondi
            limit: Numero massimo risultati
            
        Returns:
            Lista trace lenti con analisi
        """
        traces = self.client.get_traces(limit=100)
        
        slow = [t for t in traces if t.duration_ms > threshold_ms]
        slow.sort(key=lambda x: x.duration_ms, reverse=True)
        
        results = []
        for trace in slow[:limit]:
            analysis = self.client.analyze_trace(trace)
            results.append({
                'trace_url': analysis['trace_url'],
                'duration_ms': trace.duration_ms,
                'input_preview': trace.input[:100],
                'tools_used': analysis['tool_summary']['tools_used']
            })
        
        return results
    
    def find_failed_traces(self, limit: int = 20) -> List[Dict]:
        """
        Trova trace falliti.
        
        Args:
            limit: Numero massimo risultati
            
        Returns:
            Lista trace falliti con errori
        """
        traces = self.client.get_traces(limit=100)
        
        failed = [t for t in traces if t.status != 'success']
        
        results = []
        for trace in failed[:limit]:
            tool_calls = self.client.extract_tool_calls(trace)
            failed_tools = [t for t in tool_calls if t.error]
            
            results.append({
                'trace_url': trace.url,
                'status': trace.status,
                'input_preview': trace.input[:100],
                'failed_tools': [{'name': t.name, 'error': t.error} for t in failed_tools]
            })
        
        return results


class LangSmithSetup:
    """Helper per setup LangSmith"""
    
    @staticmethod
    def get_setup_instructions() -> str:
        """Istruzioni per setup LangSmith"""
        return """
SETUP LANGSMITH

1. Vai su smith.langchain.com e accedi

2. Crea un nuovo progetto o seleziona esistente

3. Copia i seguenti valori:
   - Project ID: dalla URL del progetto
   - Org ID: Settings > Organization (se presente)

4. Genera API Key:
   Settings > API Keys > Create API Key

5. Inserisci i valori nel wizard o in .env:
   LANGSMITH_API_KEY=lsv2_sk_xxxxx
"""
    
    @staticmethod
    def validate_api_key(api_key: str) -> tuple[bool, str]:
        """
        Valida una API key LangSmith.
        
        Returns:
            (is_valid, message)
        """
        if not api_key:
            return False, "API key vuota"
        
        if not api_key.startswith('lsv2_'):
            return False, "Formato API key non valido (deve iniziare con lsv2_)"
        
        # Test connessione
        try:
            response = requests.get(
                "https://api.smith.langchain.com/api/v1/info",
                headers={'x-api-key': api_key},
                timeout=10
            )
            
            if response.status_code == 200:
                return True, "API key valida"
            elif response.status_code == 401:
                return False, "API key non autorizzata"
            else:
                return False, f"Errore verifica: {response.status_code}"
        except Exception as e:
            return False, f"Errore connessione: {e}"
    
    @staticmethod
    def extract_project_id(url: str) -> Optional[str]:
        """
        Estrae project ID da URL LangSmith.
        
        Args:
            url: URL del progetto
            
        Returns:
            Project ID o None
        """
        # Format: https://smith.langchain.com/o/ORG/projects/p/PROJECT_ID
        # o: https://smith.langchain.com/projects/p/PROJECT_ID
        
        if '/projects/p/' in url:
            parts = url.split('/projects/p/')
            if len(parts) > 1:
                project_id = parts[1].split('/')[0].split('?')[0]
                return project_id
        
        return None
    
    @staticmethod
    def extract_org_id(url: str) -> Optional[str]:
        """
        Estrae org ID da URL LangSmith.
        
        Args:
            url: URL del progetto
            
        Returns:
            Org ID o None
        """
        if '/o/' in url:
            parts = url.split('/o/')
            if len(parts) > 1:
                org_id = parts[1].split('/')[0]
                return org_id
        
        return None
