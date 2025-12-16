# Chatbot Tester - Project Notes

**Mantra: If it can be done, it must be visible, explained, and configurable.**

## Documentation

| Guide | Content |
|-------|---------|
| [README.md](README.md) | Overview and quick start |
| [docs/CONFIGURATION.md](docs/CONFIGURATION.md) | Complete configuration guide |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Docker, GitHub Actions, PyPI |

---

## Main Commands

### Running tests
```bash
# New full run
python run.py -p my-chatbot -m auto --no-interactive --new-run

# Continue existing run (pending only)
python run.py -p my-chatbot -m auto --no-interactive

# Single test (overwrite)
python run.py -p my-chatbot -m auto --no-interactive -t TEST_050 --tests all

# Failed tests only
python run.py -p my-chatbot -m auto --no-interactive --tests failed
```

### Health Check
```bash
# Verify services before execution
python run.py --health-check -p my-chatbot

# Run tests skipping health check
python run.py -p my-chatbot -m auto --no-interactive --skip-health-check
```

---

## run_config.json Configuration

| Option | Description | Menu |
|--------|-------------|------|
| `env` | Environment: DEV, STAGING, PROD | Configure |
| `dry_run` | Simulate without executing | Toggle [1] |
| `use_langsmith` | Enable LangSmith tracing | Toggle [2] |
| `use_rag` | Enable RAG retrieval | Toggle [3] |
| `use_ollama` | Enable Ollama evaluation | Toggle [4] |
| `single_turn` | Initial question only | Toggle [5] |
| `active_run` | Run number on Google Sheets | Auto |

### Complete CLI Options

```bash
python run.py [OPTIONS]

# Project and mode
-p, --project       Project name
-m, --mode          train | assisted | auto
-t, --test          Single test ID
--tests             all | pending | failed
--new-run           Force new RUN

# Behavior
--no-interactive    No user prompts
--dry-run           Simulate
--headless          Hidden browser

# Services
--health-check      Verify services and exit
--skip-health-check Skip verification

# Debug
--debug             Detailed output
--lang              it | en
-v, --version       Show version

# Export
--export            pdf | excel | html | csv | all
--export-run        Run number to export

# Notifications
--notify            desktop | email | teams | all
--test-notify       Test notification configuration

# Performance
--perf-report       Show performance report
--perf-dashboard    Historical performance dashboard
--perf-compare      Compare two runs (e.g., 15:16)
--list-runs         List all runs from all projects
```

---

## Screenshots

Screenshots must capture the ENTIRE conversation with ALL products visible.

**Key file:** `src/browser.py` method `take_conversation_screenshot()`
- Uses CSS injection to hide input bar, footer, scroll indicators
- Expands containers to show all content
- Captures `section.llm__thread`

---

## Report Structure

```
reports/{project}/run_{N}/
├── report.html       # Interactive HTML report
├── screenshots/      # Conversation screenshots
│   ├── TEST_001.png
│   └── ...
└── performance/      # Performance metrics
    └── performance_run_{N}.json
```

---

## Main Modules

| Module | Description |
|--------|-------------|
| `run.py` | Entry point, CLI, interactive menu |
| `src/tester.py` | Main test engine |
| `src/browser.py` | Playwright automation |
| `src/health.py` | Health checks, circuit breaker, retry |
| `src/sheets_client.py` | Google Sheets integration |
| `src/langsmith_client.py` | LangSmith tracing |
| `src/ollama_client.py` | Local AI evaluation |
| `src/config_loader.py` | Configuration loading |
| `src/i18n.py` | IT/EN translations |
| `src/ui.py` | Console UI (Rich) |
| `src/finetuning.py` | Fine-tuning pipeline |
| `src/parallel.py` | Parallel execution, browser pool |
| `src/cache.py` | In-memory and disk caching |
| `src/comparison.py` | A/B comparison, regressions, flaky tests |
| `src/scheduler.py` | Scheduled runs, distributed execution |
| `src/notifications.py` | Email, Desktop, Teams notifications |
| `src/export.py` | Export PDF, Excel, HTML, CSV |
| `src/github_actions.py` | GitHub Actions integration |
| `src/performance.py` | Performance metrics collection |
| `wizard/main.py` | New project wizard |

---

## Parallel Execution (v1.2.0)

### CLI
```bash
# 3 browsers in parallel
python run.py -p my-chatbot -m auto --parallel --no-interactive

# 5 browsers
python run.py -p my-chatbot -m auto --parallel --workers 5 --no-interactive
```

