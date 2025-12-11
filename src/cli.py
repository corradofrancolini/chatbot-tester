"""
CLI Entry Point for chatbot-tester package.

This module provides the main entry point when installed via pip.
"""

import sys
from pathlib import Path

# Ensure the package root is in path
sys.path.insert(0, str(Path(__file__).parent.parent))


def main():
    """Main entry point for the chatbot-tester CLI."""
    # Import and run the main function from run.py
    from run import main as run_main
    run_main()


if __name__ == "__main__":
    main()
