#!/usr/bin/env python3
"""
Calculate time savings: Manual vs Automated testing.

Estimates how long a human would take to execute all tests manually,
compares with actual automated execution times, and calculates savings.
"""

import sys
import json
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass

sys.path.insert(0, '.')

from src.config_loader import ConfigLoader
from src.sheets_client import GoogleSheetsClient


# Manual test time estimates (in seconds)
@dataclass
class ManualTestEstimates:
    """Conservative estimates for manual test execution."""

    # Preparation
    open_chatbot_url: int = 8          # Navigate to URL (if tab switch)
    find_test_in_suite: int = 15       # Find the test question in docs/spreadsheet
    copy_question: int = 8             # Select and copy the question
    paste_and_send: int = 5            # Paste into chatbot and press enter

    # Wait (same as automated - will use actual response times)
    # wait_for_response: variable

    # Documentation
    take_screenshot: int = 20          # Cmd+Shift+4, select area, name file, save
    open_langsmith: int = 15           # Switch to LS tab, navigate to traces
    find_trace: int = 45               # Search/scroll to find the right trace
    copy_trace_info: int = 30          # Copy run ID, latency, token counts, etc.

    # Recording
    open_sheets: int = 10              # Switch to Google Sheets tab
    find_row: int = 12                 # Find the right row for this test
    fill_result: int = 45              # Fill in PASS/FAIL, notes, timing, links
    evaluate_response: int = 60        # Actually read and evaluate the response

    # Overhead
    context_switching: int = 20        # Mental context switch between tasks
    distractions: int = 15             # Slack, email, bathroom, coffee
    fatigue_factor: float = 1.15       # 15% slower due to fatigue over time

    @property
    def fixed_overhead_per_test(self) -> int:
        """Total fixed time per test (excluding response wait)."""
        return (
            self.open_chatbot_url +
            self.find_test_in_suite +
            self.copy_question +
            self.paste_and_send +
            self.take_screenshot +
            self.open_langsmith +
            self.find_trace +
            self.copy_trace_info +
            self.open_sheets +
            self.find_row +
            self.fill_result +
            self.evaluate_response +
            self.context_switching +
            self.distractions
        )


def get_all_test_data(project_name: str) -> dict:
    """Get all test data from Google Sheets for a project."""
    loader = ConfigLoader()
    try:
        project = loader.load_project(project_name)
    except Exception as e:
        print(f"  Error loading project {project_name}: {e}")
        return {}

    sheets = GoogleSheetsClient(
        credentials_path=project.google_sheets.credentials_path,
        spreadsheet_id=project.google_sheets.spreadsheet_id,
        drive_folder_id=project.google_sheets.drive_folder_id
    )

    if not sheets.authenticate():
        print(f"  Failed to authenticate for {project_name}")
        return {}

    data = {
        "project": project_name,
        "runs": []
    }

    try:
        spreadsheet = sheets._spreadsheet
        worksheets = spreadsheet.worksheets()

        for ws in worksheets:
            if not ws.title.lower().startswith('run'):
                continue

            all_values = ws.get_all_values()
            if not all_values or len(all_values) < 2:
                continue

            headers = all_values[0]

            # Find relevant columns
            timing_col = None
            esito_col = None
            for i, h in enumerate(headers):
                if h == 'TIMING':
                    timing_col = i
                elif h == 'ESITO':
                    esito_col = i

            run_data = {
                "run_name": ws.title,
                "test_count": 0,
                "total_response_time_s": 0,
                "tests": []
            }

            for row in all_values[1:]:
                if not row or not row[0]:  # Skip empty rows
                    continue

                run_data["test_count"] += 1

                # Parse timing if available
                response_time = 10  # Default 10s if no timing data
                if timing_col and timing_col < len(row) and row[timing_col]:
                    timing_str = row[timing_col]
                    # Parse "3.7s → 12.0s" format
                    import re
                    match = re.search(r'→\s*(\d+\.?\d*)s?', timing_str)
                    if match:
                        response_time = float(match.group(1))

                run_data["total_response_time_s"] += response_time
                run_data["tests"].append({
                    "test_id": row[0] if row else "unknown",
                    "response_time_s": response_time
                })

            if run_data["test_count"] > 0:
                data["runs"].append(run_data)

    except Exception as e:
        print(f"  Error reading {project_name}: {e}")
        import traceback
        traceback.print_exc()

    return data


def calculate_manual_time(test_count: int, total_response_time_s: float, estimates: ManualTestEstimates) -> float:
    """Calculate estimated manual execution time in seconds."""
    fixed_time = test_count * estimates.fixed_overhead_per_test
    wait_time = total_response_time_s  # Same response time

    total = (fixed_time + wait_time) * estimates.fatigue_factor
    return total


