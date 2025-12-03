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
        """
        Ottiene i trace recenti.
        
        Args:
            limit: Numero massimo trace
            start_time: Filtro data inizio
            end_time: Filtro data fine
            
        Returns:
            Lista TraceInfo
        """
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
        Ottiene i run figli (tool calls, chain steps).
        
        Args:
            parent_id: ID del run padre
            
        Returns:
            Lista di run figli
        """
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
📋 SETUP LANGSMITH

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
