#!/usr/bin/env python3
"""
Run specific tests across multiple projects in parallel.
Each project runs in its own subprocess.
"""

import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime

# Test IDs to run
TESTS = [
    "TEST_006", "TEST_007", "TEST_008", "TEST_009", "TEST_011",
    "TEST_012", "TEST_013", "TEST_014", "TEST_016", "TEST_017",
    "TEST_018", "TEST_020", "TEST_021", "TEST_027", "TEST_028",
    "TEST_034", "TEST_044", "TEST_052", "TEST_053", "TEST_054"
]

# Projects to run
PROJECTS = ["silicon-a", "silicon-b", "silicon-prod"]


def run_project_tests(project: str) -> dict:
    """Run all tests for a single project sequentially."""
    results = {"project": project, "passed": 0, "failed": 0, "errors": []}

    print(f"\n{'='*60}")
    print(f"[{project}] Starting {len(TESTS)} tests...")
    print(f"{'='*60}")

    for i, test_id in enumerate(TESTS, 1):
        print(f"[{project}] ({i}/{len(TESTS)}) Running {test_id}...")

        cmd = [
            sys.executable, "run.py",
            "-p", project,
            "-m", "auto",
            "-t", test_id,
            "--single-turn",
            "--no-interactive"
        ]
        # Only force new run for the first test
        if i == 1:
            cmd.append("--new-run")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 min timeout per test
            )

            if result.returncode == 0:
                results["passed"] += 1
                print(f"[{project}] ({i}/{len(TESTS)}) {test_id}: OK")
            else:
                results["failed"] += 1
                results["errors"].append(f"{test_id}: exit code {result.returncode}")
                print(f"[{project}] ({i}/{len(TESTS)}) {test_id}: FAILED")

        except subprocess.TimeoutExpired:
            results["failed"] += 1
            results["errors"].append(f"{test_id}: timeout")
            print(f"[{project}] ({i}/{len(TESTS)}) {test_id}: TIMEOUT")
        except Exception as e:
            results["failed"] += 1
            results["errors"].append(f"{test_id}: {str(e)}")
            print(f"[{project}] ({i}/{len(TESTS)}) {test_id}: ERROR - {e}")

    print(f"\n[{project}] Complete: {results['passed']}/{len(TESTS)} passed")
    return results


def main():
    start_time = datetime.now()

    print(f"\n{'#'*60}")
    print(f"# PARALLEL TEST RUNNER")
    print(f"# Projects: {', '.join(PROJECTS)}")
    print(f"# Tests per project: {len(TESTS)}")
    print(f"# Total tests: {len(TESTS) * len(PROJECTS)}")
    print(f"# Start: {start_time.strftime('%H:%M:%S')}")
    print(f"{'#'*60}")

    all_results = []

    # Run all projects in parallel
    with ProcessPoolExecutor(max_workers=len(PROJECTS)) as executor:
        futures = {executor.submit(run_project_tests, p): p for p in PROJECTS}

        for future in as_completed(futures):
            project = futures[future]
            try:
                result = future.result()
                all_results.append(result)
            except Exception as e:
                print(f"[{project}] Fatal error: {e}")
                all_results.append({"project": project, "passed": 0, "failed": len(TESTS), "errors": [str(e)]})

    # Summary
    end_time = datetime.now()
    duration = end_time - start_time

    print(f"\n{'#'*60}")
    print(f"# SUMMARY")
    print(f"{'#'*60}")

    total_passed = sum(r["passed"] for r in all_results)
    total_failed = sum(r["failed"] for r in all_results)

    for r in all_results:
        status = "OK" if r["failed"] == 0 else "ISSUES"
        print(f"  {r['project']}: {r['passed']}/{len(TESTS)} passed [{status}]")
        if r["errors"]:
            for err in r["errors"][:3]:  # Show first 3 errors
                print(f"    - {err}")

    print(f"\n  Total: {total_passed}/{len(TESTS) * len(PROJECTS)} passed")
    print(f"  Duration: {duration}")
    print(f"{'#'*60}\n")


if __name__ == "__main__":
    main()
