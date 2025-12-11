#!/bin/bash
# =============================================================================
# CHATBOT TESTER - Script di Disinstallazione
# =============================================================================
# Rimuove il Chatbot Tester e le sue dipendenze.
# Esegui con: ./uninstall.sh
# =============================================================================

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
TRASH="🗑️"
GEAR="⚙️"

# Directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"

# -----------------------------------------------------------------------------
# Funzioni di utilità
# -----------------------------------------------------------------------------

print_header() {
    echo ""
    echo -e "${RED}╔═══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${RED}║${NC}           ${BOLD}CHATBOT TESTER - DISINSTALLAZIONE${NC}                   ${RED}║${NC}"
    echo -e "${RED}╚═══════════════════════════════════════════════════════════════╝${NC}"
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
# Conferma Utente
# -----------------------------------------------------------------------------

confirm_uninstall() {
    echo -e "${YELLOW}${WARN} ATTENZIONE: Questa operazione rimuoverà:${NC}"
    echo ""
    echo "  • Virtual environment Python (venv/)"
    echo "  • Cache e file temporanei"
    echo "  • Report locali (reports/)"
    echo ""
    
    # Check progetti esistenti
    if [[ -d "$SCRIPT_DIR/projects" ]]; then
        local project_count=$(find "$SCRIPT_DIR/projects" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l | tr -d ' ')
        if [[ "$project_count" -gt 0 ]]; then
            echo -e "${YELLOW}  • $project_count progetto/i configurato/i${NC}"
        fi
    fi
    
    echo ""
    read -p "Sei sicuro di voler procedere? (digita 'DISINSTALLA' per confermare): " confirm
    
    if [[ "$confirm" != "DISINSTALLA" ]]; then
        print_info "Disinstallazione annullata"
        exit 0
    fi
    
    echo ""
}

# -----------------------------------------------------------------------------
# Opzioni di Pulizia
# -----------------------------------------------------------------------------

ask_cleanup_options() {
    print_step "Opzioni di pulizia..."
    
    # Mantieni progetti?
    KEEP_PROJECTS=false
    if [[ -d "$SCRIPT_DIR/projects" ]]; then
        local project_count=$(find "$SCRIPT_DIR/projects" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l | tr -d ' ')
        if [[ "$project_count" -gt 0 ]]; then
            echo ""
            read -p "Vuoi mantenere i progetti configurati? (S/n): " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Nn]$ ]]; then
                KEEP_PROJECTS=true
                print_info "I progetti saranno mantenuti"
            fi
        fi
    fi
    
    # Mantieni credenziali?
    KEEP_CREDENTIALS=false
    if [[ -f "$SCRIPT_DIR/config/.env" ]] || [[ -f "$SCRIPT_DIR/config/oauth_credentials.json" ]]; then
        echo ""
        read -p "Vuoi mantenere le credenziali (config/.env)? (S/n): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Nn]$ ]]; then
            KEEP_CREDENTIALS=true
            print_info "Le credenziali saranno mantenute"
        fi
    fi
}

# -----------------------------------------------------------------------------
# Rimozione Virtual Environment
# -----------------------------------------------------------------------------

remove_venv() {
    print_step "Rimozione virtual environment..."
    
    if [[ -d "$VENV_DIR" ]]; then
        rm -rf "$VENV_DIR"
        print_success "Virtual environment rimosso"
    else
        print_info "Virtual environment non trovato"
    fi
}

# -----------------------------------------------------------------------------
# Rimozione Cache e File Temporanei
# -----------------------------------------------------------------------------

remove_cache() {
    print_step "Rimozione cache e file temporanei..."
    
    # Python cache
    find "$SCRIPT_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find "$SCRIPT_DIR" -type f -name "*.pyc" -delete 2>/dev/null || true
    
    # Log files
    find "$SCRIPT_DIR" -type f -name "*.log" -delete 2>/dev/null || true
    
    # Wizard state files
    find "$SCRIPT_DIR" -type f -name ".wizard_state.json" -delete 2>/dev/null || true
    
    # Requirements hash
    rm -f "$SCRIPT_DIR/.requirements_hash" 2>/dev/null || true
    
    # Backup directories
    rm -rf "$SCRIPT_DIR"/.backup_* 2>/dev/null || true
    
    print_success "Cache e file temporanei rimossi"
}

