#!/bin/bash
# =============================================================================
# sync-to-public.sh
# Sincronizza chatbot-tester-private → chatbot-tester
# Esclude file sensibili e progetti cliente
# =============================================================================

set -e

PRIVATE_REPO="$HOME/Projects/chatbot-tester-private"
PUBLIC_REPO="$HOME/Projects/chatbot-tester"

# Colori
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Esclusioni - file/directory da NON sincronizzare
EXCLUDES=(
    # Git
    ".git"

    # Virtual environments (ogni repo ha il suo)
    ".venv"
    "venv"

    # Credentials e secrets
    ".env"
    "config/.env"
    "config/oauth_credentials.json"
    "config/service_account.json"
    "config/token.json"
    "auth_state.json"

    # Aider prompt logging
    ".aider*"

    # Progetti cliente (solo example-chatbot va nel pubblico)
    "projects/efg-*"
    "projects/silicon-*"
    "projects/ws-*"

    # Dati runtime
    "reports/"
    "browser-data/"
    ".wizard_state.json"

    # Cache Python
    "__pycache__"
    "*.pyc"
    ".pytest_cache"

    # IDE
    ".idea"
    ".vscode"
)

# Build rsync exclude args
EXCLUDE_ARGS=""
for pattern in "${EXCLUDES[@]}"; do
    EXCLUDE_ARGS="$EXCLUDE_ARGS --exclude=$pattern"
done

echo -e "${YELLOW}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${YELLOW}  Sync: chatbot-tester-private → chatbot-tester${NC}"
echo -e "${YELLOW}═══════════════════════════════════════════════════════════════${NC}"

# Dry run se richiesto
if [[ "$1" == "--dry-run" ]] || [[ "$1" == "-n" ]]; then
    echo -e "\n${YELLOW}[DRY RUN] Mostrando cosa verrebbe sincronizzato...${NC}\n"
    rsync -avn --delete $EXCLUDE_ARGS "$PRIVATE_REPO/" "$PUBLIC_REPO/"
    echo -e "\n${YELLOW}[DRY RUN] Nessuna modifica effettuata${NC}"
    exit 0
fi

# Sync effettivo
echo -e "\n${GREEN}[1/3]${NC} Sincronizzando file..."
rsync -av --delete $EXCLUDE_ARGS "$PRIVATE_REPO/" "$PUBLIC_REPO/"

# Verifica pattern sensibili
echo -e "\n${GREEN}[2/3]${NC} Verificando pattern sensibili..."
cd "$PUBLIC_REPO"

# Ottieni lista file modificati
CHANGED_FILES=$(git diff --name-only 2>/dev/null || echo "")
UNTRACKED_FILES=$(git ls-files --others --exclude-standard 2>/dev/null || echo "")
ALL_FILES="$CHANGED_FILES $UNTRACKED_FILES"

if [[ -n "$ALL_FILES" ]]; then
    # Filtra solo file che esistono
    EXISTING_FILES=""
    for f in $ALL_FILES; do
        [[ -f "$f" ]] && EXISTING_FILES="$EXISTING_FILES $f"
    done

    if [[ -n "$EXISTING_FILES" ]]; then
        if bash scripts/check-sensitive-patterns.sh $EXISTING_FILES 2>/dev/null; then
            echo -e "${GREEN}✓ Nessun pattern sensibile trovato${NC}"
        else
            echo -e "\n${RED}✗ ATTENZIONE: Pattern sensibili rilevati!${NC}"
            echo -e "${RED}  Rivedi le modifiche prima di committare.${NC}"
            exit 1
        fi
    else
        echo -e "${GREEN}✓ Nessun file da controllare${NC}"
    fi
else
    echo -e "${GREEN}✓ Nessuna modifica rilevata${NC}"
fi

# Commit se richiesto
if [[ "$1" == "--commit" ]] || [[ "$2" == "--commit" ]]; then
    echo -e "\n${GREEN}[3/3]${NC} Committando modifiche..."
    cd "$PUBLIC_REPO"

    if [[ -n "$(git status --porcelain)" ]]; then
        git add -A
        git commit -m "chore: sync from private repo

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
        echo -e "${GREEN}✓ Modifiche committate${NC}"
    else
        echo -e "${YELLOW}  Nessuna modifica da committare${NC}"
    fi
else
    echo -e "\n${GREEN}[3/3]${NC} Skipping commit (usa --commit per committare)"
fi

echo -e "\n${GREEN}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  ✓ Sync completato${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"

# Mostra status
echo -e "\n${YELLOW}Status repo pubblico:${NC}"
cd "$PUBLIC_REPO"
git status --short
