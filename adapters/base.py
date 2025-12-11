"""
Base Adapter - Classe base per rilevamento selettori CSS

Definisce l'interfaccia comune per tutti gli adapter
di rilevamento selettori.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from enum import Enum

from playwright.async_api import Page


class SelectorConfidence(Enum):
    """Livello di confidenza nel selettore rilevato"""
    HIGH = "high"       # Selettore univoco e stabile
    MEDIUM = "medium"   # Selettore funzionante ma potenzialmente fragile
    LOW = "low"         # Selettore generico, potrebbe non funzionare
    MANUAL = "manual"   # Inserito manualmente dall'utente


@dataclass
class SelectorInfo:
    """Informazioni su un singolo selettore"""
    selector: str
    confidence: SelectorConfidence
    method: str  # 'auto', 'click', 'manual'
    description: str = ""
    alternatives: List[str] = field(default_factory=list)


@dataclass
class SelectorSet:
    """Set completo di selettori per un chatbot"""
    textarea: Optional[SelectorInfo] = None
    submit_button: Optional[SelectorInfo] = None
    bot_messages: Optional[SelectorInfo] = None
    thread_container: Optional[SelectorInfo] = None
    user_messages: Optional[SelectorInfo] = None
    new_chat_button: Optional[SelectorInfo] = None
    
    @property
    def is_complete(self) -> bool:
        """Verifica se tutti i selettori essenziali sono presenti"""
        return all([
            self.textarea and self.textarea.selector,
            self.submit_button and self.submit_button.selector,
            self.bot_messages and self.bot_messages.selector
        ])
    
    @property
    def missing(self) -> List[str]:
        """Lista selettori mancanti"""
        missing = []
        if not self.textarea or not self.textarea.selector:
            missing.append('textarea')
        if not self.submit_button or not self.submit_button.selector:
            missing.append('submit_button')
        if not self.bot_messages or not self.bot_messages.selector:
            missing.append('bot_messages')
        return missing
    
    def to_dict(self) -> Dict[str, str]:
        """Converte in dizionario semplice selector-string"""
        return {
            'textarea': self.textarea.selector if self.textarea else '',
            'submit_button': self.submit_button.selector if self.submit_button else '',
            'bot_messages': self.bot_messages.selector if self.bot_messages else '',
            'thread_container': self.thread_container.selector if self.thread_container else '',
        }
    
    def to_detailed_dict(self) -> Dict[str, Dict[str, Any]]:
        """Converte in dizionario con tutti i dettagli"""
        result = {}
        for name, info in [
            ('textarea', self.textarea),
            ('submit_button', self.submit_button),
            ('bot_messages', self.bot_messages),
            ('thread_container', self.thread_container),
        ]:
            if info:
                result[name] = {
                    'selector': info.selector,
                    'confidence': info.confidence.value,
                    'method': info.method,
                    'alternatives': info.alternatives
                }
        return result


@dataclass
class AdapterResult:
    """Risultato dell'operazione di rilevamento"""
    success: bool
    selectors: SelectorSet
    message: str = ""
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


