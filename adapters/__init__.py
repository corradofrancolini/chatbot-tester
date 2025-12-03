"""
Adapters - Sistema di rilevamento selettori CSS

Moduli:
- base: Classe base ChatbotAdapter
- auto_detect: Rilevamento automatico con euristiche
- click_learn: Apprendimento da click utente
"""

from .base import ChatbotAdapter, AdapterResult, SelectorSet
from .auto_detect import AutoDetectAdapter
from .click_learn import ClickLearnAdapter

__all__ = [
    'ChatbotAdapter',
    'AdapterResult',
    'SelectorSet',
    'AutoDetectAdapter',
    'ClickLearnAdapter'
]
