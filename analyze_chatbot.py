#!/usr/bin/env python3
"""
Script di analisi UI chatbot Silicon.
Ispeziona il DOM per trovare i selettori corretti.
"""

import asyncio
from playwright.async_api import async_playwright

URL = "https://platform-dev.server-01.example.com/api/llm/app-silicon-search-B/it"

async def analyze():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        print(f"Navigazione a {URL}...")
        await page.goto(URL, wait_until='networkidle')
        await asyncio.sleep(2)

        print("\n" + "="*60)
        print("ANALISI STRUTTURA DOM")
        print("="*60)

        # Cerca elementi comuni per chatbot
        selectors_to_check = {
            "textarea": [
                "#llm-prompt-textarea",
                "textarea",
                "[contenteditable='true']",
                "input[type='text']",
            ],
            "submit_button": [
                "button.llm__prompt-submit",
                "button[type='submit']",
                "button:has(svg)",
                ".llm__prompt button",
            ],
            "bot_messages": [
                ".llm__message--assistant",
                ".llm__message--assistant .llm__text-body",
                "[data-role='assistant']",
                ".assistant-message",
                ".bot-message",
            ],
            "loading": [
                ".llm__loading",
                ".llm__typing",
                ".llm__dots",
                ".loading",
                ".typing-indicator",
                "[class*='loading']",
                "[class*='typing']",
                "[class*='dots']",
            ],
            "thread": [
                ".llm__thread",
                ".llm__messages",
                ".chat-messages",
                ".conversation",
            ]
        }

        for category, selectors in selectors_to_check.items():
            print(f"\n{category.upper()}:")
            for sel in selectors:
                try:
                    count = await page.locator(sel).count()
                    if count > 0:
                        el = page.locator(sel).first
                        visible = await el.is_visible()
                        tag = await el.evaluate("el => el.tagName")
                        classes = await el.evaluate("el => el.className")
                        print(f"  ✓ {sel}")
                        print(f"     count={count}, visible={visible}, tag={tag}")
                        print(f"     classes: {classes[:80]}..." if len(str(classes)) > 80 else f"     classes: {classes}")
                except Exception as e:
                    pass

        # Cerca tutte le classi che contengono "llm"
        print("\n" + "="*60)
        print("CLASSI CON 'llm' NEL NOME")
        print("="*60)

        llm_classes = await page.evaluate("""
            () => {
                const classes = new Set();
                document.querySelectorAll('[class*="llm"]').forEach(el => {
                    const cn = el.className;
                    if (typeof cn === 'string') {
                        cn.split(' ').forEach(c => {
                            if (c.includes('llm')) classes.add(c);
                        });
                    }
                });
                return Array.from(classes).sort();
            }
        """)
        for c in llm_classes:
            print(f"  .{c}")

        # Invia messaggio di test
        print("\n" + "="*60)
        print("TEST INVIO MESSAGGIO: 'Cosa fa Silicon?'")
        print("="*60)

        textarea = page.locator("#llm-prompt-textarea")
        if await textarea.count() > 0:
            print("Textarea trovata, invio messaggio di test...")
            await textarea.fill("Cosa fa Silicon?")
            await asyncio.sleep(0.3)

            submit = page.locator("button.llm__prompt-submit")
            if await submit.count() > 0:
                await submit.click()
                print("Messaggio inviato")

                # Monitora DOM per 10 secondi
                print("\nMonitoraggio DOM per 10 secondi...")

                for i in range(20):
                    await asyncio.sleep(0.5)

                    # Conta messaggi
                    msg_count = await page.locator(".llm__message--assistant").count()

                    # Cerca loading
                    loading_visible = False
                    for loading_sel in [".llm__loading", "[class*='loading']", "[class*='typing']", "[class*='dots']"]:
                        try:
                            loc = page.locator(loading_sel)
                            if await loc.count() > 0 and await loc.first.is_visible():
                                loading_visible = True
                                loading_classes = await loc.first.evaluate("el => el.className")
                                print(f"  [{i*0.5:.1f}s] LOADING: {loading_sel} -> {loading_classes}")
                                break
                        except:
                            pass

                    if not loading_visible and i % 4 == 0:
                        print(f"  [{i*0.5:.1f}s] messages={msg_count}")

                # Analizza struttura messaggio bot
                print("\n" + "="*60)
                print("STRUTTURA MESSAGGIO BOT")
                print("="*60)

                bot_msg = page.locator(".llm__message--assistant").last
                if await bot_msg.count() > 0:
                    html = await bot_msg.evaluate("el => el.outerHTML")
                    # Mostra i primi 4000 caratteri
                    print(html[:4000])
                    if len(html) > 4000:
                        print(f"\n... [{len(html)} caratteri totali]")

                    # Cerca elementi interni
                    print("\nELEMENTI INTERNI:")
                    inner_selectors = [
                        ".llm__text-body",
                        ".llm__inner",
                        ".llm__product",
                        ".llm__products",
                        "p",
                        "a",
                        "ul",
                        "li",
                    ]
                    for sel in inner_selectors:
                        count = await bot_msg.locator(sel).count()
                        if count > 0:
                            print(f"  {sel}: {count} elementi")

                    # Mostra il testo estratto
                    text = await bot_msg.text_content()
                    print(f"\nTESTO ESTRATTO ({len(text)} caratteri):")
                    print(text[:1000] if text else "(vuoto)")
                    if text and len(text) > 1000:
                        print(f"... [{len(text)} caratteri totali]")

        print("\n" + "="*60)
        print("FINE ANALISI - Premi INVIO per chiudere")
        print("="*60)
        input()

        await browser.close()

if __name__ == "__main__":
    asyncio.run(analyze())