class ChatbotAdapter(ABC):
    """
    Classe base astratta per adapter di rilevamento selettori.
    
    Gli adapter implementano diverse strategie per identificare
    gli elementi UI di un chatbot:
    - AutoDetectAdapter: euristiche basate su pattern comuni
    - ClickLearnAdapter: apprendimento da click utente
    - ManualAdapter: input manuale (fallback)
    
    Usage:
        adapter = AutoDetectAdapter(page)
        result = await adapter.detect()
        
        if result.success:
            selectors = result.selectors
    """
    
    def __init__(self, page: Page):
        """
        Inizializza l'adapter.
        
        Args:
            page: Pagina Playwright attiva
        """
        self.page = page
        self._debug_mode = False
    
    @abstractmethod
    async def detect(self) -> AdapterResult:
        """
        Rileva i selettori del chatbot.
        
        Returns:
            AdapterResult con selettori trovati
        """
        pass
    
    @abstractmethod
    async def detect_textarea(self) -> Optional[SelectorInfo]:
        """Rileva il campo di input"""
        pass
    
    @abstractmethod
    async def detect_submit_button(self) -> Optional[SelectorInfo]:
        """Rileva il bottone invio"""
        pass
    
    @abstractmethod
    async def detect_bot_messages(self) -> Optional[SelectorInfo]:
        """Rileva il selettore messaggi bot"""
        pass
    
    async def detect_thread_container(self) -> Optional[SelectorInfo]:
        """
        Rileva il container del thread (opzionale).
        Default implementation cerca pattern comuni.
        """
        return None
    
    async def validate_selector(self, selector: str, min_count: int = 0) -> bool:
        """
        Valida che un selettore funzioni.
        
        Args:
            selector: Selettore CSS da validare
            min_count: Numero minimo elementi attesi (0 = almeno 1)
            
        Returns:
            True se selettore valido
        """
        try:
            elements = self.page.locator(selector)
            count = await elements.count()
            
            if min_count > 0:
                return count >= min_count
            return count > 0
        except:
            return False
    
    async def test_selector(self, selector: str, action: str = 'visibility') -> Dict[str, Any]:
        """
        Test completo di un selettore.
        
        Args:
            selector: Selettore CSS
            action: 'visibility', 'clickable', 'fillable'
            
        Returns:
            Dict con risultati test
        """
        result = {
            'valid': False,
            'count': 0,
            'visible': False,
            'enabled': False,
            'error': None
        }
        
        try:
            elements = self.page.locator(selector)
            result['count'] = await elements.count()
            
            if result['count'] > 0:
                first = elements.first
                result['visible'] = await first.is_visible()
                result['enabled'] = await first.is_enabled()
                result['valid'] = result['visible'] if action == 'visibility' else result['enabled']
        except Exception as e:
            result['error'] = str(e)
        
        return result
    
    def enable_debug(self) -> None:
        """Abilita output debug"""
        self._debug_mode = True
    
    def _debug(self, message: str) -> None:
        """Stampa messaggio debug se abilitato"""
        if self._debug_mode:
            print(f"[DEBUG] {message}")


class ManualAdapter(ChatbotAdapter):
    """
    Adapter per input manuale dei selettori.
    
    Usato come fallback quando gli altri metodi falliscono.
    """
    
    def __init__(self, page: Page, selectors: Dict[str, str]):
        """
        Args:
            page: Pagina Playwright
            selectors: Dict con selettori manuali
        """
        super().__init__(page)
        self._manual_selectors = selectors
    
    async def detect(self) -> AdapterResult:
        """Usa i selettori manuali forniti"""
        selector_set = SelectorSet()
        warnings = []
        
        # Textarea
        if 'textarea' in self._manual_selectors:
            selector_set.textarea = await self._create_manual_info(
                self._manual_selectors['textarea'],
                'textarea'
            )
            if not selector_set.textarea:
                warnings.append('Selettore textarea non valido')
        
        # Submit button
        if 'submit_button' in self._manual_selectors:
            selector_set.submit_button = await self._create_manual_info(
                self._manual_selectors['submit_button'],
                'submit_button'
            )
            if not selector_set.submit_button:
                warnings.append('Selettore submit_button non valido')
        
        # Bot messages
        if 'bot_messages' in self._manual_selectors:
            selector_set.bot_messages = await self._create_manual_info(
                self._manual_selectors['bot_messages'],
                'bot_messages'
            )
            if not selector_set.bot_messages:
                warnings.append('Selettore bot_messages non valido')
        
        # Thread container
        if 'thread_container' in self._manual_selectors:
            selector_set.thread_container = await self._create_manual_info(
                self._manual_selectors['thread_container'],
                'thread_container'
            )
        
        return AdapterResult(
            success=selector_set.is_complete,
            selectors=selector_set,
            message='Selettori manuali configurati' if selector_set.is_complete else 'Selettori incompleti',
            warnings=warnings
        )
    
    async def _create_manual_info(self, selector: str, name: str) -> Optional[SelectorInfo]:
        """Crea SelectorInfo per selettore manuale con validazione"""
        if not selector:
            return None
        
        is_valid = await self.validate_selector(selector)
        
        if is_valid:
            return SelectorInfo(
                selector=selector,
                confidence=SelectorConfidence.MANUAL,
                method='manual',
                description=f'Selettore {name} inserito manualmente'
            )
        return None
    
    async def detect_textarea(self) -> Optional[SelectorInfo]:
        return None
    
    async def detect_submit_button(self) -> Optional[SelectorInfo]:
        return None
    
    async def detect_bot_messages(self) -> Optional[SelectorInfo]:
        return None
