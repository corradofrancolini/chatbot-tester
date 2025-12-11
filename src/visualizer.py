"""
Visualizer - Visualizzazione grafica di prompt e test

Funzionalita:
- PromptVisualizer: flowchart regole + mindmap capabilities
- TestVisualizer: waterfall trace + confronto + timeline
- Output: HTML interattivo + Terminale ASCII

Usage:
    # Visualizza prompt
    visualizer = PromptVisualizer(project_name)
    visualizer.render_html()  # Apre browser
    visualizer.render_terminal()  # Output console

    # Visualizza test
    test_viz = TestVisualizer(project_name, run_number, test_id)
    test_viz.render_html()
    test_viz.render_terminal()
"""

import re
import csv
import json
import webbrowser
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple, Union
from datetime import datetime


# ═══════════════════════════════════════════════════════════════════════════════
# Data Classes
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class PromptRule:
    """Una regola estratta dal prompt."""
    type: str  # 'condition', 'always', 'never', 'preference'
    text: str
    category: Optional[str] = None


@dataclass
class PromptCapability:
    """Una capability del prompt."""
    name: str
    description: str
    can_do: bool = True  # True = can do, False = cannot do


@dataclass
class PromptStructure:
    """Struttura parsata del prompt."""
    raw_content: str
    rules: List[PromptRule] = field(default_factory=list)
    capabilities: List[PromptCapability] = field(default_factory=list)
    sections: Dict[str, str] = field(default_factory=dict)
    tone: Optional[str] = None
    language: Optional[str] = None


@dataclass
class TestTrace:
    """Trace di un singolo test."""
    test_id: str
    question: str
    response: str
    query_data: Optional[Dict] = None
    tools_used: List[str] = field(default_factory=list)
    sources: List[Dict[str, str]] = field(default_factory=list)
    model: Optional[str] = None
    duration_ms: int = 0
    first_token_ms: int = 0
    esito: str = "UNKNOWN"
    notes: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════════════════
# Prompt Parser
# ═══════════════════════════════════════════════════════════════════════════════

