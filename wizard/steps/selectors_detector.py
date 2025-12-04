"""
Selector Detector - Rilevamento automatico selettori chatbot

Questo modulo fornisce:
- Auto-detect di selettori comuni
- Test interattivo con domande multiple
- Monitoraggio DOM per rilevare loading e messaggi
- Click-to-learn come fallback manuale
- Persistenza pattern appresi
"""

import asyncio
import json
from pathlib import Path
from typing import Optional, List, Dict, Any, Set
from dataclasses import dataclass, field
from datetime import datetime

from playwright.async_api import async_playwright, Page, Browser, BrowserContext


@dataclass
class DetectionResult:
    """Risultato del rilevamento selettori"""
    textarea: str = ""
    submit_button: str = ""
    bot_messages: str = ""
    loading_indicator: str = ""
    thread_container: str = ""
    content_inner: str = ""  # Selettore per contenuto interno (esclude feedback)

    # Metadata
    test_questions: List[str] = field(default_factory=list)
    detected_classes: Set[str] = field(default_factory=set)
    confidence: float = 0.0  # 0-1

    def is_complete(self) -> bool:
        """Verifica se tutti i selettori obbligatori sono stati rilevati"""
        return bool(self.textarea and self.submit_button and self.bot_messages)

    def to_dict(self) -> dict:
        """Converte in dizionario per YAML"""
        return {
            'textarea': self.textarea,
            'submit_button': self.submit_button,
            'bot_messages': self.bot_messages,
            'loading_indicator': self.loading_indicator,
            'thread_container': self.thread_container,
            'content_inner': self.content_inner,
        }


class PatternStore:
    """
    Persistenza pattern appresi per migliorare auto-detect futuri.
    Salva pattern che hanno funzionato su chatbot diversi.
    """

    DEFAULT_PATH = Path(__file__).parent.parent.parent / "config" / "learned_patterns.json"

    def __init__(self, path: Optional[Path] = None):
        self.path = path or self.DEFAULT_PATH
        self.patterns: Dict[str, List[str]] = self._load()

    def _load(self) -> Dict[str, List[str]]:
        """Carica pattern salvati"""
        if self.path.exists():
            try:
                with open(self.path) as f:
                    return json.load(f)
            except:
                pass
        return {
            'textarea': [],
            'submit_button': [],
            'bot_messages': [],
            'loading_indicator': [],
            'thread_container': [],
            'content_inner': [],
        }

    def save(self) -> None:
        """Salva pattern"""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, 'w') as f:
            json.dump(self.patterns, f, indent=2)

    def add_pattern(self, category: str, selector: str) -> None:
        """Aggiunge un pattern appreso"""
        if category not in self.patterns:
            self.patterns[category] = []
        if selector and selector not in self.patterns[category]:
            self.patterns[category].insert(0, selector)  # Priorità ai più recenti
            self.save()

    def get_patterns(self, category: str) -> List[str]:
        """Ottiene pattern per categoria (appresi + default)"""
        return self.patterns.get(category, [])


