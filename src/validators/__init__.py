"""
Validators package for structured output validation.

Provides validation for:
- HTML structured output (product cards, tables, lists)
- Vision-based validation using GPT-4 Vision
"""

from .structured import StructuredValidator, StructuredValidationResult
from .vision import VisionValidator

__all__ = [
    'StructuredValidator',
    'StructuredValidationResult',
    'VisionValidator',
]