class PromptParser:
    """Estrae struttura semantica dal testo del prompt."""

    # Pattern per identificare regole - Italiano
    RULE_PATTERNS_IT = {
        'condition': [
            r'(?<![a-zA-Z])[Ss]e\s+(?:l[\'aeo]\s+)?(.+?),?\s+(?:allora\s+)?(.+?)(?:\.|$)',
            r'[Qq]uando\s+(.+?),?\s+(.+?)(?:\.|$)',
            r'[Nn]el caso\s+(.+?),?\s+(.+?)(?:\.|$)',
        ],
        'always': [
            r'[Ss]empre\s+(.+?)(?:\.|$)',
            r'[Dd]evi sempre\s+(.+?)(?:\.|$)',
            r'[Aa]ssicurati di\s+(.+?)(?:\.|$)',
        ],
        'never': [
            r'[Mm]ai\s+(.+?)(?:\.|$)',
            r'[Nn]on\s+(?:devi\s+)?(.+?)(?:\.|$)',
            r'[Ee]vita(?:re)?\s+(.+?)(?:\.|$)',
        ],
        'preference': [
            r'[Pp]referibilmente\s+(.+?)(?:\.|$)',
            r'[Cc]erca di\s+(.+?)(?:\.|$)',
            r'[Ss]arebbe meglio\s+(.+?)(?:\.|$)',
        ]
    }

    # Pattern per identificare regole - English
    RULE_PATTERNS_EN = {
        'condition': [
            r'IF\s+(.+?)\s*[→\-]+\s*(.+?)(?:\n|$)',  # IF ... → ...
            r'[Ii]f\s+(.+?),?\s+(?:then\s+)?(.+?)(?:\.|$)',  # If ... then ...
            r'[Ww]hen\s+(.+?),?\s+(.+?)(?:\.|$)',  # When ...
        ],
        'always': [
            r'ALWAYS\s+(.+?)(?:\.|$)',
            r'[Aa]lways\s+(.+?)(?:\.|$)',
            r'MUST\s+(.+?)(?:\.|$)',
            r'[Mm]ust\s+(.+?)(?:\.|$)',
            r'[Ss]hould\s+(.+?)(?:\.|$)',
            r'[Ee]nsure\s+(?:that\s+)?(.+?)(?:\.|$)',
        ],
        'never': [
            r'NEVER\s+(.+?)(?:\.|$)',
            r'[Nn]ever\s+(.+?)(?:\.|$)',
            r'MUST NOT\s+(.+?)(?:\.|$)',
            r'[Dd]o NOT\s+(.+?)(?:\.|$)',
            r'[Dd]o not\s+(.+?)(?:\.|$)',
            r'[Aa]void\s+(.+?)(?:\.|$)',
            r'[Ss]hould not\s+(.+?)(?:\.|$)',
        ],
        'preference': [
            r'[Pp]referably\s+(.+?)(?:\.|$)',
            r'[Tt]ry to\s+(.+?)(?:\.|$)',
            r'[Ii]t is better to\s+(.+?)(?:\.|$)',
            r'[Ii]deally\s+(.+?)(?:\.|$)',
        ],
        'critical': [
            r'CRITICAL(?:\s+RULE)?:\s*(.+?)(?:\n|$)',
            r'[Cc]ritical(?:\s+rule)?:\s*(.+?)(?:\n|$)',
            r'IMPORTANT:\s*(.+?)(?:\n|$)',
            r'[Ii]mportant:\s*(.+?)(?:\n|$)',
            r'WARNING:\s*(.+?)(?:\n|$)',
        ]
    }

    # Pattern per capabilities - Italiano
    CAPABILITY_PATTERNS_IT = {
        'can_do': [
            r'[Pp]uoi\s+(.+?)(?:\.|$)',
            r'[Ss]ei in grado di\s+(.+?)(?:\.|$)',
            r'[Hh]ai accesso a\s+(.+?)(?:\.|$)',
        ],
        'cannot_do': [
            r'[Nn]on puoi\s+(.+?)(?:\.|$)',
            r'[Nn]on hai accesso a\s+(.+?)(?:\.|$)',
            r'[Nn]on sei in grado di\s+(.+?)(?:\.|$)',
        ]
    }

    # Pattern per capabilities - English
    CAPABILITY_PATTERNS_EN = {
        'can_do': [
            r'[Yy]ou can\s+(.+?)(?:\.|$)',
            r'[Yy]ou are able to\s+(.+?)(?:\.|$)',
            r'[Yy]ou have access to\s+(.+?)(?:\.|$)',
            r'[Cc]an\s+(.+?)(?:\.|$)',
        ],
        'cannot_do': [
            r'[Yy]ou cannot\s+(.+?)(?:\.|$)',
            r'[Yy]ou can\'t\s+(.+?)(?:\.|$)',
            r'[Yy]ou are not able to\s+(.+?)(?:\.|$)',
            r'[Cc]annot\s+(.+?)(?:\.|$)',
        ]
    }

    def parse(self, content: str) -> PromptStructure:
        """Parsa il contenuto del prompt."""
        structure = PromptStructure(raw_content=content)

        # Prima identifica la lingua per usare i pattern corretti
        structure.language = self._detect_language(content)

        # Estrai sezioni markdown (## HEADING) - priorita alta per prompt strutturati
        structure.sections = self._extract_sections(content)

        # Estrai workflow steps (### Step N:)
        workflow_steps = self._extract_workflow_steps(content)
        if workflow_steps:
            structure.sections['_workflow_steps'] = workflow_steps

        # Estrai regole usando pattern della lingua corretta
        structure.rules = self._extract_rules(content, structure.language)

        # Estrai capabilities
        structure.capabilities = self._extract_capabilities(content, structure.language)

        # Identifica tone
        structure.tone = self._detect_tone(content)

        return structure

    def _extract_rules(self, content: str, language: str = 'en') -> List[PromptRule]:
        """Estrae regole dal prompt usando pattern specifici per lingua."""
        rules = []
        seen_texts = set()  # Per evitare duplicati

        # Seleziona pattern in base alla lingua
        if language == 'it':
            patterns_dict = self.RULE_PATTERNS_IT
        else:
            patterns_dict = self.RULE_PATTERNS_EN

        # Prima estrai regole da blocchi CRITICAL/IMPORTANT
        critical_patterns = self.RULE_PATTERNS_EN.get('critical', [])
        for pattern in critical_patterns:
            for match in re.finditer(pattern, content, re.MULTILINE):
                text = match.group(0).strip()
                if len(text) > 15 and text not in seen_texts:
                    seen_texts.add(text)
                    rules.append(PromptRule(
                        type='critical',
                        text=text
                    ))

        # Poi estrai regole standard
        for rule_type, patterns in patterns_dict.items():
            if rule_type == 'critical':
                continue  # Gia' gestito sopra
            for pattern in patterns:
                for match in re.finditer(pattern, content, re.MULTILINE):
                    text = match.group(0).strip()
                    # Ignora match troppo corti o che sono dentro code blocks
                    if len(text) > 15 and text not in seen_texts:
                        # Verifica che non sia in un code block
                        if not self._is_in_code_block(content, match.start()):
                            seen_texts.add(text)
                            rules.append(PromptRule(
                                type=rule_type,
                                text=text
                            ))

        # Estrai regole da liste numerate con keyword
        list_rules = self._extract_list_rules(content, language)
        for rule in list_rules:
            if rule.text not in seen_texts:
                seen_texts.add(rule.text)
                rules.append(rule)

        return rules

    def _is_in_code_block(self, content: str, position: int) -> bool:
        """Verifica se una posizione e' dentro un code block."""
        # Conta i ``` prima della posizione
        code_markers = content[:position].count('```')
        # Se dispari, siamo dentro un code block
        return code_markers % 2 == 1

    def _extract_list_rules(self, content: str, language: str) -> List[PromptRule]:
        """Estrae regole da liste numerate/puntate."""
        rules = []

        # Pattern per liste con keyword importanti
        if language == 'en':
            keywords = {
                'never': r'^\s*[\d\.\-\*]+\s*((?:NEVER|Never|Do NOT|Don\'t|Avoid).+?)$',
                'always': r'^\s*[\d\.\-\*]+\s*((?:ALWAYS|Always|MUST|Must|Ensure).+?)$',
                'critical': r'^\s*[\d\.\-\*]+\s*\*\*(.+?)\*\*',  # **bold** in lists
            }
        else:
            keywords = {
                'never': r'^\s*[\d\.\-\*]+\s*((?:Mai|Non|Evita).+?)$',
                'always': r'^\s*[\d\.\-\*]+\s*((?:Sempre|Devi|Assicurati).+?)$',
            }

        for rule_type, pattern in keywords.items():
            for match in re.finditer(pattern, content, re.MULTILINE):
                text = match.group(1).strip().strip('*')
                if len(text) > 10:
                    rules.append(PromptRule(type=rule_type, text=text))

        return rules

    def _extract_capabilities(self, content: str, language: str = 'en') -> List[PromptCapability]:
        """Estrae capabilities dal prompt."""
        capabilities = []
        seen = set()

        # Seleziona pattern in base alla lingua
        if language == 'it':
            patterns_dict = self.CAPABILITY_PATTERNS_IT
        else:
            patterns_dict = self.CAPABILITY_PATTERNS_EN

        for cap_type, patterns in patterns_dict.items():
            for pattern in patterns:
                for match in re.finditer(pattern, content, re.MULTILINE):
                    text = match.group(1).strip()
                    if len(text) > 5 and text not in seen:
                        seen.add(text)
                        capabilities.append(PromptCapability(
                            name=text[:50],
                            description=text,
                            can_do=(cap_type == 'can_do')
                        ))

        # Estrai anche da sezioni strutturate
        structured_caps = self._extract_structured_capabilities(content)
        for cap in structured_caps:
            if cap.description not in seen:
                seen.add(cap.description)
                capabilities.append(cap)

        return capabilities

    def _extract_structured_capabilities(self, content: str) -> List[PromptCapability]:
        """Estrae capabilities da sezioni strutturate del prompt."""
        capabilities = []

        # Cerca sezioni come "## INPUT SOURCES", "## OUTPUT FORMAT", etc.
        section_patterns = [
            (r'##\s*INPUT\s*SOURCES?\s*\n(.*?)(?=\n##|\Z)', True, 'Input'),
            (r'##\s*OUTPUT\s*FORMAT\s*\n(.*?)(?=\n##|\Z)', True, 'Output'),
            (r'##\s*WORKFLOW\s*\n(.*?)(?=\n##|\Z)', True, 'Workflow'),
            (r'##\s*GENERATION\s*\n(.*?)(?=\n##|\Z)', True, 'Generation'),
        ]

        for pattern, can_do, prefix in section_patterns:
            match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
            if match:
                section_content = match.group(1)
                # Estrai items dalla sezione
                items = re.findall(r'^\s*[\d\.\-\*]+\s*\*\*(.+?)\*\*', section_content, re.MULTILINE)
                for item in items[:5]:  # Max 5 per sezione
                    capabilities.append(PromptCapability(
                        name=f"{prefix}: {item[:40]}",
                        description=item,
                        can_do=can_do
                    ))

        return capabilities

    def _extract_workflow_steps(self, content: str) -> List[Dict[str, str]]:
        """Estrae step del workflow (### Step N: ...)."""
        steps = []

        # Pattern per step numerati
        pattern = r'###\s*Step\s*(\d+):\s*(.+?)(?=\n###|\n##|\Z)'
        for match in re.finditer(pattern, content, re.DOTALL):
            step_num = match.group(1)
            step_content = match.group(2).strip()
            # Estrai titolo (prima riga)
            title_match = re.match(r'^([^\n]+)', step_content)
            title = title_match.group(1) if title_match else f"Step {step_num}"
            steps.append({
                'number': step_num,
                'title': title,
                'content': step_content[:500]  # Limita contenuto
            })

        return steps

    def _extract_sections(self, content: str) -> Dict[str, str]:
        """Estrae sezioni markdown dal prompt."""
        sections = {}
        current_section = "intro"
        current_content = []

        for line in content.split('\n'):
            # Match ## HEADING (level 2) per sezioni principali
            if line.startswith('## '):
                # Salva sezione precedente
                if current_content:
                    sections[current_section] = '\n'.join(current_content).strip()
                # Nuova sezione
                current_section = line[3:].strip().lower()
                current_content = []
            elif line.startswith('# ') and not line.startswith('## '):
                # Titolo principale (level 1)
                if current_content:
                    sections[current_section] = '\n'.join(current_content).strip()
                current_section = line.lstrip('#').strip().lower()
                current_content = []
            else:
                current_content.append(line)

        # Salva ultima sezione
        if current_content:
            sections[current_section] = '\n'.join(current_content).strip()

        return sections

    def _detect_tone(self, content: str) -> Optional[str]:
        """Rileva il tone of voice dal prompt."""
        tone_keywords = {
            'formal': ['formal', 'formale', 'professional', 'professionale', 'cortese', 'polite'],
            'informal': ['informal', 'informale', 'friendly', 'amichevole', 'colloquiale', 'conversational'],
            'technical': ['technical', 'tecnico', 'precise', 'preciso', 'detailed', 'dettagliato', 'specific', 'specifico'],
            'empathetic': ['empathetic', 'empatico', 'supportive', 'supportivo', 'understanding', 'comprensivo'],
            'structured': ['workflow', 'step', 'phase', 'paragraph', 'xml', 'json', 'output format'],
        }

        content_lower = content.lower()
        for tone, keywords in tone_keywords.items():
            if any(kw in content_lower for kw in keywords):
                return tone

        return None

    def _detect_language(self, content: str) -> str:
        """Rileva la lingua del prompt."""
        italian_words = ['sei', 'devi', 'puoi', 'quando', 'sempre', 'mai', 'utente']
        english_words = ['you', 'must', 'should', 'when', 'always', 'never', 'user']

        content_lower = content.lower()
        italian_count = sum(1 for w in italian_words if w in content_lower)
        english_count = sum(1 for w in english_words if w in content_lower)

        return 'it' if italian_count > english_count else 'en'


