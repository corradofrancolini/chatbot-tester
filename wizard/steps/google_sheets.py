"""
Step 5: Google Sheets Configuration
Configures optional Google Sheets integration for reports.
"""

import os
import webbrowser
from typing import Tuple, Optional
from pathlib import Path
from rich.prompt import Prompt, Confirm

from wizard.steps.base import BaseStep
from wizard.utils import PROJECT_ROOT, validate_file_path
from src.ui import console
from src.i18n import t


class GoogleSheetsStep(BaseStep):
    """Step 5: Configure Google Sheets integration."""
    
    step_number = 5
    step_key = "step5"
    is_optional = True
    estimated_time = 10.0
    
    GOOGLE_CLOUD_CONSOLE = "https://console.cloud.google.com/apis/credentials"
    SETUP_GUIDE = """
    Per configurare Google Sheets:
    
    1. Vai su Google Cloud Console: {url}
    2. Crea un nuovo progetto (o usa uno esistente)
    3. Abilita "Google Sheets API" e "Google Drive API"
    4. Crea credenziali OAuth 2.0 (tipo "Desktop app")
    5. Scarica il file JSON delle credenziali
    6. Inserisci il percorso del file qui sotto
    """
    
    def _validate_credentials(self, path: str) -> Tuple[bool, str]:
        """Validate Google OAuth credentials file."""
        import json
        
        try:
            with open(path, 'r') as f:
                creds = json.load(f)
            
            # Check for required fields
            if 'installed' in creds or 'web' in creds:
                return True, ""
            else:
                return False, "File non sembra essere credenziali OAuth valide"
                
        except json.JSONDecodeError:
            return False, "File JSON non valido"
        except FileNotFoundError:
            return False, "File non trovato"
        except Exception as e:
            return False, str(e)
    
    def _authenticate_google(self, credentials_path: str) -> bool:
        """Perform Google OAuth authentication."""
        try:
            from google_auth_oauthlib.flow import InstalledAppFlow
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            import pickle
            
            SCOPES = [
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive.file'
            ]
            
            token_path = PROJECT_ROOT / "config" / "token.pickle"
            creds = None
            
            # Load existing token if available
            if token_path.exists():
                with open(token_path, 'rb') as token:
                    creds = pickle.load(token)
            
            # If no valid credentials, authenticate
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    console.print("   Aggiornamento token...")
                    creds.refresh(Request())
                else:
                    console.print(f"  {t('step5.auth_instructions')}")
                    flow = InstalledAppFlow.from_client_secrets_file(
                        credentials_path, SCOPES
                    )
                    creds = flow.run_local_server(port=0)
                
                # Save token
                with open(token_path, 'wb') as token:
                    pickle.dump(creds, token)
            
            console.print(f"  [green]✓ {t('step5.auth_success')}[/green]")
            return True
            
        except Exception as e:
            console.print(f"  [red]✗ {t('step5.auth_fail')}: {e}[/red]")
            return False
    
    def _test_spreadsheet(self, spreadsheet_id: str) -> Tuple[bool, str]:
        """Test access to a spreadsheet."""
        try:
            import gspread
            from google.oauth2.credentials import Credentials
            import pickle
            
            token_path = PROJECT_ROOT / "config" / "token.pickle"
            with open(token_path, 'rb') as token:
                creds = pickle.load(token)
            
            gc = gspread.authorize(creds)
            spreadsheet = gc.open_by_key(spreadsheet_id)
            
            return True, spreadsheet.title
            
        except Exception as e:
            return False, str(e)
    
    def _create_spreadsheet(self, name: str) -> Tuple[bool, str, str]:
        """Create a new spreadsheet."""
        try:
            import gspread
            from google.oauth2.credentials import Credentials
            import pickle
            
            token_path = PROJECT_ROOT / "config" / "token.pickle"
            with open(token_path, 'rb') as token:
                creds = pickle.load(token)
            
            gc = gspread.authorize(creds)
            spreadsheet = gc.create(name)
            
            # Setup header row
            worksheet = spreadsheet.sheet1
            headers = [
                "TEST ID", "DATE", "MODE", "QUESTION", "CONVERSATION",
                "SCREENSHOT", "PROMPT VER", "MODEL VER", "ENV", "ESITO", "NOTES"
            ]
            worksheet.append_row(headers)
            
            return True, spreadsheet.id, spreadsheet.title
            
        except Exception as e:
            return False, "", str(e)
    
    def _test_drive_folder(self, folder_id: str) -> Tuple[bool, str]:
        """Test access to a Drive folder."""
        try:
            from googleapiclient.discovery import build
            from google.oauth2.credentials import Credentials
            import pickle
            
            token_path = PROJECT_ROOT / "config" / "token.pickle"
            with open(token_path, 'rb') as token:
                creds = pickle.load(token)
            
            service = build('drive', 'v3', credentials=creds)
            folder = service.files().get(fileId=folder_id, fields='name').execute()
            
            return True, folder.get('name', 'Unknown')
            
        except Exception as e:
            return False, str(e)
    
    def run(self) -> Tuple[bool, str]:
        """Execute Google Sheets configuration."""
        self.show()
        
        # Options
        console.print(f"\n  [bold]{t('step5.options_title')}[/bold]\n")
        console.print(f"  [1] {t('step5.option_local')}")
        console.print(f"  [2] {t('step5.option_sheets')} [yellow][{t('common.recommended')}][/yellow]")
        console.print(f"  [3] {t('step5.option_later')}")
        
        choice = Prompt.ask("\n  Scelta", choices=["1", "2", "3"], default="1")
        
        if choice == "1":
            # Local only
            self.state.google_sheets_enabled = False
            console.print("\n  [green]✓ Report salvati solo localmente (HTML/CSV)[/green]")
            
        elif choice == "3":
            # Configure later
            self.state.google_sheets_enabled = False
            console.print("\n  [cyan]>  Potrai configurare Google Sheets in seguito modificando project.yaml[/cyan]")
            
        else:
            # Configure Google Sheets
            console.print(f"\n  [bold]{t('step5.setup_title')}[/bold]")
            console.print(self.SETUP_GUIDE.format(url=self.GOOGLE_CLOUD_CONSOLE))
            
            # Check if credentials exist
            has_creds = Confirm.ask(f"\n  {t('step5.credentials_prompt')}", default=False)
            
            if not has_creds:
                console.print(f"\n  {t('step5.credentials_guide')}")
                webbrowser.open(self.GOOGLE_CLOUD_CONSOLE)
                console.print("\n  [dim]Premi INVIO quando hai scaricato le credenziali...[/dim]")
                input()
            
            # Get credentials path
            while True:
                creds_path = Prompt.ask(f"\n  {t('step5.credentials_path')}")
                creds_path = os.path.expanduser(creds_path)
                
                is_valid, error = self._validate_credentials(creds_path)
                
                if is_valid:
                    console.print(f"  [green]✓ {t('step5.credentials_ok')}[/green]")
                    
                    # Copy to config folder
                    config_dir = PROJECT_ROOT / "config"
                    config_dir.mkdir(parents=True, exist_ok=True)
                    
                    import shutil
                    dest_path = config_dir / "oauth_credentials.json"
                    shutil.copy(creds_path, dest_path)
                    
                    break
                else:
                    console.print(f"  [red]✗ {t('step5.credentials_invalid')}: {error}[/red]")
            
            # Authenticate
            console.print(f"\n   {t('step5.auth_prompt')}")
            
            if not self._authenticate_google(str(dest_path)):
                # Auth failed, skip
                self.state.google_sheets_enabled = False
                console.print("\n  [yellow]!  Autenticazione fallita, continuo senza Sheets[/yellow]")
            else:
                # Get spreadsheet ID
                console.print(f"\n  {t('step5.spreadsheet_prompt')}")
                console.print("  [dim](lascia vuoto per creare un nuovo foglio)[/dim]")
                
                spreadsheet_id = Prompt.ask("\n  Spreadsheet ID", default="")
                
                if spreadsheet_id:
                    # Test existing spreadsheet
                    success, name = self._test_spreadsheet(spreadsheet_id)
                    
                    if success:
                        console.print(f"  [green]✓ {t('step5.spreadsheet_found', name=name)}[/green]")
                        self.state.spreadsheet_id = spreadsheet_id
                    else:
                        console.print(f"  [red]✗ {t('step5.spreadsheet_invalid')}: {name}[/red]")
                        
                        if Confirm.ask("  Vuoi crearne uno nuovo?", default=True):
                            spreadsheet_id = ""
                
                if not spreadsheet_id:
                    # Create new spreadsheet
                    console.print(f"\n   {t('step5.spreadsheet_new')}")
                    
                    name = f"Chatbot Tests - {self.state.project_name}"
                    success, new_id, new_name = self._create_spreadsheet(name)
                    
                    if success:
                        console.print(f"  [green]✓ {t('step5.spreadsheet_created', name=new_name)}[/green]")
                        console.print(f"  [cyan]ID: {new_id}[/cyan]")
                        self.state.spreadsheet_id = new_id
                    else:
                        console.print(f"  [red]✗ Errore creazione: {new_name}[/red]")
                
                # Get Drive folder ID (for screenshots)
                console.print(f"\n  {t('step5.folder_prompt')}")
                console.print("  [dim](opzionale, per salvare gli screenshot)[/dim]")
                
                folder_id = Prompt.ask("\n  Drive Folder ID", default="")
                
                if folder_id:
                    success, name = self._test_drive_folder(folder_id)
                    
                    if success:
                        console.print(f"  [green]✓ {t('step5.folder_found', name=name)}[/green]")
                        self.state.drive_folder_id = folder_id
                    else:
                        console.print(f"  [yellow]!  {t('step5.folder_invalid')}: {name}[/yellow]")
                
                self.state.google_sheets_enabled = True
        
        # Summary
        console.print()
        console.print("  [cyan]─" * 50 + "[/cyan]")
        console.print(f"  · Google Sheets: {'Abilitato' if self.state.google_sheets_enabled else 'Disabilitato'}")
        if self.state.google_sheets_enabled:
            console.print(f"  · Spreadsheet ID: {self.state.spreadsheet_id or 'Non configurato'}")
            console.print(f"  · Drive Folder ID: {self.state.drive_folder_id or 'Non configurato'}")
        console.print("  [cyan]─" * 50 + "[/cyan]")
        console.print()
        
        console.print("  [dim]Premi INVIO per continuare, 'b' per tornare indietro...[/dim]")
        nav = input("  ").strip().lower()
        
        if nav == 'b':
            return True, 'back'
        elif nav == 'q':
            return False, 'quit'
        
        self.state.mark_step_complete(self.step_number)
        return True, 'next'
