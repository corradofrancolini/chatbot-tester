import pytest
from src.parsing.prompt_parser import PromptParser, PromptStructure

import textwrap

def test_prompt_parser_parse_basic():
    """Test parsing of a simple prompt structure."""
    content = textwrap.dedent("""
    # Introduction
    You are a helpful assistant.

    # Rules
    - If user asks for X, do Y.
    - Always be polite.
    - Never shout.

    # Capabilities
    - Can search web.
    - Cannot fly.
    """)
    parser = PromptParser()
    structure = parser.parse(content)

    assert isinstance(structure, PromptStructure)
    assert "introduction" in structure.sections
    assert "rules" in structure.sections
    assert structure.language == 'en'

    # Check if some rules were extracted (list items)
    assert len(structure.rules) > 0

def test_prompt_parser_italian():
    """Test parsing of Italian prompt."""
    content = textwrap.dedent("""
    # Introduzione
    Sei un assistente utile.

    Se l'utente chiede aiuto, rispondi con gentilezza.
    """)
    parser = PromptParser()
    structure = parser.parse(content)

    assert structure.language == 'it'
    assert len(structure.rules) > 0
