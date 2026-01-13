# PRD: Chatbot Tester

## 1. Problema

Testare chatbot manualmente è:
- **Tedioso**: ripetere le stesse domande dopo ogni deploy
- **Inconsistente**: valutazioni soggettive, niente storico
- **Opaco**: difficile capire perché un chatbot fallisce

## 2. Visione

> *"If it can be done, it must be visible, explained, and configurable."*

Un framework di testing che rende ogni aspetto del chatbot **misurabile, tracciabile e automatizzabile**.

## 3. Utenti Target

- **Primario**: Sviluppatore/QA del chatbot
- **Secondario**: Team che erediterà il progetto

## 4. Priorità

**Affidabilità** e **Velocità** sono le priorità principali.

## 5. Funzionalità Core

| Categoria | Feature |
|-----------|---------|
| **Execution** | 3 modalità (Train/Assisted/Auto), esecuzione parallela |
| **Tracing** | LangSmith integration, waterfall tree, token breakdown |
| **Reporting** | Google Sheets, export PDF/Excel/HTML/CSV, screenshot |
| **Analysis** | Regression detection, flaky tests, A/B comparison |
| **Diagnostics** | Failure classification, hypothesis generation, fix suggestions |
| **Automation** | GitHub Actions, scheduler, notifications |

## 6. Nice-to-Have

- Dashboard web
- Notifiche Slack
- Auto-diagnosi post-run
- LLM-powered hypothesis verification

## 7. Non-Goal

- Testare API direttamente (solo via browser/UI)
- Generare test automaticamente
- Supporto multi-tenant/SaaS

## 8. Vincoli Tecnici

- Python 3.11+
- Playwright (browser automation)
- Google Sheets API + Drive API
- LangSmith API
- Ollama (opzionale)

## 9. Metriche di Successo

- Pass rate per run
- TTFR (Time to First Response)
- Regression count tra run
- Copertura test per categoria

## 10. Decisioni Architetturali

| Decisione | Motivazione | Data |
|-----------|-------------|------|
| ExecutionContext pattern | Riduce accoppiamento (13→1 param) | 2024-12-24 |
| TestExecutor self-contained | Riutilizzabile standalone | 2024-12-24 |
| Sheet schema separato | Manutenibilità colonne | 2024-12-24 |
| TestMode enum | Type safety | 2024-12-24 |

Vedi [DECISIONS.md](DECISIONS.md) per dettagli completi.
