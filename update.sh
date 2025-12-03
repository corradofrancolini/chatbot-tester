#!/bin/bash
# =============================================================================
# CHATBOT TESTER - Script di Aggiornamento
# =============================================================================
# Aggiorna il tool all'ultima versione.
# Esegui con: ./update.sh
# =============================================================================

set -e

# Colori
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'
BOLD='\033[1m'

# Emoji
CHECK="✅"
CROSS="❌"
WARN="⚠️"
INFO="💡"
ROCKET="🚀"
GEAR="⚙️"
REFRESH="🔄"

# Directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"

# -----------------------------------------------------------------------------
# Funzioni di utilità
# -----------------------------------------------------------------------------

print_header() {
    echo ""
    echo -e "${CYAN}╔═══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║${NC}           ${BOLD}CHATBOT TESTER - AGGIORNAMENTO${NC}                     ${CYAN}║${NC}"
    echo -e "${CYAN}╚═══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

print_step() {
    echo -e "\n${BLUE}${GEAR} $1${NC}"
}

print_success() {
    echo -e "${GREEN}${CHECK} $1${NC}"
}

print_error() {
    echo -e "${RED}${CROSS} $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}${WARN} $1${NC}"
}

print_info() {
    echo -e "${CYAN}${INFO} $1${NC}"
}

# -----------------------------------------------------------------------------
# Check Pre-update
# -----------------------------------------------------------------------------

check_git_status() {
    print_step "Verifica metodo di installazione..."
    
    cd "$SCRIPT_DIR"
    
    # Check se è un repo git
    if [[ ! -d ".git" ]]; then
        echo ""
        print_warning "Installazione da archivio (non Git)"
        echo ""
        echo -e "  Per aggiornare manualmente:"
        echo -e "  ${CYAN}1.${NC} Scarica la nuova versione"
        echo -e "  ${CYAN}2.${NC} Estrai in una cartella temporanea"
        echo -e "  ${CYAN}3.${NC} Copia i tuoi progetti: ${YELLOW}cp -r projects/ <nuova-cartella>/${NC}"
        echo -e "  ${CYAN}4.${NC} Copia le credenziali: ${YELLOW}cp config/.env <nuova-cartella>/config/${NC}"
        echo -e "  ${CYAN}5.${NC} Esegui ${YELLOW}./install.sh${NC} nella nuova cartella"
        echo ""
        print_info "I tuoi dati sono in: projects/ e config/.env"
        echo ""
        
        # Offri di aggiornare solo le dipendenze Python
        read -p "Vuoi aggiornare le dipendenze Python? (s/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Ss]$ ]]; then
            UPDATE_DEPS_ONLY=true
            return 0
        else
            exit 0
        fi
    fi
    
    # Check modifiche locali
    if [[ -n $(git status --porcelain) ]]; then
        print_warning "Modifiche locali rilevate"
        echo ""
        git status --short
        echo ""
        read -p "Vuoi continuare? Le modifiche potrebbero essere sovrascritte (s/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Ss]$ ]]; then
            print_info "Aggiornamento annullato"
            exit 0
        fi
    fi
    
    print_success "Repository Git OK"
}

# -----------------------------------------------------------------------------
# Backup Configurazioni
# -----------------------------------------------------------------------------

backup_configs() {
    print_step "Backup configurazioni..."
    
    local backup_dir="$SCRIPT_DIR/.backup_$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$backup_dir"
    
    # Backup .env se esiste
    if [[ -f "$SCRIPT_DIR/config/.env" ]]; then
        cp "$SCRIPT_DIR/config/.env" "$backup_dir/"
        print_success "Backup config/.env"
    fi
    
    # Backup oauth credentials se esiste
    if [[ -f "$SCRIPT_DIR/config/oauth_credentials.json" ]]; then
        cp "$SCRIPT_DIR/config/oauth_credentials.json" "$backup_dir/"
        print_success "Backup oauth_credentials.json"
    fi
    
    # Backup settings personalizzati
    if [[ -f "$SCRIPT_DIR/config/settings.yaml" ]]; then
        cp "$SCRIPT_DIR/config/settings.yaml" "$backup_dir/"
        print_success "Backup settings.yaml"
    fi
    
    print_info "Backup salvato in: $backup_dir"
}

# -----------------------------------------------------------------------------
# Git Pull
# -----------------------------------------------------------------------------

git_pull() {
    print_step "Download aggiornamenti..."
    
    cd "$SCRIPT_DIR"
    
    # Salva versione corrente
    local old_version=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
    
    # Pull
    if git pull --rebase; then
        local new_version=$(git rev-parse --short HEAD)
        
        if [[ "$old_version" == "$new_version" ]]; then
            print_success "Già alla versione più recente ($new_version)"
        else
            print_success "Aggiornato: $old_version → $new_version"
            
            # Mostra changelog recente
            echo ""
            echo -e "${BOLD}Modifiche recenti:${NC}"
            git log --oneline "$old_version..$new_version" | head -10
        fi
    else
        print_error "Errore durante git pull"
        print_info "Prova: git stash && git pull && git stash pop"
        exit 1
    fi
}

# -----------------------------------------------------------------------------
# Aggiorna Dipendenze
# -----------------------------------------------------------------------------

update_dependencies() {
    print_step "Aggiornamento dipendenze Python..."
    
    # Check se venv esiste
    if [[ ! -d "$VENV_DIR" ]]; then
        print_warning "Virtual environment non trovato"
        print_info "Esegui ./install.sh per installazione completa"
        exit 1
    fi
    
    # Attiva venv
    source "$VENV_DIR/bin/activate"
    
    # Check se requirements.txt è cambiato
    local req_hash_file="$SCRIPT_DIR/.requirements_hash"
    local current_hash=$(md5 -q "$SCRIPT_DIR/requirements.txt" 2>/dev/null || md5sum "$SCRIPT_DIR/requirements.txt" | cut -d' ' -f1)
    
    if [[ -f "$req_hash_file" ]]; then
        local old_hash=$(cat "$req_hash_file")
        
        if [[ "$current_hash" == "$old_hash" ]]; then
            print_success "Dipendenze già aggiornate"
            return 0
        fi
    fi
    
    # Aggiorna pip
    pip install --upgrade pip --quiet
    
    # Aggiorna dipendenze
    pip install -r "$SCRIPT_DIR/requirements.txt" --upgrade --quiet
    
    # Salva hash
    echo "$current_hash" > "$req_hash_file"
    
    print_success "Dipendenze Python aggiornate"
}

# -----------------------------------------------------------------------------
# Aggiorna Playwright
# -----------------------------------------------------------------------------

update_playwright() {
    print_step "Verifica browser Playwright..."
    
    source "$VENV_DIR/bin/activate"
    
    # Check se Playwright ha bisogno di aggiornamento
    if python -c "from playwright.sync_api import sync_playwright" 2>/dev/null; then
        # Aggiorna browser se necessario
        python -m playwright install chromium --quiet 2>/dev/null || true
        print_success "Browser Playwright OK"
    else
        print_warning "Playwright potrebbe richiedere reinstallazione"
        print_info "Esegui: python -m playwright install chromium"
    fi
}

# -----------------------------------------------------------------------------
# Messaggio Finale
# -----------------------------------------------------------------------------

print_success_message() {
    echo ""
    echo -e "${GREEN}╔═══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║${NC}          ${BOLD}${REFRESH} AGGIORNAMENTO COMPLETATO! ${REFRESH}${NC}                      ${GREEN}║${NC}"
    echo -e "${GREEN}╚═══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "Per avviare il tool:"
    echo -e "  ${YELLOW}source venv/bin/activate${NC}"
    echo -e "  ${YELLOW}python run.py${NC}"
    echo ""
}

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

# Flag per aggiornamento solo dipendenze (no git)
UPDATE_DEPS_ONLY=false

main() {
    print_header
    
    check_git_status
    backup_configs
    
    if [[ "$UPDATE_DEPS_ONLY" == "false" ]]; then
        git_pull
    fi
    
    update_dependencies
    update_playwright
    
    print_success_message
}

# Esegui
main
