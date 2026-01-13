"""
Google Sheets Client - Google Sheets report integration

Handles:
- OAuth authentication
- Creating/managing RUN sheets
- Creating/updating reports
- Uploading screenshots to Drive
- Skipping already completed tests in current RUN
- Thread-safe for parallel execution
"""

import os
import re
import json
import threading
import asyncio
from pathlib import Path
from typing import Optional, List, Dict, Any, TYPE_CHECKING
from datetime import datetime
from dataclasses import dataclass, field

try:
    import gspread
    from google.oauth2.credentials import Credentials
    from google.oauth2.service_account import Credentials as ServiceAccountCredentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    GOOGLE_AVAILABLE = True
except ImportError:
    GOOGLE_AVAILABLE = False

# Per type hints senza import circolari
if TYPE_CHECKING:
    from .config_loader import RunConfig


# Scopes necessari
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive.file'
]


def escape_formula(value: Any) -> str:
    """
    Escape valori che potrebbero essere interpretati come formule da Google Sheets.

    Se un valore inizia con =, +, -, @, aggiungi un apostrofo ' all'inizio
    per forzare Google Sheets a trattarlo come testo.

    Args:
        value: Valore da escape (può essere str, int, None, etc.)

    Returns:
        Stringa escaped safe per Google Sheets
    """
    if value is None:
        return ""

    str_value = str(value)

    # Se inizia con caratteri che potrebbero essere formule, aggiungi '
    if str_value and str_value[0] in ('=', '+', '-', '@'):
        return f"'{str_value}"

    return str_value


# Import shared models
from .models import TestResult, ScreenshotUrls
from .models.sheet_schema import COLUMNS, COLUMN_WIDTHS, COLUMN_INDEX, CHAR_LIMITS
from .clients.base import BaseClient


