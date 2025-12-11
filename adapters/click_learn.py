"""
Click Learn Adapter - Apprendimento selettori da click utente

Permette all'utente di cliccare sugli elementi UI per
insegnare al sistema quali selettori usare.
"""

import asyncio
from typing import Optional, Callable
from dataclasses import dataclass

from playwright.async_api import Page

from .base import (
    ChatbotAdapter, AdapterResult, SelectorSet,
    SelectorInfo, SelectorConfidence
)


@dataclass
class ClickResult:
    """Risultato di un click catturato"""
    selector: str
    tag_name: str
    class_name: str
    id_attr: str
    text_content: str
    attributes: dict


class ClickLearnAdapter(ChatbotAdapter):
    """
    Adapter per apprendimento da click utente.
    
    Inietta JavaScript nella pagina per catturare i click
    dell'utente e derivare i selettori CSS corrispondenti.
    
    Usage:
        adapter = ClickLearnAdapter(page)
        
        # Imposta callback per istruzioni
        adapter.on_instruction = lambda msg: print(msg)
        
        result = await adapter.detect()
    """
    
    def __init__(
        self,
        page: Page,
        timeout_seconds: int = 30,
        on_instruction: Optional[Callable[[str], None]] = None
    ):
        """
        Args:
            page: Pagina Playwright
            timeout_seconds: Timeout per ogni click
            on_instruction: Callback per mostrare istruzioni
        """
        super().__init__(page)
        self.timeout_seconds = timeout_seconds
        self.on_instruction = on_instruction or print
    
    async def detect(self) -> AdapterResult:
        """
        Guida l'utente attraverso il processo di click-to-learn.
        
        Returns:
            AdapterResult con selettori appresi
        """
        selector_set = SelectorSet()
        warnings = []
        
        self.on_instruction("\nAPPRENDIMENTO DA CLICK")
        self.on_instruction("Segui le istruzioni per identificare gli elementi del chatbot.\n")

        # 1. Textarea
        self.on_instruction("Step 1/3: Clicca sul CAMPO DI INPUT dove scrivi i messaggi")
        textarea_result = await self._capture_click('textarea')
        if textarea_result:
            selector_set.textarea = await self._create_selector_info(textarea_result)
            self.on_instruction(f"  ✓ Campo input catturato: {selector_set.textarea.selector}\n")
        else:
            warnings.append("Textarea non catturato")
            self.on_instruction("  ! Campo input non catturato\n")

        # 2. Submit button
        self.on_instruction("Step 2/3: Clicca sul BOTTONE INVIO")
        submit_result = await self._capture_click('submit_button')
        if submit_result:
            selector_set.submit_button = await self._create_selector_info(submit_result)
            self.on_instruction(f"  ✓ Bottone invio catturato: {selector_set.submit_button.selector}\n")
        else:
            warnings.append("Submit button non catturato")
            self.on_instruction("  ! Bottone invio non catturato\n")

        # 3. Bot message
        self.on_instruction("Step 3/3: Clicca su un MESSAGGIO DEL BOT (se presente)")
        self.on_instruction("   (Premi ESC o attendi il timeout se non ci sono messaggi)")
        bot_result = await self._capture_click('bot_messages', allow_skip=True)
        if bot_result:
            selector_set.bot_messages = await self._create_selector_info(bot_result)
            self.on_instruction(f"  ✓ Messaggi bot catturati: {selector_set.bot_messages.selector}\n")
        else:
            warnings.append("Bot messages non catturato - potrebbe essere necessario configurarlo manualmente")
            self.on_instruction("  ! Messaggi bot non catturati\n")
        
        success = selector_set.is_complete
        message = "Apprendimento completato!" if success else f"Elementi mancanti: {', '.join(selector_set.missing)}"
        
        return AdapterResult(
            success=success,
            selectors=selector_set,
            message=message,
            warnings=warnings
        )
    
    async def detect_textarea(self) -> Optional[SelectorInfo]:
        """Cattura textarea da click"""
        self.on_instruction("👆 Clicca sul campo di input...")
        result = await self._capture_click('textarea')
        return await self._create_selector_info(result) if result else None
    
    async def detect_submit_button(self) -> Optional[SelectorInfo]:
        """Cattura submit button da click"""
        self.on_instruction("👆 Clicca sul bottone invio...")
        result = await self._capture_click('submit_button')
        return await self._create_selector_info(result) if result else None
    
    async def detect_bot_messages(self) -> Optional[SelectorInfo]:
        """Cattura bot messages da click"""
        self.on_instruction("👆 Clicca su un messaggio del bot...")
        result = await self._capture_click('bot_messages', allow_skip=True)
        return await self._create_selector_info(result) if result else None
    
    async def _capture_click(
        self,
        element_name: str,
        allow_skip: bool = False
    ) -> Optional[ClickResult]:
        """
        Cattura un click dell'utente.
        
        Args:
            element_name: Nome elemento per logging
            allow_skip: Permetti ESC per saltare
            
        Returns:
            ClickResult o None
        """
        # Inietta script di cattura
        capture_script = """
        () => {
            return new Promise((resolve) => {
                let resolved = false;
                
                const handler = (e) => {
                    if (resolved) return;
                    
                    // Previeni comportamento default
                    e.preventDefault();
                    e.stopPropagation();
                    
                    const el = e.target;
                    
                    // Raccogli informazioni elemento
                    const result = {
                        tag_name: el.tagName.toLowerCase(),
                        class_name: el.className || '',
                        id_attr: el.id || '',
                        text_content: (el.textContent || '').substring(0, 100).trim(),
                        attributes: {}
                    };
                    
                    // Raccogli attributi utili
                    ['type', 'name', 'placeholder', 'aria-label', 'data-testid', 
                     'role', 'contenteditable', 'data-role'].forEach(attr => {
                        const val = el.getAttribute(attr);
                        if (val) result.attributes[attr] = val;
                    });
                    
                    // Costruisci selettore ottimale
                    let selector = '';
                    
                    // Priorità: ID
                    if (el.id) {
                        selector = '#' + CSS.escape(el.id);
                    }
                    // data-testid
                    else if (el.getAttribute('data-testid')) {
                        selector = `[data-testid="${el.getAttribute('data-testid')}"]`;
                    }
                    // aria-label
                    else if (el.getAttribute('aria-label')) {
                        selector = `${el.tagName.toLowerCase()}[aria-label="${el.getAttribute('aria-label')}"]`;
                    }
                    // Classi significative
                    else if (el.className && typeof el.className === 'string') {
                        const classes = el.className.split(' ')
                            .filter(c => c && c.length > 2 && !c.match(/^(ng-|_|css-)/));
                        if (classes.length > 0) {
                            selector = '.' + classes.slice(0, 2).map(c => CSS.escape(c)).join('.');
                        }
                    }
                    
                    // Fallback: tag + attributi
                    if (!selector) {
                        selector = el.tagName.toLowerCase();
                        if (el.getAttribute('type')) {
                            selector += `[type="${el.getAttribute('type')}"]`;
                        }
                        if (el.getAttribute('placeholder')) {
                            const ph = el.getAttribute('placeholder').substring(0, 30);
                            selector += `[placeholder*="${ph}"]`;
                        }
                    }
                    
                    result.selector = selector;
                    
                    // Cleanup e resolve
                    document.removeEventListener('click', handler, true);
                    document.removeEventListener('keydown', escHandler, true);
                    resolved = true;
                    resolve(result);
                };
                
                const escHandler = (e) => {
                    if (e.key === 'Escape' && !resolved) {
                        document.removeEventListener('click', handler, true);
                        document.removeEventListener('keydown', escHandler, true);
                        resolved = true;
                        resolve(null);
                    }
                };
                
                document.addEventListener('click', handler, true);
                document.addEventListener('keydown', escHandler, true);
                
                // Timeout
                setTimeout(() => {
                    if (!resolved) {
                        document.removeEventListener('click', handler, true);
                        document.removeEventListener('keydown', escHandler, true);
                        resolved = true;
                        resolve(null);
                    }
                }, """ + str(self.timeout_seconds * 1000) + """);
            });
        }
        """
        
        try:
            result = await self.page.evaluate(capture_script)
            
            if result:
                return ClickResult(
                    selector=result['selector'],
                    tag_name=result['tag_name'],
                    class_name=result['class_name'],
                    id_attr=result['id_attr'],
                    text_content=result['text_content'],
                    attributes=result['attributes']
                )
            
            return None
            
        except asyncio.TimeoutError:
            self._debug(f"Timeout cattura {element_name}")
            return None
        except Exception as e:
            self._debug(f"Errore cattura {element_name}: {e}")
            return None
    
    async def _create_selector_info(self, click_result: ClickResult) -> Optional[SelectorInfo]:
        """Crea SelectorInfo da ClickResult con validazione"""
        if not click_result or not click_result.selector:
            return None
        
        # Valida che il selettore funzioni
        is_valid = await self.validate_selector(click_result.selector)
        
        if not is_valid:
            # Prova selettori alternativi
            alternatives = self._generate_alternatives(click_result)
            for alt in alternatives:
                if await self.validate_selector(alt):
                    return SelectorInfo(
                        selector=alt,
                        confidence=SelectorConfidence.MEDIUM,
                        method='click-alternative',
                        description=f'Alternativa per {click_result.tag_name}',
                        alternatives=[click_result.selector]
                    )
            
            # Usa comunque il selettore originale con bassa confidenza
            return SelectorInfo(
                selector=click_result.selector,
                confidence=SelectorConfidence.LOW,
                method='click-unvalidated',
                description=f'Da click su {click_result.tag_name} (non validato)'
            )
        
        return SelectorInfo(
            selector=click_result.selector,
            confidence=SelectorConfidence.HIGH,
            method='click',
            description=f'Da click su {click_result.tag_name}',
            alternatives=self._generate_alternatives(click_result)
        )
    
    def _generate_alternatives(self, click_result: ClickResult) -> list[str]:
        """Genera selettori alternativi dal click result"""
        alternatives = []
        
        # Alternativa basata su tag + classe
        if click_result.class_name:
            classes = click_result.class_name.split()
            if classes:
                alternatives.append(f"{click_result.tag_name}.{classes[0]}")
        
        # Alternativa basata su attributi
        for attr, value in click_result.attributes.items():
            if attr in ['data-testid', 'aria-label', 'role']:
                alternatives.append(f'[{attr}="{value}"]')
        
        # Alternativa solo tag
        alternatives.append(click_result.tag_name)
        
        return alternatives[:5]  # Max 5 alternative


