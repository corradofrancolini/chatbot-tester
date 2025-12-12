#!/bin/bash
# Pre-commit hook to detect sensitive data patterns
# Prevents accidental commits of project-specific names, URLs, or IDs

# Patterns to detect (add your own sensitive patterns here)
PATTERNS=(
    "silicon-"
    "example-bot"
    "wslabs\.it"
    "1nUQd_"
    "1cW66"
    "d600c6c5"
)

# Build regex pattern
REGEX=$(IFS='|'; echo "${PATTERNS[*]}")

# Check each file passed by pre-commit
FOUND=0
for file in "$@"; do
    if [ -f "$file" ]; then
        if grep -qE "$REGEX" "$file" 2>/dev/null; then
            echo "ERROR: Sensitive pattern found in: $file"
            grep -nE "$REGEX" "$file" 2>/dev/null | head -5
            FOUND=1
        fi
    fi
done

if [ $FOUND -eq 1 ]; then
    echo ""
    echo "Commit blocked: Please remove sensitive data before committing."
    echo "Patterns checked: ${PATTERNS[*]}"
    exit 1
fi

exit 0
