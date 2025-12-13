#!/usr/bin/env python3
"""
Trigger CircleCI pipeline from command line.

Usage:
    python trigger_circleci.py -p silicon-b -m auto --tests pending
    python trigger_circleci.py -p silicon-b --new-run
    python trigger_circleci.py --status  # Check running pipelines
"""

import argparse
import json
import os
import sys
from datetime import datetime

try:
    import requests
except ImportError:
    print("Install requests: pip install requests")
    sys.exit(1)


# CircleCI API configuration
CIRCLECI_API_URL = "https://circleci.com/api/v2"
# Set this in environment or replace with your token
CIRCLECI_TOKEN = os.environ.get("CIRCLECI_TOKEN", "")
# Your project slug (e.g., "gh/username/repo" or "github/username/repo")
PROJECT_SLUG = os.environ.get("CIRCLECI_PROJECT_SLUG", "gh/corradofrancolini/chatbot-tester-private")


def trigger_pipeline(project: str, mode: str, tests: str, new_run: bool) -> dict:
    """Trigger a CircleCI pipeline with parameters."""
    if not CIRCLECI_TOKEN:
        print("ERROR: Set CIRCLECI_TOKEN environment variable")
        print("  Get your token at: https://app.circleci.com/settings/user/tokens")
        sys.exit(1)

    url = f"{CIRCLECI_API_URL}/project/{PROJECT_SLUG}/pipeline"

    headers = {
        "Circle-Token": CIRCLECI_TOKEN,
        "Content-Type": "application/json"
    }

    payload = {
        "branch": "main",
        "parameters": {
            "manual_trigger": True,
            "project": project,
            "mode": mode,
            "tests": tests,
            "new_run": new_run
        }
    }

    print(f"\nTriggering CircleCI pipeline...")
    print(f"  Project: {project}")
    print(f"  Mode: {mode}")
    print(f"  Tests: {tests}")
    print(f"  New run: {new_run}")

    response = requests.post(url, headers=headers, json=payload)

    if response.status_code == 201:
        data = response.json()
        print(f"\n✓ Pipeline triggered successfully!")
        print(f"  Pipeline ID: {data.get('id')}")
        print(f"  Number: {data.get('number')}")
        print(f"  State: {data.get('state')}")
        print(f"\n  View at: https://app.circleci.com/pipelines/{PROJECT_SLUG}/{data.get('number')}")
        return data
    else:
        print(f"\n✗ Failed to trigger pipeline")
        print(f"  Status: {response.status_code}")
        print(f"  Response: {response.text}")
        return None


def get_pipeline_status(pipeline_id: str = None) -> list:
    """Get status of recent pipelines."""
    if not CIRCLECI_TOKEN:
        print("ERROR: Set CIRCLECI_TOKEN environment variable")
        sys.exit(1)

    url = f"{CIRCLECI_API_URL}/project/{PROJECT_SLUG}/pipeline"

    headers = {
        "Circle-Token": CIRCLECI_TOKEN
    }

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        data = response.json()
        pipelines = data.get("items", [])[:10]  # Last 10

        print(f"\n{'='*60}")
        print(f"Recent Pipelines for {PROJECT_SLUG}")
        print(f"{'='*60}\n")

        for p in pipelines:
            created = p.get("created_at", "")[:19].replace("T", " ")
            state = p.get("state", "unknown")
            number = p.get("number", "?")

            # State emoji
            state_icon = {
                "created": "🔵",
                "pending": "🟡",
                "running": "🟠",
                "success": "✅",
                "failed": "❌",
                "error": "💥"
            }.get(state, "⚪")

            print(f"  {state_icon} #{number} [{state}] - {created}")

        return pipelines
    else:
        print(f"Failed to get pipelines: {response.status_code}")
        return []


def get_workflow_status(pipeline_id: str) -> list:
    """Get workflow status for a pipeline."""
    if not CIRCLECI_TOKEN:
        return []

    url = f"{CIRCLECI_API_URL}/pipeline/{pipeline_id}/workflow"

    headers = {
        "Circle-Token": CIRCLECI_TOKEN
    }

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        return response.json().get("items", [])
    return []


def main():
    parser = argparse.ArgumentParser(description="Trigger CircleCI pipeline")

    parser.add_argument("-p", "--project", default="silicon-b",
                       help="Project name (default: silicon-b)")
    parser.add_argument("-m", "--mode", default="auto",
                       choices=["auto", "assisted", "train"],
                       help="Test mode (default: auto)")
    parser.add_argument("--tests", default="pending",
                       choices=["all", "pending", "failed"],
                       help="Which tests to run (default: pending)")
    parser.add_argument("--new-run", action="store_true",
                       help="Create new run in Google Sheets")
    parser.add_argument("--status", action="store_true",
                       help="Show recent pipeline status")

    args = parser.parse_args()

    if args.status:
        get_pipeline_status()
    else:
        trigger_pipeline(
            project=args.project,
            mode=args.mode,
            tests=args.tests,
            new_run=args.new_run
        )


if __name__ == "__main__":
    main()