class InteractiveClickLearnAdapter(ClickLearnAdapter):
    """
    Versione interattiva con highlight visivo.
    
    Evidenzia gli elementi al passaggio del mouse per
    aiutare l'utente a selezionare quelli corretti.
    """
    
    async def inject_highlight_style(self) -> None:
        """Inietta stile CSS per highlight"""
        style = """
        .chatbot-tester-highlight {
            outline: 3px solid #3b82f6 !important;
            outline-offset: 2px !important;
            background-color: rgba(59, 130, 246, 0.1) !important;
            cursor: pointer !important;
        }
        .chatbot-tester-selected {
            outline: 3px solid #22c55e !important;
            outline-offset: 2px !important;
            background-color: rgba(34, 197, 94, 0.1) !important;
        }
        """
        await self.page.add_style_tag(content=style)
    
    async def inject_highlight_script(self) -> None:
        """Inietta script per highlight al hover"""
        script = """
        let lastHighlighted = null;
        
        document.addEventListener('mouseover', (e) => {
            if (lastHighlighted) {
                lastHighlighted.classList.remove('chatbot-tester-highlight');
            }
            e.target.classList.add('chatbot-tester-highlight');
            lastHighlighted = e.target;
        });
        
        document.addEventListener('mouseout', (e) => {
            e.target.classList.remove('chatbot-tester-highlight');
        });
        """
        await self.page.evaluate(script)
    
    async def detect(self) -> AdapterResult:
        """Override con highlight visivo"""
        await self.inject_highlight_style()
        await self.inject_highlight_script()
        
        return await super().detect()
    
    async def cleanup(self) -> None:
        """Rimuove stili e script iniettati"""
        cleanup_script = """
        document.querySelectorAll('.chatbot-tester-highlight, .chatbot-tester-selected')
            .forEach(el => {
                el.classList.remove('chatbot-tester-highlight', 'chatbot-tester-selected');
            });
        """
        await self.page.evaluate(cleanup_script)
