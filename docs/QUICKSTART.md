# Quick Start Guide

Get your first chatbot test running in 5 minutes.

---

## Prerequisites

- Python 3.10+
- macOS 12+ (or Linux)
- A web-based chatbot to test

---

## Step 1: Install

```bash
git clone https://github.com/corradofrancolini/chatbot-tester.git
cd chatbot-tester
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

---

## Step 2: Create Your First Project

Run the interactive wizard:

```bash
python run.py --new-project
```

The wizard will guide you through:

1. **Project name** - e.g., `my-chatbot`
2. **Chatbot URL** - the page where your chatbot lives
3. **Login** - if required, login in the browser that opens
4. **Selectors** - auto-detected or click-to-learn
5. **Test cases** - import from JSON/CSV or create later

---

## Step 3: Add Test Cases

Create a simple `tests.json` in your project folder:

```json
[
  {
    "id": "TC001",
    "question": "What are your opening hours?",
    "category": "info",
    "expected_topics": ["hours", "open"]
  },
  {
    "id": "TC002",
    "question": "How do I reset my password?",
    "category": "account",
    "expected_topics": ["password", "reset", "email"]
  }
]
```

Or import from CSV:

```csv
id,question,category,expected_topics
TC001,"What are your opening hours?",info,"hours,open"
TC002,"How do I reset my password?",account,"password,reset,email"
```

---

## Step 4: Run Your First Test

### Train Mode (learning)

Start with Train mode to teach the tool what good responses look like:

```bash
python run.py -p my-chatbot -m train
```

The browser opens, sends each question, and asks you to evaluate the response.

### Auto Mode (automated)

Once you've trained on some tests, run fully automated:

```bash
python run.py -p my-chatbot -m auto --no-interactive --new-run
```

---

## Step 5: View Results

After the run completes:

```bash
# Open the HTML report
open reports/my-chatbot/run_1/report.html

# Or export to other formats
python run.py -p my-chatbot --export pdf
python run.py -p my-chatbot --export excel
```

---

## Common Commands

| Command | Description |
|---------|-------------|
| `python run.py` | Interactive menu |
| `python run.py -p PROJECT -m train` | Train mode |
| `python run.py -p PROJECT -m auto --no-interactive` | Auto mode (pending tests) |
| `python run.py -p PROJECT -m auto --no-interactive --new-run` | Auto mode (new run) |
| `python run.py -p PROJECT --tests failed` | Re-run failed tests |
| `python run.py -p PROJECT --export pdf` | Export report |
| `python run.py --health-check -p PROJECT` | Check services |

---

## Project Structure

After setup, your project folder looks like:

```
projects/my-chatbot/
├── project.yaml      # Chatbot URL, selectors, settings
├── tests.json        # Your test cases
├── run_config.json   # Current run state
└── browser-data/     # Saved browser session
```

---

## What's Next?

- **Add more tests** - build a comprehensive test suite
- **Configure Google Sheets** - for team collaboration ([docs/CONFIGURATION.md](CONFIGURATION.md))
- **Enable LangSmith** - for detailed response debugging
- **Set up CI/CD** - run tests automatically ([docs/DEPLOYMENT.md](DEPLOYMENT.md))
- **Configure notifications** - get alerts on failures

---

## Troubleshooting

**Browser doesn't open?**
```bash
playwright install chromium
```

**Session expired?**
```bash
rm -rf projects/my-chatbot/browser-data/
python run.py -p my-chatbot  # Login again
```

**Selectors not working?**
Run the wizard again with `--new-project` or edit `project.yaml` manually.

For more help: [docs/TROUBLESHOOTING.md](TROUBLESHOOTING.md)

---

## Full Documentation

| Guide | Description |
|-------|-------------|
| [NEW_PROJECT.md](NEW_PROJECT.md) | Detailed project configuration |
| [CONFIGURATION.md](CONFIGURATION.md) | All configuration options |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Docker, GitHub Actions, CI/CD |
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | Common issues and solutions |
