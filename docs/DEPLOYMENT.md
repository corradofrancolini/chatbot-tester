# Deployment Guide

This guide explains different execution options for Chatbot Tester, from cloud automation to local execution.

---

## Table of Contents

1. [Deployment Patterns](#execution-patterns)
2. [GitHub Actions (Recommended)](#2-github-actions-recommended)
3. [Docker](#3-docker)
4. [PyPI Package](#4-pypi-package)
5. [Standalone Binary](#5-standalone-binary)
6. [GitHub Action Marketplace](#6-github-action-marketplace)

---

## Deployment Patterns

### Public Framework + Private Projects (Recommended)

This is the industry-standard pattern for automation tools:

**Public Repository** (`chatbot-tester`)
- Contains the framework code
- Generic documentation and examples
- Safe for open source distribution
- No sensitive project data

**Private Fork** (`chatbot-tester-private`)
- Contains your real projects and configurations
- Client-specific test suites
- Authentication credentials as secrets
- Production workflows

```
chatbot-tester (public)           chatbot-tester-private (private)
├── src/                          ├── src/                  ← synced
├── docs/                         ├── docs/                 ← synced
├── projects/                     ├── projects/
│   └── example-chatbot/          │   ├── client-a/         ← your projects
└── .github/workflows/            │   ├── client-b/
    └── chatbot-test.yml          │   └── internal/
                                  └── .github/workflows/
                                      └── chatbot-test.yml  ← with secrets
```

#### Setup Process

1. **Use the public repository** for development and updates
2. **Create a private fork** for your projects:
   ```bash
   gh repo fork --private --clone --fork-name chatbot-tester-private
   ```
3. **Add your projects** to the private fork
4. **Configure secrets** in the private repository
5. **Sync updates** from public to private as needed

#### Benefits
- ✅ Zero data leakage risk
- ✅ Framework stays reusable and open
- ✅ Easy updates from public repo
- ✅ Production-ready CI/CD
- ✅ Follows industry best practices

---

## 2. GitHub Actions (Recommended)

Run tests directly on GitHub servers, without any local software.

### Setup (one-time)

#### For Private Fork

If you're using the private fork pattern, configure these secrets in your **private repository**:

| Secret | Value | Required | How to get |
|--------|-------|----------|------------|
| `BROWSER_AUTH_STATE` | Base64 encoded browser session | **Yes** | See [Authentication Setup](#authentication-setup) |
| `LANGSMITH_API_KEY` | Your LangSmith API key | No | From LangSmith dashboard |
| `GOOGLE_OAUTH_CREDENTIALS` | Google OAuth credentials JSON | No | From Google Cloud Console |
| `GOOGLE_TOKEN_JSON` | Google OAuth token with refresh | No | Generated after first auth |

#### For Public Repository Testing

The public repository only needs these for testing with `example-chatbot`:

| Secret | Value | Required |
|--------|-------|----------|
| `LANGSMITH_API_KEY` | Your LangSmith API key | No |

#### Authentication Setup

To enable automated login for your chatbots:

1. **Generate auth state** (run locally):
   ```bash
   python -c "
   from playwright.sync_api import sync_playwright

   with sync_playwright() as p:
       browser = p.chromium.launch(headless=False)
       context = browser.new_context()
       page = context.new_page()
       page.goto('https://your-chatbot-url.com')

       input('Login manually, then press ENTER...')

       context.storage_state(path='auth_state.json')
       print('Auth state saved!')
       browser.close()
   "
   ```

2. **Convert to base64 and upload**:
   ```bash
   base64 -i auth_state.json | pbcopy
   gh secret set BROWSER_AUTH_STATE
   # Paste the base64 content
   ```

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
   - `project`: project name (e.g., `example-chatbot`)
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
  -f project=example-chatbot \
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

## 3. Docker

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
  -p example-chatbot -m auto --no-interactive

# With environment variables
docker run \
  -e LANGSMITH_API_KEY=your_key \
  -v $(pwd)/projects:/app/projects \
  chatbot-tester \
  -p example-chatbot -m auto --no-interactive
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
  -p example-chatbot -m auto --no-interactive"
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
    command: ["-p", "example-chatbot", "-m", "auto", "--no-interactive"]
```

Run:
```bash
docker-compose run chatbot-tester
```

---

## 4. PyPI Package

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
chatbot-tester -p example-chatbot -m auto --no-interactive

# Health check
chatbot-tester --health-check -p example-chatbot
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

## 5. Standalone Binary

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
./dist/chatbot-tester -p example-chatbot -m auto --no-interactive
```

### Notes

- The binary includes Python but does **not** include Playwright browsers
- You must install Chromium separately: `playwright install chromium`
- For complete distribution, use Docker

---

## 6. GitHub Action Marketplace

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
          project: example-chatbot
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

## Recommended Deployment Strategy

### For Individual Use
1. **Start local** - Clone the public repo and run locally
2. **Add your projects** - Create projects in the `projects/` directory
3. **Use Train mode** - Build your test suite and training data
4. **Move to private fork** - When ready for automation

### For Team Use
1. **Private fork** - Set up `yourcompany-chatbot-testing`
2. **Shared secrets** - Configure team authentication
3. **Scheduled runs** - Use GitHub Actions for continuous testing
4. **Branch protection** - Require tests to pass before merging

### For Enterprise
1. **Self-hosted runners** - For sensitive environments
2. **Docker containers** - Consistent execution environments
3. **Multiple projects** - Separate by team/product/environment
4. **Integration** - Connect to existing CI/CD pipelines

### Security Best Practices
- ✅ **Never commit** authentication credentials
- ✅ **Use secrets** for all sensitive data
- ✅ **Rotate credentials** regularly
- ✅ **Limit secret access** to necessary personnel
- ✅ **Monitor usage** through GitHub Actions logs
- ✅ **Keep fork private** when containing real projects

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
python run.py --health-check -p example-chatbot

# Skip health check to force
python run.py -p example-chatbot -m auto --skip-health-check
```