### How it works
1. `BrowserPool` creates N isolated Chromium browsers
2. Tests are distributed to workers
3. Each worker accumulates results in `ThreadSafeSheetsClient`
4. At the end, `flush()` writes everything in batch to Google Sheets

### Developer API
```python
from src.sheets_client import ThreadSafeSheetsClient, ParallelResultsCollector

# Thread-safe wrapper for Sheets
safe_client = ThreadSafeSheetsClient(sheets_client)
safe_client.queue_result(result)    # Thread-safe
safe_client.queue_screenshot(path, test_id)
safe_client.flush()                 # Write batch

# Or: in-memory collector
collector = ParallelResultsCollector()
collector.add(result)
all_results = collector.get_all()
```

### Configuration (settings.yaml)
```yaml
parallel:
  enabled: false
  max_workers: 3
  retry_strategy: exponential  # none | linear | exponential
  max_retries: 2
  rate_limit_per_minute: 60

cache:
  enabled: true
  memory:
    max_entries: 1000
    default_ttl_seconds: 300
```

---

## Testing Analysis (v1.2.0)

### CLI
```bash
# Compare last 2 runs
python run.py -p my-chatbot --compare

# Compare specific runs
python run.py -p my-chatbot --compare 15:16

# Show regressions in last run
python run.py -p my-chatbot --regressions

# Regressions in specific run
python run.py -p my-chatbot --regressions 16

# Flaky tests over last 10 runs
python run.py -p my-chatbot --flaky

# Flaky tests over last 20 runs
python run.py -p my-chatbot --flaky 20
```

### Interactive Menu
From `python run.py` > **[5] Testing Analysis**:
- **Compare RUN** - A/B comparison between two runs
- **Detect Regressions** - PASS->FAIL tests
- **Flaky Tests** - Inconsistent results
- **Coverage** - Test distribution by category
- **Stability Report** - Test suite quality overview
- **Performance** - Metrics and trends

### Modules (`src/comparison.py`)

```python
from src.comparison import (
    RunComparator, RegressionDetector,
    CoverageAnalyzer, FlakyTestDetector
)

# A/B comparison
comparator = RunComparator(project)
result = comparator.compare(15, 16)  # RUN 15 vs 16
result = comparator.compare_latest() # Last 2

# Regressions
detector = RegressionDetector(project)
regressions = detector.check_for_regressions(16)
# TestChange(test_id, old_status, new_status, change_type)

# Flaky tests
flaky = FlakyTestDetector(project)
flaky_tests = flaky.detect_flaky_tests(last_n_runs=10, threshold=0.3)
# FlakyTestReport(test_id, flaky_score, pass_count, fail_count)

# Coverage
coverage = CoverageAnalyzer(project)
report = coverage.analyze(tests)
# CoverageReport(total_tests, categories_covered, gaps)
```

### Key Concepts

| Term | Definition |
|------|------------|
| **Regression** | Test that passed and now fails (PASS->FAIL) |
| **Improvement** | Test that failed and now passes (FAIL->PASS) |
| **Flaky Score** | 0 = stable, 1 = random results |
| **Coverage Gap** | Categories with few tests |

---

## Automation (v1.2.0)

### Scheduled Runs (Local)

```bash
# Add daily schedule
python run.py --add-schedule my-chatbot:daily

# Add weekly schedule
python run.py --add-schedule my-chatbot:weekly

# List configured schedules
python run.py --list-schedules

# Start local scheduler (cron-like, Ctrl+C to stop)
python run.py --scheduler
```

### Scheduled Runs (GitHub Actions)

The workflow `.github/workflows/scheduled-tests.yml` runs automatically:
- **Daily** (6:00 UTC): Pending tests on all projects
- **Weekly** (Mon 2:00 UTC): Full run with new RUN

```yaml
# To enable, required secrets are:
# - LANGSMITH_API_KEY
# - GOOGLE_OAUTH_CREDENTIALS
# - GOOGLE_TOKEN_JSON
# - SLACK_WEBHOOK_URL (optional, for notifications)
```

### Scheduler API

```python
from src.scheduler import LocalScheduler, ScheduleConfig, ScheduleType

scheduler = LocalScheduler()

# Add custom schedule
scheduler.add_schedule(ScheduleConfig(
    name="my-schedule",
    project="my-chatbot",
    schedule_type=ScheduleType.DAILY,  # DAILY, WEEKLY, HOURLY, INTERVAL
    mode="auto",
    tests="pending",
    cron_hour=6,
    cron_minute=0
))

# Start (blocks process)
scheduler.start()

# Or in background
scheduler.start_background()
```

### Distributed Execution

