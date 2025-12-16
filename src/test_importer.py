"""
Test Importer Module

Provides advanced test case import functionality with:
- Multiple source support (file, Google Sheets, URL/API)
- Configurable field mapping
- Strict validation
- Interactive conflict resolution
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional
from dataclasses import dataclass, field

import requests
from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich import box

console = Console()


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class ValidationReport:
    """Report from test validation."""
    valid_tests: List[Dict[str, Any]]
    invalid_tests: List[Tuple[int, Dict[str, Any], List[str]]]  # (row, test, errors)
    total: int = 0
    valid_count: int = 0
    error_count: int = 0

    def __post_init__(self):
        self.total = len(self.valid_tests) + len(self.invalid_tests)
        self.valid_count = len(self.valid_tests)
        self.error_count = len(self.invalid_tests)


@dataclass
class ConflictReport:
    """Report from conflict detection."""
    conflicts: List[Tuple[Dict[str, Any], Dict[str, Any]]]  # (new, existing)
    new_only: List[Dict[str, Any]]
    unchanged: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ImportResult:
    """Result from an import operation."""
    tests: List[Dict[str, Any]]
    validation_report: ValidationReport
    source_type: str = ""  # 'file', 'google_sheets', 'url'
    source_path: str = ""


# =============================================================================
# Field Mapper
# =============================================================================

class FieldMapper:
    """
    Maps custom field names to standard test schema fields.

    Supports automatic detection of common variations and
    interactive configuration for custom mappings.
    """

    # Standard schema fields
    STANDARD_FIELDS = ['id', 'question', 'category', 'expected', 'expected_topics',
                       'followups', 'data', 'tags']

    # Default mappings for common variations
    DEFAULT_MAPPINGS = {
        # Italian
        'domanda': 'question',
        'categoria': 'category',
        'argomenti': 'expected_topics',
        'argomenti_attesi': 'expected_topics',
        'followup': 'followups',
        'dati': 'data',
        'etichette': 'tags',
        'atteso': 'expected',
        'risposta_attesa': 'expected',
        # English variations
        'test_id': 'id',
        'testid': 'id',
        'test id': 'id',
        'topics': 'expected_topics',
        'expected topics': 'expected_topics',
        'follow_ups': 'followups',
        'follow-ups': 'followups',
        'follow ups': 'followups',
        'followup_1': 'followups',
        'followup_2': 'followups',
        'followup_3': 'followups',
        'custom_data': 'data',
        'metadata': 'data',
        'labels': 'tags',
    }

    def __init__(self, custom_mappings: Dict[str, str] = None):
        """
        Initialize mapper with optional custom mappings.

        Args:
            custom_mappings: Dict mapping source field -> standard field
        """
        self.mappings = {**self.DEFAULT_MAPPINGS}
        if custom_mappings:
            self.mappings.update(custom_mappings)

    def detect_mappings(self, headers: List[str]) -> Dict[str, str]:
        """
        Auto-detect mappings from source headers.

        Args:
            headers: List of column/field names from source

        Returns:
            Dict mapping source header -> standard field
        """
        detected = {}
        unmapped = []

        for header in headers:
            normalized = header.lower().strip()

            # Check if already standard
            if normalized in self.STANDARD_FIELDS:
                detected[header] = normalized
            # Check known mappings
            elif normalized in self.mappings:
                detected[header] = self.mappings[normalized]
            # Check for followup pattern (followup1, followup_2, etc.)
            elif re.match(r'followup[_\s]?\d+', normalized):
                detected[header] = 'followups'
            else:
                unmapped.append(header)

        return detected, unmapped

    def apply(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply mappings to transform a source row to standard schema.

        Args:
            row: Source data row

        Returns:
            Transformed row with standard field names
        """
        result = {}
        followups_collected = []

        for key, value in row.items():
            normalized_key = key.lower().strip()

            # Skip empty values
            if value is None or (isinstance(value, str) and not value.strip()):
                continue

            # Determine target field
            if normalized_key in self.STANDARD_FIELDS:
                target = normalized_key
            elif normalized_key in self.mappings:
                target = self.mappings[normalized_key]
            elif re.match(r'followup[_\s]?\d+', normalized_key):
                # Collect followup columns into array
                followups_collected.append(str(value))
                continue
            else:
                # Keep unmapped fields in 'data'
                if 'data' not in result:
                    result['data'] = {}
                result['data'][key] = value
                continue

            # Handle special field types
            if target == 'expected_topics':
                # Convert comma-separated string to list
                if isinstance(value, str):
                    result[target] = [t.strip() for t in value.split(',') if t.strip()]
                elif isinstance(value, list):
                    result[target] = value
            elif target == 'followups':
                # Collect into list
                if isinstance(value, str):
                    followups_collected.append(value)
                elif isinstance(value, list):
                    followups_collected.extend(value)
            elif target == 'tags':
                # Convert comma-separated string to list
                if isinstance(value, str):
                    result[target] = [t.strip() for t in value.split(',') if t.strip()]
                elif isinstance(value, list):
                    result[target] = value
            elif target == 'data':
                # Merge into data dict
                if isinstance(value, dict):
                    if 'data' not in result:
                        result['data'] = {}
                    result['data'].update(value)
                elif isinstance(value, str):
                    try:
                        parsed = json.loads(value)
                        if isinstance(parsed, dict):
                            if 'data' not in result:
                                result['data'] = {}
                            result['data'].update(parsed)
                    except json.JSONDecodeError:
                        pass
            else:
                result[target] = str(value).strip() if isinstance(value, str) else value

        # Add collected followups
        if followups_collected:
            result['followups'] = followups_collected

        return result

    def interactive_configure(self, headers: List[str]) -> Dict[str, str]:
        """
        Interactively configure mappings for unknown headers.

        Args:
            headers: List of source headers

        Returns:
            Complete mapping dict
        """
        detected, unmapped = self.detect_mappings(headers)

        if not unmapped:
            return detected

        console.print("\n  [yellow]Campi non riconosciuti:[/yellow]")
        for header in unmapped:
            console.print(f"    · {header}")

        console.print("\n  [bold]Configura mappatura:[/bold]")
        console.print("  Campi disponibili: id, question, category, expected,")
        console.print("                     expected_topics, followups, data, tags")
        console.print("  Premi INVIO per saltare un campo\n")

        for header in unmapped:
            target = Prompt.ask(
                f"  '{header}' → ",
                default=""
            )
            if target and target.lower() in self.STANDARD_FIELDS:
                detected[header] = target.lower()
                self.mappings[header.lower()] = target.lower()

        return detected