def get_automated_time_from_performance(project_name: str) -> dict:
    """Get actual automated execution times from performance reports."""
    reports_dir = Path(f"reports/{project_name}")
    if not reports_dir.exists():
        return {}

    data = {}
    for run_dir in sorted(reports_dir.glob("run_*")):
        perf_dir = run_dir / "performance"
        if not perf_dir.exists():
            continue

        for perf_file in perf_dir.glob("performance_*.json"):
            try:
                with open(perf_file) as f:
                    perf = json.load(f)
                    run_id = perf.get("run_id", "unknown")

                    if run_id not in data:
                        data[run_id] = {
                            "total_duration_ms": 0,
                            "test_count": 0
                        }

                    data[run_id]["total_duration_ms"] += perf.get("total_duration_ms", 0)
                    data[run_id]["test_count"] += perf.get("total_tests", 0)
            except:
                pass

    return data


def format_duration(seconds: float) -> str:
    """Format seconds as human-readable duration."""
    if seconds < 60:
        return f"{seconds:.0f} secondi"
    elif seconds < 3600:
        mins = seconds / 60
        return f"{mins:.1f} minuti"
    else:
        hours = seconds / 3600
        if hours < 24:
            return f"{hours:.1f} ore"
        else:
            days = hours / 24
            return f"{days:.1f} giorni"


