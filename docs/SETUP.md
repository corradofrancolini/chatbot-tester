# Detailed Setup Guide

This guide walks you through step-by-step installation and configuration of Chatbot Tester.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Installation](#installation)
3. [Basic Configuration](#basic-configuration)
4. [Google Sheets Configuration](#google-sheets-configuration)
5. [LangSmith Configuration](#langsmith-configuration)
6. [Ollama Configuration](#ollama-configuration)
7. [Installation Verification](#installation-verification)

---

## Prerequisites

### Operating System

| Requirement | Minimum | Recommended |
|-------------|---------|-------------|
| macOS | 12.0 (Monterey) | 14.0+ (Sonoma) |
| Disk space | 500 MB | 2 GB |
| RAM | 4 GB | 8 GB+ |

### Required Software

#### Python 3.10+

Check installed version:
```bash
python3 --version
```

If not present or lower version:
```bash
# Install via Homebrew
brew install python@3.12
```

#### Homebrew

Check installation:
```bash
brew --version
```

If not present:
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

#### Git

Check installation:
```bash
git --version
```

If not present:
```bash
brew install git
```

---

## Installation

### 1. Download the project

```bash
# Clone the repository
git clone https://github.com/your-org/chatbot-tester.git

# Enter the folder
cd chatbot-tester
```

### 2. Run the installer

```bash
./install.sh
```

The installer will automatically:

1. Check operating system (macOS 12.0+)
2. Check Homebrew
3. Check Python 3.10+
4. Check Git
5. Check disk space (500 MB)
6. Create Python virtual environment
7. Install Python dependencies
8. Install Playwright + Chromium
9. Create folder structure
10. Create startup script

### 3. Verify installation

```bash
./chatbot-tester --help
```

You should see the tool's help.

---

## Basic Configuration

### Global Settings

The `config/settings.yaml` file contains global settings:

```yaml
app:
  version: "1.0.0"
  language: "it"  # it | en

browser:
  headless: false      # true for execution without GUI
  viewport:
    width: 1280
    height: 720
  device_scale_factor: 2  # For retina screenshots

test:
  max_turns: 15              # Max conversation turns
  screenshot_on_complete: true

reports:
  local:
    enabled: true
    format: ["html", "csv"]

ui:
  colors: true
  progress_bar: true
```

### Common Customizations

#### Headless execution (without visible browser)

```yaml
browser:
  headless: true
```

#### Default English language

```yaml
app:
  language: "en"
```

#### Longer timeouts

Modify in the project's `project.yaml`:
```yaml
chatbot:
  timeouts:
    page_load: 60000     # 60 seconds
    bot_response: 120000 # 2 minutes
```

---

## Google Sheets Configuration

> **Optional**: If you don't configure Google Sheets, reports will be local only.

### 1. Create Google Cloud project

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project or select an existing one
3. Note the **Project ID**

### 2. Enable APIs

1. Go to **APIs & Services** → **Library**
2. Search and enable:
   - **Google Sheets API**
   - **Google Drive API**

### 3. Create OAuth credentials

1. Go to **APIs & Services** → **Credentials**
2. Click **Create credentials** → **OAuth client ID**
3. Select **Desktop application**
4. Give it a name (e.g., "Chatbot Tester")
5. Click **Create**
6. Download the JSON file

### 4. Configure credentials

```bash
# Copy the downloaded file
cp ~/Downloads/client_secret_*.json config/oauth_credentials.json
```

### 5. Create the Spreadsheet

1. Go to [Google Sheets](https://sheets.google.com)
2. Create a new sheet
3. Copy the ID from the URL: `https://docs.google.com/spreadsheets/d/THIS_IS_THE_ID/edit`

### 6. Create Drive folder for screenshots

1. Go to [Google Drive](https://drive.google.com)
2. Create a new folder (e.g., "Chatbot Tests Screenshots")
3. Copy the ID from the URL: `https://drive.google.com/drive/folders/THIS_IS_THE_ID`

### 7. First authorization

The first time you use Google Sheets, the browser will open to authorize access. Follow the on-screen instructions.

---

## LangSmith Configuration

> **Optional**: LangSmith provides advanced debugging of chatbot responses.

### 1. Create account

1. Go to [smith.langchain.com](https://smith.langchain.com)
2. Create an account or log in

### 2. Generate API Key

1. Go to **Settings** → **API Keys**
2. Click **Create API Key**
3. Copy the key (starts with `lsv2_sk_`)

### 3. Find Project ID and Org ID

1. **Project ID**: Go to Projects, click on the project, the ID is in the URL
2. **Org ID**: Go to Settings → Organization, the ID is visible

### 4. Configure

Add to the `config/.env` file:

```bash
LANGSMITH_API_KEY=lsv2_sk_xxxxxxxxxxxxx
```

And in the project's `project.yaml`:

```yaml
langsmith:
  enabled: true
  project_id: "your-project-id"
  org_id: "your-org-id"
  tool_names:
    - "retrieval_tool"
    - "calculator"
```

### 5. Auto-detect tool names

The wizard can automatically detect tool names from LangSmith traces. During configuration, run a manual test on the chatbot and the wizard will analyze the trace to extract tool names.

---

## Ollama Configuration

> **Optional for Train mode, required for Assisted/Auto**.

### 1. Install Ollama

```bash
brew install ollama
```

### 2. Start the service

```bash
ollama serve
```

> Leave this terminal open or configure Ollama as a system service.

### 3. Download the Mistral model

```bash
ollama pull mistral
```

This will download ~4GB of data.

### 4. Verify it works

```bash
ollama run mistral "Hello, are you working?"
```

### 5. Project configuration

In `project.yaml`:

```yaml
ollama:
  enabled: true
  model: "mistral"
  url: "http://localhost:11434/api/generate"
```

### Alternative models

| Model | RAM | Speed | Quality |
|-------|-----|-------|---------|
| mistral | 4GB | ⭐⭐⭐ | ⭐⭐⭐ |
| llama2 | 4GB | ⭐⭐⭐ | ⭐⭐ |
| mixtral | 8GB | ⭐⭐ | ⭐⭐⭐⭐ |
| codellama | 4GB | ⭐⭐⭐ | ⭐⭐ (for code) |

---

## Installation Verification

### Complete test

```bash
# 1. Verify CLI
./chatbot-tester --help

# 2. Verify Python modules
source .venv/bin/activate
python -c "from src import tester, browser, config_loader; print('Modules OK')"

# 3. Verify Playwright
python -c "from playwright.sync_api import sync_playwright; print('Playwright OK')"

# 4. Verify Ollama (if configured)
curl -s http://localhost:11434/api/tags | python -c "import sys,json; print('Ollama OK' if json.load(sys.stdin) else 'Ollama not running')"

# 5. Dry run
./chatbot-tester --project=my-chatbot --dry-run
```

### Final checklist

- [ ] `./chatbot-tester --help` works
- [ ] Virtual environment active (`.venv/`)
- [ ] Chromium installed (`.venv/lib/...`)
- [ ] `config/.env` configured (if using external services)
- [ ] At least one project in `projects/`

---

## Next Steps

**Setup complete!**

Now you can:
1. [Create a new project](NEW_PROJECT.md)
2. Configure test cases
3. Start with Train mode

---

## Problems?

See the [Troubleshooting Guide](TROUBLESHOOTING.md) or open an issue on GitHub.