class InteractiveDetector:
    """
    Rileva selettori chatbot in modo interattivo.

    Fasi:
    1. auto_detect() - Prova pattern comuni
    2. test_question() - Invia domanda e monitora DOM
    3. learn_from_click() - Fallback: utente clicca elemento
    """

    # Pattern comuni (espandibili via PatternStore)
    DEFAULT_PATTERNS = {
        'textarea': [
            "#llm-prompt-textarea",
            "textarea[placeholder*='message' i]",
            "textarea[placeholder*='scrivi' i]",
            "textarea[placeholder*='chiedi' i]",
            "textarea[placeholder*='type' i]",
            "textarea[placeholder*='ask' i]",
            "[contenteditable='true']",
            ".chat-input textarea",
            "#chat-input",
            "textarea.prompt",
            "form textarea",
        ],
        'submit_button': [
            "button.llm__prompt-submit",
            "button[type='submit']",
            "button[aria-label*='send' i]",
            "button[aria-label*='invia' i]",
            "button:has(svg[class*='send'])",
            ".send-button",
            "button.submit",
            "form button:last-child",
        ],
        'bot_messages': [
            ".llm__message--assistant",
            "[data-role='assistant']",
            "[data-message-role='assistant']",
            ".message.assistant",
            ".message.bot",
            ".bot-message",
            ".ai-response",
            ".assistant-message",
            "[class*='assistant']",
            "[class*='bot-response']",
        ],
        'loading_indicator': [
            ".llm__busyIndicator",
            ".loading",
            ".typing-indicator",
            ".typing",
            ".dots",
            ".spinner",
            "[class*='loading']",
            "[class*='typing']",
            "[class*='dots']",
            "[class*='spinner']",
            "[class*='busy']",
        ],
        'thread_container': [
            ".llm__scroller",
            ".llm__thread",
            ".llm__messages",
            ".chat-messages",
            ".conversation",
            ".messages-container",
            "[class*='thread']",
            "[class*='messages']",
        ],
        'content_inner': [
            ".llm__inner",
            ".message-content",
            ".response-content",
            "[class*='content']",
            "[class*='body']",
        ],
    }

    # Keyword per classificare elementi
    LOADING_KEYWORDS = ['load', 'typing', 'dots', 'spinner', 'busy', 'wait', 'pending']
    MESSAGE_KEYWORDS = ['message', 'response', 'assistant', 'bot', 'reply', 'answer']

    def __init__(self, url: str):
        self.url = url
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

        self.result = DetectionResult()
        self.pattern_store = PatternStore()

        # Stato monitoraggio
        self._initial_classes: Set[str] = set()
        self._seen_classes: Set[str] = set()

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()

    async def start(self) -> None:
        """Avvia browser"""
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=False)
        self._context = await self._browser.new_context(
            viewport={'width': 1280, 'height': 720}
        )
        self._page = await self._context.new_page()

        # Naviga all'URL
        await self._page.goto(self.url, wait_until='networkidle')
        await asyncio.sleep(1)

        # Snapshot iniziale classi
        self._initial_classes = await self._get_all_classes()

    async def stop(self) -> None:
        """Chiude browser"""
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def _get_all_classes(self) -> Set[str]:
        """Ottiene tutte le classi CSS nel DOM"""
        classes = await self._page.evaluate("""
            () => {
                const classes = new Set();
                document.querySelectorAll('*').forEach(el => {
                    const cn = el.className;
                    if (typeof cn === 'string') {
                        cn.split(' ').filter(c => c).forEach(c => classes.add(c));
                    }
                });
                return Array.from(classes);
            }
        """)
        return set(classes)

    async def auto_detect(self) -> DetectionResult:
        """
        Fase 1: Prova pattern comuni per trovare selettori.
        Usa sia pattern default che pattern appresi.
        """
        print("\n🔍 Auto-detect selettori in corso...")

        for category in ['textarea', 'submit_button', 'bot_messages',
                         'loading_indicator', 'thread_container', 'content_inner']:
            # Combina pattern appresi + default
            patterns = (
                self.pattern_store.get_patterns(category) +
                self.DEFAULT_PATTERNS.get(category, [])
            )

            selector = await self._try_patterns(patterns, category)
            if selector:
                setattr(self.result, category, selector)
                print(f"  ✅ {category}: {selector}")
            else:
                print(f"  ⚠️  {category}: non trovato")

        return self.result

    async def _try_patterns(self, patterns: List[str], name: str) -> Optional[str]:
        """Prova ogni pattern fino a trovarne uno funzionante"""
        for pattern in patterns:
            try:
                locator = self._page.locator(pattern)
                count = await locator.count()
                if count > 0:
                    # Verifica visibilità per i primi elementi
                    try:
                        is_visible = await locator.first.is_visible()
                        if is_visible:
                            return pattern
                    except:
                        # Se non possiamo verificare visibilità, accetta comunque
                        return pattern
            except:
                continue
        return None

    async def test_question(self, question: str) -> Dict[str, Any]:
        """
        Fase 2: Invia domanda e monitora DOM per rilevare nuovi elementi.

        Returns:
            {
                'success': bool,
                'response_text': str,
                'new_classes': List[str],
                'loading_detected': Optional[str],
                'message_detected': Optional[str],
            }
        """
        result = {
            'success': False,
            'response_text': '',
            'new_classes': [],
            'loading_detected': None,
            'message_detected': None,
        }

        # Verifica che abbiamo textarea e submit
        if not self.result.textarea or not self.result.submit_button:
            print("  ❌ Mancano textarea o submit button")
            return result

        try:
            # Snapshot prima
            before_classes = await self._get_all_classes()
            before_message_count = 0
            if self.result.bot_messages:
                before_message_count = await self._page.locator(self.result.bot_messages).count()

            # Invia messaggio
            textarea = self._page.locator(self.result.textarea)
            await textarea.fill(question)
            await asyncio.sleep(0.2)

            submit = self._page.locator(self.result.submit_button)
            await submit.click()

            print(f"  📤 Messaggio inviato: {question[:50]}...")

            # Monitora DOM
            monitoring = await self._monitor_dom_changes(
                before_classes=before_classes,
                before_message_count=before_message_count,
                timeout_s=30
            )

            result['new_classes'] = list(monitoring['new_classes'])
            result['loading_detected'] = monitoring.get('loading_selector')
            result['message_detected'] = monitoring.get('message_selector')
            result['success'] = monitoring.get('got_response', False)
            result['response_text'] = monitoring.get('response_text', '')

            # Aggiorna selettori se ne abbiamo trovati di nuovi
            if monitoring.get('loading_selector') and not self.result.loading_indicator:
                self.result.loading_indicator = monitoring['loading_selector']
                print(f"  🔄 Loading rilevato: {monitoring['loading_selector']}")

            if monitoring.get('message_selector') and not self.result.bot_messages:
                self.result.bot_messages = monitoring['message_selector']
                print(f"  💬 Messaggi rilevati: {monitoring['message_selector']}")

            if monitoring.get('content_selector') and not self.result.content_inner:
                self.result.content_inner = monitoring['content_selector']
                print(f"  📝 Content inner rilevato: {monitoring['content_selector']}")

            # Aggiungi domanda alla lista
            self.result.test_questions.append(question)

        except Exception as e:
            print(f"  ❌ Errore: {e}")

        return result

    async def _monitor_dom_changes(
        self,
        before_classes: Set[str],
        before_message_count: int,
        timeout_s: float = 30
    ) -> Dict[str, Any]:
        """
        Monitora il DOM durante la risposta del bot.

        Rileva:
        - Elementi loading (appaiono e scompaiono)
        - Nuovi messaggi
        - Nuove classi
        """
        result = {
            'new_classes': set(),
            'loading_selector': None,
            'message_selector': None,
            'content_selector': None,
            'got_response': False,
            'response_text': '',
        }

        loading_candidates = []
        message_candidates = []
        content_candidates = []

        start_time = asyncio.get_event_loop().time()
        check_count = 0

        while asyncio.get_event_loop().time() - start_time < timeout_s:
            check_count += 1

            # Ottieni classi attuali
            current_classes = await self._get_all_classes()
            new_classes = current_classes - before_classes - self._seen_classes

            # Analizza nuove classi
            for cls in new_classes:
                cls_lower = cls.lower()

                # È un loading indicator?
                if any(kw in cls_lower for kw in self.LOADING_KEYWORDS):
                    selector = f".{cls}"
                    # Verifica se è visibile
                    try:
                        loc = self._page.locator(selector)
                        if await loc.count() > 0 and await loc.first.is_visible():
                            loading_candidates.append(selector)
                            if check_count <= 20:  # Solo nei primi secondi
                                print(f"    🔄 Loading candidate: {selector}")
                    except:
                        pass

                # È un messaggio?
                if any(kw in cls_lower for kw in self.MESSAGE_KEYWORDS):
                    selector = f".{cls}"
                    message_candidates.append(selector)

                # È un content container?
                if 'inner' in cls_lower or 'content' in cls_lower or 'body' in cls_lower:
                    selector = f".{cls}"
                    content_candidates.append(selector)

            result['new_classes'].update(new_classes)
            self._seen_classes.update(new_classes)

            # Verifica se c'è un nuovo messaggio
            if self.result.bot_messages:
                try:
                    current_count = await self._page.locator(self.result.bot_messages).count()
                    if current_count > before_message_count:
                        # Aspetta stabilità
                        await asyncio.sleep(1)

                        # Estrai testo
                        last_msg = self._page.locator(self.result.bot_messages).last

                        # Prova content_inner se disponibile
                        if self.result.content_inner:
                            inner = last_msg.locator(self.result.content_inner)
                            if await inner.count() > 0:
                                texts = []
                                for i in range(await inner.count()):
                                    t = await inner.nth(i).text_content()
                                    if t:
                                        texts.append(t.strip())
                                result['response_text'] = "\n".join(texts)
                            else:
                                result['response_text'] = await last_msg.text_content() or ''
                        else:
                            result['response_text'] = await last_msg.text_content() or ''

                        result['got_response'] = True

                        # Cerca content_inner se non l'abbiamo
                        if not self.result.content_inner:
                            for sel in ['.llm__inner', '.message-content', '[class*="inner"]']:
                                try:
                                    if await last_msg.locator(sel).count() > 0:
                                        result['content_selector'] = sel
                                        break
                                except:
                                    pass

                        break
                except:
                    pass

            await asyncio.sleep(0.3)

        # Determina loading (quello che è apparso e poi scomparso)
        if loading_candidates:
            final_classes = await self._get_all_classes()
            for candidate in loading_candidates:
                cls_name = candidate[1:]  # Rimuovi il punto
                if cls_name not in final_classes:
                    result['loading_selector'] = candidate
                    break
            # Se nessuno è scomparso, prendi il primo
            if not result['loading_selector']:
                result['loading_selector'] = loading_candidates[0]

        # Determina messaggio
        if message_candidates and not self.result.bot_messages:
            result['message_selector'] = message_candidates[0]

        # Content
        if content_candidates and not result['content_selector']:
            result['content_selector'] = content_candidates[0]

        return result

    async def learn_from_click(self, element_name: str, timeout_s: int = 30) -> Optional[str]:
        """
        Fase 3 (fallback): L'utente clicca sull'elemento desiderato.

        Args:
            element_name: Nome elemento (per messaggio utente)
            timeout_s: Timeout in secondi

        Returns:
            Selettore CSS dell'elemento cliccato
        """
        print(f"\n👆 Clicca su: {element_name}")
        print(f"   Hai {timeout_s} secondi...")

        selector_result = await self._page.evaluate("""
            (timeout) => {
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
                                // Cerca classe più specifica (più lunga)
                                const bestClass = classes.sort((a, b) => b.length - a.length)[0];
                                selector = '.' + bestClass;
                            }
                        }
                        // Fallback: tag + attributi
                        if (!selector) {
                            selector = el.tagName.toLowerCase();
                            if (el.getAttribute('type')) {
                                selector += '[type="' + el.getAttribute('type') + '"]';
                            }
                            if (el.getAttribute('placeholder')) {
                                selector += '[placeholder*="' + el.getAttribute('placeholder').substring(0, 20) + '"]';
                            }
                        }

                        document.removeEventListener('click', handler, true);
                        resolve(selector);
                    };

                    document.addEventListener('click', handler, true);

                    setTimeout(() => {
                        document.removeEventListener('click', handler, true);
                        resolve(null);
                    }, timeout);
                });
            }
        """, timeout_s * 1000)

        if selector_result:
            print(f"  ✅ Selettore catturato: {selector_result}")

            # Verifica che funzioni
            try:
                count = await self._page.locator(selector_result).count()
                if count > 0:
                    return selector_result
                else:
                    print(f"  ⚠️ Selettore non trova elementi, riprova")
                    return None
            except:
                return selector_result
        else:
            print("  ❌ Timeout - nessun click rilevato")
            return None

    async def validate_selectors(self, test_message: str = "ciao") -> Dict[str, bool]:
        """
        Validazione finale: verifica che tutti i selettori funzionino.

        Returns:
            Dizionario con risultato validazione per ogni selettore
        """
        results = {
            'textarea': False,
            'submit_button': False,
            'bot_messages': False,
            'loading_indicator': True,  # Opzionale
            'overall': False,
        }

        print("\n🧪 Validazione selettori...")

        # Ricarica pagina per stato pulito
        await self._page.reload(wait_until='networkidle')
        await asyncio.sleep(1)

        # Test textarea
        if self.result.textarea:
            try:
                textarea = self._page.locator(self.result.textarea)
                if await textarea.count() > 0 and await textarea.first.is_visible():
                    await textarea.fill(test_message)
                    results['textarea'] = True
                    print(f"  ✅ Textarea: OK")
                else:
                    print(f"  ❌ Textarea: non visibile")
            except Exception as e:
                print(f"  ❌ Textarea: {e}")

        # Test submit
        if self.result.submit_button and results['textarea']:
            try:
                submit = self._page.locator(self.result.submit_button)
                if await submit.count() > 0 and await submit.first.is_visible():
                    await submit.click()
                    results['submit_button'] = True
                    print(f"  ✅ Submit: OK")
                else:
                    print(f"  ❌ Submit: non visibile")
            except Exception as e:
                print(f"  ❌ Submit: {e}")

        # Test bot_messages (attendi risposta)
        if self.result.bot_messages and results['submit_button']:
            try:
                # Attendi fino a 30 secondi per una risposta
                for _ in range(60):
                    count = await self._page.locator(self.result.bot_messages).count()
                    if count > 0:
                        results['bot_messages'] = True
                        print(f"  ✅ Bot messages: OK ({count} messaggi)")
                        break
                    await asyncio.sleep(0.5)

                if not results['bot_messages']:
                    print(f"  ❌ Bot messages: nessun messaggio dopo 30s")
            except Exception as e:
                print(f"  ❌ Bot messages: {e}")

        # Overall
        results['overall'] = all([
            results['textarea'],
            results['submit_button'],
            results['bot_messages']
        ])

        if results['overall']:
            print(f"\n✅ Validazione completata con successo!")
        else:
            print(f"\n❌ Validazione fallita - alcuni selettori non funzionano")

        return results

    def save_learned_patterns(self) -> None:
        """Salva i pattern che hanno funzionato"""
        if self.result.textarea:
            self.pattern_store.add_pattern('textarea', self.result.textarea)
        if self.result.submit_button:
            self.pattern_store.add_pattern('submit_button', self.result.submit_button)
        if self.result.bot_messages:
            self.pattern_store.add_pattern('bot_messages', self.result.bot_messages)
        if self.result.loading_indicator:
            self.pattern_store.add_pattern('loading_indicator', self.result.loading_indicator)
        if self.result.thread_container:
            self.pattern_store.add_pattern('thread_container', self.result.thread_container)
        if self.result.content_inner:
            self.pattern_store.add_pattern('content_inner', self.result.content_inner)

        print("💾 Pattern salvati per usi futuri")


