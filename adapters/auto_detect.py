"""
Auto Detect Adapter - Rilevamento automatico selettori con euristiche

Usa pattern comuni per identificare automaticamente gli elementi
UI dei chatbot più diffusi.
"""

from typing import Optional, List, Tuple
from dataclasses import dataclass

from playwright.async_api import Page

from .base import (
    ChatbotAdapter, AdapterResult, SelectorSet,
    SelectorInfo, SelectorConfidence
)


@dataclass
class SelectorPattern:
    """Pattern per rilevamento selettore"""
    selector: str
    confidence: SelectorConfidence
    description: str = ""


class AutoDetectAdapter(ChatbotAdapter):
    """
    Adapter per rilevamento automatico basato su euristiche.
    
    Cerca pattern comuni usati dai framework chatbot più diffusi:
    - Custom elements (llm__, chat-, etc.)
    - ARIA attributes
    - Placeholder patterns
    - Structural patterns
    
    Usage:
        adapter = AutoDetectAdapter(page)
        result = await adapter.detect()
    """
    
    # Pattern per textarea (ordinati per priorità/confidenza)
    TEXTAREA_PATTERNS: List[SelectorPattern] = [
        # Pattern specifici chatbot
        SelectorPattern("#llm-prompt-textarea", SelectorConfidence.HIGH, "EFG chatbot"),
        SelectorPattern("[data-testid='chat-input']", SelectorConfidence.HIGH, "Test ID standard"),
        SelectorPattern("[data-testid='prompt-textarea']", SelectorConfidence.HIGH, "OpenAI-style"),
        SelectorPattern(".chat-input textarea", SelectorConfidence.HIGH, "Chat input class"),
        
        # ARIA patterns
        SelectorPattern("textarea[aria-label*='message' i]", SelectorConfidence.MEDIUM, "ARIA message"),
        SelectorPattern("textarea[aria-label*='prompt' i]", SelectorConfidence.MEDIUM, "ARIA prompt"),
        SelectorPattern("textarea[aria-label*='chat' i]", SelectorConfidence.MEDIUM, "ARIA chat"),
        SelectorPattern("textarea[aria-label*='input' i]", SelectorConfidence.MEDIUM, "ARIA input"),
        
        # Placeholder patterns
        SelectorPattern("textarea[placeholder*='message' i]", SelectorConfidence.MEDIUM, "Placeholder message"),
        SelectorPattern("textarea[placeholder*='type' i]", SelectorConfidence.MEDIUM, "Placeholder type"),
        SelectorPattern("textarea[placeholder*='ask' i]", SelectorConfidence.MEDIUM, "Placeholder ask"),
        SelectorPattern("textarea[placeholder*='scrivi' i]", SelectorConfidence.MEDIUM, "Placeholder italiano"),
        SelectorPattern("textarea[placeholder*='digita' i]", SelectorConfidence.MEDIUM, "Placeholder italiano"),
        SelectorPattern("textarea[placeholder*='send' i]", SelectorConfidence.MEDIUM, "Placeholder send"),
        
        # Class patterns
        SelectorPattern("textarea.prompt", SelectorConfidence.MEDIUM, "Class prompt"),
        SelectorPattern("textarea.chat-input", SelectorConfidence.MEDIUM, "Class chat-input"),
        SelectorPattern("textarea.message-input", SelectorConfidence.MEDIUM, "Class message-input"),
        
        # Contenteditable (usato da alcuni chatbot)
        SelectorPattern("[contenteditable='true'][role='textbox']", SelectorConfidence.MEDIUM, "Contenteditable textbox"),
        SelectorPattern("[contenteditable='true'][data-placeholder]", SelectorConfidence.LOW, "Contenteditable generic"),
        
        # Generici (bassa confidenza)
        SelectorPattern("form textarea", SelectorConfidence.LOW, "Form textarea"),
        SelectorPattern("[role='textbox']", SelectorConfidence.LOW, "Role textbox"),
    ]
    
    # Pattern per submit button
    SUBMIT_PATTERNS: List[SelectorPattern] = [
        # Pattern specifici
        SelectorPattern("button.llm__prompt-submit", SelectorConfidence.HIGH, "EFG submit"),
        SelectorPattern("[data-testid='send-button']", SelectorConfidence.HIGH, "Test ID send"),
        SelectorPattern("[data-testid='submit-button']", SelectorConfidence.HIGH, "Test ID submit"),
        
        # ARIA patterns
        SelectorPattern("button[aria-label*='send' i]", SelectorConfidence.MEDIUM, "ARIA send"),
        SelectorPattern("button[aria-label*='invia' i]", SelectorConfidence.MEDIUM, "ARIA invia"),
        SelectorPattern("button[aria-label*='submit' i]", SelectorConfidence.MEDIUM, "ARIA submit"),
        
        # Icon-based patterns
        SelectorPattern("button:has(svg[class*='send'])", SelectorConfidence.MEDIUM, "SVG send icon"),
        SelectorPattern("button:has(svg[data-icon='paper-plane'])", SelectorConfidence.MEDIUM, "Paper plane icon"),
        SelectorPattern("button:has([class*='send'])", SelectorConfidence.MEDIUM, "Send class element"),
        
        # Class patterns
        SelectorPattern("button.send-button", SelectorConfidence.MEDIUM, "Class send-button"),
        SelectorPattern("button.submit-button", SelectorConfidence.MEDIUM, "Class submit-button"),
        SelectorPattern(".chat-submit button", SelectorConfidence.MEDIUM, "Chat submit container"),
        
        # Generici
        SelectorPattern("button[type='submit']", SelectorConfidence.LOW, "Type submit"),
        SelectorPattern("form button:last-child", SelectorConfidence.LOW, "Last form button"),
    ]
    
    # Pattern per messaggi bot
    BOT_MESSAGE_PATTERNS: List[SelectorPattern] = [
        # Pattern specifici
        SelectorPattern(".llm__message--assistant .llm__text-body", SelectorConfidence.HIGH, "EFG assistant"),
        SelectorPattern("[data-role='assistant']", SelectorConfidence.HIGH, "Data role assistant"),
        SelectorPattern("[data-message-author='assistant']", SelectorConfidence.HIGH, "Message author"),
        
        # Class patterns
        SelectorPattern(".message.assistant", SelectorConfidence.MEDIUM, "Class message assistant"),
        SelectorPattern(".message.bot", SelectorConfidence.MEDIUM, "Class message bot"),
        SelectorPattern(".message[data-role='assistant']", SelectorConfidence.MEDIUM, "Message data role"),
        SelectorPattern(".bot-message", SelectorConfidence.MEDIUM, "Class bot-message"),
        SelectorPattern(".ai-response", SelectorConfidence.MEDIUM, "Class ai-response"),
        SelectorPattern(".assistant-message", SelectorConfidence.MEDIUM, "Class assistant-message"),
        
        # Pattern generici con attributi
        SelectorPattern("[class*='assistant-message']", SelectorConfidence.LOW, "Partial class assistant"),
        SelectorPattern("[class*='bot-response']", SelectorConfidence.LOW, "Partial class bot"),
        SelectorPattern("[class*='ai-message']", SelectorConfidence.LOW, "Partial class ai"),
    ]
    
    # Pattern per thread container
    THREAD_PATTERNS: List[SelectorPattern] = [
        SelectorPattern(".llm__thread", SelectorConfidence.HIGH, "EFG thread"),
        SelectorPattern("[data-testid='chat-thread']", SelectorConfidence.HIGH, "Test ID thread"),
        SelectorPattern(".chat-thread", SelectorConfidence.MEDIUM, "Class chat-thread"),
        SelectorPattern(".message-container", SelectorConfidence.MEDIUM, "Class message-container"),
        SelectorPattern(".conversation-container", SelectorConfidence.MEDIUM, "Class conversation"),
        SelectorPattern("[role='log']", SelectorConfidence.LOW, "Role log"),
    ]
    
    async def detect(self) -> AdapterResult:
        """
        Esegue il rilevamento automatico completo.
        
        Returns:
            AdapterResult con tutti i selettori rilevati
        """
        self._debug("Inizio rilevamento automatico...")
        
        selector_set = SelectorSet()
        warnings = []
        
        # Rileva textarea
        selector_set.textarea = await self.detect_textarea()
        if not selector_set.textarea:
            warnings.append("Textarea non rilevato automaticamente")
        else:
            self._debug(f"Textarea: {selector_set.textarea.selector} ({selector_set.textarea.confidence.value})")
        
        # Rileva submit button
        selector_set.submit_button = await self.detect_submit_button()
        if not selector_set.submit_button:
            warnings.append("Submit button non rilevato automaticamente")
        else:
            self._debug(f"Submit: {selector_set.submit_button.selector} ({selector_set.submit_button.confidence.value})")
        
        # Rileva bot messages
        selector_set.bot_messages = await self.detect_bot_messages()
        if not selector_set.bot_messages:
            warnings.append("Bot messages non rilevato automaticamente")
        else:
            self._debug(f"Bot messages: {selector_set.bot_messages.selector} ({selector_set.bot_messages.confidence.value})")
        
        # Rileva thread container (opzionale)
        selector_set.thread_container = await self.detect_thread_container()
        if selector_set.thread_container:
            self._debug(f"Thread: {selector_set.thread_container.selector}")
        
        success = selector_set.is_complete
        message = "Tutti i selettori rilevati!" if success else f"Selettori mancanti: {', '.join(selector_set.missing)}"
        
        return AdapterResult(
            success=success,
            selectors=selector_set,
            message=message,
            warnings=warnings
        )
    
    async def detect_textarea(self) -> Optional[SelectorInfo]:
        """Rileva il campo di input usando i pattern definiti"""
        return await self._detect_with_patterns(
            self.TEXTAREA_PATTERNS,
            'textarea',
            require_visible=True,
            require_enabled=True
        )
    
    async def detect_submit_button(self) -> Optional[SelectorInfo]:
        """Rileva il bottone invio usando i pattern definiti"""
        return await self._detect_with_patterns(
            self.SUBMIT_PATTERNS,
            'submit_button',
            require_visible=True,
            require_enabled=True
        )
    
    async def detect_bot_messages(self) -> Optional[SelectorInfo]:
        """Rileva il selettore messaggi bot"""
        # Prima cerca pattern esatti
        result = await self._detect_with_patterns(
            self.BOT_MESSAGE_PATTERNS,
            'bot_messages',
            require_visible=False,  # Potrebbero non esserci messaggi ancora
            require_enabled=False
        )
        
        if result:
            return result
        
        # Se non trovato, prova a inferire dalla struttura della pagina
        return await self._infer_bot_messages()
    
    async def detect_thread_container(self) -> Optional[SelectorInfo]:
        """Rileva il container del thread (opzionale)"""
        return await self._detect_with_patterns(
            self.THREAD_PATTERNS,
            'thread_container',
            require_visible=True,
            require_enabled=False
        )
    
    async def _detect_with_patterns(
        self,
        patterns: List[SelectorPattern],
        name: str,
        require_visible: bool = True,
        require_enabled: bool = False
    ) -> Optional[SelectorInfo]:
        """
        Prova ogni pattern fino a trovarne uno funzionante.
        
        Args:
            patterns: Lista pattern da provare
            name: Nome elemento per debug
            require_visible: Richiedi elemento visibile
            require_enabled: Richiedi elemento abilitato
            
        Returns:
            SelectorInfo o None
        """
        alternatives = []
        
        for pattern in patterns:
            try:
                elements = self.page.locator(pattern.selector)
                count = await elements.count()
                
                if count == 0:
                    continue
                
                first = elements.first
                is_visible = await first.is_visible()
                is_enabled = await first.is_enabled() if require_enabled else True
                
                # Verifica requisiti
                if require_visible and not is_visible:
                    self._debug(f"  {pattern.selector}: non visibile")
                    alternatives.append(pattern.selector)
                    continue
                
                if require_enabled and not is_enabled:
                    self._debug(f"  {pattern.selector}: disabilitato")
                    alternatives.append(pattern.selector)
                    continue
                
                self._debug(f"  ✓ {pattern.selector}")
                
                return SelectorInfo(
                    selector=pattern.selector,
                    confidence=pattern.confidence,
                    method='auto',
                    description=pattern.description,
                    alternatives=alternatives
                )
                
            except Exception as e:
                self._debug(f"  {pattern.selector}: errore - {e}")
                continue
        
        return None
    
    async def _infer_bot_messages(self) -> Optional[SelectorInfo]:
        """
        Tenta di inferire il selettore messaggi bot dalla struttura.
        
        Cerca elementi che sembrano contenere messaggi.
        """
        # Pattern euristica: cerca div con classi contenenti 'message' o 'response'
        heuristic_patterns = [
            "div[class*='message']",
            "div[class*='response']",
            "p[class*='message']",
        ]
        
        for pattern in heuristic_patterns:
            try:
                elements = self.page.locator(pattern)
                count = await elements.count()
                
                if count >= 1:
                    # Verifica che non siano input dell'utente
                    first = elements.first
                    classes = await first.get_attribute('class') or ''
                    
                    # Skip se sembra un messaggio utente
                    if 'user' in classes.lower() or 'human' in classes.lower():
                        continue
                    
                    return SelectorInfo(
                        selector=pattern,
                        confidence=SelectorConfidence.LOW,
                        method='auto-heuristic',
                        description='Inferito da struttura pagina'
                    )
            except:
                continue
        
        return None
    
    async def get_page_structure(self) -> dict:
        """
        Analizza la struttura della pagina per debugging.
        
        Returns:
            Dict con info struttura
        """
        structure = {
            'forms': 0,
            'textareas': 0,
            'buttons': 0,
            'inputs': 0,
            'contenteditable': 0,
            'common_classes': []
        }
        
        try:
            structure['forms'] = await self.page.locator('form').count()
            structure['textareas'] = await self.page.locator('textarea').count()
            structure['buttons'] = await self.page.locator('button').count()
            structure['inputs'] = await self.page.locator('input').count()
            structure['contenteditable'] = await self.page.locator('[contenteditable="true"]').count()
            
            # Cerca classi comuni chat-related
            for class_pattern in ['chat', 'message', 'thread', 'conversation', 'prompt', 'assistant', 'bot']:
                count = await self.page.locator(f'[class*="{class_pattern}"]').count()
                if count > 0:
                    structure['common_classes'].append((class_pattern, count))
        except:
            pass
        
        return structure