```python
from src.scheduler import DistributedCoordinator, WorkerConfig

coordinator = DistributedCoordinator()

# Register worker
coordinator.register_worker(WorkerConfig(
    worker_id="worker-1",
    host="192.168.1.10",
    port=5000,
    projects=["my-chatbot"]
))

# Distribute tests
distribution = coordinator.distribute_tests(tests, project="my-chatbot")
# {"worker-1": [test1, test3], "worker-2": [test2, test4]}
```

---

## Report Export (v1.2.0)

### CLI

```bash
# Export last run to PDF
python run.py -p my-chatbot --export pdf

# Export specific run to Excel
python run.py -p my-chatbot --export excel --export-run 15

# Export all formats
python run.py -p my-chatbot --export all

# Available formats: pdf, excel, html, csv, all
```

### Optional Dependencies

```bash
# For PDF
pip install reportlab pillow

# For Excel
pip install openpyxl
```

### Output

Exported files are saved in:
```
reports/{project}/run_{N}/exports/
├── project_runN.pdf
├── project_runN.xlsx
├── project_runN.html
└── project_runN.csv
```

### API

```python
from src.export import RunReport, ReportExporter

# Load report
report = RunReport.from_local_report(Path("reports/my-chatbot/run_15/report.json"))

# Export
exporter = ReportExporter(report)
exporter.to_pdf(Path("output.pdf"))
exporter.to_excel(Path("output.xlsx"))
exporter.to_html(Path("output.html"))
exporter.to_csv(Path("output.csv"))

# Multiple export
results = exporter.export_all(Path("exports/"))
```

---

## Notifications (v1.2.0)

### CLI

```bash
# Test notification configuration
python run.py --test-notify

# Send desktop notification (last run)
python run.py -p my-chatbot --notify desktop

# Send email
python run.py -p my-chatbot --notify email

# Send to Teams
python run.py -p my-chatbot --notify teams

# Send on all configured channels
python run.py -p my-chatbot --notify all
```

### Configuration (settings.yaml)

```yaml
notifications:
  email:
    enabled: true
    smtp_host: "smtp.gmail.com"
    smtp_port: 587
    smtp_user: "your@email.com"
    smtp_password_env: "SMTP_PASSWORD"  # export SMTP_PASSWORD=xxx
    recipients:
      - "team@example.com"

  desktop:
    enabled: true
    sound: true

  teams:
    enabled: true
    webhook_url_env: "TEAMS_WEBHOOK_URL"  # export TEAMS_WEBHOOK_URL=https://...

  triggers:
    on_complete: true     # Every completed run
    on_failure: true      # Failures only
    on_regression: false  # Regressions detected
    on_flaky: true        # Flaky tests detected
```

### Teams Webhook

To configure Teams:
1. Go to Teams channel > Connectors > Incoming Webhook
2. Create webhook and copy URL
3. `export TEAMS_WEBHOOK_URL="https://..."`

### API

```python
from src.notifications import NotificationManager, NotificationConfig, TestRunSummary

# Config
config = NotificationConfig(
    desktop_enabled=True,
    email_enabled=True,
    teams_enabled=True
)

manager = NotificationManager(config)

# Results summary
summary = TestRunSummary(
    project="my-chatbot",
    run_number=15,
    total_tests=50,
    passed=45,
    failed=5,
    pass_rate=90.0
)

# Notify on all channels
manager.notify_run_complete(summary)

# Single channel notification
manager.send_desktop("Title", "Message")
manager.send_email("Subject", "Body")
manager.send_teams("Title", "Message")
```

---

## Deployment (v1.1.0)

### Docker
```bash
docker build -t chatbot-tester .
docker run -v ./projects:/app/projects chatbot-tester -p my-chatbot -m auto
```

### GitHub Actions
```bash
# Run tests in cloud
gh workflow run chatbot-test.yml -f project=my-chatbot -f mode=auto

# Monitor with progress bar
python run.py --watch-cloud
```

### PyPI (after publishing)
```bash
pip install chatbot-tester
chatbot-tester -p my-chatbot -m auto
```

### Standalone binary
```bash
pip install pyinstaller
pyinstaller chatbot-tester.spec
./dist/chatbot-tester -p my-chatbot -m auto
```

---

## Deployment Files

| File | Purpose |
|------|---------|
| `Dockerfile` | Docker image build |
| `.github/workflows/chatbot-test.yml` | Cloud test execution |
| `.github/workflows/scheduled-tests.yml` | Scheduled test runs |
| `.github/workflows/build-release.yml` | Automatic release builds |
| `action.yml` | GitHub Action for marketplace |
| `pyproject.toml` | PyPI configuration |
| `chatbot-tester.spec` | PyInstaller configuration |

