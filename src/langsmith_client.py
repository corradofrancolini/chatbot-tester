"""
LangSmith Client - Integrazione per debug e analisi chatbot

Gestisce:
- Recupero trace delle conversazioni
- Analisi tool routing
- Estrazione metriche performance
- Context envelope inspection
- Estrazione automatica modello/provider
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
    
    def format_for_sheets(self) -> str:
        """Formatta il report per inserimento in Google Sheets (colonna NOTES)"""
        parts = []
        
        if self.model:
            parts.append(f"Model: {self.model}")
        
        if self.duration_ms:
            parts.append(f"Duration: {self.duration_ms}ms")
        
        if self.first_token_ms:
            parts.append(f"First token: {self.first_token_ms}ms")
        
        if self.tokens_total:
            parts.append(f"Tokens: {self.tokens_input}in/{self.tokens_output}out ({self.tokens_total} total)")
        
        if self.tools_used:
            parts.append(f"Tools: {', '.join(self.tools_used)}")
        
        if self.failed_tools:
            parts.append(f"Failed: {self.failed_tools}")
        
        if self.status and self.status != "success":
            parts.append(f"Status: {self.status}")
        
        if self.error:
            parts.append(f"Error: {self.error[:100]}")
        
        return " | ".join(parts) if parts else ""
    
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
    - Estrazione automatica modello/provider
    """
    
    BASE_URL = "https://api.smith.langchain.com/api/v1"
    
    def __init__(self,
                 api_key: str,
                 project_id: str,
                 org_id: str = "",
                 tool_names: Optional[List[str]] = None):
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
        """Verifica se LangSmith è raggiungibile."""
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
        params = {
            'limit': limit,
            'session': self.project_id
        }
        
        if start_time:
            params['start_time'] = start_time.isoformat()
        if end_time:
            params['end_time'] = end_time.isoformat()
        
        try:
            response = self._session.get(
                f"{self.BASE_URL}/runs",
                params=params,
                timeout=30
            )
            
            if response.status_code != 200:
                return []
            
            runs = response.json().get('runs', [])
            traces = []
            
            for run in runs:
                trace = self._parse_run(run)
                if trace:
                    traces.append(trace)
            
            return traces
            
        except Exception as e:
            print(f"⚠️ Errore recupero traces: {e}")
            return []
    
    def get_latest_trace(self, 
                         after: Optional[datetime] = None,
                         input_contains: Optional[str] = None) -> Optional[TraceInfo]:
        """Ottiene il trace più recente."""
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
        """Ottiene un trace specifico per ID."""
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
        """Ottiene i run figli (tool calls, chain steps)."""
        try:
            response = self._session.get(
                f"{self.BASE_URL}/runs",
                params={
                    'parent_run': parent_id,
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
        """Estrae le chiamate ai tool da un trace."""
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
        """Costruisce URL diretto al trace."""
        base = "https://smith.langchain.com"
        if self.org_id:
            return f"{base}/o/{self.org_id}/projects/p/{self.project_id}/r/{trace_id}"
        return f"{base}/projects/p/{self.project_id}/r/{trace_id}"
    
    def auto_detect_tool_names(self, sample_size: int = 10) -> List[str]:
        """Auto-rileva i nomi dei tool usati nel progetto."""
        traces = self.get_traces(limit=sample_size)
        
        tool_names = set()
        for trace in traces:
            tools = self.extract_tool_calls(trace)
            for tool in tools:
                tool_names.add(tool.name)
        
        return sorted(list(tool_names))
    
    def analyze_trace(self, trace: TraceInfo) -> Dict[str, Any]:
        """Analisi completa di un trace."""
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
                                 search_window_minutes: int = 5) -> LangSmithReport:
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
            first_token_ms=model_info.get('first_token_ms', 0)
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
                usage = outputs.get('llm_output', {}).get('token_usage', {})
                
                if not usage:
                    # Prova formato alternativo
                    usage = outputs.get('usage', {}) or run.get('metrics', {})
                
                if usage:
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
            print(f"⚠️ Errore parsing run: {e}")
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
    """Helper per debugging avanzato con LangSmith."""
    
    def __init__(self, client: LangSmithClient):
        self.client = client
    
    def debug_conversation(self, 
                           question: str,
                           search_window_minutes: int = 5) -> Dict[str, Any]:
        """Debug completo di una conversazione."""
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
        """Riassunto performance delle ultime ore."""
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


class LangSmithSetup:
    """Helper per setup LangSmith"""
    
    @staticmethod
    def get_setup_instructions() -> str:
        return """
📋 SETUP LANGSMITH

1. Vai su smith.langchain.com e accedi
2. Crea un nuovo progetto o seleziona esistente
3. Copia Project ID dalla URL del progetto
4. Genera API Key: Settings > API Keys > Create API Key
5. Inserisci i valori nel wizard o in .env
"""
    
    @staticmethod
    def validate_api_key(api_key: str) -> tuple:
        if not api_key:
            return False, "API key vuota"
        
        if not api_key.startswith('lsv2_'):
            return False, "Formato API key non valido"
        
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
        if '/projects/p/' in url:
            parts = url.split('/projects/p/')
            if len(parts) > 1:
                return parts[1].split('/')[0].split('?')[0]
        return None
    
    @staticmethod
    def extract_org_id(url: str) -> Optional[str]:
        if '/o/' in url:
            parts = url.split('/o/')
            if len(parts) > 1:
                return parts[1].split('/')[0]
        return None
