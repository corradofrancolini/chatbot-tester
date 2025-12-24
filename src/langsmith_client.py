"""
LangSmith Client - Integration for chatbot debugging and analysis

Handles:
- Conversation trace retrieval
- Tool routing analysis
- Performance metrics extraction
- Context envelope inspection
"""

import requests
import time
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from .clients.base import BaseClient
from .models.langsmith import (
    TraceInfo, ToolCall, WaterfallStep, SourceDocument, LangSmithReport
)





class LangSmithClient(BaseClient):
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

        # Retry config
        self._max_retries = 3
        self._base_delay = 1.0  # secondi
        self._max_delay = 30.0  # secondi

    def _request_with_retry(self, method: str, url: str, **kwargs) -> Optional[requests.Response]:
        """
        Esegue richiesta HTTP con retry e exponential backoff per 429.

        Args:
            method: 'get' o 'post'
            url: URL da chiamare
            **kwargs: argomenti per requests (json, timeout, etc.)

        Returns:
            Response o None se tutti i retry falliscono
        """
        delay = self._base_delay

        for attempt in range(self._max_retries + 1):
            try:
                if method == 'get':
                    response = self._session.get(url, **kwargs)
                else:
                    response = self._session.post(url, **kwargs)

                # Successo
                if response.status_code == 200:
                    return response

                # Rate limit - retry con backoff
                if response.status_code == 429:
                    if attempt < self._max_retries:
                        # Cerca Retry-After header
                        retry_after = response.headers.get('Retry-After')
                        if retry_after:
                            delay = min(float(retry_after), self._max_delay)

                        print(f"  ⏳ LangSmith rate limit, retry in {delay:.1f}s...")
                        time.sleep(delay)
                        delay = min(delay * 2, self._max_delay)  # Exponential backoff
                        continue
                    else:
                        print(f"! LangSmith rate limit, max retries reached")
                        return None

                # Altri errori - non ritentare
                print(f"! LangSmith API error: {response.status_code}")
                return response

            except requests.exceptions.Timeout:
                if attempt < self._max_retries:
                    print(f"  ⏳ LangSmith timeout, retry in {delay:.1f}s...")
                    time.sleep(delay)
                    delay = min(delay * 2, self._max_delay)
                    continue
                print(f"! LangSmith timeout, max retries reached")
                return None

            except Exception as e:
                print(f"! LangSmith request error: {e}")
                return None

        return None

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

        response = self._request_with_retry(
            'post',
            f"{self.BASE_URL}/runs/query",
            json=payload,
            timeout=30
        )

        if not response or response.status_code != 200:
            return []

        runs = response.json().get('runs', [])
        traces = []

        for run in runs:
            trace = self._parse_run(run)
            if trace:
                traces.append(trace)

        return traces

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
        response = self._request_with_retry(
            'get',
            f"{self.BASE_URL}/runs/{trace_id}",
            timeout=30
        )

        if response and response.status_code == 200:
            return self._parse_run(response.json())

        return None

    def get_child_runs(self, parent_id: str) -> List[Dict]:
        """
        Ottiene tutti i run nel trace (tool calls, LLM, chain steps).

        Args:
            parent_id: ID del trace padre

        Returns:
            Lista di run nel trace
        """
        response = self._request_with_retry(
            'post',
            f"{self.BASE_URL}/runs/query",
            json={
                'trace': parent_id,
                'limit': 100
            },
            timeout=30
        )

        if response and response.status_code == 200:
            return response.json().get('runs', [])

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

        # Estrai vector store provider
        vector_store = self._extract_vector_store(trace.id)

        # Calcola metriche di timing dal waterfall
        timing_metrics = self._calculate_timing_metrics(waterfall)

        # Calcola token/s
        tokens_output = model_info.get('tokens_output', 0)
        llm_duration = timing_metrics.get('llm_duration_ms', 0)
        tokens_per_second = 0.0
        if tokens_output > 0 and llm_duration > 0:
            tokens_per_second = tokens_output / (llm_duration / 1000)

        return LangSmithReport(
            trace_url=analysis['trace_url'],
            duration_ms=analysis['duration_ms'],
            status=analysis['status'],
            model=model_info.get('model', '') or analysis.get('model', ''),
            model_provider=model_info.get('provider', ''),
            vector_store=vector_store,
            tokens_input=model_info.get('tokens_input', 0),
            tokens_output=tokens_output,
            tokens_total=analysis['tokens_used'] or model_info.get('tokens_total', 0),
            tools_used=analysis['tool_summary']['tools_used'],
            tool_count=analysis['tool_summary']['total_calls'],
            failed_tools=analysis['tool_summary']['failed_calls'],
            first_token_ms=model_info.get('first_token_ms', 0),
            query=trace.input,
            response=trace.output,
            waterfall=waterfall,
            sources=sources,
            # Nuove metriche timing
            llm_duration_ms=timing_metrics.get('llm_duration_ms', 0),
            llm_calls=timing_metrics.get('llm_calls', 0),
            tool_duration_ms=timing_metrics.get('tool_duration_ms', 0),
            retriever_duration_ms=timing_metrics.get('retriever_duration_ms', 0),
            chain_duration_ms=timing_metrics.get('chain_duration_ms', 0),
            tokens_per_second=tokens_per_second
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
            response = self._request_with_retry(
                'get',
                f"{self.BASE_URL}/runs/{trace_id}",
                timeout=10
            )
            if response and response.status_code == 200:
                run_data = response.json()
                extra = run_data.get('extra', {})
                metadata = extra.get('metadata', {})

                model_info['model'] = metadata.get('model', '') or metadata.get('ls_model_name', '')
                model_info['provider'] = metadata.get('ls_provider', '')

        return model_info

    def _calculate_timing_metrics(self, waterfall: List[WaterfallStep]) -> Dict[str, Any]:
        """
        Calcola metriche di timing aggregate dal waterfall.

        Args:
            waterfall: Lista di WaterfallStep

        Returns:
            Dict con metriche aggregate per tipo di run
        """
        metrics = {
            'llm_duration_ms': 0,
            'llm_calls': 0,
            'tool_duration_ms': 0,
            'retriever_duration_ms': 0,
            'chain_duration_ms': 0,
            'other_duration_ms': 0
        }

        for step in waterfall:
            run_type = step.run_type.lower()
            duration = step.duration_ms

            if run_type in ['llm', 'chat_model', 'chatmodel']:
                metrics['llm_duration_ms'] += duration
                metrics['llm_calls'] += 1
            elif run_type == 'tool':
                metrics['tool_duration_ms'] += duration
            elif run_type in ['retriever', 'vectorstore']:
                metrics['retriever_duration_ms'] += duration
            elif run_type in ['chain', 'agent']:
                metrics['chain_duration_ms'] += duration
            else:
                metrics['other_duration_ms'] += duration

        return metrics

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
                run_end = run.get('end_time', '')

                if run_start and run_end:
                    # Parse timestamps - gestisci sia formato con Z che senza
                    run_start_str = run_start.replace('Z', '+00:00')
                    run_end_str = run_end.replace('Z', '+00:00')

                    # Se non ha timezone info, parsalo come naive datetime
                    try:
                        run_start_dt = datetime.fromisoformat(run_start_str)
                    except:
                        # Prova senza timezone
                        run_start_dt = datetime.fromisoformat(run_start.split('+')[0].replace('Z', ''))

                    try:
                        run_end_dt = datetime.fromisoformat(run_end_str)
                    except:
                        run_end_dt = datetime.fromisoformat(run_end.split('+')[0].replace('Z', ''))

                    # Calcola durata (naive datetime comparison)
                    if run_start_dt.tzinfo:
                        run_start_dt = run_start_dt.replace(tzinfo=None)
                    if run_end_dt.tzinfo:
                        run_end_dt = run_end_dt.replace(tzinfo=None)

                    duration_ms = int((run_end_dt - run_start_dt).total_seconds() * 1000)

                    # Calcola offset dall'inizio del trace
                    trace_start_naive = trace_start.replace(tzinfo=None) if trace_start.tzinfo else trace_start
                    start_offset_ms = int((run_start_dt - trace_start_naive).total_seconds() * 1000)
            except Exception as e:
                # Debug: print(f"Error parsing timestamps: {e}")
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
                            full_content=page_content,  # Contenuto completo per RAG evaluation
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
                                full_content=doc,  # Contenuto completo
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

    def _extract_vector_store(self, trace_id: str) -> str:
        """
        Estrae il vector store provider dai retriever runs.

        Cerca nei run di tipo 'retriever' il campo metadata ls_vector_store_provider.

        Args:
            trace_id: ID del trace

        Returns:
            Nome del vector store (es. "Qdrant", "FAISS") o stringa vuota
        """
        child_runs = self.get_child_runs(trace_id)

        for run in child_runs:
            run_type = run.get('run_type', '')
            run_name = run.get('name', '').lower()

            # Cerca nei retriever runs
            if run_type == 'retriever' or 'retriev' in run_name or 'vectorstore' in run_name:
                extra = run.get('extra', {})
                metadata = extra.get('metadata', {})

                # Cerca ls_vector_store_provider
                vector_store = metadata.get('ls_vector_store_provider', '')
                if vector_store:
                    # Pulisci il nome (es. "QdrantVectorStore" -> "Qdrant")
                    vector_store = vector_store.replace('VectorStore', '').replace('vectorstore', '')
                    return vector_store

                # Fallback: cerca ls_retriever_name
                retriever_name = metadata.get('ls_retriever_name', '')
                if retriever_name and 'qdrant' in retriever_name.lower():
                    return 'Qdrant'
                elif retriever_name and 'faiss' in retriever_name.lower():
                    return 'FAISS'
                elif retriever_name and 'chroma' in retriever_name.lower():
                    return 'Chroma'
                elif retriever_name and 'pinecone' in retriever_name.lower():
                    return 'Pinecone'

        return ""

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


# Import from clients subpackage
from .clients.langsmith_setup import LangSmithSetup
