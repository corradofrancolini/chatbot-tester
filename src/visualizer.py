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

import webbrowser
from pathlib import Path
from typing import Optional, List, Dict, Any

# Import from parsing subpackage
from .parsing.prompt_parser import (
    PromptParser,
    PromptRule,
    PromptCapability,
    PromptStructure,
)
from .parsing.test_extractor import (
    TestDataExtractor,
    TestTrace,
)


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

        status_color = '#3fb950' if trace.result == 'PASS' else '#f85149'

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
            <span class="status">{trace.result}</span>
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

        items.append((f'{trace.duration_ms}ms', 'Response completata', f'Esito: {trace.result}'))

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
        status_color = cls.GREEN if trace.result == 'PASS' else cls.RED

        lines = [
            '',
            f'{cls.BOLD}{cls.BLUE}TEST VISUALIZER: {trace.test_id}{cls.RESET} '
            f'{status_color}[{trace.result}]{cls.RESET}',
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
        lines.append(f'  {trace.duration_ms}ms .......... Response [{trace.result}]')

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
