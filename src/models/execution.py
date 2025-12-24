"""
ExecutionContext - Centralized dependencies for test execution.

Groups all dependencies needed by TestExecutor into a single context object,
reducing constructor complexity from 13 parameters to 1.
"""

from dataclasses import dataclass, field
from typing import Optional, Any, TYPE_CHECKING
from enum import Enum


class TestMode(Enum):
    """Test execution modes."""
    TRAIN = "train"
    ASSISTED = "assisted"
    AUTO = "auto"


if TYPE_CHECKING:
    from ..browser import BrowserManager
    from ..ollama_client import OllamaClient
    from ..langsmith_client import LangSmithClient
    from ..config_loader import GlobalSettings, RunConfig
    from ..training import TrainingData
    from ..performance import PerformanceCollector
    from ..evaluation import Evaluator
    from ..baselines import BaselinesCache
    from ..report_local import ReportGenerator
    from ..sheets_client import GoogleSheetsClient
    from rich.console import Console


@dataclass
class ExecutionContext:
    """
    Bundled dependencies for test execution.

    Required:
        browser: Browser automation manager
        settings: Global configuration settings

    Optional services:
        ollama: Local LLM for evaluation
        langsmith: LangSmith tracing client
        evaluator: Response evaluator
        training: Training data for pattern matching
        baselines: Golden answers cache

    Optional output:
        perf_collector: Performance metrics collector
        report: Local report generator
        sheets: Google Sheets client for persisting results
        console: Rich console for status output

    Optional config:
        run_config: Current run configuration
        project: Project configuration
        single_turn: If True, stop after first bot response
        current_mode: Test mode (AUTO, TRAIN, ASSISTED)
    """
    # Required
    browser: 'BrowserManager'
    settings: 'GlobalSettings'

    # AI Services
    ollama: Optional['OllamaClient'] = None
    langsmith: Optional['LangSmithClient'] = None
    evaluator: Optional['Evaluator'] = None

    # Data
    training: Optional['TrainingData'] = None
    baselines: Optional['BaselinesCache'] = None

    # Output
    perf_collector: Optional['PerformanceCollector'] = None
    report: Optional['ReportGenerator'] = None
    sheets: Optional['GoogleSheetsClient'] = None
    console: Optional['Console'] = None

    # Config
    run_config: Optional['RunConfig'] = None
    project: Any = None  # ProjectConfig
    single_turn: bool = False
    current_mode: TestMode = TestMode.AUTO
