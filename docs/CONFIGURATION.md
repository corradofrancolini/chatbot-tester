# Complete Configuration Guide

This guide documents **all** configuration options available in Chatbot Tester.

**Mantra: If it can be done, it must be visible, explained, and configurable.**

---

## Table of Contents

1. [CLI Options](#1-cli-options)
2. [Configuration Files](#2-configuration-files)
   - [settings.yaml](#settingsyaml-global-configuration)
   - [project.yaml](#projectyaml-project-configuration)
   - [run_config.json](#run_configjson-run-state)
3. [Runtime Toggles](#3-runtime-toggles)
4. [Environment Variables](#4-environment-variables)
5. [Test Case Schema](#5-test-case-schema)

---

## 1. CLI Options

All options available via `python run.py [OPTIONS]`:

### Project Selection

| Option | Description | Example |
|--------|-------------|---------|
| `-p, --project` | Project name | `-p my-chatbot` |
| `--new-project` | Start new project wizard | `--new-project` |

### Test Modes

| Option | Description | Values |
|--------|-------------|--------|
| `-m, --mode` | Execution mode | `train`, `assisted`, `auto` |
| `-t, --test` | Run single test | `-t TEST_001` |
| `--tests` | Which tests to run | `all`, `pending` (default), `failed` |
| `--new-run` | Force new RUN | flag |

### Browser Behavior

| Option | Description | Default |
|--------|-------------|---------|
| `--headless` | Invisible browser | `false` |
| `--no-interactive` | No user prompts | `false` |
| `--dry-run` | Simulate without executing | `false` |

### Services and Debug

| Option | Description | Note |
|--------|-------------|------|
| `--health-check` | Check services and exit | Exits with code 0/1 |
| `--skip-health-check` | Skip initial check | Speeds up startup |
| `--debug` | Detailed debug output | For troubleshooting |

### Parallel Execution

| Option | Description | Default |
|--------|-------------|---------|
| `--parallel` | Run tests in parallel | `false` |
| `--workers` | Number of parallel browsers | `3` (max: 5) |

**How it works:**
- Each worker has an isolated Chromium browser
- Results are accumulated in memory
- At the end, they are written in batch to Google Sheets
- Thread-safe: no risk of overwriting

**When to use it:**
- Large test suites (50+ tests)
- CI/CD where time is critical
- Hardware with sufficient RAM (each browser ~200MB)

### Testing Analysis

| Option | Description | Example |
|--------|-------------|---------|
| `--compare` | Compare runs | `--compare 15:16` or `--compare` |
| `--regressions` | Show regressions | `--regressions 16` or `--regressions` |
| `--flaky` | Flaky tests | `--flaky 20` (default: 10 runs) |

### Language and Version

| Option | Description | Default |
|--------|-------------|---------|
| `--lang` | Interface language | `it` |
| `-v, --version` | Show version | - |
| `--help` | Show help | - |

### Complete Examples

```bash
# Automatic tests with new run, headless
python run.py -p my-chatbot -m auto --no-interactive --new-run --headless

# Debug a single test
python run.py -p my-chatbot -m auto -t TEST_001 --debug

# Quick health check
python run.py --health-check -p my-chatbot

# English interface
python run.py --lang en

# Parallel execution with 4 workers
python run.py -p my-chatbot -m auto --parallel --workers 4 --no-interactive

# Compare last 2 runs
python run.py -p my-chatbot --compare

# Regressions in run 16
python run.py -p my-chatbot --regressions 16

# Flaky tests over 20 runs
python run.py -p my-chatbot --flaky 20
```

---

## 2. Configuration Files

### settings.yaml (Global Configuration)

**Path:** `config/settings.yaml`

These settings apply to **all** projects.

```yaml
# =============================================================================
# CHATBOT TESTER - Global Settings
# =============================================================================

app:
  version: "1.1.0"
  language: "it"              # Default language: it | en

# -----------------------------------------------------------------------------
# Browser
# -----------------------------------------------------------------------------
browser:
  headless: false             # true = hidden browser
  slow_mo: 0                  # ms pause between actions (useful for debug)
  viewport:
    width: 1280               # Window width
    height: 720               # Window height
  device_scale_factor: 2      # 2 = retina display (HD screenshots)

# -----------------------------------------------------------------------------
# Test
# -----------------------------------------------------------------------------
test:
  max_turns: 15               # Max turns per conversation
  screenshot_on_complete: true
  default_wait_after_send: 1000  # ms wait after sending message

# -----------------------------------------------------------------------------
# Report
# -----------------------------------------------------------------------------
reports:
  local:
    enabled: true
    formats:
      - html                  # Interactive HTML report
      - csv                   # Data export
    keep_last_n: 50           # Keep last N runs (0 = all)

# -----------------------------------------------------------------------------
# Terminal UI
# -----------------------------------------------------------------------------
ui:
  colors: true                # Terminal colors
  progress_bar: true          # Show progress bar
  clear_screen: true          # Clear screen between steps

# -----------------------------------------------------------------------------
# Parallel Execution
# -----------------------------------------------------------------------------
parallel:
  enabled: false            # true = enable parallel execution
  max_workers: 3            # Number of parallel browsers (1-5)
  retry_strategy: "exponential"  # none | linear | exponential
  max_retries: 2            # Attempts for failed test
  base_delay_ms: 1000       # Base delay between retries
  rate_limit_per_minute: 60 # Request limit to chatbot

# -----------------------------------------------------------------------------
# Cache
# -----------------------------------------------------------------------------
cache:
  enabled: true             # Enable response caching
  memory:
    max_entries: 1000       # Max entries in memory
    default_ttl_seconds: 300  # Default TTL (5 minutes)
  langsmith:
    trace_ttl_seconds: 300  # Trace cache (5 minutes)
    report_ttl_seconds: 600 # Report cache (10 minutes)

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
logging:
  level: "INFO"               # DEBUG | INFO | WARNING | ERROR
  file: "chatbot-tester.log"
  max_size_mb: 10
  backup_count: 3
```

#### Detailed Options

| Section | Option | Description | Impact |
|---------|--------|-------------|--------|
| `browser.headless` | Visible/hidden browser | `true` for CI/cloud, `false` for debug |
| `browser.slow_mo` | Slow down browser actions | Useful to see what's happening |
| `browser.device_scale_factor` | Screenshot quality | `2` = retina, `1` = normal |
| `test.max_turns` | Conversation limit | Prevents infinite loops |
| `test.screenshot_on_complete` | Automatic capture | Each test saves screenshot |
| `test.default_wait_after_send` | Pause after send | Increase if chatbot is slow |
| `reports.keep_last_n` | Automatic cleanup | `0` = keep all |
| `ui.colors` | Colored output | `false` for pipe/log |
| `parallel.enabled` | Parallel execution | `true` for fast tests |
| `parallel.max_workers` | Simultaneous browsers | 1-5, more workers = more RAM |
| `parallel.retry_strategy` | Retry strategy | `exponential` for slow APIs |
| `cache.enabled` | Response caching | Reduces LangSmith calls |
| `cache.memory.max_entries` | Cache limit | Balance RAM vs hit rate |
| `logging.level` | Log verbosity | `DEBUG` for troubleshooting |

---

### project.yaml (Project Configuration)

**Path:** `projects/<name>/project.yaml`

Specific configuration for each chatbot.

```yaml
project:
  name: my-chatbot
  description: Chatbot description
  created: '2024-12-01'
  language: it                # Main test language

# -----------------------------------------------------------------------------
# Target Chatbot
# -----------------------------------------------------------------------------
chatbot:
  url: https://example.com/chatbot

  # CSS selectors for UI elements
  selectors:
    textarea: '#chat-input'           # Message input field
    submit_button: 'button.send'      # Send button
    bot_messages: '.message.bot'      # Bot messages
    thread_container: '.chat-thread'  # Conversation container
    loading_indicator: '.typing'      # "typing" indicator

  # Extra CSS for screenshots (hides elements)
  screenshot_css: |
    .unwanted-element { display: none !important; }

  # Timeouts in milliseconds
  timeouts:
    page_load: 30000          # Page load wait
    bot_response: 60000       # Bot response wait

  # Performance options
  skip_screenshot: false      # Skip screenshot capture (faster tests)

# -----------------------------------------------------------------------------
# Authentication (optional, for cloud CI)
# -----------------------------------------------------------------------------
auth:
  type: none                  # none | basic | form | sso
  # See detailed examples below

# -----------------------------------------------------------------------------
# Test Defaults
# -----------------------------------------------------------------------------
test_defaults:
  email: test@example.com     # Email for tests requiring auth
  countries:                  # Default values for select fields
    - Italy
    - Germany
  confirmations:
    - 'yes'
    - 'no'

# -----------------------------------------------------------------------------
# Google Sheets (optional)
# -----------------------------------------------------------------------------
google_sheets:
  enabled: true
  spreadsheet_id: '1abc...'   # ID from sheet URL
  drive_folder_id: '1xyz...'  # Folder ID for screenshots

# -----------------------------------------------------------------------------
# LangSmith (optional)
# -----------------------------------------------------------------------------
langsmith:
  enabled: true
  api_key_env: LANGSMITH_API_KEY  # Environment variable name
  project_id: 'uuid-...'          # LangSmith project ID
  org_id: ''                      # Org ID (empty = default)
  tool_names: []                  # Tools to track (empty = auto)

# -----------------------------------------------------------------------------
# Ollama LLM (optional)
# -----------------------------------------------------------------------------
ollama:
  enabled: true
  model: llama3.2:3b              # Model for evaluation
  url: http://localhost:11434/api/generate
```

#### CSS Selectors - How to Find Them

1. Open the chatbot in browser
2. Press `F12` for DevTools
3. Use the element selector (arrow icon)
4. Click on the desired element
5. Copy the CSS selector from HTML

**Common examples:**
```yaml
# By ID
textarea: '#message-input'

# By class
bot_messages: '.chat-message.assistant'

# By attribute
submit_button: 'button[type="submit"]'

# Combined
thread_container: 'div.chat-container > .messages'
```

#### Screenshot CSS - Customization

The `screenshot_css` field injects CSS before capturing the screenshot:

```yaml
screenshot_css: |
  /* Hide footer */
  footer { display: none !important; }

  /* Hide input bar */
  .input-bar { display: none !important; }

  /* Expand container */
  .chat-container {
    max-height: none !important;
    overflow: visible !important;
  }

  /* Hide scrollbar */
  ::-webkit-scrollbar { display: none !important; }
```

#### Authentication Configuration

For chatbots requiring login (especially for cloud CI), configure the `auth` section:

**No Auth (default):**
```yaml
auth:
  type: none
```

**HTTP Basic Auth:**
```yaml
auth:
  type: basic
  basic_username_env: CHATBOT_USERNAME   # Env var name for username
  basic_password_env: CHATBOT_PASSWORD   # Env var name for password
```

**Form Login:**
```yaml
auth:
  type: form
  form_username_selector: '#username'     # CSS selector for username field
  form_password_selector: '#password'     # CSS selector for password field
  form_submit_selector: '#login-btn'      # CSS selector for submit button
  form_username_env: CHATBOT_USERNAME     # Env var name for username
  form_password_env: CHATBOT_PASSWORD     # Env var name for password
  form_success_selector: '#chat-input'    # Element visible after login
  timeout_ms: 30000                       # Auth timeout
```

**SSO (Microsoft/Google):**
```yaml
auth:
  type: sso
  sso_provider: microsoft                 # microsoft | google
  sso_email_env: SSO_EMAIL                # Env var for email
  sso_password_env: SSO_PASSWORD          # Env var for password
  sso_success_selector: '#chat-input'     # Element visible after login
  timeout_ms: 30000                       # Auth timeout
```

**GitHub Actions Secrets:**

For cloud CI, store credentials as repository secrets:
```bash
# Set secrets
gh secret set CHATBOT_USERNAME --body "your-username"
gh secret set CHATBOT_PASSWORD --body "your-password"
```

Then in your workflow:
```yaml
env:
  CHATBOT_USERNAME: ${{ secrets.CHATBOT_USERNAME }}
  CHATBOT_PASSWORD: ${{ secrets.CHATBOT_PASSWORD }}
```

---

### run_config.json (Run State)

**Path:** `projects/<name>/run_config.json`

Current test session state. Also modifiable from interactive menu.

```json
{
  "env": "DEV",
  "prompt_version": "v2.1",
  "model_version": "gpt-4o",
  "active_run": 15,
  "run_start": "2025-12-05T10:00:00",
  "tests_completed": 25,
  "mode": "auto",
  "last_test_id": "TEST_025",
  "dry_run": false,
  "use_langsmith": true,
  "use_rag": false,
  "use_ollama": true,
  "single_turn": false
}
```

#### Run Options

| Option | Type | Description | Where to Configure |
|--------|------|-------------|-------------------|
| `env` | string | Environment: DEV, STAGING, PROD | Menu > Configure |
| `prompt_version` | string | Chatbot prompt version | Menu > Configure |
| `model_version` | string | Chatbot LLM model version | Auto from LangSmith |
| `active_run` | number | Run number on Google Sheets | Auto |
| `dry_run` | bool | Simulate without executing | Menu > Toggle |
| `use_langsmith` | bool | Enable LangSmith tracing | Menu > Toggle |
| `use_rag` | bool | Enable RAG retrieval | Menu > Toggle |
| `use_ollama` | bool | Enable Ollama evaluation | Menu > Toggle |
| `single_turn` | bool | Initial question only | Menu > Toggle |

#### Single Turn Mode

When `single_turn: true`:
- Executes **only** the initial question for each test
- Does **not** generate followups with Ollama
- Useful for quick tests or when Ollama is not available

---

## 3. Runtime Toggles

Accessible from interactive menu: **Project > Toggle Options**

| Toggle | Effect ON | Effect OFF |
|--------|-----------|------------|
| **Dry Run** | Simulate tests without executing | Real execution |
| **LangSmith** | Retrieve traces and sources | Skip LangSmith |
| **RAG** | Enable RAG search | Disable RAG |
| **Ollama** | Automatic AI evaluation | Manual evaluation |
| **Single Turn** | Initial question only | Full conversation |

### From CLI

```bash
# Dry run
python run.py -p my-chatbot -m auto --dry-run

# Without Ollama (set in run_config.json)
# Modify: "use_ollama": false
python run.py -p my-chatbot -m auto --no-interactive
```

---

## 4. Environment Variables

**Path:** `config/.env` (not versioned)

```bash
# LangSmith
LANGSMITH_API_KEY=lsv2_sk_...

# Google (optional, if not using credentials file)
GOOGLE_APPLICATION_CREDENTIALS=/path/to/credentials.json

# OpenAI (for fine-tuning)
OPENAI_API_KEY=sk-...
```

### Configuration Priority

1. **CLI** (highest priority)
2. **Environment variables**
3. **run_config.json**
4. **project.yaml**
5. **settings.yaml** (lowest priority)

---

## 5. Test Case Schema

**Path:** `projects/<name>/tests.json`

Defines the test cases to execute. Each test case is a JSON object with the following fields:

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique test identifier (e.g., "TEST_001") |
| `question` | string | Initial question to send to chatbot |

### Optional Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `category` | string | "" | Test category for grouping |
| `expected` | string | "" | Expected behavior (qualitative description) |
| `expected_answer` | string | null | Expected answer for semantic matching |
| `rag_context_file` | string | null | Path to RAG context file (relative to project/) |
| `followups` | array | [] | List of followup questions |
| `data` | object | {} | Test-specific data (email, country, etc.) |
| `tags` | array | [] | Tags for filtering tests |

### Basic Example

```json
[
  {
    "id": "TEST_001",
    "question": "What are your opening hours?",
    "category": "info",
    "expected": "Should list business hours"
  },
  {
    "id": "TEST_002",
    "question": "How do I reset my password?",
    "category": "account",
    "followups": ["I don't have access to my email"]
  }
]
```

### Evaluation Example (with expected_answer)

```json
[
  {
    "id": "TEST_001",
    "question": "What products do you have?",
    "category": "catalog",
    "expected": "Lists available products",
    "expected_answer": "We have products A, B, and C available in various sizes.",
    "rag_context_file": "knowledge/products.md"
  }
]
```

### With Dynamic Data

```json
[
  {
    "id": "TEST_003",
    "question": "I'd like to schedule an appointment",
    "data": {
      "email": "test@example.com",
      "country": "IT",
      "preferred_date": "2025-01-15"
    },
    "followups": [
      "Can we do morning instead?",
      "Please confirm the appointment"
    ]
  }
]
```

### RAG Context Files

When using `rag_context_file`, create a knowledge file in your project folder:

```
projects/my-chatbot/
├── knowledge/
│   ├── products.md      # Product catalog
│   ├── faq.md           # FAQ content
│   └── policies.md      # Company policies
└── tests.json
```

The evaluation system uses these files to measure:
- **Groundedness**: Is the answer based on provided context?
- **Faithfulness**: Does the answer accurately represent the context?
- **Relevance**: Is the answer relevant to the question?

---

## Troubleshooting

### Browser doesn't open

```bash
# Install browser
playwright install chromium

# Verify
playwright --version
```

### Selectors don't work

1. Open browser with `--debug`:
   ```bash
   python run.py -p my-project --debug
   ```
2. Verify selectors in DevTools
3. Update `project.yaml`

### Empty screenshots

Verify `screenshot_css` doesn't hide necessary elements.

### Frequent timeouts

Increase timeouts in `project.yaml`:
```yaml
chatbot:
  timeouts:
    page_load: 60000    # 60 seconds
    bot_response: 120000 # 2 minutes
```

---

## Quick Reference

### Main Files

| File | Scope | Modify |
|------|-------|--------|
| `config/settings.yaml` | Global | Manual |
| `projects/<name>/project.yaml` | Project | Wizard or manual |
| `projects/<name>/run_config.json` | Session | Menu or manual |
| `config/.env` | Credentials | Manual |

### Useful Commands

```bash
# View configuration
cat projects/my-chatbot/project.yaml
cat projects/my-chatbot/run_config.json

# Reset run
rm projects/my-chatbot/run_config.json

# Reset browser session
rm -rf projects/my-chatbot/browser-data/
```
