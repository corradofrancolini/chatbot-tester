#!/usr/bin/env python3
"""
Test script per verificare l'output del report LangSmith.

Uso:
    python test_langsmith_report.py
    python test_langsmith_report.py "Quali penne avete?"
"""

import sys
import os
from pathlib import Path

# Aggiungi src al path
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

# Carica .env
env_path = Path(__file__).parent / "config" / ".env"
load_dotenv(env_path)

from src.langsmith_client import LangSmithClient, LangSmithReport


def main():
    # Configura client
    api_key = os.getenv("LANGSMITH_API_KEY")
    project_id = os.getenv("LANGSMITH_PROJECT_ID", "your-project-id")  # Set via environment

    if not api_key:
        print("✗ LANGSMITH_API_KEY non trovata in config/.env")
        return

    print(f"Connessione a LangSmith...")
    print(f"   Project ID: {project_id}")

    client = LangSmithClient(
        api_key=api_key,
        project_id=project_id
    )

    # Verifica connessione
    if not client.is_available():
        print("✗ LangSmith non raggiungibile")
        return

    print("✓ Connesso a LangSmith\n")

    # Query di test
    if len(sys.argv) > 1:
        question = sys.argv[1]
    else:
        question = None  # Prende l'ultimo trace

    print("=" * 70)
    print("RECUPERO ULTIMO TRACE" + (f" per: '{question[:50]}...'" if question else ""))
    print("=" * 70)

    # Ottieni report
    if question:
        report = client.get_report_for_question(question, search_window_minutes=60)
    else:
        # Prendi l'ultimo trace
        trace = client.get_latest_trace()
        if trace:
            report = client.get_report_for_question(
                trace.input[:50] if trace.input else "",
                search_window_minutes=120
            )
        else:
            print("✗ Nessun trace trovato")
            return

    if report.error and not report.trace_url:
        print(f"✗ {report.error}")
        return

    # Mostra dati raw
    print("\nDATI RAW:")
    print(f"   trace_url: {report.trace_url}")
    print(f"   query: {report.query[:100]}..." if report.query else "   query: (vuota)")
    print(f"   response: {report.response[:100]}..." if report.response else "   response: (vuota)")
    print(f"   model: {report.model}")
    print(f"   model_provider: {report.model_provider}")
    print(f"   duration_ms: {report.duration_ms}")
    print(f"   first_token_ms: {report.first_token_ms}")
    print(f"   tokens_input: {report.tokens_input}")
    print(f"   tokens_output: {report.tokens_output}")
    print(f"   tokens_total: {report.tokens_total}")
    print(f"   tools_used: {report.tools_used}")
    print(f"   tool_count: {report.tool_count}")
    print(f"   failed_tools: {report.failed_tools}")
    print(f"   status: {report.status}")
    print(f"   error: {report.error}")

    # Waterfall
    print(f"\nWATERFALL ({len(report.waterfall)} step):")
    for step in report.waterfall:
        indent = "  " * step.depth
        print(f"   {indent}{step.name} [{step.run_type}] {step.duration_ms}ms (offset: {step.start_offset_ms}ms)")
        if step.error:
            print(f"   {indent}  ERROR: {step.error}")

    # Output formattato per Sheets
    print("\n" + "=" * 70)
    print("OUTPUT format_for_sheets() - per colonna NOTES:")
    print("=" * 70)
    formatted = report.format_for_sheets()
    print(formatted if formatted else "(vuoto)")

    # Model version
    print("\n" + "=" * 70)
    print("OUTPUT get_model_version() - per colonna MODEL VER:")
    print("=" * 70)
    print(report.get_model_version() or "(vuoto)")

    print("\n" + "=" * 70)
    print("LINK TRACE:")
    print("=" * 70)
    print(report.trace_url)


if __name__ == "__main__":
    main()