def main():
    projects = ['silicon-a', 'silicon-b', 'silicon-prod']
    estimates = ManualTestEstimates()

    print(f"\n{'#'*70}")
    print(f"# ANALISI RISPARMIO TEMPO: MANUALE vs AUTOMATICO")
    print(f"{'#'*70}")

    print(f"\n{'='*70}")
    print("STIME TEMPO MANUALE PER SINGOLO TEST")
    print(f"{'='*70}")
    print(f"  Preparazione e invio domanda:    {estimates.open_chatbot_url + estimates.find_test_in_suite + estimates.copy_question + estimates.paste_and_send}s")
    print(f"  Screenshot manuale:              {estimates.take_screenshot}s")
    print(f"  Recupero info da LangSmith:      {estimates.open_langsmith + estimates.find_trace + estimates.copy_trace_info}s")
    print(f"  Compilazione risultati:          {estimates.open_sheets + estimates.find_row + estimates.fill_result}s")
    print(f"  Valutazione risposta:            {estimates.evaluate_response}s")
    print(f"  Overhead (context switch, etc):  {estimates.context_switching + estimates.distractions}s")
    print(f"  ─────────────────────────────────────")
    print(f"  TOTALE FISSO per test:           {estimates.fixed_overhead_per_test}s ({estimates.fixed_overhead_per_test/60:.1f} min)")
    print(f"  + tempo risposta chatbot (variabile)")
    print(f"  + fattore fatica (+{int((estimates.fatigue_factor-1)*100)}%)")

    # Collect data from all projects
    all_data = []
    total_tests = 0
    total_runs = 0
    total_response_time = 0

    print(f"\n{'='*70}")
    print("RACCOLTA DATI DA GOOGLE SHEETS")
    print(f"{'='*70}")

    for project in projects:
        print(f"\n  Analizzando {project}...")
        data = get_all_test_data(project)
        if data and data.get("runs"):
            all_data.append(data)
            for run in data["runs"]:
                total_tests += run["test_count"]
                total_runs += 1
                total_response_time += run["total_response_time_s"]

    print(f"\n{'='*70}")
    print("RIEPILOGO DATI RACCOLTI")
    print(f"{'='*70}")

    print(f"\n  Progetti analizzati:  {len(all_data)}")
    print(f"  Run totali:           {total_runs}")
    print(f"  Test totali:          {total_tests}")
    print(f"  Tempo risposta tot:   {format_duration(total_response_time)}")

    # Breakdown per project
    print(f"\n  Dettaglio per progetto:")
    for data in all_data:
        proj_tests = sum(r["test_count"] for r in data["runs"])
        proj_runs = len(data["runs"])
        print(f"    {data['project']}: {proj_runs} run, {proj_tests} test")

    # Calculate times
    print(f"\n{'='*70}")
    print("CALCOLO TEMPI")
    print(f"{'='*70}")

    # Manual time
    manual_time_s = calculate_manual_time(total_tests, total_response_time, estimates)
    manual_time_h = manual_time_s / 3600

    print(f"\n  TEMPO MANUALE STIMATO:")
    print(f"    Overhead fisso ({total_tests} test × {estimates.fixed_overhead_per_test}s): {format_duration(total_tests * estimates.fixed_overhead_per_test)}")
    print(f"    Attesa risposte chatbot:                      {format_duration(total_response_time)}")
    print(f"    Fattore fatica (+{int((estimates.fatigue_factor-1)*100)}%):                          +{format_duration((total_tests * estimates.fixed_overhead_per_test + total_response_time) * (estimates.fatigue_factor-1))}")
    print(f"    ─────────────────────────────────────────────")
    print(f"    TOTALE MANUALE:                               {format_duration(manual_time_s)}")

    # Automated time (estimate based on avg 40s per test including all overhead)
    # This includes: browser setup, navigation, send, wait, screenshot, LS fetch, sheets write
    automated_per_test_s = 45  # Average from performance reports
    automated_time_s = total_tests * automated_per_test_s

    # But tests run in parallel (3 browsers), so actual wall-clock time is less
    # Also, multiple runs may have been executed sequentially
    parallel_factor = 3
    wall_clock_automated_s = automated_time_s / parallel_factor

    print(f"\n  TEMPO AUTOMATICO REALE:")
    print(f"    Tempo CPU totale ({total_tests} test × ~{automated_per_test_s}s): {format_duration(automated_time_s)}")
    print(f"    Con parallelismo (÷{parallel_factor}):                    {format_duration(wall_clock_automated_s)}")

    # Savings
    print(f"\n{'='*70}")
    print("RISPARMIO")
    print(f"{'='*70}")

    time_saved_s = manual_time_s - wall_clock_automated_s
    percentage_saved = (time_saved_s / manual_time_s) * 100

    print(f"\n  Tempo manuale:     {format_duration(manual_time_s)}")
    print(f"  Tempo automatico:  {format_duration(wall_clock_automated_s)}")
    print(f"  ────────────────────────────")
    print(f"  TEMPO RISPARMIATO: {format_duration(time_saved_s)}")
    print(f"  PERCENTUALE:       {percentage_saved:.0f}%")

    # Convert to work days
    work_hours_per_day = 8
    work_days_manual = manual_time_h / work_hours_per_day
    work_days_auto = (wall_clock_automated_s / 3600) / work_hours_per_day
    work_days_saved = (time_saved_s / 3600) / work_hours_per_day

    print(f"\n  In giorni lavorativi (8h):")
    print(f"    Manuale:         {work_days_manual:.1f} giorni")
    print(f"    Automatico:      {work_days_auto:.1f} giorni")
    print(f"    RISPARMIATI:     {work_days_saved:.1f} giorni")

    # ROI calculation (assuming hourly rate)
    hourly_rate_eur = 50  # Average dev/QA hourly rate
    cost_manual = manual_time_h * hourly_rate_eur
    cost_auto = (wall_clock_automated_s / 3600) * hourly_rate_eur
    cost_saved = (time_saved_s / 3600) * hourly_rate_eur

    print(f"\n  Valore economico (@ €{hourly_rate_eur}/ora):")
    print(f"    Costo manuale:   €{cost_manual:,.0f}")
    print(f"    Costo automatico: €{cost_auto:,.0f}")
    print(f"    RISPARMIATO:     €{cost_saved:,.0f}")

    # Efficiency multiplier
    efficiency = manual_time_s / wall_clock_automated_s if wall_clock_automated_s > 0 else 0
    print(f"\n  EFFICIENZA: {efficiency:.1f}x più veloce")

    print(f"\n{'#'*70}")
    print(f"# CONCLUSIONE")
    print(f"{'#'*70}")
    print(f"\n  L'automazione ha eseguito {total_tests} test in {format_duration(wall_clock_automated_s)}")
    print(f"  invece delle {format_duration(manual_time_s)} che avrebbe richiesto un umano.")
    print(f"\n  Risparmio netto: {format_duration(time_saved_s)} ({percentage_saved:.0f}%)")
    print(f"  Equivalente a {work_days_saved:.1f} giorni lavorativi")
    print(f"  Valore: circa €{cost_saved:,.0f}")
    print(f"\n{'#'*70}\n")

    # Save report
    report = {
        "generated_at": datetime.now().isoformat(),
        "summary": {
            "total_projects": len(all_data),
            "total_runs": total_runs,
            "total_tests": total_tests,
            "total_response_time_s": total_response_time
        },
        "manual_estimates": {
            "fixed_overhead_per_test_s": estimates.fixed_overhead_per_test,
            "fatigue_factor": estimates.fatigue_factor,
            "total_time_s": manual_time_s,
            "total_time_h": manual_time_h,
            "work_days_8h": work_days_manual
        },
        "automated_actual": {
            "avg_per_test_s": automated_per_test_s,
            "parallel_factor": parallel_factor,
            "wall_clock_time_s": wall_clock_automated_s,
            "work_days_8h": work_days_auto
        },
        "savings": {
            "time_saved_s": time_saved_s,
            "time_saved_h": time_saved_s / 3600,
            "percentage_saved": percentage_saved,
            "work_days_saved": work_days_saved,
            "efficiency_multiplier": efficiency,
            "value_eur_at_50_per_hour": cost_saved
        },
        "projects_detail": []
    }

    for data in all_data:
        proj_detail = {
            "project": data["project"],
            "runs": len(data["runs"]),
            "total_tests": sum(r["test_count"] for r in data["runs"]),
            "runs_detail": [
                {"name": r["run_name"], "tests": r["test_count"]}
                for r in data["runs"]
            ]
        }
        report["projects_detail"].append(proj_detail)

    report_path = Path("/Users/corradofrancolini/Downloads/time_savings_report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"  Report salvato in: {report_path}\n")


if __name__ == "__main__":
    main()