class SmartAutoDetectAdapter(AutoDetectAdapter):
    """
    Versione avanzata con apprendimento adattivo.
    
    Analizza la struttura della pagina e adatta i pattern
    in base al framework rilevato.
    """
    
    # Framework signatures
    FRAMEWORK_SIGNATURES = {
        'langchain': ['.llm__', '[data-langchain]'],
        'openai': ['[data-testid*="openai"]', '.openai-'],
        'dialogflow': ['.df-', '[data-dialogflow]'],
        'rasa': ['.rasa-', '[data-rasa]'],
        'botpress': ['.bp-', '[data-botpress]'],
        'custom': []  # Fallback
    }
    
    async def detect_framework(self) -> str:
        """Rileva il framework chatbot in uso"""
        for framework, signatures in self.FRAMEWORK_SIGNATURES.items():
            for sig in signatures:
                try:
                    count = await self.page.locator(sig).count()
                    if count > 0:
                        self._debug(f"Framework rilevato: {framework}")
                        return framework
                except:
                    continue
        
        return 'custom'
    
    async def detect(self) -> AdapterResult:
        """Override con rilevamento framework-aware"""
        framework = await self.detect_framework()
        
        # TODO: Personalizzare pattern in base al framework
        # Per ora usa il metodo standard
        return await super().detect()
