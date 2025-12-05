"""
Google Sheets Client - Integrazione report su Google Sheets

Gestisce:
- Autenticazione OAuth
- Creazione/gestione fogli per RUN
- Creazione/aggiornamento report
- Upload screenshot su Drive
- Skip test già completati nella RUN corrente
- Thread-safe per esecuzione parallela
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


@dataclass
class ScreenshotUrls:
    """URL screenshot per embedding e visualizzazione"""
    image_url: str = ""  # URL diretto per =IMAGE()
    view_url: str = ""   # URL per visualizzazione alta risoluzione


@dataclass
class TestResult:
    """Risultato di un singolo test per il report"""
    test_id: str
    date: str
    mode: str  # Train, Assisted, Auto
    question: str
    conversation: str
    screenshot_url: str = ""  # Legacy: URL singolo
    screenshot_urls: Optional[ScreenshotUrls] = None  # Nuovo: entrambi gli URL
    prompt_version: str = ""
    model_version: str = ""
    environment: str = ""
    esito: str = ""  # PASS, FAIL, SKIP, ERROR
    notes: str = ""
    langsmith_url: str = ""


class GoogleSheetsClient:
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
    
    # Colonne standard del report
    COLUMNS = [
        "TEST ID",
        "DATE",
        "MODE",
        "QUESTION",
        "CONVERSATION",
        "SCREENSHOT",      # Immagine inline (thumbnail)
        "SCREENSHOT URL",  # Link alta risoluzione
        "PROMPT VER",
        "MODEL VER",
        "ENV",
        "ESITO",
        "NOTES",
        "LANGSMITH"
    ]

    # Larghezze colonne in pixel
    COLUMN_WIDTHS = [100, 140, 80, 250, 400, 200, 200, 100, 100, 60, 80, 200, 350]
    
    def __init__(self,
                 credentials_path: str,
                 spreadsheet_id: str,
                 drive_folder_id: str = "",
                 token_path: Optional[str] = None):
        """
        Inizializza il client.
        
        Args:
            credentials_path: Path al file OAuth credentials
            spreadsheet_id: ID dello spreadsheet Google
            drive_folder_id: ID cartella Drive per screenshot (opzionale)
            token_path: Path per salvare il token (default: accanto a credentials)
        """
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
    
    def authenticate(self) -> bool:
        """
        Esegue autenticazione OAuth.
        
        Returns:
            True se autenticazione riuscita
        """
        try:
            creds = None
            
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
        
        Args:
            run_number: Numero RUN da cercare
            
        Returns:
            Worksheet o None se non trovato
        """
        if not self._spreadsheet:
            return None
        
        pattern = f"Run {run_number:03d}"
        for worksheet in self._spreadsheet.worksheets():
            if worksheet.title.startswith(pattern):
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
            
            # Formatta header (bold, centrato)
            worksheet.format('A1:L1', {
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

            row = [
                result.test_id,
                result.date,
                result.mode,
                result.question,
                result.conversation,
                screenshot_formula,     # SCREENSHOT: immagine inline
                screenshot_view_url,    # SCREENSHOT URL: link alta risoluzione
                result.prompt_version,
                result.model_version,
                result.environment,
                result.esito,
                result.notes,
                result.langsmith_url
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

                rows.append([
                    r.test_id, r.date, r.mode, r.question, r.conversation,
                    screenshot_formula, screenshot_view_url,
                    r.prompt_version, r.model_version,
                    r.environment, r.esito, r.notes, r.langsmith_url
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


class GoogleSheetsSetup:
    """Helper per setup Google Sheets"""
    
    @staticmethod
    def get_console_url() -> str:
        """URL Google Cloud Console per creare progetto"""
        return "https://console.cloud.google.com/apis/credentials"
    
    @staticmethod
    def get_setup_instructions() -> str:
        """Istruzioni per setup OAuth"""
        return """
# SETUP GOOGLE SHEETS

1. Vai su Google Cloud Console:
   https://console.cloud.google.com/apis/credentials

2. Crea un nuovo progetto (o seleziona esistente)

3. Abilita le API:
   - Google Sheets API
   - Google Drive API

4. Crea credenziali OAuth 2.0:
   - Tipo: Desktop application
   - Scarica il file JSON

5. Rinomina il file in 'oauth_credentials.json'
   e copialo nella cartella config/

6. Al primo avvio, si aprirà il browser
   per autorizzare l'accesso
"""
    
    @staticmethod
    def validate_credentials_file(path: Path) -> tuple[bool, str]:
        """
        Valida un file credentials OAuth.
        
        Returns:
            (is_valid, message)
        """
        if not path.exists():
            return False, f"File non trovato: {path}"
        
        try:
            with open(path) as f:
                data = json.load(f)
            
            # Verifica campi richiesti
            if 'installed' not in data and 'web' not in data:
                return False, "Formato credentials non valido"
            
            config = data.get('installed') or data.get('web')
            
            required = ['client_id', 'client_secret']
            missing = [r for r in required if r not in config]
            
            if missing:
                return False, f"Campi mancanti: {', '.join(missing)}"
            
            return True, "Credentials valide"
            
        except json.JSONDecodeError:
            return False, "File JSON non valido"
        except Exception as e:
            return False, f"Errore: {e}"
    
    @staticmethod
    def extract_spreadsheet_id(url_or_id: str) -> str:
        """
        Estrae l'ID spreadsheet da URL o ID diretto.
        
        Args:
            url_or_id: URL completo o ID
            
        Returns:
            ID spreadsheet
        """
        # Se è già un ID
        if '/' not in url_or_id:
            return url_or_id
        
        # Estrai da URL
        # Format: https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit...
        parts = url_or_id.split('/')
        try:
            d_index = parts.index('d')
            return parts[d_index + 1]
        except:
            return url_or_id
    
    @staticmethod
    def extract_folder_id(url_or_id: str) -> str:
        """
        Estrae l'ID folder Drive da URL o ID diretto.
        
        Args:
            url_or_id: URL completo o ID
            
        Returns:
            ID folder
        """
        if '/' not in url_or_id:
            return url_or_id
        
        # Format: https://drive.google.com/drive/folders/FOLDER_ID
        parts = url_or_id.split('/')
        try:
            folders_index = parts.index('folders')
            folder_id = parts[folders_index + 1]
            # Rimuovi query params
            return folder_id.split('?')[0]
        except:
            return url_or_id


# =============================================================================
# THREAD-SAFE WRAPPER PER ESECUZIONE PARALLELA
# =============================================================================

class ThreadSafeSheetsClient:
    """
    Wrapper thread-safe per GoogleSheetsClient.

    Accumula risultati in memoria durante l'esecuzione parallela
    e li scrive in batch alla fine, evitando race conditions.

    Usage:
        # Wrap client esistente
        safe_client = ThreadSafeSheetsClient(sheets_client)

        # Da worker paralleli (thread-safe)
        safe_client.queue_result(result)
        safe_client.queue_screenshot(file_path, test_id)

        # Alla fine (scrivi tutto)
        safe_client.flush()
    """

    def __init__(self, client: GoogleSheetsClient):
        """
        Args:
            client: GoogleSheetsClient gia autenticato e configurato
        """
        self._client = client
        self._results_queue: List[TestResult] = []
        self._screenshots_queue: List[tuple] = []  # (file_path, test_id)
        self._lock = threading.RLock()
        self._upload_lock = threading.RLock()  # Lock separato per upload Drive

        # Mapping test_id -> screenshot_urls per associazione post-upload
        self._screenshot_urls: Dict[str, ScreenshotUrls] = {}

    @property
    def client(self) -> GoogleSheetsClient:
        """Accesso al client sottostante"""
        return self._client

    @property
    def queued_count(self) -> int:
        """Numero risultati in coda"""
        with self._lock:
            return len(self._results_queue)

    def queue_result(self, result: TestResult) -> None:
        """
        Accoda un risultato per scrittura batch.
        Thread-safe.

        Args:
            result: TestResult da accodare
        """
        with self._lock:
            self._results_queue.append(result)

    def queue_screenshot(self, file_path: Path, test_id: str) -> None:
        """
        Accoda uno screenshot per upload batch.
        Thread-safe.

        Args:
            file_path: Path al file screenshot
            test_id: ID del test
        """
        with self._lock:
            self._screenshots_queue.append((file_path, test_id))

    def upload_screenshot_now(self, file_path: Path, test_id: str) -> Optional[ScreenshotUrls]:
        """
        Upload screenshot immediatamente (thread-safe).
        Utile se vuoi fare upload durante l'esecuzione.

        Args:
            file_path: Path al file screenshot
            test_id: ID del test

        Returns:
            ScreenshotUrls o None
        """
        with self._upload_lock:
            urls = self._client.upload_screenshot(file_path, test_id)
            if urls:
                with self._lock:
                    self._screenshot_urls[test_id] = urls
            return urls

    def get_screenshot_urls(self, test_id: str) -> Optional[ScreenshotUrls]:
        """Ottiene URL screenshot gia uploadato"""
        with self._lock:
            return self._screenshot_urls.get(test_id)

    def flush_screenshots(self) -> int:
        """
        Upload tutti gli screenshot in coda.

        Returns:
            Numero screenshot uploadati
        """
        with self._lock:
            screenshots_to_upload = self._screenshots_queue.copy()
            self._screenshots_queue.clear()

        uploaded = 0
        for file_path, test_id in screenshots_to_upload:
            urls = self.upload_screenshot_now(file_path, test_id)
            if urls:
                uploaded += 1

        return uploaded

    def flush_results(self) -> int:
        """
        Scrive tutti i risultati in coda su Google Sheets.

        Returns:
            Numero risultati scritti
        """
        with self._lock:
            if not self._results_queue:
                return 0

            results_to_write = self._results_queue.copy()
            self._results_queue.clear()

        # Associa screenshot_urls ai risultati se disponibili
        for result in results_to_write:
            if result.test_id in self._screenshot_urls:
                result.screenshot_urls = self._screenshot_urls[result.test_id]

        # Scrivi batch
        return self._client.append_results(results_to_write)

    def flush(self) -> tuple:
        """
        Flush completo: prima screenshot, poi risultati.

        Returns:
            (screenshots_uploaded, results_written)
        """
        screenshots = self.flush_screenshots()
        results = self.flush_results()
        return screenshots, results

    def is_test_completed(self, test_id: str) -> bool:
        """
        Verifica se un test e gia completato (nella RUN o in coda).
        Thread-safe.
        """
        with self._lock:
            # Check coda locale
            if any(r.test_id == test_id for r in self._results_queue):
                return True

        # Check foglio remoto
        return self._client.is_test_completed(test_id)

    def get_completed_tests(self) -> set:
        """
        Ottiene tutti i test completati (remoti + in coda).
        Thread-safe.
        """
        with self._lock:
            queued = {r.test_id for r in self._results_queue}

        remote = self._client.get_completed_tests()
        return remote | queued


class ParallelResultsCollector:
    """
    Collector per risultati da esecuzione parallela.

    Versione piu leggera di ThreadSafeSheetsClient che
    accumula solo in memoria senza dipendere da Sheets.
    Utile se vuoi gestire la scrittura separatamente.

    Usage:
        collector = ParallelResultsCollector()

        # Da worker paralleli
        collector.add(result)

        # Alla fine
        all_results = collector.get_all()
        sheets_client.append_results(all_results)
    """

    def __init__(self):
        self._results: List[TestResult] = []
        self._lock = threading.RLock()
        self._completed_ids: set = set()

    def add(self, result: TestResult) -> None:
        """Aggiunge risultato (thread-safe)"""
        with self._lock:
            self._results.append(result)
            self._completed_ids.add(result.test_id)

    def get_all(self) -> List[TestResult]:
        """Ottiene tutti i risultati (copia)"""
        with self._lock:
            return self._results.copy()

    def clear(self) -> None:
        """Svuota il collector"""
        with self._lock:
            self._results.clear()
            self._completed_ids.clear()

    def is_completed(self, test_id: str) -> bool:
        """Verifica se test e gia nel collector"""
        with self._lock:
            return test_id in self._completed_ids

    @property
    def count(self) -> int:
        """Numero risultati raccolti"""
        with self._lock:
            return len(self._results)

    def get_summary(self) -> Dict[str, int]:
        """Statistiche sui risultati raccolti"""
        with self._lock:
            passed = sum(1 for r in self._results if r.esito == "PASS")
            failed = sum(1 for r in self._results if r.esito == "FAIL")
            errors = sum(1 for r in self._results if r.esito == "ERROR")
            skipped = sum(1 for r in self._results if r.esito == "SKIP")

            return {
                "total": len(self._results),
                "passed": passed,
                "failed": failed,
                "errors": errors,
                "skipped": skipped
            }
