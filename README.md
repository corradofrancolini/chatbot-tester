# Chatbot Tester

Automated testing tool for web chatbots with multi-project support, local AI, and advanced reporting.

[![macOS](https://img.shields.io/badge/macOS-12.0+-blue.svg)](https://www.apple.com/macos/)
[![Python](https://img.shields.io/badge/Python-3.10+-green.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Getting Started

| New here? | Start with |
|-----------|------------|
| **5-minute setup** | [**Quick Start Guide**](docs/QUICKSTART.md) |
| **Detailed configuration** | [New Project Guide](docs/NEW_PROJECT.md) |
| **All options** | [Configuration Reference](docs/CONFIGURATION.md) |

```bash
# Clone and install
git clone https://github.com/corradofrancolini/chatbot-tester.git
cd chatbot-tester && python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && playwright install chromium

# Create your first project
python run.py --new-project
```

---

## Features

- **Multi-project**: Test different chatbots from the same installation
- **3 Modes**: Train, Assisted, Auto for each testing phase
- **Local AI**: Ollama for privacy-first analysis
- **Flexible Reports**: Local HTML + optional Google Sheets
- **Report Export**: PDF, Excel, HTML, CSV
- **Notifications**: Desktop (macOS), Email, Microsoft Teams
- **Full Screenshots**: Capture entire conversation with all products
- **Single-Turn Mode**: Execute only initial question without followups
- **LangSmith Integration**: Advanced chatbot response debugging
- **Testing Analysis**: A/B comparison, regressions, flaky tests
- **Parallel Execution**: Multi-browser for fast testing
- **Scheduled Runs**: Local cron and GitHub Actions
- **Performance Metrics**: Timing, throughput, latency tracking with alerting
- **Bilingual**: Italian and English
- **Health Check**: Service verification before execution
- **Cloud Execution**: Run tests on GitHub Actions without local Chromium
- **Docker Ready**: Ready-to-use container

---

## Quick Start

### 1. Installation

```bash
# Clone the repository
git clone https://github.com/corradofrancolini/chatbot-tester.git
cd chatbot-tester

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
playwright install chromium
```

### 2. Run tests

```bash
# Auto mode - new run
python run.py -p my-chatbot -m auto --no-interactive --new-run

# Auto mode - continue existing run
python run.py -p my-chatbot -m auto --no-interactive

# Train mode (learning)
python run.py -p my-chatbot -m train
```

---

## CLI Commands

### Test Execution

```bash
# New full run (creates new Google Sheets sheet)
python run.py -p <project> -m auto --no-interactive --new-run

# Continue existing run (pending tests only)
python run.py -p <project> -m auto --no-interactive

# Execute single test
python run.py -p <project> -m auto --no-interactive -t TEST_050

# Re-run single test (overwrite)
python run.py -p <project> -m auto --no-interactive -t TEST_050 --tests all

# Re-run all failed tests
python run.py -p <project> -m auto --no-interactive --tests failed

# Re-run all tests (overwrite)
python run.py -p <project> -m auto --no-interactive --tests all
```

### Report Export

```bash
# Export last run to HTML
python run.py -p <project> --export html

# Export specific run to PDF
python run.py -p <project> --export pdf --export-run 15

# Export all formats
python run.py -p <project> --export all
```

### Performance Metrics

```bash
# Show performance report for last run
python run.py -p <project> --perf-report

# Historical dashboard (last N runs)
python run.py -p <project> --perf-dashboard 10

# Compare two runs (e.g., local vs cloud)
python run.py -p <project> --perf-compare 15:16

# List all runs from all projects
python run.py --list-runs
```

### Notifications

```bash
# Test desktop notification
python run.py -p <project> --test-notify

# Send notification after run
python run.py -p <project> -m auto --no-interactive --notify desktop
```

### Options

| Option | Description | Default |
|--------|-------------|---------|
| `-p, --project` | Project name | - |
| `-m, --mode` | Mode: train, assisted, auto | train |
| `-t, --test` | Single test ID to execute | - |
| `--tests` | Which tests: all, pending, failed | pending |
| `--new-run` | Create new run on Google Sheets | false |
| `--no-interactive` | Non-interactive execution | false |
| `--dry-run` | Simulate without executing | false |
| `--health-check` | Check services and exit | false |
| `--skip-health-check` | Skip service verification | false |
| `--headless` | Browser in headless mode | false |
| `--lang` | Interface language: it, en | it |
| `--debug` | Detailed debug output | false |
| `--export` | Export report: pdf, excel, html, csv, all | - |
| `--export-run` | Run number to export | latest |
| `--notify` | Send notification: desktop, email, teams, all | - |
| `--test-notify` | Test notification configuration | false |
| `--perf-report` | Show performance report | - |
| `--perf-dashboard` | Historical performance dashboard | - |
| `--list-runs` | List recent runs from all projects | - |
| `-v, --version` | Show version | - |

For the complete guide to all configuration options, see [docs/CONFIGURATION.md](docs/CONFIGURATION.md).

---

## Test Modes

| Mode | Description | When to use |
|------|-------------|-------------|
| **Train** | Execute tests manually, tool learns | Initial setup |
| **Assisted** | AI suggests, you confirm | Validation, corrections |
| **Auto** | Fully automatic | Regression testing |

---

## Configuration

### run_config.json

Each project has a `projects/<name>/run_config.json` file:

```json
{
  "env": "DEV",
  "active_run": 15,
  "mode": "auto",
  "use_langsmith": true,
  "use_ollama": true,
  "single_turn": true
}
```

| Option | Description | Accessible from |
|--------|-------------|-----------------|
| `env` | Environment: DEV, STAGING, PROD | Menu > Configure |
| `active_run` | Active run number on Google Sheets | Automatic |
| `dry_run` | Simulate without executing | Menu > Toggle |
| `use_langsmith` | Enable LangSmith tracing | Menu > Toggle |
| `use_rag` | Enable RAG retrieval | Menu > Toggle |
| `use_ollama` | Enable Ollama evaluation | Menu > Toggle |
| `single_turn` | Initial question only, no followups | Menu > Toggle |

### Runtime Toggles

From interactive menu: **Project > Toggle Options**

```
[1] Dry Run:      OFF  (simulate without executing)
[2] LangSmith:    ON   (tracing active)
[3] RAG:          OFF  (disabled)
[4] Ollama:       ON   (AI evaluation)
[5] Single Turn:  ON   (initial question only)
```

---

## Screenshots

Screenshots capture the **entire conversation** with all products visible.

- Automatically hides: input bar, footer, scroll indicators
- Expands containers to show all content
- Saves to: `reports/<project>/run_<N>/screenshots/`

---

## Project Structure

```
chatbot-tester/
├── run.py                  # Entry point
├── CLAUDE.md               # Project notes for Claude Code
│
├── config/
│   ├── .env                # Credentials (gitignored)
│   └── settings.yaml       # Global settings
│
├── projects/               # Configured projects
│   └── <project-name>/
│       ├── project.yaml    # Chatbot configuration
│       ├── tests.json      # Test cases
│       ├── run_config.json # Current run state
│       └── browser-data/   # Browser session
│
├── reports/                # Local reports
│   └── <project-name>/
│       └── run_<N>/
│           ├── report.html
│           ├── screenshots/
│           └── performance/
│
└── src/                    # Source code
    ├── browser.py          # Playwright automation
    ├── tester.py           # Test logic
    ├── config_loader.py    # Configuration management
    ├── export.py           # Export PDF, Excel, HTML, CSV
    ├── notifications.py    # Desktop, Email, Teams notifications
    └── performance.py      # Performance metrics collection
```

---

## Integrations

### Ollama (Local AI)

```bash
# Install Ollama
brew install ollama

# Start service
ollama serve

# Download model
ollama pull llama3.2:3b
```

### Google Sheets

1. Create project on [Google Cloud Console](https://console.cloud.google.com)
2. Enable Google Sheets API and Google Drive API
3. Create OAuth 2.0 credentials
4. Configure in `config/.env`

### LangSmith

1. Create account on [smith.langchain.com](https://smith.langchain.com)
2. Generate API Key
3. Configure in `config/.env`

### Notifications

Configure in `config/settings.yaml`:

```yaml
notifications:
  desktop:
    enabled: true      # macOS native
    sound: true
  email:
    enabled: false
    smtp_host: "smtp.gmail.com"
    smtp_port: 587
    smtp_user: "your@email.com"
    recipients: ["team@email.com"]
  teams:
    enabled: false
    webhook_url_env: "TEAMS_WEBHOOK_URL"  # Environment variable
  triggers:
    on_complete: true  # Notify on run completion
    on_failure: true   # Notify on failures
```

**Microsoft Teams**: Create an Incoming Webhook in Teams channel and set the environment variable:
```bash
export TEAMS_WEBHOOK_URL="https://outlook.office.com/webhook/..."
```

---

## Deployment

Run tests without local Chromium. See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for the complete guide.

### GitHub Actions (recommended)

```bash
# Install GitHub CLI
brew install gh

# Launch tests in the cloud
gh workflow run chatbot-test.yml -f project=my-chatbot -f mode=auto

# Monitor cloud run with progress bar
python run.py --watch-cloud
```

### Docker

```bash
# Build
docker build -t chatbot-tester .

# Run
docker run -v ./projects:/app/projects chatbot-tester -p my-chatbot -m auto
```

### Health Check

```bash
# Verify services before execution
python run.py --health-check -p my-chatbot
```

---

## Documentation

| Guide | Description |
|-------|-------------|
| [**QUICKSTART.md**](docs/QUICKSTART.md) | **5-minute setup guide** |
| [NEW_PROJECT.md](docs/NEW_PROJECT.md) | Detailed project configuration |
| [CONFIGURATION.md](docs/CONFIGURATION.md) | Complete guide to all options |
| [DEPLOYMENT.md](docs/DEPLOYMENT.md) | Deploy on Docker, GitHub Actions, PyPI |
| [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Common issues and solutions |
| [CLAUDE.md](CLAUDE.md) | Development notes for Claude Code |

---

## Troubleshooting

**Browser doesn't open**
```bash
source .venv/bin/activate
playwright install chromium
```

**"Module not found" error**
```bash
source .venv/bin/activate
pip install -r requirements.txt
```

**Session expired**
```bash
rm -rf projects/<name>/browser-data/
python run.py -p <name>
```

---

## License

MIT License - see [LICENSE](LICENSE) for details.
