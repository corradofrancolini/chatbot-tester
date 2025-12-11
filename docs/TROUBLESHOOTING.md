# Troubleshooting

Guide to solving common problems.

---

## Table of Contents

1. [Installation Problems](#installation-problems)
2. [Browser Problems](#browser-problems)
3. [Connection Problems](#connection-problems)
4. [Selector Problems](#selector-problems)
5. [Ollama Problems](#ollama-problems)
6. [Google Sheets Problems](#google-sheets-problems)
7. [LangSmith Problems](#langsmith-problems)
8. [Common Errors](#common-errors)
9. [Complete Reset](#complete-reset)

---

## Installation Problems

### "Command not found: ./install.sh"

**Cause**: The file doesn't have execution permissions.

**Solution**:
```bash
chmod +x install.sh update.sh uninstall.sh
./install.sh
```

### "Python 3.10+ not found"

**Solution**:
```bash
# Install Python 3.12 via Homebrew
brew install python@3.12

# Verify
python3.12 --version
```

### "Homebrew not found"

**Solution**:
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# For Apple Silicon, add to PATH
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
eval "$(/opt/homebrew/bin/brew shellenv)"
```

### "pip install fails"

**Possible causes and solutions**:

```bash
# 1. Upgrade pip
source .venv/bin/activate
pip install --upgrade pip

# 2. Install system dependencies
xcode-select --install

# 3. Try installing one at a time
pip install playwright
pip install rich
# ... etc
```

### "Insufficient disk space"

**Solution**:
```bash
# Check available space
df -h .

# Free up space
# - Empty trash
# - Remove old backups
# - Use Disk Utility to optimize
```

---

## Browser Problems

### "Browser doesn't open"

**Solutions**:

```bash
# 1. Reinstall Chromium
source .venv/bin/activate
playwright install chromium --force

# 2. Verify installation
playwright install --help

# 3. If on Apple Silicon
playwright install chromium --with-deps
```

### "Browser opens but page is blank"

**Cause**: Connection problem or incorrect URL.

**Solutions**:
1. Verify the URL is correct in `project.yaml`
2. Try the URL manually in a browser
3. Check internet connection

### "Screenshots aren't being saved"

**Solutions**:

```bash
# 1. Check folder permissions
ls -la reports/

# 2. Create manually if it doesn't exist
mkdir -p reports/<project>/screenshots

# 3. Check disk space
df -h .
```

### "Browser closes unexpectedly"

**Possible causes**:
- Timeout too short
- JavaScript error on the page
- Memory problem

**Solutions**:

```yaml
# In project.yaml, increase timeout
chatbot:
  timeouts:
    page_load: 60000
    bot_response: 120000
```

---

## Connection Problems

### "URL not reachable"

**Verify**:
```bash
# Test connection
curl -I https://chat.example.com

# Check DNS
nslookup chat.example.com

# Check if you're behind proxy/VPN
```

### "SSL/TLS error"

**Solutions**:
```bash
# 1. Check system date/time
date

# 2. If self-signed certificate, may need to
# modify configuration (not recommended for production)
```

### "Timeout during bot response"

**Solutions**:

```yaml
# In project.yaml
chatbot:
  timeouts:
    bot_response: 120000  # Increase to 2 minutes
```

```bash
# Check latency
ping chat.example.com
```

---

## Selector Problems

### "Selector not found"

**Diagnosis**:
1. Open the chatbot in Chrome
2. Press F12 → Console
3. Run:
```javascript
document.querySelector('#your-selector')
```

**If it returns `null`**, the selector is wrong.

**Solutions**:
1. Use Click-to-learn:
```bash
./chatbot-tester --new-project
# At step 4, choose "Click-to-learn"
```

2. Find manually with DevTools:
   - F12 → Elements
   - Click the selector icon (arrow)
   - Click on the element
   - Right-click → Copy → Copy selector

### "Selector finds multiple elements"

The selector must be unique.

**Solutions**:
```css
/* Too generic */
.message

/* More specific */
.message.assistant:last-child

/* With parent ID */
#chat-container .message.assistant
```

### "Bot responds but isn't detected"

**Possible causes**:
- Wrong message selector
- Response loaded dynamically
- Hidden iframe

**Solutions**:
```yaml
# In project.yaml, try different selectors
chatbot:
  selectors:
    bot_messages: ".ai-response, .bot-message, [data-role='assistant']"
```

---

## Ollama Problems

### "Ollama not responding"

**Verify**:
```bash
# Is Ollama running?
curl http://localhost:11434/api/tags

# If error, start Ollama
ollama serve
```

### "Mistral model not found"

```bash
# Download the model
ollama pull mistral

# Check available models
ollama list
```

### "Ollama responses slow"

**Solutions**:
1. Check available RAM (Activity Monitor)
2. Close other applications
3. Use a lighter model:
```yaml
ollama:
  model: "llama2"  # Faster than mistral
```

### "'Out of memory' error"

```bash
# Check memory usage
ollama ps

# Restart Ollama
pkill ollama
ollama serve
```

---

## Google Sheets Problems

### "OAuth / Authentication error"

**Solutions**:

```bash
# 1. Remove saved tokens
rm -f config/token.json

# 2. Verify credentials
cat config/oauth_credentials.json | python -m json.tool

# 3. Re-run authorization
./chatbot-tester --project=<name>
# Follow the OAuth flow in browser
```

### "Spreadsheet not found"

**Verify**:
1. Is the ID correct? (from Sheets URL)
2. Did you share the sheet with the OAuth account?
3. Is Sheets API enabled?

```bash
# Test access
curl -s "https://sheets.googleapis.com/v4/spreadsheets/YOUR_ID" \
  -H "Authorization: Bearer $(cat config/token.json | jq -r .access_token)"
```

### "API quota exceeded"

Google Sheets has limits:
- 100 requests / 100 seconds / user
- 500 requests / 100 seconds / project

**Solutions**:
1. Reduce test frequency
2. Use batch updates
3. Enable more quota in Google Cloud Console

### "Screenshots not uploaded to Drive"

**Verify**:
1. Is Drive API enabled?
2. Is Drive folder shared?
3. Is Drive Folder ID correct?

---

## LangSmith Problems

### "Invalid API Key"

**Verify**:
```bash
# Test key
curl -s "https://api.smith.langchain.com/projects" \
  -H "x-api-key: YOUR_KEY"
```

**If 401 error**:
1. Regenerate the key in LangSmith
2. Update `config/.env`

### "Traces not found"

**Possible causes**:
1. Wrong Project ID
2. Wrong Org ID
3. No recent traces

**Verify**:
1. Go to smith.langchain.com
2. Verify there are traces in the project
3. Compare Project ID and Org ID

### "Tool names not detected"

**Solutions**:
1. Run a manual test on the chatbot
2. Wait for the trace to appear in LangSmith
3. Re-run the wizard for auto-detect

---

## Common Errors

### "ModuleNotFoundError"

```bash
# Make sure you're using the venv
source .venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt
```

### "FileNotFoundError: project.yaml"

```bash
# Verify the project exists
ls projects/

# If missing, recreate
./chatbot-tester --new-project
```

### "JSONDecodeError in tests.json"

```bash
# Validate JSON
cat projects/<name>/tests.json | python -m json.tool

# Common errors:
# - Trailing comma: [{"a": 1},]  ← WRONG
# - Single quotes: {'a': 1}      ← WRONG
# - Comments: /* comment */      ← WRONG
```

### "PermissionError"

```bash
# Fix permissions
chmod -R u+rw projects/ reports/ config/
```

### "TimeoutError"

**Solutions**:
1. Increase timeout in `project.yaml`
2. Check connection
3. The chatbot might be slow

---

## Complete Reset

If nothing works, complete reset:

### Reset single project

```bash
# Remove browser data and training
rm -rf projects/<name>/browser-data/
rm -f projects/<name>/training_data.json
echo "[]" > projects/<name>/training_data.json

# Remove reports
rm -rf reports/<name>/
```

### Reset installation

```bash
# Uninstall
./uninstall.sh

# Remove residuals
rm -rf .venv/
rm -rf projects/*/browser-data/

# Reinstall
./install.sh
```

### Complete reset (WARNING: you'll lose everything!)

```bash
# Backup first!
cp -r projects/ ~/backup-chatbot-tester-projects/
cp config/.env ~/backup-env

# Reset
./uninstall.sh --remove-all

# Reinstall
./install.sh
```

---

## Logs and Debug

### Enable verbose logs

```bash
./chatbot-tester --project=<name> --verbose
```

### Playwright logs

```bash
DEBUG=pw:api ./chatbot-tester --project=<name>
```

### Python logs

```python
# In run.py, temporarily add:
import logging
logging.basicConfig(level=logging.DEBUG)
```

---

## Support

If the problem persists:

1. **Gather information**:
```bash
# Versions
python --version
./chatbot-tester --version
ollama --version 2>/dev/null

# System
sw_vers
uname -m
```

2. **Create a GitHub issue** with:
   - Problem description
   - Steps to reproduce
   - Error logs
   - Software versions

---

## FAQ

**Q: Can I use Firefox instead of Chromium?**
A: No, currently only Chromium is supported for consistency.

**Q: Does it work on Windows/Linux?**
A: No, only macOS is officially supported.

**Q: Can I test multiple chatbots simultaneously?**
A: Yes, create separate projects and run them in different terminals.

**Q: Is browser data shared between projects?**
A: No, each project has its own isolated browser session.

**Q: How do I backup data?**
A: Copy the `projects/` folder and `config/.env`.
