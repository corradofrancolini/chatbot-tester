"""
Prompt Parser - Extracts semantic structure from prompt text

Parses prompts to identify:
- Rules (conditions, always, never, preferences)
- Capabilities (can do, cannot do)
- Sections (markdown headings)
- Workflow steps
- Tone and language
"""

import re
from dataclasses import dataclass, field
from typing import Optional, List, Dict


@dataclass
class PromptRule:
    """Una regola estratta dal prompt."""
    type: str  # 'condition', 'always', 'never', 'preference', 'critical'
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
            r'IF\s+(.+?)\s*[→\-]+\s*(.+?)(?:\n|$)',
            r'[Ii]f\s+(.+?),?\s+(?:then\s+)?(.+?)(?:\.|$)',
            r'[Ww]hen\s+(.+?),?\s+(.+?)(?:\.|$)',
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

        # Estrai sezioni markdown (## HEADING)
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
        seen_texts = set()

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
                    rules.append(PromptRule(type='critical', text=text))

        # Poi estrai regole standard
        for rule_type, patterns in patterns_dict.items():
            if rule_type == 'critical':
                continue
            for pattern in patterns:
                for match in re.finditer(pattern, content, re.MULTILINE):
                    text = match.group(0).strip()
                    if len(text) > 15 and text not in seen_texts:
                        if not self._is_in_code_block(content, match.start()):
                            seen_texts.add(text)
                            rules.append(PromptRule(type=rule_type, text=text))

        # Estrai regole da liste numerate con keyword
        list_rules = self._extract_list_rules(content, language)
        for rule in list_rules:
            if rule.text not in seen_texts:
                seen_texts.add(rule.text)
                rules.append(rule)

        return rules

    def _is_in_code_block(self, content: str, position: int) -> bool:
        """Verifica se una posizione e' dentro un code block."""
        code_markers = content[:position].count('```')
        return code_markers % 2 == 1

    def _extract_list_rules(self, content: str, language: str) -> List[PromptRule]:
        """Estrae regole da liste numerate/puntate."""
        rules = []

        if language == 'en':
            keywords = {
                'never': r'^\s*[\d\.\-\*]+\s*((?:NEVER|Never|Do NOT|Don\'t|Avoid).+?)$',
                'always': r'^\s*[\d\.\-\*]+\s*((?:ALWAYS|Always|MUST|Must|Ensure).+?)$',
                'critical': r'^\s*[\d\.\-\*]+\s*\*\*(.+?)\*\*',
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

        # Estrai da sezioni strutturate
        structured_caps = self._extract_structured_capabilities(content)
        for cap in structured_caps:
            if cap.description not in seen:
                seen.add(cap.description)
                capabilities.append(cap)

        return capabilities

    def _extract_structured_capabilities(self, content: str) -> List[PromptCapability]:
        """Estrae capabilities da sezioni strutturate del prompt."""
        capabilities = []

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
                items = re.findall(r'^\s*[\d\.\-\*]+\s*\*\*(.+?)\*\*', section_content, re.MULTILINE)
                for item in items[:5]:
                    capabilities.append(PromptCapability(
                        name=f"{prefix}: {item[:40]}",
                        description=item,
                        can_do=can_do
                    ))

        return capabilities

    def _extract_workflow_steps(self, content: str) -> List[Dict[str, str]]:
        """Estrae step del workflow (### Step N: ...)."""
        steps = []

        pattern = r'###\s*Step\s*(\d+):\s*(.+?)(?=\n###|\n##|\Z)'
        for match in re.finditer(pattern, content, re.DOTALL):
            step_num = match.group(1)
            step_content = match.group(2).strip()
            title_match = re.match(r'^([^\n]+)', step_content)
            title = title_match.group(1) if title_match else f"Step {step_num}"
            steps.append({
                'number': step_num,
                'title': title,
                'content': step_content[:500]
            })

        return steps

    def _extract_sections(self, content: str) -> Dict[str, str]:
        """Estrae sezioni markdown dal prompt."""
        sections = {}
        current_section = "intro"
        current_content = []

        for line in content.split('\n'):
            if line.startswith('## '):
                if current_content:
                    sections[current_section] = '\n'.join(current_content).strip()
                current_section = line[3:].strip().lower()
                current_content = []
            elif line.startswith('# ') and not line.startswith('## '):
                if current_content:
                    sections[current_section] = '\n'.join(current_content).strip()
                current_section = line.lstrip('#').strip().lower()
                current_content = []
            else:
                current_content.append(line)

        if current_content:
            sections[current_section] = '\n'.join(current_content).strip()

        return sections

    def _detect_tone(self, content: str) -> Optional[str]:
        """Rileva il tone of voice dal prompt."""
        tone_keywords = {
            'formal': ['formal', 'formale', 'professional', 'professionale', 'cortese', 'polite'],
            'informal': ['informal', 'informale', 'friendly', 'amichevole', 'colloquiale', 'conversational'],
            'technical': ['technical', 'tecnico', 'precise', 'preciso', 'detailed', 'dettagliato'],
            'empathetic': ['empathetic', 'empatico', 'supportive', 'supportivo', 'understanding'],
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
