"""
Google Sheets Client - Integrazione report su Google Sheets

Gestisce:
- Autenticazione OAuth
- Creazione/aggiornamento report
- Upload screenshot su Drive
- Skip test già completati
"""

import os
import json
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime
from dataclasses import dataclass

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


# Scopes necessari
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive.file'
]


@dataclass
class TestResult:
    """Risultato di un singolo test per il report"""
    test_id: str
    date: str
    mode: str  # Train, Assisted, Auto
    question: str
    conversation: str
    screenshot_url: str = ""
    prompt_version: str = ""
    model_version: str = ""
    environment: str = ""
    esito: str = ""  # PASS, FAIL, SKIP, ERROR
    notes: str = ""
    langsmith_url: str = ""


class GoogleSheetsClient:
    """
    Client per Google Sheets con supporto OAuth.
    
    Features:
    - Autenticazione OAuth con token refresh
    - Append righe al report
    - Check test già eseguiti (per skip)
    - Upload screenshot su Drive
    
    Usage:
        client = GoogleSheetsClient(
            credentials_path="credentials.json",
            spreadsheet_id="xxx",
            drive_folder_id="yyy"
        )
        
        if client.authenticate():
            client.append_result(result)
    """
    
    # Colonne standard del report
    COLUMNS = [
        "TEST ID",
        "DATE",
        "MODE",
        "QUESTION",
        "CONVERSATION",
        "SCREENSHOT",
        "PROMPT VER",
        "MODEL VER",
        "ENV",
        "ESITO",
        "NOTES",
        "LANGSMITH"
    ]
    
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
        self._worksheet = None
        
        # Cache test esistenti
        self._existing_tests: set = set()
    
    @property
    def is_authenticated(self) -> bool:
        """Verifica se autenticato"""
        return self._credentials is not None and self._credentials.valid
    
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
                    print(f"❌ File credentials non trovato: {self.credentials_path}")
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
            self._worksheet = self._spreadsheet.sheet1
            
            # Drive service per upload
            if self.drive_folder_id:
                self._drive_service = build('drive', 'v3', credentials=creds)
            
            # Carica test esistenti
            self._load_existing_tests()
            
            print("✅ Google Sheets autenticato")
            return True
            
        except Exception as e:
            print(f"❌ Errore autenticazione Google: {e}")
            return False
    
    def _load_existing_tests(self) -> None:
        """Carica gli ID dei test già nel report"""
        try:
            # Leggi colonna TEST ID
            col_values = self._worksheet.col_values(1)  # Prima colonna
            self._existing_tests = set(col_values[1:])  # Skip header
        except:
            self._existing_tests = set()
    
    def is_test_completed(self, test_id: str) -> bool:
        """
        Verifica se un test è già nel report.
        
        Args:
            test_id: ID del test
            
        Returns:
            True se già completato
        """
        return test_id in self._existing_tests
    
    def get_completed_tests(self) -> set[str]:
        """Ritorna set dei test già completati"""
        return self._existing_tests.copy()
    
    def ensure_headers(self) -> None:
        """Assicura che le intestazioni siano presenti"""
        try:
            first_row = self._worksheet.row_values(1)
            if not first_row or first_row != self.COLUMNS:
                self._worksheet.update('A1', [self.COLUMNS])
        except:
            self._worksheet.update('A1', [self.COLUMNS])
    
    def append_result(self, result: TestResult) -> bool:
        """
        Aggiunge un risultato al report.
        
        Args:
            result: TestResult da aggiungere
            
        Returns:
            True se aggiunta riuscita
        """
        try:
            row = [
                result.test_id,
                result.date,
                result.mode,
                result.question,
                result.conversation,
                result.screenshot_url,
                result.prompt_version,
                result.model_version,
                result.environment,
                result.esito,
                result.notes,
                result.langsmith_url
            ]
            
            self._worksheet.append_row(row, value_input_option='USER_ENTERED')
            self._existing_tests.add(result.test_id)
            
            return True
        except Exception as e:
            print(f"❌ Errore append riga: {e}")
            return False
    
    def append_results(self, results: List[TestResult]) -> int:
        """
        Aggiunge più risultati in batch.
        
        Args:
            results: Lista TestResult
            
        Returns:
            Numero risultati aggiunti con successo
        """
        if not results:
            return 0
        
        try:
            rows = []
            for r in results:
                rows.append([
                    r.test_id, r.date, r.mode, r.question, r.conversation,
                    r.screenshot_url, r.prompt_version, r.model_version,
                    r.environment, r.esito, r.notes, r.langsmith_url
                ])
            
            self._worksheet.append_rows(rows, value_input_option='USER_ENTERED')
            
            for r in results:
                self._existing_tests.add(r.test_id)
            
            return len(results)
        except Exception as e:
            print(f"❌ Errore batch append: {e}")
            return 0
    
    def upload_screenshot(self, 
                          file_path: Path,
                          test_id: str) -> Optional[str]:
        """
        Carica screenshot su Google Drive.
        
        Args:
            file_path: Path al file screenshot
            test_id: ID del test (per nome file)
            
        Returns:
            URL pubblico del file o None
        """
        if not self._drive_service or not self.drive_folder_id:
            return None
        
        if not file_path.exists():
            return None
        
        try:
            # Metadata file
            file_metadata = {
                'name': f"{test_id}_{file_path.name}",
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
            
            return file.get('webViewLink', '')
            
        except Exception as e:
            print(f"⚠️ Errore upload screenshot: {e}")
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
        try:
            self._worksheet.update_cell(row, col, value)
            return True
        except:
            return False
    
    def find_test_row(self, test_id: str) -> Optional[int]:
        """
        Trova la riga di un test specifico.
        
        Args:
            test_id: ID del test
            
        Returns:
            Numero riga o None
        """
        try:
            cell = self._worksheet.find(test_id)
            return cell.row if cell else None
        except:
            return None
    
    def get_all_results(self) -> List[Dict[str, Any]]:
        """
        Ottiene tutti i risultati dal report.
        
        Returns:
            Lista di dizionari con i risultati
        """
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
            print(f"❌ Errore creazione spreadsheet: {e}")
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
📋 SETUP GOOGLE SHEETS

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
