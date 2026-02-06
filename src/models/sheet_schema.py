"""
Google Sheets Schema - Column definitions and configuration.

Centralizes all column-related configuration for Google Sheets reports.
This reduces the size of sheets_client.py and makes schema changes easier.
"""

from dataclasses import dataclass
from typing import List, Dict, Optional


# Standard report columns (24 columns total)
COLUMNS = [
    "TEST ID",
    "DATE",
    "MODE",
    "QUESTION",
    "EXPECTED ANSWER",  # Golden answer (from test set, if provided)
    "CONVERSATION",
    "SCREENSHOT",      # Inline image (thumbnail)
    "SCREENSHOT URL",  # High-res link
    "PROMPT VER",      # Prompt version (from run config)
    "MODEL VER",       # provider/model
    "ENV",             # DEV/PROD (dropdown)
    "TIMING",          # TTFR → Total (e.g., "2.3s → 12.0s")
    "RESULT",          # Pass/Fail/Partial (dropdown, reviewer fills)
    "BASELINE",        # Checkbox: if ✓, this response is the golden answer
    "NOTES",           # Reviewer notes (free text)
    "LS REPORT",       # LangSmith report (text)
    "LS TRACE LINK",   # LangSmith trace link
    # Evaluation metrics
    "SEMANTIC",        # Semantic similarity score (0-1)
    "JUDGE",           # LLM-as-judge score (0-1)
    "GROUND",          # Groundedness score (0-1)
    "FAITH",           # Faithfulness score (0-1)
    "RELEV",           # Relevance score (0-1)
    "OVERALL",         # Overall evaluation score (0-1)
    "JUDGE REASON"     # LLM-as-judge reasoning
]

# Column widths in pixels (matches COLUMNS order)
COLUMN_WIDTHS = [
    100,   # TEST ID
    140,   # DATE
    80,    # MODE
    250,   # QUESTION
    300,   # EXPECTED ANSWER
    400,   # CONVERSATION
    200,   # SCREENSHOT
    200,   # SCREENSHOT URL
    100,   # PROMPT VER
    100,   # MODEL VER
    60,    # ENV
    110,   # TIMING
    100,   # RESULT
    70,    # BASELINE
    200,   # NOTES
    300,   # LS REPORT
    350,   # LS TRACE LINK
    70,    # SEMANTIC
    70,    # JUDGE
    70,    # GROUND
    70,    # FAITH
    70,    # RELEV
    70,    # OVERALL
    200    # JUDGE REASON
]

# Column indices for quick lookup
COLUMN_INDEX = {name: idx for idx, name in enumerate(COLUMNS)}


@dataclass
class ColumnConfig:
    """Configuration for a single column."""
    name: str
    width: int
    index: int
    is_score: bool = False  # True for 0-1 score columns
    is_dropdown: bool = False  # True for dropdown columns
    max_length: Optional[int] = None  # Max chars for truncation


def get_column_index(column_name: str) -> int:
    """Get 0-based index for a column name."""
    return COLUMN_INDEX.get(column_name, -1)


def get_header_range(num_columns: Optional[int] = None) -> str:
    """Get the header range string (e.g., 'A1:W1')."""
    if num_columns is None:
        num_columns = len(COLUMNS)
    end_col = chr(ord('A') + num_columns - 1) if num_columns <= 26 else 'Z'
    return f"A1:{end_col}1"


# Score columns that should be formatted as percentages or decimals
SCORE_COLUMNS = ["SEMANTIC", "JUDGE", "GROUND", "FAITH", "RELEV", "OVERALL"]

# Dropdown columns with allowed values
DROPDOWN_COLUMNS = {
    "RESULT": ["PASS", "FAIL", "PARTIAL", "SKIP", ""],
    "ENV": ["DEV", "STAGING", "PROD"],
    "MODE": ["AUTO", "TRAIN", "ASSISTED"]
}

# Columns that support checkboxes
CHECKBOX_COLUMNS = ["BASELINE"]

# Maximum character limits for truncation
CHAR_LIMITS = {
    "CONVERSATION": 5000,
    "JUDGE REASON": 500,
    "LS REPORT": 2000
}