# ═══════════════════════════════════════════════════════════════════════════════
# Test Data Extractor
# ═══════════════════════════════════════════════════════════════════════════════

class TestDataExtractor:
    """Estrae dati di test dal report CSV."""

    def __init__(self, project_name: str, base_dir: Optional[Path] = None):
        self.project_name = project_name
        if base_dir:
            self.base_dir = Path(base_dir)
        else:
            self.base_dir = Path(__file__).parent.parent
        self.reports_dir = self.base_dir / "reports" / project_name

    def get_latest_run(self) -> Optional[int]:
        """Trova l'ultima run disponibile."""
        if not self.reports_dir.exists():
            return None

        run_dirs = list(self.reports_dir.glob("run_*"))
        if not run_dirs:
            return None

        run_numbers = []
        for d in run_dirs:
            try:
                num = int(d.name.split('_')[1])
                run_numbers.append(num)
            except (IndexError, ValueError):
                pass

        return max(run_numbers) if run_numbers else None

    def get_test(self, run_number: int, test_id: str) -> Optional[TestTrace]:
        """Estrae un singolo test dalla run."""
        report_path = self.reports_dir / f"run_{run_number:03d}" / "report.csv"
        if not report_path.exists():
            return None

        with open(report_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('test_id') == test_id:
                    return self._parse_row(row)

        return None

    def get_all_tests(self, run_number: int) -> List[TestTrace]:
        """Estrae tutti i test da una run."""
        report_path = self.reports_dir / f"run_{run_number:03d}" / "report.csv"
        if not report_path.exists():
            return []

        tests = []
        with open(report_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                trace = self._parse_row(row)
                if trace:
                    tests.append(trace)

        return tests

    def _parse_row(self, row: Dict[str, str]) -> Optional[TestTrace]:
        """Parsa una riga del CSV in TestTrace."""
        notes = row.get('notes', '')

        # Estrai sezioni strutturate dalle notes
        query_data = self._extract_section(notes, 'QUERY')
        response = self._extract_section(notes, 'RESPONSE')
        performance = self._extract_section(notes, 'PERFORMANCE')
        tools_section = self._extract_section(notes, 'TOOLS')
        sources_section = self._extract_section(notes, 'SOURCES')

        # Parse performance
        model = None
        duration = 0
        first_token = 0
        if performance:
            model_match = re.search(r'Model:\s*(.+)', performance)
            if model_match:
                model = model_match.group(1).strip()
            dur_match = re.search(r'Duration:\s*(\d+)ms', performance)
            if dur_match:
                duration = int(dur_match.group(1))
            ft_match = re.search(r'First Token:\s*(\d+)ms', performance)
            if ft_match:
                first_token = int(ft_match.group(1))

        # Parse tools
        tools = []
        if tools_section:
            tools = [t.strip() for t in tools_section.split('\n') if t.strip()]

        # Parse sources
        sources = []
        if sources_section:
            for line in sources_section.split('\n'):
                if line.strip().startswith('•'):
                    source_text = line.strip()[1:].strip()
                    sources.append({'path': source_text})

        return TestTrace(
            test_id=row.get('test_id', ''),
            question=row.get('question', ''),
            response=response or row.get('conversation', ''),
            query_data=self._parse_json_safe(query_data) if query_data else None,
            tools_used=tools,
            sources=sources,
            model=model,
            duration_ms=int(row.get('duration_ms', 0)) or duration,
            first_token_ms=first_token,
            esito=row.get('esito', 'UNKNOWN'),
            notes=notes
        )

    def _extract_section(self, text: str, section_name: str) -> Optional[str]:
        """Estrae una sezione dal testo delle notes."""
        # Pattern che accetta "=== TOOLS ===" o "=== TOOLS (1) ==="
        pattern = rf'=== {section_name}(?: \(\d+\))? ===\s*\n(.*?)(?===|$)'
        match = re.search(pattern, text, re.DOTALL)
        if match:
            return match.group(1).strip()
        return None

    def _parse_json_safe(self, text: str) -> Optional[Dict]:
        """Prova a parsare JSON, ritorna None se fallisce."""
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return None


# ═══════════════════════════════════════════════════════════════════════════════
# HTML Renderer
# ═══════════════════════════════════════════════════════════════════════════════

class HTMLRenderer:
    """Genera output HTML interattivo."""

    @staticmethod
    def prompt_page(structure: PromptStructure, project_name: str) -> str:
        """Genera pagina HTML per visualizzazione prompt."""
        rules_html = HTMLRenderer._rules_to_flowchart(structure.rules)
        caps_html = HTMLRenderer._capabilities_to_mindmap(structure.capabilities)
        sections_html = HTMLRenderer._sections_to_html(structure.sections)
        workflow_html = HTMLRenderer._workflow_to_html(structure.sections.get('_workflow_steps', []))

        return f'''<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Prompt Visualizer - {project_name}</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0d1117;
            color: #c9d1d9;
            padding: 20px;
            line-height: 1.6;
        }}
        .container {{ max-width: 1400px; margin: 0 auto; }}
        h1 {{
            color: #58a6ff;
            border-bottom: 1px solid #30363d;
            padding-bottom: 15px;
            margin-bottom: 30px;
        }}
        h2 {{
            color: #8b949e;
            margin: 30px 0 15px;
            font-size: 1.2em;
        }}
        .grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 30px;
        }}
        @media (max-width: 900px) {{
            .grid {{ grid-template-columns: 1fr; }}
        }}
        .card {{
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 8px;
            padding: 20px;
        }}
        .flowchart {{
            display: flex;
            flex-direction: column;
            gap: 15px;
        }}
        .rule {{
            background: #21262d;
            border-left: 4px solid #58a6ff;
            padding: 12px 15px;
            border-radius: 0 6px 6px 0;
        }}
        .rule.condition {{ border-color: #f0883e; }}
        .rule.always {{ border-color: #3fb950; }}
        .rule.never {{ border-color: #f85149; }}
        .rule.preference {{ border-color: #a371f7; }}
        .rule-type {{
            font-size: 0.75em;
            text-transform: uppercase;
            color: #8b949e;
            margin-bottom: 5px;
        }}
        .mindmap {{
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
        }}
        .capability {{
            background: #238636;
            padding: 8px 15px;
            border-radius: 20px;
            font-size: 0.9em;
        }}
        .capability.cannot {{ background: #da3633; }}
        .meta {{
            display: flex;
            gap: 20px;
            margin-bottom: 20px;
        }}
        .meta-item {{
            background: #21262d;
            padding: 10px 15px;
            border-radius: 6px;
        }}
        .meta-label {{ color: #8b949e; font-size: 0.85em; }}
        .raw-prompt {{
            background: #21262d;
            padding: 15px;
            border-radius: 6px;
            font-family: monospace;
            font-size: 0.9em;
            white-space: pre-wrap;
            max-height: 400px;
            overflow-y: auto;
        }}
        .collapsible {{
            cursor: pointer;
            user-select: none;
        }}
        .collapsible:after {{
            content: ' [+]';
            color: #8b949e;
        }}
        .collapsible.active:after {{
            content: ' [-]';
        }}
        .content {{
            display: none;
            margin-top: 10px;
        }}
        .content.show {{ display: block; }}
        .rule.critical {{ border-color: #f85149; background: #2d1f1f; }}
        .workflow {{
            display: flex;
            flex-direction: column;
            gap: 10px;
            margin-top: 15px;
        }}
        .workflow-step {{
            display: flex;
            align-items: flex-start;
            gap: 15px;
        }}
        .step-number {{
            width: 32px;
            height: 32px;
            background: #238636;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            flex-shrink: 0;
        }}
        .step-content {{
            flex: 1;
            background: #21262d;
            padding: 12px 15px;
            border-radius: 6px;
        }}
        .step-title {{ color: #58a6ff; font-weight: 600; }}
        .sections-list {{
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-top: 15px;
        }}
        .section-tag {{
            background: #21262d;
            padding: 8px 15px;
            border-radius: 20px;
            font-size: 0.9em;
            border: 1px solid #30363d;
        }}
        .section-tag.has-content {{ border-color: #238636; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Prompt Visualizer: {project_name}</h1>

        <div class="meta">
            <div class="meta-item">
                <div class="meta-label">Lingua</div>
                <div>{structure.language or 'N/A'}</div>
            </div>
            <div class="meta-item">
                <div class="meta-label">Tone</div>
                <div>{structure.tone or 'N/A'}</div>
            </div>
            <div class="meta-item">
                <div class="meta-label">Regole</div>
                <div>{len(structure.rules)}</div>
            </div>
            <div class="meta-item">
                <div class="meta-label">Capabilities</div>
                <div>{len(structure.capabilities)}</div>
            </div>
        </div>

        <div class="grid">
            <div class="card">
                <h2>Flowchart Regole</h2>
                <div class="flowchart">
                    {rules_html}
                </div>
            </div>

            <div class="card">
                <h2>Mind Map Capabilities</h2>
                <div class="mindmap">
                    {caps_html}
                </div>
            </div>
        </div>

        {workflow_html}

        <h2 class="collapsible" onclick="toggleContent(this)">Sezioni Markdown</h2>
        <div class="content">
            {sections_html}
        </div>

        <h2 class="collapsible" onclick="toggleContent(this)">Prompt Originale</h2>
        <div class="content">
            <div class="raw-prompt">{structure.raw_content}</div>
        </div>
    </div>

    <script>
        function toggleContent(el) {{
            el.classList.toggle('active');
            el.nextElementSibling.classList.toggle('show');
        }}
    </script>
</body>
</html>'''

    @staticmethod
    def _rules_to_flowchart(rules: List[PromptRule]) -> str:
        """Converte regole in HTML flowchart."""
        if not rules:
            return '<p style="color:#8b949e">Nessuna regola rilevata</p>'

        html_parts = []
        for rule in rules:
            html_parts.append(f'''
                <div class="rule {rule.type}">
                    <div class="rule-type">{rule.type}</div>
                    <div>{rule.text}</div>
                </div>
            ''')
        return '\n'.join(html_parts)

    @staticmethod
    def _capabilities_to_mindmap(capabilities: List[PromptCapability]) -> str:
        """Converte capabilities in HTML mindmap."""
        if not capabilities:
            return '<p style="color:#8b949e">Nessuna capability rilevata</p>'

        html_parts = []
        for cap in capabilities:
            css_class = '' if cap.can_do else 'cannot'
            prefix = '' if cap.can_do else ''
            html_parts.append(
                f'<span class="capability {css_class}" title="{cap.description}">'
                f'{prefix}{cap.name}</span>'
            )
        return '\n'.join(html_parts)

    @staticmethod
    def _sections_to_html(sections: Dict[str, Any]) -> str:
        """Converte sezioni markdown in HTML."""
        if not sections:
            return '<p style="color:#8b949e">Nessuna sezione rilevata</p>'

        html_parts = ['<div class="sections-list">']
        for name, content in sections.items():
            if name.startswith('_'):
                continue  # Skip internal sections like _workflow_steps
            has_content = bool(content) and len(str(content)) > 10
            css_class = 'has-content' if has_content else ''
            display_name = name.replace('_', ' ').title()
            html_parts.append(
                f'<span class="section-tag {css_class}" title="{len(str(content))} chars">'
                f'{display_name}</span>'
            )
        html_parts.append('</div>')
        return '\n'.join(html_parts)

    @staticmethod
    def _workflow_to_html(steps: List[Dict[str, str]]) -> str:
        """Converte workflow steps in HTML."""
        if not steps:
            return ''

        html_parts = [
            '<div class="card" style="margin-top:20px">',
            '<h2>Workflow Steps</h2>',
            '<div class="workflow">'
        ]

        for step in steps:
            html_parts.append(f'''
                <div class="workflow-step">
                    <div class="step-number">{step.get('number', '?')}</div>
                    <div class="step-content">
                        <div class="step-title">{step.get('title', 'Step')}</div>
                    </div>
                </div>
            ''')

        html_parts.append('</div></div>')
        return '\n'.join(html_parts)

    @staticmethod
    def test_page(trace: TestTrace, project_name: str, prompt_structure: Optional[PromptStructure] = None) -> str:
        """Genera pagina HTML per visualizzazione test."""
        waterfall_html = HTMLRenderer._trace_to_waterfall(trace)
        timeline_html = HTMLRenderer._trace_to_timeline(trace)
        comparison_html = HTMLRenderer._trace_to_comparison(trace, prompt_structure)

        status_color = '#3fb950' if trace.esito == 'PASS' else '#f85149'

        return f'''<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Test Visualizer - {trace.test_id}</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0d1117;
            color: #c9d1d9;
            padding: 20px;
            line-height: 1.6;
        }}
        .container {{ max-width: 1400px; margin: 0 auto; }}
        h1 {{
            color: #58a6ff;
            border-bottom: 1px solid #30363d;
            padding-bottom: 15px;
            margin-bottom: 30px;
            display: flex;
            align-items: center;
            gap: 15px;
        }}
        .status {{
            background: {status_color};
            color: white;
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 0.7em;
        }}
        h2 {{
            color: #8b949e;
            margin: 30px 0 15px;
            font-size: 1.2em;
        }}
        .tabs {{
            display: flex;
            gap: 5px;
            margin-bottom: 20px;
        }}
        .tab {{
            background: #21262d;
            border: 1px solid #30363d;
            color: #c9d1d9;
            padding: 10px 20px;
            border-radius: 6px 6px 0 0;
            cursor: pointer;
        }}
        .tab.active {{
            background: #161b22;
            border-bottom-color: #161b22;
        }}
        .tab-content {{
            display: none;
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 0 6px 6px 6px;
            padding: 20px;
        }}
        .tab-content.active {{ display: block; }}
        .waterfall {{
            display: flex;
            flex-direction: column;
            gap: 0;
        }}
        .waterfall-step {{
            display: flex;
            align-items: stretch;
        }}
        .waterfall-bar {{
            width: 4px;
            background: #30363d;
            margin-right: 20px;
        }}
        .waterfall-bar.active {{ background: #58a6ff; }}
        .waterfall-content {{
            flex: 1;
            padding: 15px 0;
        }}
        .waterfall-label {{
            color: #58a6ff;
            font-weight: 600;
            margin-bottom: 8px;
        }}
        .waterfall-data {{
            background: #21262d;
            padding: 12px 15px;
            border-radius: 6px;
            font-family: monospace;
            font-size: 0.9em;
            white-space: pre-wrap;
            max-height: 200px;
            overflow-y: auto;
        }}
        .timeline {{
            display: flex;
            flex-direction: column;
            gap: 20px;
        }}
        .timeline-item {{
            display: flex;
            align-items: flex-start;
            gap: 15px;
        }}
        .timeline-dot {{
            width: 12px;
            height: 12px;
            background: #58a6ff;
            border-radius: 50%;
            margin-top: 5px;
            flex-shrink: 0;
        }}
        .timeline-time {{
            color: #8b949e;
            font-size: 0.85em;
            min-width: 80px;
        }}
        .comparison {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
        }}
        .comparison-col {{
            background: #21262d;
            padding: 15px;
            border-radius: 6px;
        }}
        .comparison-title {{
            color: #8b949e;
            margin-bottom: 10px;
            font-size: 0.9em;
        }}
        .source-item {{
            background: #21262d;
            padding: 10px;
            border-radius: 6px;
            margin-top: 10px;
            font-size: 0.85em;
        }}
        .metrics {{
            display: flex;
            gap: 20px;
            margin-bottom: 20px;
        }}
        .metric {{
            background: #21262d;
            padding: 15px;
            border-radius: 6px;
            text-align: center;
        }}
        .metric-value {{
            font-size: 1.5em;
            font-weight: 600;
            color: #58a6ff;
        }}
        .metric-label {{
            color: #8b949e;
            font-size: 0.85em;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>
            Test: {trace.test_id}
            <span class="status">{trace.esito}</span>
        </h1>

        <div class="metrics">
            <div class="metric">
                <div class="metric-value">{trace.duration_ms}ms</div>
                <div class="metric-label">Duration</div>
            </div>
            <div class="metric">
                <div class="metric-value">{trace.first_token_ms}ms</div>
                <div class="metric-label">First Token</div>
            </div>
            <div class="metric">
                <div class="metric-value">{len(trace.tools_used)}</div>
                <div class="metric-label">Tools</div>
            </div>
            <div class="metric">
                <div class="metric-value">{len(trace.sources)}</div>
                <div class="metric-label">Sources</div>
            </div>
        </div>

        <div class="tabs">
            <div class="tab active" onclick="showTab('waterfall')">Waterfall</div>
            <div class="tab" onclick="showTab('timeline')">Timeline</div>
            <div class="tab" onclick="showTab('comparison')">Confronto</div>
        </div>

        <div id="waterfall" class="tab-content active">
            {waterfall_html}
        </div>

        <div id="timeline" class="tab-content">
            {timeline_html}
        </div>

        <div id="comparison" class="tab-content">
            {comparison_html}
        </div>
    </div>

    <script>
        function showTab(tabId) {{
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            document.querySelector(`[onclick="showTab('${{tabId}}')"]`).classList.add('active');
            document.getElementById(tabId).classList.add('active');
        }}
    </script>
</body>
</html>'''

    @staticmethod
    def _trace_to_waterfall(trace: TestTrace) -> str:
        """Genera waterfall HTML."""
        steps = [
            ('Query', trace.question, True),
            ('Tools', ', '.join(trace.tools_used) if trace.tools_used else 'Nessuno', bool(trace.tools_used)),
            ('Sources', '\n'.join(s.get('path', '')[:100] for s in trace.sources) if trace.sources else 'Nessuna', bool(trace.sources)),
            ('Response', trace.response[:500] + '...' if len(trace.response) > 500 else trace.response, True),
        ]

        html_parts = ['<div class="waterfall">']
        for label, data, active in steps:
            bar_class = 'active' if active else ''
            html_parts.append(f'''
                <div class="waterfall-step">
                    <div class="waterfall-bar {bar_class}"></div>
                    <div class="waterfall-content">
                        <div class="waterfall-label">{label}</div>
                        <div class="waterfall-data">{data}</div>
                    </div>
                </div>
            ''')
        html_parts.append('</div>')
        return '\n'.join(html_parts)

    @staticmethod
    def _trace_to_timeline(trace: TestTrace) -> str:
        """Genera timeline HTML."""
        items = [
            ('0ms', 'Query ricevuta', trace.question),
            (f'{trace.first_token_ms}ms', 'First Token', f'Modello: {trace.model or "N/A"}'),
        ]

        if trace.tools_used:
            items.append(('', 'Tools chiamati', ', '.join(trace.tools_used)))

        if trace.sources:
            items.append(('', 'Sources consultate', f'{len(trace.sources)} documenti'))

        items.append((f'{trace.duration_ms}ms', 'Response completata', f'Esito: {trace.esito}'))

        html_parts = ['<div class="timeline">']
        for time, label, detail in items:
            html_parts.append(f'''
                <div class="timeline-item">
                    <div class="timeline-dot"></div>
                    <div class="timeline-time">{time}</div>
                    <div>
                        <strong>{label}</strong>
                        <div style="color:#8b949e">{detail}</div>
                    </div>
                </div>
            ''')
        html_parts.append('</div>')
        return '\n'.join(html_parts)

    @staticmethod
    def _trace_to_comparison(trace: TestTrace, prompt_structure: Optional[PromptStructure]) -> str:
        """Genera confronto prompt vs risposta."""
        prompt_rules = ''
        if prompt_structure and prompt_structure.rules:
            prompt_rules = '<ul>'
            for rule in prompt_structure.rules[:5]:
                prompt_rules += f'<li>{rule.text}</li>'
            prompt_rules += '</ul>'
        else:
            prompt_rules = '<p style="color:#8b949e">Nessuna regola disponibile</p>'

        return f'''
            <div class="comparison">
                <div class="comparison-col">
                    <div class="comparison-title">REGOLE PROMPT APPLICABILI</div>
                    {prompt_rules}
                </div>
                <div class="comparison-col">
                    <div class="comparison-title">RISPOSTA DEL BOT</div>
                    <div style="white-space:pre-wrap">{trace.response[:800]}</div>
                </div>
            </div>
        '''


# ═══════════════════════════════════════════════════════════════════════════════
# Terminal Renderer
# ═══════════════════════════════════════════════════════════════════════════════

class TerminalRenderer:
    """Genera output ASCII per terminale."""

    # ANSI colors
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    BLUE = '\033[34m'
    GREEN = '\033[32m'
    RED = '\033[31m'
    YELLOW = '\033[33m'
    CYAN = '\033[36m'
    MAGENTA = '\033[35m'

    @classmethod
    def prompt_view(cls, structure: PromptStructure, project_name: str) -> str:
        """Genera vista terminale del prompt."""
        lines = [
            '',
            f'{cls.BOLD}{cls.BLUE}PROMPT VISUALIZER: {project_name}{cls.RESET}',
            f'{cls.DIM}{"=" * 60}{cls.RESET}',
            '',
            f'{cls.DIM}Lingua:{cls.RESET} {structure.language or "N/A"}  '
            f'{cls.DIM}Tone:{cls.RESET} {structure.tone or "N/A"}  '
            f'{cls.DIM}Regole:{cls.RESET} {len(structure.rules)}  '
            f'{cls.DIM}Capabilities:{cls.RESET} {len(structure.capabilities)}',
            '',
        ]

        # Flowchart regole
        lines.append(f'{cls.BOLD}FLOWCHART REGOLE{cls.RESET}')
        lines.append(f'{cls.DIM}{"-" * 40}{cls.RESET}')

        if structure.rules:
            for rule in structure.rules:
                color = {
                    'condition': cls.YELLOW,
                    'always': cls.GREEN,
                    'never': cls.RED,
                    'preference': cls.MAGENTA,
                }.get(rule.type, cls.RESET)

                lines.append(f'  {color}[{rule.type.upper()}]{cls.RESET}')
                # Wrap text
                wrapped = cls._wrap_text(rule.text, 55)
                for i, line in enumerate(wrapped):
                    prefix = '    ' if i > 0 else '    '
                    lines.append(f'{prefix}{line}')
                lines.append('')
        else:
            lines.append(f'  {cls.DIM}Nessuna regola rilevata{cls.RESET}')
            lines.append('')

        # Mind map capabilities
        lines.append(f'{cls.BOLD}MIND MAP CAPABILITIES{cls.RESET}')
        lines.append(f'{cls.DIM}{"-" * 40}{cls.RESET}')

        if structure.capabilities:
            can_do = [c for c in structure.capabilities if c.can_do]
            cannot_do = [c for c in structure.capabilities if not c.can_do]

            if can_do:
                lines.append(f'  {cls.GREEN}CAN DO:{cls.RESET}')
                for cap in can_do:
                    lines.append(f'    + {cap.name}')

            if cannot_do:
                lines.append(f'  {cls.RED}CANNOT DO:{cls.RESET}')
                for cap in cannot_do:
                    lines.append(f'    - {cap.name}')
        else:
            lines.append(f'  {cls.DIM}Nessuna capability rilevata{cls.RESET}')

        lines.append('')
        return '\n'.join(lines)

    @classmethod
    def test_view(cls, trace: TestTrace, prompt_structure: Optional[PromptStructure] = None) -> str:
        """Genera vista terminale del test."""
        status_color = cls.GREEN if trace.esito == 'PASS' else cls.RED

        lines = [
            '',
            f'{cls.BOLD}{cls.BLUE}TEST VISUALIZER: {trace.test_id}{cls.RESET} '
            f'{status_color}[{trace.esito}]{cls.RESET}',
            f'{cls.DIM}{"=" * 60}{cls.RESET}',
            '',
            f'{cls.DIM}Duration:{cls.RESET} {trace.duration_ms}ms  '
            f'{cls.DIM}First Token:{cls.RESET} {trace.first_token_ms}ms  '
            f'{cls.DIM}Model:{cls.RESET} {trace.model or "N/A"}',
            '',
        ]

        # Waterfall
        lines.append(f'{cls.BOLD}WATERFALL TRACE{cls.RESET}')
        lines.append(f'{cls.DIM}{"-" * 40}{cls.RESET}')

        waterfall_steps = [
            ('QUERY', trace.question, cls.CYAN),
            ('TOOLS', ', '.join(trace.tools_used) if trace.tools_used else 'Nessuno', cls.YELLOW),
            ('SOURCES', f'{len(trace.sources)} documenti' if trace.sources else 'Nessuna', cls.MAGENTA),
            ('RESPONSE', trace.response[:200] + '...' if len(trace.response) > 200 else trace.response, cls.GREEN),
        ]

        for label, data, color in waterfall_steps:
            lines.append(f'  {color}|{cls.RESET}')
            lines.append(f'  {color}+-- [{label}]{cls.RESET}')
            wrapped = cls._wrap_text(data, 50)
            for line in wrapped:
                lines.append(f'  {color}|{cls.RESET}   {line}')
            lines.append(f'  {color}|{cls.RESET}')

        lines.append('')

        # Timeline
        lines.append(f'{cls.BOLD}TIMELINE{cls.RESET}')
        lines.append(f'{cls.DIM}{"-" * 40}{cls.RESET}')
        lines.append(f'  0ms .......... Query ricevuta')
        lines.append(f'  {trace.first_token_ms}ms .......... First Token')
        if trace.tools_used:
            lines.append(f'       .......... Tools: {", ".join(trace.tools_used)}')
        if trace.sources:
            lines.append(f'       .......... Sources: {len(trace.sources)} docs')
        lines.append(f'  {trace.duration_ms}ms .......... Response [{trace.esito}]')

        lines.append('')
        return '\n'.join(lines)

    @staticmethod
    def _wrap_text(text: str, width: int) -> List[str]:
        """Wrap text to specified width."""
        words = text.split()
        lines = []
        current_line = []
        current_length = 0

        for word in words:
            if current_length + len(word) + 1 <= width:
                current_line.append(word)
                current_length += len(word) + 1
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                current_line = [word]
                current_length = len(word)

        if current_line:
            lines.append(' '.join(current_line))

        return lines or ['']


# ═══════════════════════════════════════════════════════════════════════════════
# Main Visualizer Classes
# ═══════════════════════════════════════════════════════════════════════════════

class PromptVisualizer:
    """Visualizzatore del prompt."""

    def __init__(self, project_name: str, base_dir: Optional[Path] = None):
        self.project_name = project_name
        if base_dir:
            self.base_dir = Path(base_dir)
        else:
            self.base_dir = Path(__file__).parent.parent

        self.parser = PromptParser()
        self.structure: Optional[PromptStructure] = None

    def load(self) -> bool:
        """Carica e parsa il prompt corrente."""
        from src.prompt_manager import PromptManager

        manager = PromptManager(self.project_name, self.base_dir)
        content = manager.get_current()

        if not content:
            return False

        self.structure = self.parser.parse(content)
        return True

    def render_html(self, output_path: Optional[Path] = None, open_browser: bool = True) -> Optional[Path]:
        """Genera e apre HTML."""
        if not self.structure:
            if not self.load():
                return None

        html = HTMLRenderer.prompt_page(self.structure, self.project_name)

        if output_path is None:
            output_path = self.base_dir / "reports" / self.project_name / "prompt_viz.html"

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)

        if open_browser:
            webbrowser.open(f'file://{output_path.absolute()}')

        return output_path

    def render_terminal(self) -> str:
        """Genera output terminale."""
        if not self.structure:
            if not self.load():
                return "Errore: impossibile caricare il prompt"

        return TerminalRenderer.prompt_view(self.structure, self.project_name)


class TestVisualizer:
    """Visualizzatore del singolo test."""

    def __init__(self, project_name: str, run_number: Optional[int] = None,
                 test_id: Optional[str] = None, base_dir: Optional[Path] = None):
        self.project_name = project_name
        self.run_number = run_number
        self.test_id = test_id

        if base_dir:
            self.base_dir = Path(base_dir)
        else:
            self.base_dir = Path(__file__).parent.parent

        self.extractor = TestDataExtractor(project_name, self.base_dir)
        self.trace: Optional[TestTrace] = None
        self.prompt_structure: Optional[PromptStructure] = None

    def load(self) -> bool:
        """Carica dati del test."""
        # Determina run number
        if self.run_number is None:
            self.run_number = self.extractor.get_latest_run()
            if self.run_number is None:
                return False

        # Se test_id specificato, carica quel test
        if self.test_id:
            self.trace = self.extractor.get_test(self.run_number, self.test_id)
        else:
            # Altrimenti carica il primo test
            tests = self.extractor.get_all_tests(self.run_number)
            if tests:
                self.trace = tests[0]

        if not self.trace:
            return False

        # Carica anche struttura prompt per confronto
        try:
            from src.prompt_manager import PromptManager
            manager = PromptManager(self.project_name, self.base_dir)
            content = manager.get_current()
            if content:
                parser = PromptParser()
                self.prompt_structure = parser.parse(content)
        except Exception:
            pass

        return True

    def render_html(self, output_path: Optional[Path] = None, open_browser: bool = True) -> Optional[Path]:
        """Genera e apre HTML."""
        if not self.trace:
            if not self.load():
                return None

        html = HTMLRenderer.test_page(self.trace, self.project_name, self.prompt_structure)

        if output_path is None:
            output_path = (self.base_dir / "reports" / self.project_name /
                          f"run_{self.run_number:03d}" / f"test_viz_{self.trace.test_id}.html")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)

        if open_browser:
            webbrowser.open(f'file://{output_path.absolute()}')

        return output_path

    def render_terminal(self) -> str:
        """Genera output terminale."""
        if not self.trace:
            if not self.load():
                return "Errore: impossibile caricare il test"

        return TerminalRenderer.test_view(self.trace, self.prompt_structure)


# ═══════════════════════════════════════════════════════════════════════════════
# CLI Functions
# ═══════════════════════════════════════════════════════════════════════════════

def visualize_prompt_cli(project_name: str, output: str = 'html') -> None:
    """CLI per visualizzazione prompt."""
    from src.ui import get_ui
    ui = get_ui()

    viz = PromptVisualizer(project_name)

    if output == 'html':
        path = viz.render_html()
        if path:
            ui.success(f"Visualizzazione aperta: {path}")
        else:
            ui.error("Impossibile caricare il prompt")
    else:
        result = viz.render_terminal()
        print(result)


def visualize_test_cli(project_name: str, test_id: Optional[str] = None,
                       run_number: Optional[int] = None, output: str = 'html') -> None:
    """CLI per visualizzazione test."""
    from src.ui import get_ui
    ui = get_ui()

    viz = TestVisualizer(project_name, run_number, test_id)

    if output == 'html':
        path = viz.render_html()
        if path:
            ui.success(f"Visualizzazione aperta: {path}")
        else:
            ui.error("Impossibile caricare il test")
    else:
        result = viz.render_terminal()
        print(result)
