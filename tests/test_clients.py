import pytest
from src.clients.base import BaseClient
from src.ollama_client import OllamaClient
from src.langsmith_client import LangSmithClient
from src.sheets_client import GoogleSheetsClient

def test_clients_inherit_base():
    """Verify all clients inherit from BaseClient."""
    assert issubclass(OllamaClient, BaseClient)
    assert issubclass(LangSmithClient, BaseClient)
    assert issubclass(GoogleSheetsClient, BaseClient)

def test_base_client_abc():
    """Verify BaseClient cannot be instantiated directly."""
    with pytest.raises(TypeError):
        BaseClient()

def test_ollama_client_is_available_method():
    """Verify OllamaClient has is_available method."""
    client = OllamaClient(url="http://mock-url")
    assert hasattr(client, 'is_available')
    # We don't call it to avoid network request, unless we mock.
