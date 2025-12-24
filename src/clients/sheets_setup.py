"""
Google Sheets Setup - Helper utilities for Google Sheets/Drive configuration

Provides validation and URL extraction utilities for Google API credentials.
"""

import json
from pathlib import Path


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
