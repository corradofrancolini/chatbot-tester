# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for chatbot-tester standalone binary.

Build command:
    pyinstaller chatbot-tester.spec

Output:
    dist/chatbot-tester (single executable)
"""

import sys
from pathlib import Path

# Get the project root
PROJECT_ROOT = Path(SPECPATH)

block_cipher = None

# Collect all source files
a = Analysis(
    ['run.py'],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=[
        # Include source packages
        ('src', 'src'),
        ('wizard', 'wizard'),
        # Include config templates (not actual credentials)
        ('config/settings.yaml', 'config') if Path('config/settings.yaml').exists() else None,
    ],
    hiddenimports=[
        # Core dependencies
        'rich',
        'rich.console',
        'rich.panel',
        'rich.text',
        'rich.table',
        'rich.progress',
        'yaml',
        'dotenv',
        'requests',
        'questionary',

        # Playwright
        'playwright',
        'playwright.async_api',
        'playwright.sync_api',

        # Google APIs (optional)
        'gspread',
        'google.auth',
        'google.oauth2',
        'google.oauth2.credentials',
        'google_auth_oauthlib',
        'googleapiclient',
        'googleapiclient.discovery',

        # Data processing
        'pandas',
        'openpyxl',

        # Our modules
        'src',
        'src.browser',
        'src.tester',
        'src.config_loader',
        'src.ollama_client',
        'src.langsmith_client',
        'src.sheets_client',
        'src.report_local',
        'src.ui',
        'src.i18n',
        'src.health',
        'src.training',
        'src.finetuning',
        'wizard',
        'wizard.main',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude test frameworks
        'pytest',
        'pytest_asyncio',

        # Exclude dev tools
        'black',
        'ruff',
        'mypy',

        # Exclude unnecessary stdlib
        'tkinter',
        'unittest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# Filter out None entries from datas
a.datas = [d for d in a.datas if d is not None]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='chatbot-tester',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # Add 'icon.ico' or 'icon.icns' if available
)