class GoogleSheetsClient(BaseClient):
    """
    Client per Google Sheets con supporto OAuth e gestione RUN.

    Features:
    - Autenticazione OAuth con token refresh
    - Creazione fogli per ogni RUN
    - Append righe al report
    - Check test già eseguiti nella RUN corrente
    - Upload screenshot su Drive

    Usage:
        client = GoogleSheetsClient(
            credentials_path="credentials.json",
            spreadsheet_id="xxx",
            drive_folder_id="yyy"
        )

        if client.authenticate():
            # Crea o riprende RUN
            client.setup_run_sheet(run_config)
            client.append_result(result)
    """

    # Schema imported from models.sheet_schema
    COLUMNS = COLUMNS
    COLUMN_WIDTHS = COLUMN_WIDTHS

    def __init__(self,
                 credentials_path: str,
                 spreadsheet_id: str,
                 drive_folder_id: str = "",
                 token_path: Optional[str] = None,
                 column_preset: str = "standard",
                 column_list: Optional[List[str]] = None):
        """
        Inizializza il client.

        Args:
            credentials_path: Path al file OAuth credentials
            spreadsheet_id: ID dello spreadsheet Google
            drive_folder_id: ID cartella Drive per screenshot (opzionale)
            token_path: Path per salvare il token (default: accanto a credentials)
            column_preset: Preset colonne (standard, minimal, custom) - per compatibilità
            column_list: Lista colonne custom - per compatibilità
        """
        # Store column config for future use
        self.column_preset = column_preset
        self.column_list = column_list
        if not GOOGLE_AVAILABLE:
            raise ImportError("Dipendenze Google non installate. Esegui: pip install gspread google-auth google-auth-oauthlib google-api-python-client")

        self.credentials_path = Path(credentials_path)
        self.spreadsheet_id = spreadsheet_id
        self.drive_folder_id = drive_folder_id

        # Token path
        if token_path:
            self.token_path = Path(token_path)
        else:
            self.token_path = self.credentials_path.parent / "token.json"

        # Clients (inizializzati dopo auth)
        self._credentials: Optional[Credentials] = None
        self._gspread_client = None
        self._drive_service = None
        self._spreadsheet = None
        self._worksheet = None  # Foglio RUN corrente

        # Stato RUN
        self._current_run: Optional[int] = None

        # Cache test esistenti nella RUN corrente
        self._existing_tests: set = set()

    @property
    def is_authenticated(self) -> bool:
        """Verifica se autenticato"""
        return self._credentials is not None and self._credentials.valid

    @property
    def current_run(self) -> Optional[int]:
        """Numero RUN corrente"""
        return self._current_run

    def _is_service_account_file(self, path: Path) -> bool:
        """Check if credentials file is a Service Account key."""
        try:
            with open(path) as f:
                data = json.load(f)
            return data.get('type') == 'service_account'
        except Exception:
            return False

    def is_available(self) -> bool:
        """Check availability."""
        return self.authenticate()

    def authenticate(self) -> bool:
        """
        Esegue autenticazione Google (Service Account o OAuth).

        Rileva automaticamente il tipo di credenziali:
        - Service Account: usa direttamente il file JSON (nessun token, nessuna scadenza)
        - OAuth: richiede token.json e refresh periodico

        Returns:
            True se autenticazione riuscita
        """
        try:
            creds = None

            # Verifica se è un Service Account (preferito per server)
            if self.credentials_path.exists() and self._is_service_account_file(self.credentials_path):
                # Service Account - nessun token necessario, nessuna scadenza
                creds = ServiceAccountCredentials.from_service_account_file(
                    str(self.credentials_path),
                    scopes=SCOPES
                )
                self._credentials = creds

                # Inizializza clients
                self._gspread_client = gspread.authorize(creds)
                self._spreadsheet = self._gspread_client.open_by_key(self.spreadsheet_id)

                # Drive service per upload
                if self.drive_folder_id:
                    self._drive_service = build('drive', 'v3', credentials=creds)

                return True

            # Fallback: OAuth flow (per uso locale/interattivo)
            # Prova a caricare token esistente
            if self.token_path.exists():
                creds = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)

            # Refresh se scaduto
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except:
                    creds = None

            # Nuovo login se necessario
            if not creds or not creds.valid:
                if not self.credentials_path.exists():
                    print(f"✗ File credentials non trovato: {self.credentials_path}")
                    return False

                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.credentials_path), SCOPES
                )
                creds = flow.run_local_server(port=0)

                # Salva token
                with open(self.token_path, 'w') as f:
                    f.write(creds.to_json())

            self._credentials = creds

            # Inizializza clients
            self._gspread_client = gspread.authorize(creds)
            self._spreadsheet = self._gspread_client.open_by_key(self.spreadsheet_id)

            # Drive service per upload
            if self.drive_folder_id:
                self._drive_service = build('drive', 'v3', credentials=creds)

            pass  # Feedback gestito dal chiamante
            return True

        except Exception as e:
            print(f"✗ Errore autenticazione Google: {e}")
            return False

    # ==================== GESTIONE RUN ====================

    def get_next_run_number(self) -> int:
        """
        Trova il prossimo numero RUN disponibile.
        Scansiona i fogli esistenti con pattern "Run NNN".

        Returns:
            Prossimo numero RUN (1 se nessuna RUN esiste)
        """
        if not self._spreadsheet:
            return 1

        run_numbers = []
        for worksheet in self._spreadsheet.worksheets():
            match = re.match(r'^Run (\d{3})', worksheet.title)
            if match:
                run_numbers.append(int(match.group(1)))

        return max(run_numbers) + 1 if run_numbers else 1

    def get_run_sheet(self, run_number: int) -> Optional[Any]:
        """
        Trova il foglio di una RUN esistente.

        Cerca fogli con qualsiasi prefisso (Run, GGP, PARA, ecc.)
        che contengano il numero specificato nel formato XXX.

        Args:
            run_number: Numero RUN da cercare

        Returns:
            Worksheet o None se non trovato
        """
        if not self._spreadsheet:
            return None

        # Formato numero a 3 cifre (es. 037, 038)
        number_pattern = f"{run_number:03d}"

        # Prima cerca con prefisso "Run" (priorità ai test standard)
        for worksheet in self._spreadsheet.worksheets():
            if worksheet.title.startswith(f"Run {number_pattern}"):
                return worksheet

        # Se non trova, cerca qualsiasi foglio con quel numero (GGP, PARA, ecc.)
        for worksheet in self._spreadsheet.worksheets():
            if number_pattern in worksheet.title:
                return worksheet

        return None

    def create_run_sheet(self,
                         run_number: int,
                         env: str = "DEV",
                         mode: str = "train",
                         prompt_version: str = "",
                         model_version: str = "") -> Optional[Any]:
        """
        Crea un nuovo foglio per una RUN.

        Args:
            run_number: Numero RUN
            env: Ambiente (DEV/PROD)
            mode: Modalità test (train/assisted/auto)
            prompt_version: Versione prompt (opzionale)
            model_version: Versione modello (opzionale)

        Returns:
            Worksheet creato o None
        """
        if not self._spreadsheet:
            return None

        try:
            # Costruisci nome foglio
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
            sheet_name = f"Run {run_number:03d} [{env}] {mode} - {timestamp}"

            # Crea foglio
            worksheet = self._spreadsheet.add_worksheet(
                title=sheet_name,
                rows=1000,
                cols=len(self.COLUMNS)
            )

            # Aggiungi header
            worksheet.update('A1', [self.COLUMNS])

            # Formatta header (bold, centrato) - 23 colonne (A-W)
            worksheet.format('A1:W1', {
                'textFormat': {'bold': True},
                'horizontalAlignment': 'CENTER'
            })

            # Imposta larghezze colonne
            self._set_column_widths(worksheet)

            print(f"✓ Creato foglio: {sheet_name}")
            return worksheet

        except Exception as e:
            print(f"✗ Errore creazione foglio RUN: {e}")
            return None

    def _set_column_widths(self, worksheet) -> None:
        """Imposta le larghezze delle colonne"""
        try:
            requests = []
            for i, width in enumerate(self.COLUMN_WIDTHS):
                requests.append({
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": worksheet.id,
                            "dimension": "COLUMNS",
                            "startIndex": i,
                            "endIndex": i + 1
                        },
                        "properties": {"pixelSize": width},
                        "fields": "pixelSize"
                    }
                })

            self._spreadsheet.batch_update({"requests": requests})
        except Exception as e:
            print(f"! Errore impostazione larghezze colonne: {e}")

    def setup_run_sheet(self,
                        run_config: 'RunConfig',
                        force_new: bool = False) -> bool:
        """
        Imposta il foglio per la RUN corrente.
        Riprende RUN esistente o ne crea una nuova.

        Args:
            run_config: Configurazione RUN
            force_new: Forza creazione nuova RUN

        Returns:
            True se setup riuscito
        """
        # Se c'è una RUN attiva e non forziamo, riprendi
        if run_config.active_run and not force_new:
            worksheet = self.get_run_sheet(run_config.active_run)
            if worksheet:
                self._worksheet = worksheet
                self._current_run = run_config.active_run
                self._load_existing_tests()
                print(f"✓ Continuo su: {worksheet.title}")
                return True

        # Crea nuova RUN
        run_number = self.get_next_run_number()
        worksheet = self.create_run_sheet(
            run_number=run_number,
            env=run_config.env,
            mode=run_config.mode,
            prompt_version=run_config.prompt_version,
            model_version=run_config.model_version
        )

        if worksheet:
            self._worksheet = worksheet
            self._current_run = run_number
            self._existing_tests = set()  # Nuova RUN, nessun test

            # Aggiorna run_config
            run_config.active_run = run_number
            run_config.run_start = datetime.now().isoformat()
            run_config.tests_completed = 0

            return True

        return False

    def get_all_run_numbers(self) -> List[int]:
        """
        Ottiene tutti i numeri RUN esistenti.

        Returns:
            Lista ordinata di numeri RUN
        """
        if not self._spreadsheet:
            return []

        run_numbers = []
        for worksheet in self._spreadsheet.worksheets():
            match = re.match(r'^Run (\d{3})', worksheet.title)
            if match:
                run_numbers.append(int(match.group(1)))

        return sorted(run_numbers)

    def get_run_info(self, run_number: int) -> Optional[Dict[str, Any]]:
        """
        Ottiene informazioni su una RUN specifica.

        Args:
            run_number: Numero RUN

        Returns:
            Dizionario con info o None
        """
        worksheet = self.get_run_sheet(run_number)
        if not worksheet:
            return None

        try:
            # Parse nome foglio
            # Format: "Run 015 [DEV] train - 2025-12-02 10:30"
            title = worksheet.title
            match = re.match(
                r'Run (\d{3}) \[(\w+)\] (\w+) - (.+)',
                title
            )

            # Conta test
            test_ids = worksheet.col_values(1)[1:]  # Skip header

            info = {
                'run_number': run_number,
                'title': title,
                'tests_count': len(test_ids),
                'worksheet': worksheet
            }

            if match:
                info['env'] = match.group(2)
                info['mode'] = match.group(3)
                info['timestamp'] = match.group(4)

            return info

        except Exception as e:
            print(f"! Errore lettura info RUN: {e}")
            return None

    # ==================== GESTIONE TEST ====================

    def _load_existing_tests(self) -> None:
        """Carica gli ID dei test già nel foglio RUN corrente"""
        if not self._worksheet:
            self._existing_tests = set()
            return

        try:
            col_values = self._worksheet.col_values(1)  # Prima colonna
            self._existing_tests = set(col_values[1:])  # Skip header
        except:
            self._existing_tests = set()

    def is_test_completed(self, test_id: str) -> bool:
        """
        Verifica se un test è già nella RUN corrente.

        Args:
            test_id: ID del test

        Returns:
            True se già completato
        """
        return test_id in self._existing_tests

    def get_completed_tests(self) -> set[str]:
        """Ritorna set dei test già completati nella RUN corrente"""
        return self._existing_tests.copy()

    def set_columns_for_test_file(self,
                                   test_file_name: str,
                                   by_test_file: Dict[str, Any],
                                   default_preset: str = "standard",
                                   default_list: Optional[List[str]] = None) -> None:
        """
        Configura colonne per test file specifico.

        Args:
            test_file_name: Nome del file test (es. "tests.json")
            by_test_file: Configurazione per file specifici
            default_preset: Preset di default
            default_list: Lista colonne custom di default
        """
        # Cerca configurazione per questo file
        file_config = by_test_file.get(test_file_name, {})
        if file_config:
            self.column_preset = file_config.get('preset', default_preset)
            self.column_list = file_config.get('custom', default_list)
        else:
            self.column_preset = default_preset
            self.column_list = default_list

    def ensure_headers(self) -> None:
        """Assicura che le intestazioni siano presenti"""
        if not self._worksheet:
            return

        try:
            first_row = self._worksheet.row_values(1)
            if not first_row or first_row != self.COLUMNS:
                self._worksheet.update('A1', [self.COLUMNS])
        except:
            self._worksheet.update('A1', [self.COLUMNS])

    # Altezza default per righe con screenshot (in pixel)
    DEFAULT_ROW_HEIGHT = 120

    def append_result(self, result: TestResult, row_height: Optional[int] = None) -> bool:
        """
        Aggiunge un risultato al report.

        Args:
            result: TestResult da aggiungere
            row_height: Altezza riga in pixel (default: DEFAULT_ROW_HEIGHT se c'è screenshot)

        Returns:
            True se aggiunta riuscita
        """
        if not self._worksheet:
            print("✗ Nessun foglio RUN attivo")
            return False

        try:
            # Prepara valori screenshot
            screenshot_formula = ""
            screenshot_view_url = ""
            has_screenshot = False

            if result.screenshot_urls:
                # Nuovo formato: usa IMAGE() per thumbnail
                if result.screenshot_urls.image_url:
                    # =IMAGE(url, 2) -> mode 2 = fit to cell
                    screenshot_formula = f'=IMAGE("{result.screenshot_urls.image_url}", 2)'
                    has_screenshot = True
                screenshot_view_url = result.screenshot_urls.view_url
            elif result.screenshot_url:
                # Legacy: URL singolo (mantieni retrocompatibilità)
                screenshot_view_url = result.screenshot_url

            # Helper per formattare score (0-1 -> percentuale)
            def fmt_score(val):
                return f"{val:.0%}" if val is not None else ""

            # 23 colonne: TEST ID, DATE, MODE, QUESTION, CONVERSATION, SCREENSHOT,
            # SCREENSHOT URL, PROMPT VER, MODEL VER, ENV, TIMING, RESULT, BASELINE, NOTES, LS REPORT, LS TRACE LINK,
            # SEMANTIC, JUDGE, GROUND, FAITH, RELEV, OVERALL, JUDGE REASON
            row = [
                result.test_id,
                result.date,
                result.mode,
                result.question,
                result.conversation,
                screenshot_formula,                     # SCREENSHOT: immagine inline
                screenshot_view_url,                    # SCREENSHOT URL: link alta risoluzione
                result.prompt_version,                  # PROMPT VER: da run config
                result.model_version,                   # MODEL VER: provider/modello
                result.environment or "DEV",            # ENV: default DEV
                result.timing,                          # TIMING: "TTFR → Total"
                "",                                     # RESULT: vuoto (compilato dal reviewer)
                "",                                     # BASELINE: vuoto (checkbox golden answer)
                "",                                     # NOTES: vuoto (note del reviewer)
                escape_formula(result.langsmith_report), # LS REPORT: report LangSmith (escaped)
                result.langsmith_url,                   # LS TRACE LINK: link al trace
                # Evaluation metrics
                fmt_score(result.semantic_score),       # SEMANTIC
                fmt_score(result.judge_score),          # JUDGE
                fmt_score(result.groundedness),         # GROUND
                fmt_score(result.faithfulness),         # FAITH
                fmt_score(result.relevance),            # RELEV
                fmt_score(result.overall_score),        # OVERALL
                result.judge_reasoning                  # JUDGE REASON
            ]

            self._worksheet.append_row(row, value_input_option='USER_ENTERED')
            self._existing_tests.add(result.test_id)

            # Auto-resize riga se c'è screenshot
            if has_screenshot:
                # Trova il numero della riga appena aggiunta
                row_count = len(self._worksheet.col_values(1))
                height = row_height or self.DEFAULT_ROW_HEIGHT
                self.set_row_height(row_count, height)

            return True
        except Exception as e:
            print(f"✗ Errore append riga: {e}")
            return False

    def append_results(self, results: List[TestResult], row_height: Optional[int] = None) -> int:
        """
        Aggiunge più risultati in batch.

        Args:
            results: Lista TestResult
            row_height: Altezza righe in pixel (default: DEFAULT_ROW_HEIGHT)

        Returns:
            Numero risultati aggiunti con successo
        """
        if not results:
            return 0

        if not self._worksheet:
            print("✗ Nessun foglio RUN attivo")
            return 0

        try:
            # Trova prima riga disponibile
            start_row = len(self._worksheet.col_values(1)) + 1

            rows = []
            has_any_screenshot = False

            for r in results:
                # Prepara valori screenshot
                screenshot_formula = ""
                screenshot_view_url = ""

                if r.screenshot_urls:
                    if r.screenshot_urls.image_url:
                        screenshot_formula = f'=IMAGE("{r.screenshot_urls.image_url}", 2)'
                        has_any_screenshot = True
                    screenshot_view_url = r.screenshot_urls.view_url
                elif r.screenshot_url:
                    screenshot_view_url = r.screenshot_url

                # Helper per formattare score (0-1 -> percentuale)
                def fmt_score(val):
                    return f"{val:.0%}" if val is not None else ""

                # 23 colonne
                rows.append([
                    r.test_id, r.date, r.mode, r.question, r.conversation,
                    screenshot_formula, screenshot_view_url,
                    r.prompt_version, r.model_version,
                    r.environment or "DEV",           # ENV: default DEV
                    r.timing,                         # TIMING: "TTFR → Total"
                    "",                               # RESULT: vuoto (reviewer)
                    "",                               # BASELINE: vuoto (golden answer)
                    "",                               # NOTES: vuoto (reviewer)
                    escape_formula(r.langsmith_report), # LS REPORT (escaped)
                    r.langsmith_url,                  # LS TRACE LINK
                    # Evaluation metrics
                    fmt_score(r.semantic_score),      # SEMANTIC
                    fmt_score(r.judge_score),         # JUDGE
                    fmt_score(r.groundedness),        # GROUND
                    fmt_score(r.faithfulness),        # FAITH
                    fmt_score(r.relevance),           # RELEV
                    fmt_score(r.overall_score),       # OVERALL
                    r.judge_reasoning                 # JUDGE REASON
                ])

            self._worksheet.append_rows(rows, value_input_option='USER_ENTERED')

            for r in results:
                self._existing_tests.add(r.test_id)

            # Auto-resize righe se ci sono screenshot
            if has_any_screenshot:
                end_row = start_row + len(results) - 1
                height = row_height or self.DEFAULT_ROW_HEIGHT
                self.set_rows_height(start_row, end_row, height)

            return len(results)
        except Exception as e:
            print(f"✗ Errore batch append: {e}")
            return 0

    # ==================== BASELINES (GOLDEN ANSWERS) ====================

    def get_all_baselines(self) -> List[Dict[str, Any]]:
        """
        Recupera tutte le baseline (golden answers) da tutti i fogli RUN.

        Cerca in ogni foglio RUN le righe dove la colonna BASELINE
        contiene un valore truthy (✓, TRUE, 1, X, ecc.).

        Returns:
            Lista di dizionari con i dati delle baseline:
            {
                'test_id': str,
                'question': str,
                'conversation': str,
                'run_number': int,
                'date': str,
                'prompt_version': str,
                'model_version': str,
                'notes': str
            }
        """
        if not self._spreadsheet:
            return []

        baselines = []

        # Indici colonne (0-based)
        col_indices = {col: i for i, col in enumerate(self.COLUMNS)}
        baseline_col = col_indices.get('BASELINE', 12)
        test_id_col = col_indices.get('TEST ID', 0)
        date_col = col_indices.get('DATE', 1)
        question_col = col_indices.get('QUESTION', 3)
        conversation_col = col_indices.get('CONVERSATION', 4)
        prompt_ver_col = col_indices.get('PROMPT VER', 7)
        model_ver_col = col_indices.get('MODEL VER', 8)
        notes_col = col_indices.get('NOTES', 13)

        try:
            for worksheet in self._spreadsheet.worksheets():
                # Estrai numero RUN dal titolo (es. "Run 038 [DEV] auto - 2024-01-15")
                match = re.match(r'^(?:Run|GGP|PARA)\s*(\d{3})', worksheet.title)
                if not match:
                    continue

                run_number = int(match.group(1))

                # Leggi tutti i dati del foglio
                try:
                    all_values = worksheet.get_all_values()
                except Exception:
                    continue

                if len(all_values) < 2:
                    continue  # Solo header o vuoto

                # Salta header
                for row in all_values[1:]:
                    # Verifica che la riga abbia abbastanza colonne
                    if len(row) <= baseline_col:
                        continue

                    # Controlla se BASELINE è marcata
                    baseline_value = row[baseline_col].strip().upper()
                    is_baseline = baseline_value in ('TRUE', '✓', '✔', 'X', '1', 'YES', 'SI', 'SÌ')

                    if not is_baseline:
                        continue

                    # Estrai dati
                    def safe_get(idx: int) -> str:
                        return row[idx] if idx < len(row) else ""

                    baselines.append({
                        'test_id': safe_get(test_id_col),
                        'question': safe_get(question_col),
                        'conversation': safe_get(conversation_col),
                        'run_number': run_number,
                        'date': safe_get(date_col),
                        'prompt_version': safe_get(prompt_ver_col),
                        'model_version': safe_get(model_ver_col),
                        'notes': safe_get(notes_col)
                    })

        except Exception as e:
            print(f"Errore lettura baseline: {e}")

        return baselines

    # ==================== UPLOAD & UTILITY ====================

    def upload_screenshot(self,
                          file_path: Path,
                          test_id: str) -> Optional[ScreenshotUrls]:
        """
        Carica screenshot su Google Drive.

        Args:
            file_path: Path al file screenshot
            test_id: ID del test (per nome file)

        Returns:
            ScreenshotUrls con URL immagine e URL visualizzazione, o None
        """
        if not self._drive_service or not self.drive_folder_id:
            return None

        if not file_path.exists():
            return None

        try:
            # Aggiungi RUN al nome file
            run_prefix = f"Run{self._current_run:03d}_" if self._current_run else ""

            # Metadata file
            file_metadata = {
                'name': f"{run_prefix}{test_id}_{file_path.name}",
                'parents': [self.drive_folder_id]
            }

            # Upload
            media = MediaFileUpload(
                str(file_path),
                mimetype='image/png',
                resumable=True
            )

            file = self._drive_service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, webViewLink'
            ).execute()

            # Rendi pubblico
            self._drive_service.permissions().create(
                fileId=file['id'],
                body={'type': 'anyone', 'role': 'reader'}
            ).execute()

            file_id = file.get('id', '')
            web_view_link = file.get('webViewLink', '')

            # URL diretto per embedding con =IMAGE()
            # Formato: https://drive.google.com/uc?export=view&id=FILE_ID
            image_url = f"https://drive.google.com/uc?export=view&id={file_id}" if file_id else ""

            return ScreenshotUrls(
                image_url=image_url,
                view_url=web_view_link
            )

        except Exception as e:
            print(f"! Errore upload screenshot: {e}")
            return None

    def update_cell(self, row: int, col: int, value: str) -> bool:
        """
        Aggiorna una cella specifica.

        Args:
            row: Numero riga (1-indexed)
            col: Numero colonna (1-indexed)
            value: Valore da inserire

        Returns:
            True se aggiornamento riuscito
        """
        if not self._worksheet:
            return False

        try:
            self._worksheet.update_cell(row, col, value)
            return True
        except:
            return False

    def set_row_height(self, row: int, height_pixels: int = 120) -> bool:
        """
        Imposta l'altezza di una riga specifica.

        Args:
            row: Numero riga (1-indexed)
            height_pixels: Altezza in pixel (default 120 per screenshot)

        Returns:
            True se operazione riuscita
        """
        if not self._worksheet or not self._spreadsheet:
            return False

        try:
            request = {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": self._worksheet.id,
                        "dimension": "ROWS",
                        "startIndex": row - 1,  # 0-indexed
                        "endIndex": row
                    },
                    "properties": {"pixelSize": height_pixels},
                    "fields": "pixelSize"
                }
            }
            self._spreadsheet.batch_update({"requests": [request]})
            return True
        except Exception as e:
            # Non critico, log silenzioso
            return False

    def set_rows_height(self, start_row: int, end_row: int, height_pixels: int = 120) -> bool:
        """
        Imposta l'altezza di un range di righe.

        Args:
            start_row: Prima riga (1-indexed)
            end_row: Ultima riga (1-indexed, inclusa)
            height_pixels: Altezza in pixel

        Returns:
            True se operazione riuscita
        """
        if not self._worksheet or not self._spreadsheet:
            return False

        try:
            request = {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": self._worksheet.id,
                        "dimension": "ROWS",
                        "startIndex": start_row - 1,
                        "endIndex": end_row
                    },
                    "properties": {"pixelSize": height_pixels},
                    "fields": "pixelSize"
                }
            }
            self._spreadsheet.batch_update({"requests": [request]})
            return True
        except Exception as e:
            return False

    def find_test_row(self, test_id: str) -> Optional[int]:
        """
        Trova la riga di un test specifico.

        Args:
            test_id: ID del test

        Returns:
            Numero riga o None
        """
        if not self._worksheet:
            return None

        try:
            cell = self._worksheet.find(test_id)
            return cell.row if cell else None
        except:
            return None

    def get_all_results(self) -> List[Dict[str, Any]]:
        """
        Ottiene tutti i risultati dal foglio RUN corrente.

        Returns:
            Lista di dizionari con i risultati
        """
        if not self._worksheet:
            return []

        try:
            records = self._worksheet.get_all_records()
            return records
        except:
            return []

    def create_new_spreadsheet(self, title: str) -> Optional[str]:
        """
        Crea un nuovo spreadsheet.

        Args:
            title: Titolo del nuovo spreadsheet

        Returns:
            ID del nuovo spreadsheet o None
        """
        try:
            spreadsheet = self._gspread_client.create(title)

            # Aggiungi intestazioni
            worksheet = spreadsheet.sheet1
            worksheet.update('A1', [self.COLUMNS])

            # Condividi con chi ha il link
            spreadsheet.share(None, perm_type='anyone', role='reader')

            return spreadsheet.id
        except Exception as e:
            print(f"✗ Errore creazione spreadsheet: {e}")
            return None


# Import from clients subpackage
from .clients.sheets_setup import GoogleSheetsSetup
from .clients.thread_safe import ThreadSafeSheetsClient, ParallelResultsCollector
