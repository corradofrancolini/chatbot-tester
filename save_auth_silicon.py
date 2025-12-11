#!/usr/bin/env python3
from playwright.sync_api import sync_playwright

URL = "https://platform-ai-dev.ws-deploy-01.wslabs.it/api/llm/app-silicon-search-B/it"

print(f"Apertura browser su: {URL}")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    page.goto(URL)
    input("Login manualmente, poi premi INVIO...")
    context.storage_state(path="projects/silicon-b/browser-data/state.json")
    print("✓ Stato salvato in projects/silicon-b/browser-data/state.json")
    browser.close()
