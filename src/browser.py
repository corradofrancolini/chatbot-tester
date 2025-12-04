"""
Browser Manager - Wrapper Playwright per automazione chatbot

Gestisce:
- Sessione browser persistente
- Login e autenticazione
- Screenshot e cattura elementi
- Iniezione CSS per screenshot puliti
"""

import asyncio
from pathlib import Path
from typing import Optional, Callable, Any
from dataclasses import dataclass
from datetime import datetime

from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Locator


@dataclass
class BrowserSettings:
    """Impostazioni browser"""
    headless: bool = False
    viewport_width: int = 1280
    viewport_height: int = 720
    device_scale_factor: int = 2
    user_data_dir: Optional[Path] = None
    timeout_page_load: int = 30000
    timeout_bot_response: int = 60000


@dataclass
class ChatbotSelectors:
    """Selettori CSS del chatbot"""
    textarea: str
    submit_button: str
    bot_messages: str
    thread_container: str = ""
    loading_indicator: str = ""


class BrowserManager:
    """
    Manager per browser Playwright con sessione persistente.
    
    Features:
    - Sessione browser salvata per mantenere login
    - Screenshot automatici
    - Iniezione CSS per screenshot puliti
    - Gestione timeout intelligente
    
    Usage:
        async with BrowserManager(settings) as browser:
            await browser.navigate("https://chat.example.com")
            await browser.send_message("Ciao!")
            response = await browser.wait_for_response()
    """
    
    def __init__(self, settings: BrowserSettings, selectors: Optional[ChatbotSelectors] = None):
        """
        Inizializza il browser manager.
        
        Args:
            settings: Configurazione browser
            selectors: Selettori CSS del chatbot (opzionali, possono essere impostati dopo)
        """
        self.settings = settings
        self.selectors = selectors
        
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        
        # Stato
        self._is_initialized = False
        self._current_url: str = ""
        self._last_message_count: int = 0
    
    async def __aenter__(self):
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()
    
    async def start(self) -> None:
        """Avvia il browser con sessione persistente"""
        self._playwright = await async_playwright().start()
        
        # Usa sessione persistente se user_data_dir è specificato
        if self.settings.user_data_dir:
            self.settings.user_data_dir.mkdir(parents=True, exist_ok=True)
            
            self._context = await self._playwright.chromium.launch_persistent_context(
                user_data_dir=str(self.settings.user_data_dir),
                headless=self.settings.headless,
                viewport={
                    'width': self.settings.viewport_width,
                    'height': self.settings.viewport_height
                },
                device_scale_factor=self.settings.device_scale_factor,
                accept_downloads=True
            )
            self._page = self._context.pages[0] if self._context.pages else await self._context.new_page()
        else:
            # Browser non persistente
            self._browser = await self._playwright.chromium.launch(
                headless=self.settings.headless
            )
            self._context = await self._browser.new_context(
                viewport={
                    'width': self.settings.viewport_width,
                    'height': self.settings.viewport_height
                },
                device_scale_factor=self.settings.device_scale_factor
            )
            self._page = await self._context.new_page()
        
        # Timeout di default
        self._page.set_default_timeout(self.settings.timeout_page_load)
        self._is_initialized = True
    
    async def stop(self) -> None:
        """Chiude il browser salvando la sessione"""
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        
        self._is_initialized = False
    
    @property
    def page(self) -> Page:
        """Accesso diretto alla pagina Playwright"""
        if not self._page:
            raise RuntimeError("Browser non inizializzato. Chiama start() prima.")
        return self._page
    
    @property
    def is_ready(self) -> bool:
        """Verifica se il browser è pronto"""
        return self._is_initialized and self._page is not None
    
    async def navigate(self, url: str, wait_for_selector: Optional[str] = None) -> bool:
        """
        Naviga a un URL.
        
        Args:
            url: URL destinazione
            wait_for_selector: Selettore opzionale da attendere dopo il caricamento
            
        Returns:
            True se navigazione riuscita
        """
        try:
            await self._page.goto(url, wait_until='networkidle')
            self._current_url = url
            
            if wait_for_selector:
                await self._page.wait_for_selector(wait_for_selector, timeout=self.settings.timeout_page_load)
            
            # Reset contatore messaggi dopo navigazione
            await asyncio.sleep(0.5)  # Attendi che la pagina sia stabile
            if self.selectors:
                self._last_message_count = await self._count_bot_messages()
            
            return True
        except Exception as e:
            print(f"Errore navigazione a {url}: {e}")
            return False
    
    async def wait_for_login(self, 
                              check_selector: str,
                              timeout_minutes: int = 5,
                              message: str = "Effettua il login nel browser...") -> bool:
        """
        Attende che l'utente effettui il login manualmente.
        
        Args:
            check_selector: Selettore che indica login completato (es. textarea chat)
            timeout_minutes: Timeout in minuti
            message: Messaggio da mostrare
            
        Returns:
            True se login riuscito
        """
        print(f"\n⏳ {message}")
        print(f"   Hai {timeout_minutes} minuti per completare il login.")
        
        try:
            await self._page.wait_for_selector(
                check_selector,
                timeout=timeout_minutes * 60 * 1000,
                state='visible'
            )
            print("✅ Login completato!")
            return True
        except Exception:
            print("❌ Timeout login scaduto")
            return False
    
    async def send_message(self, message: str) -> bool:
        """
        Invia un messaggio al chatbot.
        
        Args:
            message: Testo del messaggio
            
        Returns:
            True se invio riuscito
        """
        if not self.selectors:
            raise ValueError("Selettori non configurati")
        
        try:
            # Conta messaggi bot attuali prima di inviare
            self._last_message_count = await self._count_bot_messages()
            
            # Trova e compila textarea
            textarea = self._page.locator(self.selectors.textarea)
            await textarea.wait_for(state='visible', timeout=10000)
            await textarea.fill(message)
            
            # Piccola pausa per sicurezza
            await asyncio.sleep(0.3)
            
            # Clicca submit
            submit = self._page.locator(self.selectors.submit_button)
            await submit.click()
            
            return True
        except Exception as e:
            print(f"Errore invio messaggio: {e}")
            return False
    
    async def wait_for_response(self, timeout_ms: Optional[int] = None) -> Optional[str]:
        """
        Attende la risposta del chatbot.

        Args:
            timeout_ms: Timeout in millisecondi (default: bot_response timeout)

        Returns:
            Testo della risposta o None se timeout
        """
        if not self.selectors:
            raise ValueError("Selettori non configurati")

        timeout = timeout_ms or self.settings.timeout_bot_response

        try:
            start_time = asyncio.get_event_loop().time()
            initial_count = self._last_message_count
            check_interval = 0.2

            print(f"  [DEBUG] wait_for_response: initial_count={initial_count}, timeout={timeout}ms")

            # Breve pausa iniziale per dare tempo al DOM di aggiornarsi
            await asyncio.sleep(0.1)

            loop_count = 0
            while (asyncio.get_event_loop().time() - start_time) * 1000 < timeout:
                loop_count += 1
                
                # Se c'è un loading indicator, aspetta che scompaia
                if self.selectors.loading_indicator:
                    loading = self._page.locator(self.selectors.loading_indicator)
                    if await loading.count() > 0:
                        try:
                            if await loading.first.is_visible():
                                if loop_count <= 3:
                                    print(f"  [DEBUG] Loading indicator visibile, aspetto...")
                                await asyncio.sleep(check_interval)
                                continue
                        except:
                            pass

                current_count = await self._count_bot_messages()
                
                if loop_count <= 5 or loop_count % 10 == 0:
                    print(f"  [DEBUG] loop {loop_count}: current_count={current_count}, initial_count={initial_count}")

                # Nuovo messaggio apparso rispetto a quando abbiamo inviato
                if current_count > initial_count:
                    print(f"  [DEBUG] Nuovo messaggio rilevato! ({current_count} > {initial_count})")
                    
                    # Attendi che il messaggio sia completo (testo stabile)
                    await self._wait_for_message_complete()

                    # Aggiorna il conteggio per prossimi messaggi
                    self._last_message_count = current_count

                    # Ottieni testo ultimo messaggio (escludendo feedback form)
                    messages = self._page.locator(self.selectors.bot_messages)
                    last_message = messages.last

                    # Prova a estrarre solo il contenuto (.llm__inner), escludendo feedback
                    inner_content = last_message.locator(".llm__inner")
                    if await inner_content.count() > 0:
                        texts = []
                        for i in range(await inner_content.count()):
                            t = await inner_content.nth(i).text_content()
                            if t:
                                texts.append(t.strip())
                        text = "\n".join(texts)
                    else:
                        text = await last_message.text_content()

                    print(f"  [DEBUG] Risposta catturata: {text[:50] if text else 'vuoto'}...")
                    return text.strip() if text else None

                await asyncio.sleep(check_interval)

            print(f"⚠️ Timeout attesa risposta bot (loop_count={loop_count})")
            return None

        except Exception as e:
            print(f"Errore attesa risposta: {e}")
            return None
    
    async def _count_bot_messages(self) -> int:
        """Conta i messaggi bot attualmente visibili"""
        try:
            messages = self._page.locator(self.selectors.bot_messages)
            return await messages.count()
        except:
            return 0
    
    async def _wait_for_message_complete(self, stability_ms: int = 1000) -> None:
        """
        Attende che il messaggio sia completo (testo stabile).
        
        Args:
            stability_ms: Millisecondi di stabilità richiesti
        """
        last_text = ""
        stable_since = None
        
        while True:
            try:
                messages = self._page.locator(self.selectors.bot_messages)
                current_text = await messages.last.text_content() or ""
                
                if current_text == last_text:
                    if stable_since is None:
                        stable_since = asyncio.get_event_loop().time()
                    elif (asyncio.get_event_loop().time() - stable_since) * 1000 >= stability_ms:
                        break
                else:
                    last_text = current_text
                    stable_since = None
                
                await asyncio.sleep(0.2)
            except:
                break
    
    async def get_conversation(self) -> list[dict]:
        """
        Ottiene l'intera conversazione visibile.
        
        Returns:
            Lista di messaggi con role e content
        """
        # Questo è un placeholder - l'implementazione reale dipende dalla struttura del chatbot
        conversation = []
        
        try:
            # Cerca tutti i messaggi nel thread
            if self.selectors.thread_container:
                container = self._page.locator(self.selectors.thread_container)
                # L'implementazione specifica dipende dalla struttura HTML
            
            # Almeno ottieni i messaggi bot
            bot_messages = self._page.locator(self.selectors.bot_messages)
            count = await bot_messages.count()
            
            for i in range(count):
                text = await bot_messages.nth(i).text_content()
                conversation.append({
                    "role": "assistant",
                    "content": text.strip() if text else ""
                })
        except:
            pass
        
        return conversation
    
    async def take_screenshot(self, 
                               path: Path,
                               full_page: bool = False,
                               inject_css: Optional[str] = None) -> bool:
        """
        Cattura screenshot.
        
        Args:
            path: Path dove salvare lo screenshot
            full_page: Se True, cattura l'intera pagina
            inject_css: CSS da iniettare prima dello screenshot
            
        Returns:
            True se screenshot riuscito
        """
        try:
            # Inietta CSS se specificato
            if inject_css:
                await self._page.add_style_tag(content=inject_css)
                await asyncio.sleep(0.3)  # Attendi rendering
            
            await self._page.screenshot(path=str(path), full_page=full_page)
            return True
        except Exception as e:
            print(f"Errore screenshot: {e}")
            return False
    
    async def take_element_screenshot(self, 
                                       selector: str,
                                       path: Path,
                                       inject_css: Optional[str] = None) -> bool:
        """
        Cattura screenshot di un elemento specifico.
        
        Args:
            selector: Selettore CSS dell'elemento
            path: Path dove salvare
            inject_css: CSS da iniettare prima
            
        Returns:
            True se riuscito
        """
        try:
            if inject_css:
                await self._page.add_style_tag(content=inject_css)
                await asyncio.sleep(0.3)
            
            element = self._page.locator(selector)
            await element.screenshot(path=str(path))
            return True
        except Exception as e:
            print(f"Errore screenshot elemento: {e}")
            return False
    
    async def execute_script(self, script: str) -> Any:
        """
        Esegue JavaScript nella pagina.
        
        Args:
            script: Codice JavaScript
            
        Returns:
            Risultato dell'esecuzione
        """
        return await self._page.evaluate(script)
    
    async def is_element_visible(self, selector: str, timeout_ms: int = 5000) -> bool:
        """
        Verifica se un elemento è visibile.
        
        Args:
            selector: Selettore CSS
            timeout_ms: Timeout in millisecondi
            
        Returns:
            True se elemento visibile
        """
        try:
            await self._page.wait_for_selector(selector, state='visible', timeout=timeout_ms)
            return True
        except:
            return False
    
    async def click_element(self, selector: str) -> bool:
        """
        Clicca un elemento.
        
        Args:
            selector: Selettore CSS
            
        Returns:
            True se click riuscito
        """
        try:
            element = self._page.locator(selector)
            await element.click()
            return True
        except Exception as e:
            print(f"Errore click su {selector}: {e}")
            return False
    
    async def get_element_text(self, selector: str) -> Optional[str]:
        """
        Ottiene il testo di un elemento.
        
        Args:
            selector: Selettore CSS
            
        Returns:
            Testo dell'elemento o None
        """
        try:
            element = self._page.locator(selector)
            text = await element.text_content()
            return text.strip() if text else None
        except:
            return None
    
    async def new_chat(self, new_chat_selector: str) -> bool:
        """
        Avvia una nuova chat (clicca bottone new chat).
        
        Args:
            new_chat_selector: Selettore del bottone nuova chat
            
        Returns:
            True se riuscito
        """
        try:
            # Clicca new chat
            await self.click_element(new_chat_selector)
            await asyncio.sleep(1)
            
            # Attendi che textarea sia pronta
            if self.selectors:
                await self._page.wait_for_selector(
                    self.selectors.textarea,
                    state='visible',
                    timeout=10000
                )
            
            # Reset contatore messaggi
            self._last_message_count = 0
            
            return True
        except Exception as e:
            print(f"Errore nuova chat: {e}")
            return False


