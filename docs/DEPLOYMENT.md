# Deployment Guide

This guide explains how to run Chatbot Tester without having Chromium running on your Mac.

---

## Table of Contents

1. [GitHub Actions (Recommended)](#1-github-actions-recommended)
2. [Docker](#2-docker)
3. [PyPI Package](#3-pypi-package)
4. [Standalone Binary](#4-standalone-binary)
5. [GitHub Action Marketplace](#5-github-action-marketplace)

---

## 1. GitHub Actions (Recommended)

Run tests directly on GitHub servers, without any local software.

### Setup (one-time)

#### Step 1: Configure Secrets

Go to **GitHub > Settings > Secrets and variables > Actions** and add:

| Secret | Value | Required |
|--------|-------|----------|
| `LANGSMITH_API_KEY` | Your LangSmith API key | No |
| `GOOGLE_CREDENTIALS` | Google credentials JSON | No |

#### Step 2: Push the workflow

The `.github/workflows/chatbot-test.yml` file is already in the repo.

```bash
git add .github/
git commit -m "Add GitHub Actions workflow"
git push
```

### Daily Usage

#### Via web interface

1. Go to **GitHub > Actions > Chatbot Test Suite**
2. Click **Run workflow**
3. Fill in the parameters:
   - `project`: project name (e.g., `my-chatbot`)
   - `mode`: `auto`, `assisted`, or `train`
   - `tests`: `all`, `pending`, or `failed`
   - `new_run`: check to create new run

#### Via CLI (recommended)

```bash
# Install GitHub CLI
brew install gh

# Login
gh auth login

# Launch tests
gh workflow run chatbot-test.yml \
  -f project=my-chatbot \
  -f mode=auto \
  -f tests=pending

# Watch status
gh run watch

# Download report
gh run download <run-id>
```

### Costs

- **Free**: 2000 minutes/month for public repos
- **Private**: 2000 minutes/month included, then $0.008/minute

---

## 2. Docker

Run tests in an isolated container, locally or on a server.

### Local Setup

```bash
# Build image
docker build -t chatbot-tester .

# Verify
docker run chatbot-tester --help
```

### Local Execution

```bash
# With existing project
docker run \
  -v $(pwd)/projects:/app/projects \
  -v $(pwd)/reports:/app/reports \
  chatbot-tester \
  -p my-chatbot -m auto --no-interactive

# With environment variables
docker run \
  -e LANGSMITH_API_KEY=your_key \
  -v $(pwd)/projects:/app/projects \
  chatbot-tester \
  -p my-chatbot -m auto --no-interactive
```

### Remote Server Execution

```bash
# Step 1: Copy image to server
docker save chatbot-tester | ssh user@server docker load

# Step 2: Copy projects
scp -r projects/ user@server:~/chatbot-tester/

# Step 3: Run remotely
ssh user@server "docker run \
  -v ~/chatbot-tester/projects:/app/projects \
  chatbot-tester \
  -p my-chatbot -m auto --no-interactive"
```

### Docker Compose (optional)

Create `docker-compose.yml`:

```yaml
version: '3.8'
services:
  chatbot-tester:
    build: .
    volumes:
      - ./projects:/app/projects
      - ./reports:/app/reports
      - ./config:/app/config
    environment:
      - LANGSMITH_API_KEY=${LANGSMITH_API_KEY}
    command: ["-p", "my-chatbot", "-m", "auto", "--no-interactive"]
```

Run:
```bash
docker-compose run chatbot-tester
```

---

## 3. PyPI Package

Install as a standard Python package.

### Prerequisites

- Python 3.10+
- pip

### Installation (after publishing)

```bash
# Basic installation
pip install chatbot-tester

# With Google Sheets support
pip install chatbot-tester[google]

# Complete
pip install chatbot-tester[all]
```

### Usage

```bash
# Direct command
chatbot-tester -p my-chatbot -m auto --no-interactive

# Health check
chatbot-tester --health-check -p my-chatbot
```

### Publishing to PyPI (for maintainers)

```bash
# Build
pip install build twine
python -m build

# Upload to TestPyPI (test)
twine upload --repository testpypi dist/*

# Upload to PyPI (production)
twine upload dist/*
```

---

## 4. Standalone Binary

Single executable without Python dependencies.

### Prerequisites

```bash
pip install pyinstaller
```

### Build

```bash
# Build for current platform
pyinstaller chatbot-tester.spec

# Output in dist/chatbot-tester
```

### Usage

```bash
# Make executable (macOS/Linux)
chmod +x dist/chatbot-tester

# Run
./dist/chatbot-tester -p my-chatbot -m auto --no-interactive
```

### Notes

- The binary includes Python but does **not** include Playwright browsers
- You must install Chromium separately: `playwright install chromium`
- For complete distribution, use Docker

---

## 5. GitHub Action Marketplace

Use Chatbot Tester as an action in other repositories.

### Usage in a workflow

```yaml
name: Test Chatbot
on: [push, workflow_dispatch]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Run Chatbot Tests
        uses: corradofrancolini/chatbot-tester@v1
        with:
          project: my-chatbot
          mode: auto
          tests: pending
          langsmith-api-key: ${{ secrets.LANGSMITH_API_KEY }}

      - name: Check results
        run: |
          echo "Passed: ${{ steps.test.outputs.passed }}"
          echo "Failed: ${{ steps.test.outputs.failed }}"
```

### Available Inputs

| Input | Description | Default |
|-------|-------------|---------|
| `project` | Project name | (required) |
| `mode` | Test mode | `auto` |
| `tests` | Which tests | `pending` |
| `new-run` | Create new run | `false` |
| `single-test` | Single test ID | - |
| `headless` | Headless browser | `true` |
| `langsmith-api-key` | API key | - |
| `google-credentials` | JSON credentials | - |

### Available Outputs

| Output | Description |
|--------|-------------|
| `report-path` | Path to HTML report |
| `passed` | Number of passed tests |
| `failed` | Number of failed tests |
| `total` | Total tests executed |

---

## Options Comparison

| Method | Setup | Cost | Maintenance | Local Chromium |
|--------|-------|------|-------------|----------------|
| GitHub Actions | Easy | Free* | Zero | No |
| Docker local | Medium | Zero | Low | Yes (in container) |
| Docker server | Medium | Server | Medium | No |
| PyPI | Easy | Zero | Zero | Yes |
| Binary | Medium | Zero | Zero | Yes |

*2000 minutes/month included

---

## Troubleshooting

### GitHub Actions fails

1. Verify secrets are configured
2. Check logs in **Actions > Run details**
3. Verify the project exists in `projects/`

### Docker doesn't find the project

```bash
# Verify volume mount
docker run -v $(pwd)/projects:/app/projects chatbot-tester ls /app/projects
```

### Health check fails

```bash
# Verify services
python run.py --health-check -p my-chatbot

# Skip health check to force
python run.py -p my-chatbot -m auto --skip-health-check
```