# -----------------------------------------------------------------------------
# Rimozione Report
# -----------------------------------------------------------------------------

remove_reports() {
    print_step "Rimozione report locali..."
    
    if [[ -d "$SCRIPT_DIR/reports" ]]; then
        rm -rf "$SCRIPT_DIR/reports"
        print_success "Report rimossi"
    else
        print_info "Nessun report trovato"
    fi
}

# -----------------------------------------------------------------------------
# Rimozione Progetti (opzionale)
# -----------------------------------------------------------------------------

remove_projects() {
    if [[ "$KEEP_PROJECTS" == true ]]; then
        print_step "Progetti mantenuti"
        print_info "I progetti sono in: projects/"
        return
    fi
    
    print_step "Rimozione progetti..."
    
    if [[ -d "$SCRIPT_DIR/projects" ]]; then
        # Rimuovi browser-data da ogni progetto
        find "$SCRIPT_DIR/projects" -type d -name "browser-data" -exec rm -rf {} + 2>/dev/null || true
        
        # Rimuovi tutti i progetti
        rm -rf "$SCRIPT_DIR/projects"
        mkdir -p "$SCRIPT_DIR/projects"  # Ricrea vuota
        print_success "Progetti rimossi"
    fi
}

# -----------------------------------------------------------------------------
# Rimozione Credenziali (opzionale)
# -----------------------------------------------------------------------------

remove_credentials() {
    if [[ "$KEEP_CREDENTIALS" == true ]]; then
        print_step "Credenziali mantenute"
        print_info "Le credenziali sono in: config/.env"
        return
    fi
    
    print_step "Rimozione credenziali..."
    
    if [[ -f "$SCRIPT_DIR/config/.env" ]]; then
        rm -f "$SCRIPT_DIR/config/.env"
        print_success "config/.env rimosso"
    fi
    
    if [[ -f "$SCRIPT_DIR/config/oauth_credentials.json" ]]; then
        rm -f "$SCRIPT_DIR/config/oauth_credentials.json"
        print_success "oauth_credentials.json rimosso"
    fi
    
    if [[ -f "$SCRIPT_DIR/config/token.json" ]]; then
        rm -f "$SCRIPT_DIR/config/token.json"
        print_success "token.json rimosso"
    fi
}

# -----------------------------------------------------------------------------
# Messaggio Finale
# -----------------------------------------------------------------------------

print_final_message() {
    echo ""
    echo -e "${GREEN}╔═══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║${NC}          ${BOLD}${TRASH} DISINSTALLAZIONE COMPLETATA ${TRASH}${NC}                      ${GREEN}║${NC}"
    echo -e "${GREEN}╚═══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    
    if [[ "$KEEP_PROJECTS" == true ]] || [[ "$KEEP_CREDENTIALS" == true ]]; then
        echo -e "${BOLD}File mantenuti:${NC}"
        [[ "$KEEP_PROJECTS" == true ]] && echo "  • projects/"
        [[ "$KEEP_CREDENTIALS" == true ]] && echo "  • config/.env, config/oauth_credentials.json"
        echo ""
    fi
    
    echo -e "Per rimuovere completamente la directory:"
    echo -e "  ${YELLOW}cd .. && rm -rf chatbot-tester${NC}"
    echo ""
    echo -e "Per reinstallare:"
    echo -e "  ${YELLOW}./install.sh${NC}"
    echo ""
}

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

main() {
    print_header
    
    confirm_uninstall
    ask_cleanup_options
    
    remove_venv
    remove_cache
    remove_reports
    remove_projects
    remove_credentials
    
    print_final_message
}

# Esegui
main
