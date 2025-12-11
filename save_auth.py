#!/usr/bin/env python3
from playwright.sync_api import sync_playwright

URL = "https://ai-chatbots-dev.efg-tech.gg/api/llm/app-efg-intranet/en"

print(f"Apertura browser su: {URL}")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    page.goto(URL)
    input("Login manualmente, poi premi INVIO...")
    context.storage_state(path="auth_state.json")
    print("Stato salvato in auth_state.json")
    browser.close()