class SelectorDetectorStep:
    """
    Step del wizard per rilevamento selettori.
    Gestisce il flusso interattivo completo.
    """

    def __init__(self, url: str):
        self.url = url
        self.detector: Optional[InteractiveDetector] = None
        self.result: Optional[DetectionResult] = None

    async def run(self) -> Optional[DetectionResult]:
        """
        Esegue lo step completo:
        1. Apri browser
        2. Auto-detect
        3. Loop interattivo domande
        4. Validazione finale
        5. Riepilogo e conferma
        """
        print(f"\n{'='*60}")
        print("CONFIGURAZIONE SELETTORI CHATBOT")
        print(f"{'='*60}")
        print(f"\n🌐 Apertura browser su: {self.url}")

        async with InteractiveDetector(self.url) as detector:
            self.detector = detector

            # Fase 1: Auto-detect
            print(f"\n{'═'*60}")
            print("FASE 1: Auto-detect selettori base")
            print(f"{'═'*60}")

            self.result = await detector.auto_detect()

            # Fase 2: Test interattivo
            print(f"\n{'═'*60}")
            print("FASE 2: Test interattivo")
            print(f"{'═'*60}")
            print("\nInvia domande al chatbot per rilevare selettori mancanti.")
            print("Prova domande diverse (prodotti, testo, info) per coprire")
            print("tutti i tipi di risposta.\n")

            question_count = 0
            while True:
                print("─" * 50)
                print("Comandi: [invio]=nuova domanda | [f]ine | [m]anuale | [r]icarica")

                choice = input(">>> ").strip()

                if choice.lower() == 'f':
                    break
                elif choice.lower() == 'm':
                    await self._manual_mode()
                elif choice.lower() == 'r':
                    await detector._page.reload(wait_until='networkidle')
                    print("  🔄 Pagina ricaricata")
                elif choice:
                    question_count += 1
                    print(f"\n📝 Domanda [{question_count}]: {choice}")

                    test_result = await detector.test_question(choice)

                    if test_result['success']:
                        preview = test_result['response_text'][:100]
                        print(f"  ✅ Risposta ricevuta: {preview}...")
                    else:
                        print("  ⚠️ Nessuna risposta rilevata")

                    if test_result['new_classes']:
                        print(f"  📊 Nuove classi: {len(test_result['new_classes'])}")
                else:
                    print("  [Inserisci una domanda o un comando]")

            # Fase 3: Validazione
            print(f"\n{'═'*60}")
            print("FASE 3: Validazione finale")
            print(f"{'═'*60}")

            do_validate = input("\nEseguire test di validazione? [S/n]: ").strip().lower()
            if do_validate != 'n':
                validation = await detector.validate_selectors()

                if not validation['overall']:
                    retry = input("\nVuoi correggere manualmente? [s/N]: ").strip().lower()
                    if retry == 's':
                        await self._manual_mode()
                        # Ri-valida
                        validation = await detector.validate_selectors()

            # Fase 4: Riepilogo
            print(f"\n{'═'*60}")
            print("RIEPILOGO SELETTORI RILEVATI")
            print(f"{'═'*60}")
            self._print_result()

            # Conferma
            print("\n" + "─" * 50)
            confirm = input("[c]onferma | [r]iprova | [e]dit manuale | [a]nnulla: ").strip().lower()

            if confirm == 'c':
                # Salva pattern appresi
                detector.save_learned_patterns()
                return self.result
            elif confirm == 'e':
                await self._manual_edit()
                detector.save_learned_patterns()
                return self.result
            elif confirm == 'r':
                return await self.run()  # Riprova da capo
            else:
                return None  # Annullato

    async def _manual_mode(self) -> None:
        """Modalità manuale: click-to-learn per ogni elemento"""
        print("\n🖱️ MODALITÀ MANUALE")
        print("Clicca sugli elementi nel browser per catturare i selettori.\n")

        elements = [
            ('textarea', 'campo input testo'),
            ('submit_button', 'bottone invio'),
            ('bot_messages', 'un messaggio del bot'),
        ]

        for attr, desc in elements:
            current = getattr(self.result, attr)
            if current:
                skip = input(f"  {attr}: {current} - Modificare? [s/N]: ").strip().lower()
                if skip != 's':
                    continue

            selector = await self.detector.learn_from_click(desc)
            if selector:
                setattr(self.result, attr, selector)

    async def _manual_edit(self) -> None:
        """Edit manuale dei selettori"""
        print("\n✏️ EDIT MANUALE")
        print("Premi INVIO per mantenere il valore attuale.\n")

        for attr in ['textarea', 'submit_button', 'bot_messages',
                     'loading_indicator', 'thread_container', 'content_inner']:
            current = getattr(self.result, attr)
            new_value = input(f"  {attr} [{current}]: ").strip()
            if new_value:
                setattr(self.result, attr, new_value)

    def _print_result(self) -> None:
        """Stampa riepilogo risultati"""
        print(f"\n  textarea:          {self.result.textarea or '(non impostato)'}")
        print(f"  submit_button:     {self.result.submit_button or '(non impostato)'}")
        print(f"  bot_messages:      {self.result.bot_messages or '(non impostato)'}")
        print(f"  loading_indicator: {self.result.loading_indicator or '(non impostato)'}")
        print(f"  thread_container:  {self.result.thread_container or '(non impostato)'}")
        print(f"  content_inner:     {self.result.content_inner or '(non impostato)'}")

        if self.result.test_questions:
            print(f"\n  Test eseguiti: {len(self.result.test_questions)}")

        status = "✅ Completo" if self.result.is_complete() else "⚠️ Incompleto"
        print(f"\n  Status: {status}")


async def run_selector_detection(url: str) -> Optional[DetectionResult]:
    """
    Funzione di utilità per eseguire il rilevamento selettori.

    Usage:
        result = await run_selector_detection("https://example.com/chat")
        if result:
            print(result.to_dict())
    """
    step = SelectorDetectorStep(url)
    return await step.run()


# Entry point per test standalone
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python selectors_detector.py <URL>")
        sys.exit(1)

    url = sys.argv[1]
    result = asyncio.run(run_selector_detection(url))

    if result:
        print("\n" + "="*60)
        print("CONFIGURAZIONE FINALE")
        print("="*60)
        print(json.dumps(result.to_dict(), indent=2))
