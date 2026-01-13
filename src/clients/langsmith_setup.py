"""
LangSmith Setup - Helper utilities for LangSmith configuration

Provides validation and URL extraction utilities for LangSmith API.
"""

import requests
from typing import Optional


class LangSmithSetup:
    """Helper per setup LangSmith"""

    @staticmethod
    def get_setup_instructions() -> str:
        """Istruzioni per setup LangSmith"""
        return """
SETUP LANGSMITH

1. Vai su smith.langchain.com e accedi

2. Crea un nuovo progetto o seleziona esistente

3. Copia i seguenti valori:
   - Project ID: dalla URL del progetto
   - Org ID: Settings > Organization (se presente)

4. Genera API Key:
   Settings > API Keys > Create API Key

5. Inserisci i valori nel wizard o in .env:
   LANGSMITH_API_KEY=lsv2_sk_xxxxx
"""

    @staticmethod
    def validate_api_key(api_key: str) -> tuple[bool, str]:
        """
        Valida una API key LangSmith.

        Returns:
            (is_valid, message)
        """
        if not api_key:
            return False, "API key vuota"

        if not api_key.startswith('lsv2_'):
            return False, "Formato API key non valido (deve iniziare con lsv2_)"

        # Test connessione
        try:
            response = requests.get(
                "https://api.smith.langchain.com/api/v1/info",
                headers={'x-api-key': api_key},
                timeout=10
            )

            if response.status_code == 200:
                return True, "API key valida"
            elif response.status_code == 401:
                return False, "API key non autorizzata"
            else:
                return False, f"Errore verifica: {response.status_code}"
        except Exception as e:
            return False, f"Errore connessione: {e}"

    @staticmethod
    def extract_project_id(url: str) -> Optional[str]:
        """
        Estrae project ID da URL LangSmith.

        Args:
            url: URL del progetto

        Returns:
            Project ID o None
        """
        # Format: https://smith.langchain.com/o/ORG/projects/p/PROJECT_ID
        # o: https://smith.langchain.com/projects/p/PROJECT_ID

        if '/projects/p/' in url:
            parts = url.split('/projects/p/')
            if len(parts) > 1:
                project_id = parts[1].split('/')[0].split('?')[0]
                return project_id

        return None

    @staticmethod
    def extract_org_id(url: str) -> Optional[str]:
        """
        Estrae org ID da URL LangSmith.

        Args:
            url: URL del progetto

        Returns:
            Org ID o None
        """
        if '/o/' in url:
            parts = url.split('/o/')
            if len(parts) > 1:
                org_id = parts[1].split('/')[0]
                return org_id

        return None
