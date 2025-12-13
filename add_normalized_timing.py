#!/usr/bin/env python3
"""
Add normalized TIMING column to Google Sheets.
Reads existing TIMING values and adds a normalized version (÷1.35 for 3-parallel factor).
"""

import re
import sys
sys.path.insert(0, '.')

from src.config_loader import ConfigLoader

PARALLEL_FACTOR = 1.35  # 3 browsers in parallel


def parse_timing(timing_str: str) -> tuple:
    """Parse '3.7s → 12.0s' into (3.7, 12.0)"""
    if not timing_str or timing_str.strip() == '':
        return None, None

    # Match pattern like "3.7s → 12.0s" or "3.7s->12.0s"
    match = re.match(r'(\d+\.?\d*)s?\s*[→\->]+\s*(\d+\.?\d*)s?', timing_str)
    if match:
        return float(match.group(1)), float(match.group(2))
    return None, None


def normalize_timing(ttfr: float, total: float, factor: float = PARALLEL_FACTOR) -> str:
    """Create normalized timing string."""
    if ttfr is None or total is None:
        return ""
    norm_ttfr = ttfr / factor
    norm_total = total / factor
    return f"{norm_ttfr:.1f}s → {norm_total:.1f}s"


def add_normalized_column(project_name: str):
    """Add normalized TIMING column to a project's GDoc."""
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
    from src.sheets_client import GoogleSheetsClient

    sheets = GoogleSheetsClient(
        credentials_path=project.google_sheets.credentials_path,
        spreadsheet_id=project.google_sheets.spreadsheet_id,
        drive_folder_id=project.google_sheets.drive_folder_id
    )

    if not sheets.authenticate():
        print("Failed to authenticate to Google Sheets")
        return

    # Get all worksheets (RUNs)
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

            # Find TIMING column
            timing_col = None
            for i, h in enumerate(headers):
                if h == 'TIMING':
                    timing_col = i
                    break

            if timing_col is None:
                print(f"    No TIMING column found")
                continue

            # Check if TIMING (norm) already exists
            norm_col = None
            for i, h in enumerate(headers):
                if 'norm' in h.lower():
                    norm_col = i
                    print(f"    TIMING (norm) already exists at column {i+1}")
                    break

            # If no norm column, we need to insert one after TIMING
            # For simplicity, let's just update the TIMING column to include both
            # Or add data to a new column at the end

            if norm_col is None:
                # Add new header
                new_col_index = len(headers)

                # Resize sheet if needed (add 1 column)
                try:
                    ws.resize(cols=new_col_index + 1)
                except:
                    pass  # May already have enough columns

                # Prepare normalized values
                normalized_values = [['TIMING (norm)']]  # Header

                for row in all_values[1:]:
                    if timing_col < len(row):
                        timing_val = row[timing_col]
                        ttfr, total = parse_timing(timing_val)
                        norm_str = normalize_timing(ttfr, total)
                        normalized_values.append([norm_str])
                    else:
                        normalized_values.append([''])

                # Write to new column
                col_letter = chr(ord('A') + new_col_index)
                range_str = f'{col_letter}1:{col_letter}{len(normalized_values)}'

                ws.update(values=normalized_values, range_name=range_str)
                print(f"    Added TIMING (norm) column at {col_letter}")
                print(f"    Processed {len(normalized_values)-1} rows")
            else:
                print(f"    Skipping - normalized column already exists")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


def main():
    projects = ['silicon-a', 'silicon-b', 'silicon-prod']

    print(f"\n{'#'*60}")
    print(f"# ADD NORMALIZED TIMING COLUMN")
    print(f"# Parallel factor: {PARALLEL_FACTOR}")
    print(f"# Projects: {', '.join(projects)}")
    print(f"{'#'*60}")

    for project in projects:
        add_normalized_column(project)

    print(f"\n{'#'*60}")
    print("# DONE")
    print(f"{'#'*60}\n")


if __name__ == "__main__":
    main()