class SelectorDetector:
    """
    Rileva automaticamente i selettori CSS del chatbot.
    
    Usa euristiche per identificare:
    - Campo input (textarea)
    - Bottone invio
    - Messaggi del bot
    - Container thread
    """
    
    # Pattern comuni per textarea
    TEXTAREA_PATTERNS = [
        "#llm-prompt-textarea",
        "[data-testid='chat-input']",
        "textarea[placeholder*='message' i]",
        "textarea[placeholder*='type' i]",
        "textarea[placeholder*='ask' i]",
        "textarea[placeholder*='scrivi' i]",
        "textarea[placeholder*='digita' i]",
        ".chat-input textarea",
        "textarea.prompt",
        "form textarea",
        "[contenteditable='true']",
    ]
    
    # Pattern comuni per submit button
    SUBMIT_PATTERNS = [
        "button.llm__prompt-submit",
        "button[type='submit']",
        "button[aria-label*='send' i]",
        "button[aria-label*='invia' i]",
        "button:has(svg[class*='send'])",
        ".send-button",
        "button.submit",
        "form button:last-child",
    ]
    
    # Pattern comuni per messaggi bot
    BOT_MESSAGE_PATTERNS = [
        ".llm__message--assistant .llm__text-body",
        "[data-role='assistant']",
        ".message.assistant",
        ".message.bot",
        ".bot-message",
        ".ai-response",
        "[class*='assistant']",
        "[class*='bot-response']",
    ]
    
    def __init__(self, page: Page):
        self.page = page
    
    async def detect_all(self) -> ChatbotSelectors:
        """
        Rileva tutti i selettori necessari.
        
        Returns:
            ChatbotSelectors con i selettori trovati
        """
        textarea = await self._detect_selector(self.TEXTAREA_PATTERNS, "textarea")
        submit = await self._detect_selector(self.SUBMIT_PATTERNS, "submit button")
        bot_messages = await self._detect_selector(self.BOT_MESSAGE_PATTERNS, "bot messages")
        
        return ChatbotSelectors(
            textarea=textarea or "",
            submit_button=submit or "",
            bot_messages=bot_messages or "",
            thread_container=""
        )
    
    async def _detect_selector(self, patterns: list[str], name: str) -> Optional[str]:
        """Prova ogni pattern fino a trovarne uno funzionante"""
        for pattern in patterns:
            try:
                element = self.page.locator(pattern)
                if await element.count() > 0:
                    is_visible = await element.first.is_visible()
                    if is_visible:
                        print(f"✅ Trovato {name}: {pattern}")
                        return pattern
            except:
                continue
        
        print(f"⚠️ Non trovato {name}")
        return None
    
    async def learn_from_click(self, element_name: str, timeout_seconds: int = 30) -> Optional[str]:
        """
        Impara un selettore dal click dell'utente.
        
        Args:
            element_name: Nome dell'elemento (per messaggio)
            timeout_seconds: Timeout in secondi
            
        Returns:
            Selettore CSS dell'elemento cliccato
        """
        print(f"\n👆 Clicca su: {element_name}")
        print(f"   Hai {timeout_seconds} secondi...")
        
        # Inietta listener per click
        selector_result = await self.page.evaluate("""
            () => {
                return new Promise((resolve) => {
                    const handler = (e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        
                        const el = e.target;
                        let selector = '';
                        
                        // Prova ID
                        if (el.id) {
                            selector = '#' + el.id;
                        }
                        // Prova classe univoca
                        else if (el.className && typeof el.className === 'string') {
                            const classes = el.className.split(' ').filter(c => c);
                            if (classes.length > 0) {
                                selector = '.' + classes.join('.');
                            }
                        }
                        // Fallback: path generico
                        if (!selector) {
                            selector = el.tagName.toLowerCase();
                        }
                        
                        document.removeEventListener('click', handler, true);
                        resolve(selector);
                    };
                    
                    document.addEventListener('click', handler, true);
                    
                    setTimeout(() => {
                        document.removeEventListener('click', handler, true);
                        resolve(null);
                    }, """ + str(timeout_seconds * 1000) + """);
                });
            }
        """)
        
        if selector_result:
            print(f"✅ Selettore catturato: {selector_result}")
        else:
            print("❌ Timeout - nessun click rilevato")
        
        return selector_result
