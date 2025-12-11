# Creating a New Project

This guide shows you how to configure a new test project for a chatbot.

---

## Table of Contents

1. [Interactive Wizard](#interactive-wizard)
2. [Manual Configuration](#manual-configuration)
3. [Selector Detection](#selector-detection)
4. [Import Test Cases](#import-test-cases)
5. [First Test](#first-test)

---

## Interactive Wizard

The easiest way to create a project is using the wizard:

```bash
./chatbot-tester --new-project
```

### Wizard Steps

#### Step 1: Prerequisites Check
The wizard verifies that everything is installed correctly.

#### Step 2: Project Information
```
Project name: my-chatbot
Description: Customer support chatbot for Example Corp
```

> The name must contain only lowercase letters, numbers, and hyphens.

#### Step 3: Chatbot URL
```
URL: https://chat.example.com/assistant
```

The wizard:
1. Verifies that the URL is reachable
2. Opens the browser for login (if needed)
3. Saves the session for future use

#### Step 4: Selector Detection

**Auto-detect** (recommended):
The wizard automatically searches for common CSS selectors.

**Click-to-learn** (fallback):
If auto-detect fails, the wizard asks you to click:
1. The textarea where you type messages
2. The send button
3. A bot message

#### Step 5: Google Sheets (optional)
```
[1] Local reports only (HTML/CSV)
[2] Configure Google Sheets
[3] Configure later
```

#### Step 6: LangSmith (optional)
```
[1] I don't use LangSmith
[2] Configure LangSmith
[3] Configure later
```

#### Step 7: Ollama (optional)
```
[1] Install Ollama + Mistral
[2] Already installed
[3] Train mode only (skip)
```

#### Step 8: Test Cases
```
[1] Import from file (JSON/CSV/Excel)
[2] Create manually
[3] Start without tests
```

#### Step 9: Summary
Configuration confirmation and save.

---

## Manual Configuration

If you prefer to configure manually:

### 1. Create the project folder

```bash
mkdir -p projects/my-chatbot
```

### 2. Create project.yaml

```bash
cat > projects/my-chatbot/project.yaml << 'EOF'
# Chatbot Tester Project Configuration

project:
  name: "my-chatbot"
  description: "Customer support chatbot"
  created: "2025-12-02"
  language: "en"

chatbot:
  url: "https://chat.example.com/assistant"

  selectors:
    textarea: "#chat-input"
    submit_button: "button.send-btn"
    bot_messages: ".message.assistant"
    thread_container: ".chat-thread"  # optional

  # CSS to inject for clean screenshots
  screenshot_css: |
    .header, .footer { display: none !important; }

  timeouts:
    page_load: 30000
    bot_response: 60000

# Default test data
test_defaults:
  email: "test@example.com"
  countries: ["Italy", "Germany", "France"]

# Google Sheets (optional)
google_sheets:
  enabled: false
  spreadsheet_id: ""
  drive_folder_id: ""

# LangSmith (optional)
langsmith:
  enabled: false
  project_id: ""
  org_id: ""
  tool_names: []

# Ollama (optional)
ollama:
  enabled: true
  model: "mistral"
  url: "http://localhost:11434/api/generate"
EOF
```

### 3. Create tests.json

```bash
cat > projects/my-chatbot/tests.json << 'EOF'
[
  {
    "id": "TC001",
    "question": "How can I reset my password?",
    "category": "account",
    "expected_topics": ["password", "reset", "email"]
  },
  {
    "id": "TC002",
    "question": "What are your opening hours?",
    "category": "info",
    "expected_topics": ["hours", "opening"]
  }
]
EOF
```

### 4. Create training_data.json (empty)

```bash
echo "[]" > projects/my-chatbot/training_data.json
```

---

## Selector Detection

### Common selectors already supported

The tool automatically searches for these patterns:

**Textarea (message input)**:
```css
#llm-prompt-textarea
[data-testid='chat-input']
textarea[placeholder*='message' i]
textarea[placeholder*='type' i]
.chat-input textarea
```

**Send button**:
```css
button.llm__prompt-submit
button[type='submit']
button[aria-label*='send' i]
.send-button
```

**Bot messages**:
```css
.llm__message--assistant .llm__text-body
[data-role='assistant']
.message.assistant
.bot-message
.ai-response
```

### Finding selectors manually

If automatic selectors don't work:

1. Open the chatbot in browser
2. Press `F12` to open DevTools
3. Click the selector icon (arrow) in the top left
4. Click on the desired element
5. In the Elements panel, right-click → Copy → Copy selector

### Click-to-learn

If you use click-to-learn mode:

1. The tool opens the browser
2. The element to click is highlighted in yellow
3. Click on the requested element
4. The tool automatically extracts the selector
5. Confirm or edit manually

---

## Import Test Cases

### From JSON

Native format, supports all features:

```json
[
  {
    "id": "TC001",
    "question": "Main question",
    "category": "category",
    "expected_topics": ["topic1", "topic2"],
    "followups": [
      {
        "condition": "contains:word",
        "question": "Follow-up question"
      }
    ]
  }
]
```

### From CSV

```csv
id,question,category,expected_topics
TC001,"How do I reset my password?",account,"password,reset,email"
TC002,"Opening hours?",info,"hours,opening"
```

### From Excel

Same format as CSV, first row as headers.

### Follow-up conditions

| Condition | Example | Description |
|-----------|---------|-------------|
| `contains:X` | `contains:email` | Response contains "email" |
| `not_contains:X` | `not_contains:error` | Response does NOT contain "error" |
| `length_gt:N` | `length_gt:100` | Response longer than N characters |
| `length_lt:N` | `length_lt:50` | Response shorter than N characters |
| `always` | `always` | Always execute |

---

## First Test

### 1. Start in Train mode

```bash
./chatbot-tester --project=my-chatbot --mode=train
```

### 2. Run a single test

```bash
./chatbot-tester --project=my-chatbot --mode=train --test=TC001
```

### 3. What happens in Train mode

1. The browser opens to the chatbot page
2. The question is sent automatically
3. Wait for the bot's response
4. You are asked to evaluate the response:
   - **Pass**: Correct response
   - **Fail**: Incorrect response
   - **Warning**: Partially correct
5. You can add notes
6. The result is saved

### 4. Check the reports

```bash
# Local report
open reports/my-chatbot/run_001/report.html

# Or view the CSV
cat reports/my-chatbot/run_001/report.csv
```

---

## Recommended Workflow

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  1. TRAIN MODE (10-20 tests)                               │
│     - Run tests manually                                    │
│     - Evaluate responses                                    │
│     - The tool learns from your feedback                    │
│                                                             │
│                          ↓                                  │
│                                                             │
│  2. ASSISTED MODE (validation)                             │
│     - AI suggests evaluations                               │
│     - You confirm or correct                                │
│     - Refine the learning                                   │
│                                                             │
│                          ↓                                  │
│                                                             │
│  3. AUTO MODE (regression)                                 │
│     - Fully automatic execution                             │
│     - Ideal for CI/CD                                       │
│     - Automatic reports                                     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## New Project Checklist

- [ ] Project created in `projects/<name>/`
- [ ] `project.yaml` configured with URL and selectors
- [ ] `tests.json` with at least some test cases
- [ ] Login completed (session saved)
- [ ] First test executed successfully
- [ ] Report generated correctly

---

## Next Steps

1. Add more test cases
2. Configure follow-ups for complex scenarios
3. Move to Assisted mode
4. Integrate with CI/CD using Auto mode

---

## Problems?

See the [Troubleshooting Guide](TROUBLESHOOTING.md).
