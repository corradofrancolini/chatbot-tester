#!/usr/bin/env python3
"""
Fix missing screenshots in Google Sheets.
Finds screenshots in local folders and uploads them to Drive,
then updates the corresponding rows in Google Sheets.
"""

import sys
import re
from pathlib import Path
from datetime import datetime

sys.path.insert(0, '.')

from src.config_loader import ConfigLoader
from src.sheets_client import GoogleSheetsClient


def find_latest_screenshot(project_path: Path, test_id: str, after_date: datetime = None) -> Path:
    """Find the most recent screenshot for a test ID."""
    screenshots = []

    for run_dir in project_path.glob("run_*"):
        ss_dir = run_dir / "screenshots"
        if not ss_dir.exists():
            continue

        for ss_file in ss_dir.glob(f"{test_id}.png"):
            mtime = datetime.fromtimestamp(ss_file.stat().st_mtime)
            if after_date and mtime < after_date:
                continue
            screenshots.append((ss_file, mtime))

    if not screenshots:
        return None

    # Return most recent
    screenshots.sort(key=lambda x: x[1], reverse=True)
    return screenshots[0][0]


def fix_screenshots_for_run(project_name: str, run_name: str, after_date: datetime = None):
    """Fix missing screenshots for a specific run."""
    print(f"\n{'='*60}")
    print(f"Processing: {project_name} - {run_name}")
    print(f"{'='*60}")

    loader = ConfigLoader()
    try:
        project = loader.load_project(project_name)
    except Exception as e:
        print(f"  Error loading project: {e}")
        return 0

    sheets = GoogleSheetsClient(
        credentials_path=project.google_sheets.credentials_path,
        spreadsheet_id=project.google_sheets.spreadsheet_id,
        drive_folder_id=project.google_sheets.drive_folder_id
    )

    if not sheets.authenticate():
        print("  Failed to authenticate")
        return 0

    try:
        spreadsheet = sheets._spreadsheet
        ws = spreadsheet.worksheet(run_name)
        all_values = ws.get_all_values()

        if not all_values:
            print("  Empty worksheet")
            return 0

        headers = all_values[0]

        # Find columns
        test_id_col = 0  # TEST ID is always first
        screenshot_col = headers.index('SCREENSHOT') if 'SCREENSHOT' in headers else None
        screenshot_url_col = headers.index('SCREENSHOT URL') if 'SCREENSHOT URL' in headers else None

        if screenshot_col is None:
            print("  No SCREENSHOT column found")
            return 0

        print(f"  SCREENSHOT col: {screenshot_col+1}, URL col: {screenshot_url_col+1 if screenshot_url_col else 'N/A'}")

        reports_path = Path(f"reports/{project_name}")
        fixed_count = 0
        updates = []

        for row_idx, row in enumerate(all_values[1:], 2):  # Start from row 2
            if not row or not row[0]:
                continue

            test_id = row[0]

            # Check if screenshot already exists
            has_screenshot = (screenshot_col < len(row) and
                           row[screenshot_col].strip() and
                           row[screenshot_col].strip() != '')

            if has_screenshot:
                continue

            # Find screenshot locally
            ss_path = find_latest_screenshot(reports_path, test_id, after_date)
            if not ss_path:
                print(f"    {test_id}: No local screenshot found")
                continue

            print(f"    {test_id}: Found {ss_path.parent.parent.name}/{ss_path.name}")

            # Upload to Drive
            urls = sheets.upload_screenshot(ss_path, test_id)
            if not urls:
                print(f"    {test_id}: Upload failed")
                continue

            # Prepare update
            # Column letters (A=0, B=1, etc.)
            ss_col_letter = chr(ord('A') + screenshot_col)
            ss_formula = f'=IMAGE("{urls.image_url}", 2)'

            updates.append({
                'range': f'{ss_col_letter}{row_idx}',
                'values': [[ss_formula]]
            })

            if screenshot_url_col:
                url_col_letter = chr(ord('A') + screenshot_url_col)
                updates.append({
                    'range': f'{url_col_letter}{row_idx}',
                    'values': [[urls.view_url]]
                })

            fixed_count += 1
            print(f"    {test_id}: Uploaded ✓")

        # Batch update
        if updates:
            ws.batch_update(updates, value_input_option='USER_ENTERED')
            print(f"\n  Updated {fixed_count} rows")

        return fixed_count

    except Exception as e:
        print(f"  Error: {e}")
        import traceback
        traceback.print_exc()
        return 0


def get_latest_run_name(project_name: str) -> str:
    """Get the name of the latest run worksheet."""
    loader = ConfigLoader()
    project = loader.load_project(project_name)

    sheets = GoogleSheetsClient(
        credentials_path=project.google_sheets.credentials_path,
        spreadsheet_id=project.google_sheets.spreadsheet_id,
        drive_folder_id=project.google_sheets.drive_folder_id
    )

    if not sheets.authenticate():
        return None

    spreadsheet = sheets._spreadsheet
    worksheets = spreadsheet.worksheets()

    # Find run worksheets and get the latest
    run_sheets = []
    for ws in worksheets:
        if ws.title.lower().startswith('run'):
            # Extract run number
            match = re.search(r'run\s*(\d+)', ws.title.lower())
            if match:
                run_num = int(match.group(1))
                run_sheets.append((run_num, ws.title))

    if not run_sheets:
        return None

    run_sheets.sort(key=lambda x: x[0], reverse=True)
    return run_sheets[0][1]


def main():
    projects = ['silicon-a', 'silicon-b', 'silicon-prod']

    # Use screenshots from today
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    print(f"\n{'#'*60}")
    print(f"# FIX MISSING SCREENSHOTS")
    print(f"# Looking for screenshots from: {today_start.strftime('%Y-%m-%d')}")
    print(f"{'#'*60}")

    total_fixed = 0

    for project in projects:
        print(f"\n  Finding latest run for {project}...")
        run_name = get_latest_run_name(project)

        if not run_name:
            print(f"  No run found for {project}")
            continue

        print(f"  Latest run: {run_name}")
        fixed = fix_screenshots_for_run(project, run_name, today_start)
        total_fixed += fixed

    print(f"\n{'#'*60}")
    print(f"# DONE - Fixed {total_fixed} screenshots total")
    print(f"{'#'*60}\n")


if __name__ == "__main__":
    main()
