#!/usr/bin/env python3
"""
Move TIMING (norm) column to be right after TIMING column.
"""

import sys
sys.path.insert(0, '.')

from src.config_loader import ConfigLoader
from src.sheets_client import GoogleSheetsClient


def fix_column_order(project_name: str):
    """Move TIMING (norm) right after TIMING."""
    print(f"\n{'='*60}")
    print(f"Processing: {project_name}")
    print(f"{'='*60}")

    # Load project config
    loader = ConfigLoader()
    try:
        project = loader.load_project(project_name)
    except Exception as e:
        print(f"Error loading project: {e}")
        return

    # Initialize sheets client
    sheets = GoogleSheetsClient(
        credentials_path=project.google_sheets.credentials_path,
        spreadsheet_id=project.google_sheets.spreadsheet_id,
        drive_folder_id=project.google_sheets.drive_folder_id
    )

    if not sheets.authenticate():
        print("Failed to authenticate to Google Sheets")
        return

    try:
        spreadsheet = sheets._spreadsheet
        worksheets = spreadsheet.worksheets()

        for ws in worksheets:
            if not ws.title.lower().startswith('run'):
                continue

            print(f"\n  Processing {ws.title}...")

            # Get all values
            all_values = ws.get_all_values()
            if not all_values:
                print(f"    Empty sheet")
                continue

            headers = all_values[0]

            # Find TIMING and TIMING (norm) columns
            timing_col = None
            norm_col = None
            for i, h in enumerate(headers):
                if h == 'TIMING':
                    timing_col = i
                elif h == 'TIMING (norm)':
                    norm_col = i

            if timing_col is None:
                print(f"    No TIMING column found")
                continue

            if norm_col is None:
                print(f"    No TIMING (norm) column found")
                continue

            # Check if already in correct position
            if norm_col == timing_col + 1:
                print(f"    Already in correct order (TIMING={timing_col+1}, norm={norm_col+1})")
                continue

            print(f"    TIMING at column {timing_col+1}, TIMING (norm) at column {norm_col+1}")
            print(f"    Moving TIMING (norm) to column {timing_col+2}...")

            # Build new data with columns reordered
            new_data = []
            for row in all_values:
                # Pad row if needed
                while len(row) <= max(timing_col, norm_col):
                    row.append('')

                new_row = []
                for i, val in enumerate(row):
                    if i == norm_col:
                        continue  # Skip norm column (will insert after timing)
                    new_row.append(val)
                    if i == timing_col:
                        # Insert norm value right after timing
                        new_row.append(row[norm_col] if norm_col < len(row) else '')

                new_data.append(new_row)

            # Clear and rewrite sheet
            ws.clear()
            ws.update(values=new_data, range_name='A1')

            print(f"    Done! Columns reordered.")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


def main():
    projects = ['silicon-a', 'silicon-b', 'silicon-prod']

    print(f"\n{'#'*60}")
    print(f"# FIX TIMING COLUMN ORDER")
    print(f"# Move TIMING (norm) right after TIMING")
    print(f"{'#'*60}")

    for project in projects:
        fix_column_order(project)

    print(f"\n{'#'*60}")
    print("# DONE")
    print(f"{'#'*60}\n")


if __name__ == "__main__":
    main()