# =============================================================================
# Test Validator
# =============================================================================

class TestValidator:
    """
    Validates test cases against the standard schema.

    Performs strict validation with detailed error reporting.
    """

    REQUIRED_FIELDS = ['question']

    FIELD_TYPES = {
        'id': str,
        'question': str,
        'category': str,
        'expected': str,
        'expected_topics': list,
        'followups': list,
        'data': dict,
        'tags': list,
    }

    def validate(self, test: Dict[str, Any], row_num: int = 0) -> Tuple[bool, List[str]]:
        """
        Validate a single test case.

        Args:
            test: Test case dict
            row_num: Row number for error messages

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []

        # Check required fields
        for field in self.REQUIRED_FIELDS:
            if field not in test or not test[field]:
                errors.append(f"campo '{field}' mancante o vuoto")

        # Check field types
        for field, expected_type in self.FIELD_TYPES.items():
            if field in test and test[field] is not None:
                value = test[field]

                if expected_type == str and not isinstance(value, str):
                    errors.append(f"'{field}' deve essere una stringa")

                elif expected_type == list:
                    if not isinstance(value, list):
                        errors.append(f"'{field}' deve essere un array")
                    elif field == 'expected_topics':
                        # Check list items are strings
                        for i, item in enumerate(value):
                            if not isinstance(item, str):
                                errors.append(f"'{field}[{i}]' deve essere una stringa")

                elif expected_type == dict and not isinstance(value, dict):
                    errors.append(f"'{field}' deve essere un oggetto")

        # Validate ID format (if present)
        if 'id' in test and test['id']:
            test_id = test['id']
            if not re.match(r'^[A-Za-z0-9_\-]+$', str(test_id)):
                errors.append("'id' contiene caratteri non validi (usa solo lettere, numeri, _, -)")

        return len(errors) == 0, errors

    def validate_batch(self, tests: List[Dict[str, Any]]) -> ValidationReport:
        """
        Validate a batch of test cases.

        Args:
            tests: List of test case dicts

        Returns:
            ValidationReport with valid/invalid tests separated
        """
        valid_tests = []
        invalid_tests = []

        for i, test in enumerate(tests, start=1):
            is_valid, errors = self.validate(test, row_num=i)

            if is_valid:
                # Auto-generate ID if missing
                if 'id' not in test or not test['id']:
                    test['id'] = f"TEST_{i:03d}"
                valid_tests.append(test)
            else:
                invalid_tests.append((i, test, errors))

        return ValidationReport(
            valid_tests=valid_tests,
            invalid_tests=invalid_tests
        )


# =============================================================================
# Conflict Resolver
# =============================================================================

class ConflictResolver:
    """
    Handles conflicts between new and existing test cases.

    Provides interactive resolution for each conflict.
    """

    def __init__(self, existing_tests: List[Dict[str, Any]]):
        """
        Initialize with existing tests.

        Args:
            existing_tests: List of existing test case dicts
        """
        self.existing = {t.get('id', ''): t for t in existing_tests if t.get('id')}

    def find_conflicts(self, new_tests: List[Dict[str, Any]]) -> ConflictReport:
        """
        Find conflicts between new and existing tests.

        Args:
            new_tests: List of new test case dicts

        Returns:
            ConflictReport with conflicts and new-only tests separated
        """
        conflicts = []
        new_only = []

        for test in new_tests:
            test_id = test.get('id', '')
            if test_id in self.existing:
                conflicts.append((test, self.existing[test_id]))
            else:
                new_only.append(test)

        return ConflictReport(conflicts=conflicts, new_only=new_only)

    def resolve_interactive(self, conflicts: List[Tuple[Dict, Dict]]) -> List[Dict[str, Any]]:
        """
        Interactively resolve each conflict.

        Args:
            conflicts: List of (new_test, existing_test) tuples

        Returns:
            List of resolved tests to include
        """
        resolved = []
        apply_to_all = None  # 's' = overwrite all, 'm' = keep all

        for new_test, existing_test in conflicts:
            test_id = new_test.get('id', 'Unknown')

            if apply_to_all == 's':
                resolved.append(new_test)
                continue
            elif apply_to_all == 'm':
                continue

            # Show comparison
            console.print(f"\n  [yellow]Conflitto: {test_id}[/yellow]")

            existing_q = existing_test.get('question', '')[:60]
            new_q = new_test.get('question', '')[:60]

            console.print(f"  [dim]Esistente:[/dim] {existing_q}{'...' if len(existing_test.get('question', '')) > 60 else ''}")
            console.print(f"  [dim]Nuovo:    [/dim] {new_q}{'...' if len(new_test.get('question', '')) > 60 else ''}")

            console.print("\n  [s] Sovrascrivi  [m] Mantieni esistente  [r] Rinomina nuovo")
            console.print("  [S] Sovrascrivi TUTTI  [M] Mantieni TUTTI")

            choice = Prompt.ask("  Azione", choices=["s", "m", "r", "S", "M"], default="m")

            if choice == 's':
                resolved.append(new_test)
            elif choice == 'r':
                new_id = Prompt.ask("  Nuovo ID", default=f"{test_id}_new")
                new_test['id'] = new_id
                resolved.append(new_test)
            elif choice == 'S':
                apply_to_all = 's'
                resolved.append(new_test)
            elif choice == 'M':
                apply_to_all = 'm'
            # 'm' = skip this test (keep existing)

        return resolved


# =============================================================================
# Test Importer
# =============================================================================

class TestImporter:
    """
    Main orchestrator for test imports from various sources.

    Supports:
    - Local files (JSON, CSV, Excel)
    - Google Sheets
    - URL/API endpoints
    """

    def __init__(self,
                 mapper: FieldMapper = None,
                 validator: TestValidator = None,
                 sheets_client: Any = None):
        """
        Initialize importer with optional components.

        Args:
            mapper: Custom FieldMapper instance
            validator: Custom TestValidator instance
            sheets_client: GoogleSheetsClient instance for Sheets import
        """
        self.mapper = mapper or FieldMapper()
        self.validator = validator or TestValidator()
        self.sheets = sheets_client

    # =========================================================================
    # File Import
    # =========================================================================

    def import_from_file(self, path: str) -> ImportResult:
        """
        Import tests from a local file.

        Args:
            path: Path to JSON, CSV, or Excel file

        Returns:
            ImportResult with tests and validation report
        """
        file_path = Path(path)
        ext = file_path.suffix.lower()

        if ext == '.json':
            raw = self._load_json(file_path)
        elif ext == '.csv':
            raw = self._load_csv(file_path)
        elif ext in ['.xlsx', '.xls']:
            raw = self._load_excel(file_path)
        else:
            raise ValueError(f"Formato non supportato: {ext}")

        result = self._process_raw_data(raw)
        result.source_type = 'file'
        result.source_path = str(path)

        return result

    def _load_json(self, path: Path) -> List[Dict[str, Any]]:
        """Load tests from JSON file."""
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Handle both array and object with 'tests' key
        if isinstance(data, list):
            return data
        elif isinstance(data, dict):
            return data.get('tests', data.get('data', []))
        else:
            return []

    def _load_csv(self, path: Path) -> List[Dict[str, Any]]:
        """Load tests from CSV file."""
        import csv

        tests = []
        with open(path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                tests.append(dict(row))

        return tests

    def _load_excel(self, path: Path) -> List[Dict[str, Any]]:
        """Load tests from Excel file."""
        try:
            import pandas as pd
        except ImportError:
            raise ImportError("pandas e openpyxl richiesti per import Excel. "
                              "Installa con: pip install pandas openpyxl")

        df = pd.read_excel(path)
        tests = []

        for _, row in df.iterrows():
            test = {}
            for col in df.columns:
                value = row[col]
                # Handle NaN values
                if pd.notna(value):
                    test[col] = value
            tests.append(test)

        return tests

    # =========================================================================
    # Google Sheets Import
    # =========================================================================

    def import_from_google_sheets(self,
                                   spreadsheet_id: str,
                                   sheet_name: str = None) -> ImportResult:
        """
        Import tests from Google Sheets.

        Args:
            spreadsheet_id: Google Sheets spreadsheet ID
            sheet_name: Name of worksheet/tab (default: first sheet or 'Tests')

        Returns:
            ImportResult with tests and validation report
        """
        if not self.sheets:
            raise ValueError("GoogleSheetsClient non configurato")

        try:
            import gspread
        except ImportError:
            raise ImportError("gspread richiesto per import da Google Sheets")

        # Get spreadsheet
        try:
            spreadsheet = self.sheets._gspread_client.open_by_key(spreadsheet_id)
        except Exception as e:
            raise ValueError(f"Impossibile aprire spreadsheet: {e}")

        # Get worksheet
        worksheet = None
        if sheet_name:
            try:
                worksheet = spreadsheet.worksheet(sheet_name)
            except gspread.WorksheetNotFound:
                raise ValueError(f"Foglio '{sheet_name}' non trovato")
        else:
            # Try 'Tests' sheet first, then first sheet
            try:
                worksheet = spreadsheet.worksheet('Tests')
            except gspread.WorksheetNotFound:
                worksheet = spreadsheet.sheet1

        # Read all data
        records = worksheet.get_all_records()

        result = self._process_raw_data(records)
        result.source_type = 'google_sheets'
        result.source_path = f"{spreadsheet_id}/{sheet_name or 'default'}"

        return result

    # =========================================================================
    # URL Import
    # =========================================================================

    def import_from_url(self,
                        url: str,
                        headers: Dict[str, str] = None,
                        timeout: int = 30) -> ImportResult:
        """
        Import tests from URL/API endpoint.

        Args:
            url: URL returning JSON data
            headers: Optional HTTP headers
            timeout: Request timeout in seconds

        Returns:
            ImportResult with tests and validation report
        """
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
        except requests.exceptions.Timeout:
            raise ValueError(f"Timeout connessione a {url}")
        except requests.exceptions.RequestException as e:
            raise ValueError(f"Errore richiesta: {e}")

        try:
            data = response.json()
        except json.JSONDecodeError:
            raise ValueError("La risposta non è JSON valido")

        # Handle both array and object with nested tests
        if isinstance(data, list):
            raw = data
        elif isinstance(data, dict):
            raw = data.get('tests', data.get('data', data.get('items', [])))
        else:
            raise ValueError("Formato risposta non supportato")

        result = self._process_raw_data(raw)
        result.source_type = 'url'
        result.source_path = url

        return result

    # =========================================================================
    # Processing
    # =========================================================================

    def _process_raw_data(self, raw: List[Dict[str, Any]]) -> ImportResult:
        """
        Process raw data through mapping and validation pipeline.

        Args:
            raw: Raw data rows

        Returns:
            ImportResult with processed tests
        """
        # Apply field mapping
        mapped = [self.mapper.apply(row) for row in raw]

        # Validate
        validation = self.validator.validate_batch(mapped)

        return ImportResult(
            tests=validation.valid_tests,
            validation_report=validation
        )


# =============================================================================
# Helper Functions
# =============================================================================

def extract_spreadsheet_id(url_or_id: str) -> str:
    """
    Extract Google Sheets spreadsheet ID from URL or return as-is if already ID.

    Args:
        url_or_id: Either a spreadsheet ID or full Google Sheets URL

    Returns:
        Spreadsheet ID
    """
    # If it's already just an ID (alphanumeric with dashes/underscores)
    if re.match(r'^[\w\-]+$', url_or_id) and 'google.com' not in url_or_id:
        return url_or_id

    # Extract from URL patterns:
    # https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit
    # https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit#gid=0
    match = re.search(r'/spreadsheets/d/([a-zA-Z0-9_-]+)', url_or_id)
    if match:
        return match.group(1)

    # Return as-is if no pattern matched
    return url_or_id


def fetch_json_from_url(url: str,
                        headers: Dict[str, str] = None,
                        timeout: int = 30) -> Any:
    """
    Fetch and parse JSON from URL.

    Args:
        url: URL to fetch
        headers: Optional HTTP headers
        timeout: Request timeout in seconds

    Returns:
        Parsed JSON data

    Raises:
        ValueError: On connection or parsing errors
    """
    try:
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.Timeout:
        raise ValueError(f"Timeout connessione a {url}")
    except requests.exceptions.RequestException as e:
        raise ValueError(f"Errore richiesta: {e}")
    except json.JSONDecodeError:
        raise ValueError("La risposta non è JSON valido")