---

## Configured Projects

- `my-chatbot` → Example chatbot project (customize in projects/ directory)

---

## TODO / Backlog

### UX
- [x] **Improved progress bar**: ETA, tests/minute, phase indicator (v1.7.0)

### Automation
- [x] **Remote notifications**: GitHub Actions workflows with Email/Teams (v1.7.0)
- [x] **Parallel execution**: Multi-browser via --parallel --workers N (v1.7.0)

### Internationalization
- [ ] **Complete i18n**: Integrate src/i18n.py in all modules

---

## Settings Menu (v1.2.0)

From main menu: **[7] Settings**

### Available submenus

| Item | Description |
|------|-------------|
| **Language** | Switch IT/EN |
| **Notifications** | Configure Desktop, Email, Teams + Triggers |
| **Browser** | Headless, viewport, slow_mo |
| **Logging** | Log level (DEBUG/INFO/WARNING/ERROR) |
| **Test Notifications** | Send test notification |

### Notifications - Submenu

```
[1] Desktop: ON/OFF     — macOS native notifications
[2] Email: ON/OFF       — SMTP notifications
[3] Teams: ON/OFF       — Microsoft Teams notifications
[4] Triggers            — When to send notifications
```

### Notification Triggers

```
[1] On Complete: ON/OFF  — Every completed run
[2] On Failure: ON/OFF   — Failures only
[3] On Regression: ON/OFF — If regressions detected
[4] On Flaky: ON/OFF     — If flaky tests detected
```

Changes are saved directly to `config/settings.yaml`.

---

## Performance Metrics (v1.6.0)

Performance metrics system for monitoring test execution.

### CLI

```bash
# Performance report for last run
python run.py -p my-chatbot --perf-report

# Report for specific run
python run.py -p my-chatbot --perf-report 18

# Historical dashboard (last N runs trend)
python run.py -p my-chatbot --perf-dashboard
python run.py -p my-chatbot --perf-dashboard 20  # last 20 runs

# Compare two runs (e.g., local vs cloud)
python run.py -p my-chatbot --perf-compare 15:16

# Export report
python run.py -p my-chatbot --perf-export json
python run.py -p my-chatbot --perf-export html  # opens in browser

# List all runs from all projects
python run.py --list-runs
```

### Interactive Menu

From `python run.py` > **[5] Testing Analysis** > **[6] Performance**:
- **Last run report** - Detailed metrics
- **Historical dashboard** - Trends over last N runs
- **Compare runs** - A/B comparison
- **Export HTML** - Interactive browser report

### Collected Metrics

| Category | Metrics |
|----------|---------|
| **Timing** | Total duration, average per test, min/max, per-phase breakdown |
| **Throughput** | Tests/minute, comparison with previous runs |
| **Reliability** | Retries, timeouts, error rate, flakiness |
| **External Services** | Chatbot latency, Google Sheets, LangSmith |

### Post-Run Report

At the end of each AUTO mode run, automatically generated:
1. **Text summary** - Main metrics recap
2. **Alerting** - Warnings if metrics out of threshold
3. **JSON file** - Complete data in `reports/{project}/performance/`

### Alerting

Configurable thresholds for automatic warnings:

| Threshold | Default |
|-----------|---------|
| Duration increase | >20% vs baseline |
| Throughput decrease | >15% |
| Error rate | >10% |
| Pass rate | <80% |
| Chatbot latency | >30s |
| Sheets latency | >5s |

### API

```python
from src.performance import (
    PerformanceCollector, PerformanceReporter, PerformanceHistory,
    PerformanceAlerter, compare_environments, format_comparison_report
)

# Metrics collection (automatic in tester.py)
collector = PerformanceCollector("run_18", "my-chatbot", "local")
collector.start_test("TEST_001")
collector.start_phase("send_question")
# ... execution ...
collector.end_phase()
collector.record_service_call("chatbot", "response", 1500.0)
collector.end_test("PASS")
run_metrics = collector.finalize()

# Report
reporter = PerformanceReporter(run_metrics)
print(reporter.generate_summary())
html = reporter.generate_html_report()

# History and trends
history = PerformanceHistory("my-chatbot", Path("reports"))
history.save_run(run_metrics)
trends = history.get_trends(last_n=10)

# Alerting
alerter = PerformanceAlerter()
alerts = alerter.check(run_metrics)
print(alerter.format_alerts())

# Local vs cloud comparison
comparison = compare_environments(local_metrics, cloud_metrics)
print(format_comparison_report(comparison))
```
