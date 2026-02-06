"""
Shared Models - Common data classes across modules

Contains unified dataclasses to avoid duplicate definitions:
- TestFailure: Used by analyzer.py and diagnostic.py
- TestResult: Unified test result for sheets, export, and local reports
- ScreenshotUrls: Screenshot URL container
- ExecutionContext: Bundled dependencies for TestExecutor
- TestMode: Test execution mode enum
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from enum import Enum

from .execution import ExecutionContext, TestMode


@dataclass
class ConversationTurn:
    """Singolo turno di conversazione"""
    role: str
    content: str
    timestamp: str = ""


@dataclass
class TestCase:
    """Definizione di un test case"""
    id: str
    question: str
    category: str = ""
    expected: str = ""
    followups: List[str] = field(default_factory=list)
    data: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    notes: str = ""
    section: str = ""
    test_target: str = ""
    expected_answer: Optional[str] = None
    rag_context_file: Optional[str] = None


@dataclass
class TestExecution:
    """Risultato esecuzione di un test (output intermedio)"""
    test_case: TestCase
    conversation: List[ConversationTurn]
    result: str
    duration_ms: int
    screenshot_path: str = ""
    langsmith_url: str = ""
    langsmith_report: str = ""
    notes: str = ""
    llm_evaluation: Optional[Dict] = None
    model_version: str = ""
    prompt_version: str = ""
    timing: str = ""
    vector_store: str = ""


@dataclass
class TestFailure:
    """
    Unified representation of a failed test.

    Used by both analyzer.py (for LLM analysis) and diagnostic.py (for diagnosis).
    """
    test_id: str
    question: str
    expected: Optional[str] = None
    actual: str = ""

    # Optional fields for additional context
    test_name: str = ""  # Human-readable test name
    notes: Optional[str] = None
    error_type: Optional[str] = None  # Type classification

    # LangSmith integration (used by analyzer)
    langsmith_url: Optional[str] = None
    langsmith_trace: Optional[Dict[str, Any]] = None
    screenshot_path: Optional[str] = None


@dataclass
class ScreenshotUrls:
    """URL screenshot per embedding e visualizzazione"""
    image_url: str = ""  # URL diretto per =IMAGE()
    view_url: str = ""   # URL per visualizzazione alta risoluzione


@dataclass
class TestResult:
    """
    Unified test result for all report types.

    Combines fields from:
    - sheets_client.TestResult (Google Sheets reports)
    - export.TestResult (CSV/HTML export)
    - report_local.TestResultLocal (local filesystem reports)

    All fields except test_id have defaults for flexibility.
    """
    test_id: str

    # Core fields (common to all)
    question: str = ""
    conversation: str = ""  # Full conversation or actual_response
    result: str = ""  # PASS, FAIL, SKIP, PARTIAL, or empty
    notes: str = ""

    # Metadata
    date: str = ""
    mode: str = ""  # Train, Assisted, Auto
    category: str = ""  # Test category/section
    environment: str = "DEV"

    # Version info
    prompt_version: str = ""
    model_version: str = ""

    # Screenshot support
    screenshot_url: str = ""  # Legacy: URL singolo
    screenshot_path: Optional[str] = None  # Local file path
    screenshot_urls: Optional[ScreenshotUrls] = None  # Both URLs

    # LangSmith integration
    langsmith_report: str = ""
    langsmith_url: str = ""
    vector_store: str = ""

    # Timing
    timing: str = ""  # "TTFR → Total" format
    duration_ms: int = 0
    duration_seconds: float = 0

    # Evaluation metrics
    score: Optional[float] = None  # Generic score
    semantic_score: Optional[float] = None
    judge_score: Optional[float] = None
    groundedness: Optional[float] = None
    faithfulness: Optional[float] = None
    relevance: Optional[float] = None
    overall_score: Optional[float] = None
    judge_reasoning: str = ""
    evaluation: Optional[str] = None  # Evaluation text

    # Export-specific fields
    expected: str = ""  # Expected answer
    actual_response: str = ""  # Alias for conversation in export context
    status: str = ""  # Alias for result in export context
    sources: List[str] = field(default_factory=list)
    conversation_history: List[Dict[str, str]] = field(default_factory=list)

    # GGP fields
    section: str = ""  # GROUNDING, GUARDRAIL, PROBING
    target: str = ""

    # Run tracking
    run_number: int = 0
    followups_count: int = 0
