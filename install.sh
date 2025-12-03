#!/bin/bash
# =============================================================================
# CHATBOT TESTER - Script di Installazione
# =============================================================================
# Installa tutte le dipendenze necessarie per il Chatbot Tester.
# Esegui con: ./install.sh
# =============================================================================

set -e  # Esce in caso di errore

# Colori per output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# Emoji
CHECK="✅"
CROSS="❌"
WARN="⚠️"
INFO="💡"
ROCKET="🚀"
GEAR="⚙️"

# Directory dello script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"

# -----------------------------------------------------------------------------
# Funzioni di utilità
# -----------------------------------------------------------------------------

print_header() {
    echo ""
    echo -e "${CYAN}╔═══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║${NC}           ${BOLD}CHATBOT TESTER - INSTALLAZIONE${NC}                     ${CYAN}║${NC}"
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

check_command() {
    if command -v "$1" &> /dev/null; then
        return 0
    else
        return 1
    fi
}

# -----------------------------------------------------------------------------
# Check Prerequisiti
# -----------------------------------------------------------------------------

check_prerequisites() {
    print_step "Verifica prerequisiti..."
    
    local errors=0
    
    # Check macOS
    if [[ "$OSTYPE" != "darwin"* ]]; then
        print_error "Questo tool supporta solo macOS"
        print_info "Sistema rilevato: $OSTYPE"
        errors=$((errors + 1))
    else
        local macos_version=$(sw_vers -productVersion)
        print_success "macOS $macos_version"
    fi
    
    # Check Python 3.10+
    if check_command python3; then
        local python_version=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        local python_major=$(echo "$python_version" | cut -d. -f1)
        local python_minor=$(echo "$python_version" | cut -d. -f2)
        
        if [[ "$python_major" -ge 3 && "$python_minor" -ge 10 ]]; then
            print_success "Python $python_version"
        else
            print_error "Python 3.10+ richiesto (trovato: $python_version)"
            errors=$((errors + 1))
        fi
    else
        print_error "Python 3 non trovato"
        print_info "Installa con: brew install python@3.11"
        errors=$((errors + 1))
    fi
    
    # Check Homebrew
    if check_command brew; then
        print_success "Homebrew installato"
    else
        print_warning "Homebrew non trovato"
        print_info "Alcune funzionalità potrebbero non essere disponibili"
        print_info "Installa da: https://brew.sh"
    fi
    
    # Check Git (opzionale - serve solo per aggiornamenti)
    if check_command git; then
        print_success "Git installato"
    else
        print_warning "Git non trovato (opzionale)"
        print_info "Git serve solo per aggiornamenti automatici"
    fi
    
    # Check spazio disco (500 MB minimo)
    local free_space=$(df -g "$SCRIPT_DIR" | awk 'NR==2 {print $4}')
    if [[ "$free_space" -ge 1 ]]; then
        print_success "Spazio disco sufficiente (${free_space}GB disponibili)"
    else
        print_warning "Spazio disco limitato (${free_space}GB disponibili)"
    fi
    
    # Check connessione internet
    if ping -c 1 -t 5 pypi.org &> /dev/null; then
        print_success "Connessione internet attiva"
    else
        print_error "Nessuna connessione internet"
        errors=$((errors + 1))
    fi
    
    if [[ $errors -gt 0 ]]; then
        echo ""
        print_error "Installazione interrotta: $errors prerequisiti mancanti"
        exit 1
    fi
    
    print_success "Tutti i prerequisiti soddisfatti!"
}

# -----------------------------------------------------------------------------
# Creazione Virtual Environment
# -----------------------------------------------------------------------------

create_venv() {
    print_step "Creazione virtual environment Python..."
    
    if [[ -d "$VENV_DIR" ]]; then
        print_warning "Virtual environment esistente trovato"
        read -p "Vuoi ricrearlo? (s/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Ss]$ ]]; then
            rm -rf "$VENV_DIR"
        else
            print_info "Uso virtual environment esistente"
            return 0
        fi
    fi
    
    python3 -m venv "$VENV_DIR"
    print_success "Virtual environment creato in: $VENV_DIR"
}

# -----------------------------------------------------------------------------
# Installazione Dipendenze Python
# -----------------------------------------------------------------------------

install_python_deps() {
    print_step "Installazione dipendenze Python..."
    
    # Attiva venv
    source "$VENV_DIR/bin/activate"
    
    # Upgrade pip
    pip install --upgrade pip --quiet
    
    # Installa requirements
    pip install -r "$SCRIPT_DIR/requirements.txt" --quiet
    
    print_success "Dipendenze Python installate"
}

# -----------------------------------------------------------------------------
# Installazione Playwright
# -----------------------------------------------------------------------------

install_playwright() {
    print_step "Installazione Playwright e browser Chromium..."
    
    source "$VENV_DIR/bin/activate"
    
    # Installa browser Chromium
    python -m playwright install chromium
    
    print_success "Playwright e Chromium installati"
}

# -----------------------------------------------------------------------------
# Creazione Struttura Cartelle
# -----------------------------------------------------------------------------

create_directories() {
    print_step "Creazione struttura cartelle..."
    
    # Crea cartelle se non esistono
    mkdir -p "$SCRIPT_DIR/config"
    mkdir -p "$SCRIPT_DIR/projects"
    mkdir -p "$SCRIPT_DIR/reports"
    mkdir -p "$SCRIPT_DIR/src"
    mkdir -p "$SCRIPT_DIR/adapters"
    mkdir -p "$SCRIPT_DIR/wizard/steps"
    mkdir -p "$SCRIPT_DIR/templates"
    mkdir -p "$SCRIPT_DIR/locales"
    mkdir -p "$SCRIPT_DIR/docs/images"
    
    # Copia .env.example se .env non esiste
    if [[ ! -f "$SCRIPT_DIR/config/.env" ]]; then
        if [[ -f "$SCRIPT_DIR/config/.env.example" ]]; then
            cp "$SCRIPT_DIR/config/.env.example" "$SCRIPT_DIR/config/.env"
            print_info "Creato config/.env da template"
        fi
    fi
    
    print_success "Struttura cartelle creata"
}

# -----------------------------------------------------------------------------
# Creazione File __init__.py
# -----------------------------------------------------------------------------

create_init_files() {
    print_step "Creazione file Python __init__.py..."
    
    touch "$SCRIPT_DIR/src/__init__.py"
    touch "$SCRIPT_DIR/adapters/__init__.py"
    touch "$SCRIPT_DIR/wizard/__init__.py"
    touch "$SCRIPT_DIR/wizard/steps/__init__.py"
    
    print_success "File __init__.py creati"
}

# -----------------------------------------------------------------------------
# Check Ollama (opzionale)
# -----------------------------------------------------------------------------

check_ollama() {
    print_step "Verifica Ollama (opzionale)..."
    
    if check_command ollama; then
        print_success "Ollama installato"
        
        # Check se Ollama è in esecuzione
        if curl -s http://localhost:11434/api/tags &> /dev/null; then
            print_success "Ollama in esecuzione"
            
            # Check modello Mistral
            if ollama list 2>/dev/null | grep -q "mistral"; then
                print_success "Modello Mistral disponibile"
            else
                print_warning "Modello Mistral non trovato"
                print_info "Installa con: ollama pull mistral"
            fi
        else
            print_warning "Ollama non in esecuzione"
            print_info "Avvia con: ollama serve"
        fi
    else
        print_info "Ollama non installato (opzionale)"
        print_info "Per modalità Assisted/Auto, installa da: https://ollama.ai"
    fi
}

# -----------------------------------------------------------------------------
# Messaggio Finale
# -----------------------------------------------------------------------------

print_success_message() {
    echo ""
    echo -e "${GREEN}╔═══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║${NC}          ${BOLD}${ROCKET} INSTALLAZIONE COMPLETATA! ${ROCKET}${NC}                      ${GREEN}║${NC}"
    echo -e "${GREEN}╚═══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${BOLD}Prossimi passi:${NC}"
    echo ""
    echo -e "  1. ${CYAN}Configura le credenziali${NC} (opzionale):"
    echo -e "     Modifica ${YELLOW}config/.env${NC} con le tue API keys"
    echo ""
    echo -e "  2. ${CYAN}Crea un nuovo progetto${NC}:"
    echo -e "     ${YELLOW}source venv/bin/activate${NC}"
    echo -e "     ${YELLOW}python run.py --new-project${NC}"
    echo ""
    echo -e "  3. ${CYAN}Oppure avvia il tool${NC}:"
    echo -e "     ${YELLOW}source venv/bin/activate${NC}"
    echo -e "     ${YELLOW}python run.py${NC}"
    echo ""
    echo -e "${BOLD}Documentazione:${NC}"
    echo -e "  • Quick Start: ${YELLOW}docs/README.md${NC}"
    echo -e "  • Setup dettagliato: ${YELLOW}docs/SETUP.md${NC}"
    echo -e "  • Troubleshooting: ${YELLOW}docs/TROUBLESHOOTING.md${NC}"
    echo ""
}

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

main() {
    print_header
    
    check_prerequisites
    create_directories
    create_venv
    install_python_deps
    install_playwright
    create_init_files
    check_ollama
    
    print_success_message
}

# Esegui
main
