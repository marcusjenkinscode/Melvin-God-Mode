#!/usr/bin/env bash
# =============================================================================
# Melvin God Mode – Debian Full Installer
# =============================================================================
# Installs all system dependencies, Python packages, Ollama, and configures
# Melvin God Mode on a Debian-based system.
#
# Usage:
#   sudo ./install.sh              – Full installation
#   sudo ./install.sh --uninstall  – Remove Melvin God Mode
# =============================================================================

set -euo pipefail

# ── colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

# ── helpers ───────────────────────────────────────────────────────────────────
info()    { echo -e "${CYAN}[INFO]${RESET}  $*"; }
success() { echo -e "${GREEN}[OK]${RESET}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
error()   { echo -e "${RED}[ERROR]${RESET} $*" >&2; }
die()     { error "$*"; exit 1; }

banner() {
    echo -e "${BOLD}${BLUE}"
    echo "  ███╗   ███╗███████╗██╗    ██╗   ██╗██╗███╗   ██╗"
    echo "  ████╗ ████║██╔════╝██║    ██║   ██║██║████╗  ██║"
    echo "  ██╔████╔██║█████╗  ██║    ██║   ██║██║██╔██╗ ██║"
    echo "  ██║╚██╔╝██║██╔══╝  ██║    ╚██╗ ██╔╝██║██║╚██╗██║"
    echo "  ██║ ╚═╝ ██║███████╗███████╗╚████╔╝ ██║██║ ╚████║"
    echo "  ╚═╝     ╚═╝╚══════╝╚══════╝ ╚═══╝  ╚═╝╚═╝  ╚═══╝"
    echo -e "${RESET}"
    echo -e "${BOLD}           God Mode – Debian Installer${RESET}"
    echo "  ──────────────────────────────────────────────────"
    echo
}

# ── root check ────────────────────────────────────────────────────────────────
require_root() {
    if [[ $EUID -ne 0 ]]; then
        die "This script must be run as root. Try: sudo ./install.sh"
    fi
}

# ── detect distro ─────────────────────────────────────────────────────────────
detect_distro() {
    if [[ -f /etc/os-release ]]; then
        # shellcheck source=/dev/null
        source /etc/os-release
        DISTRO_ID="${ID:-unknown}"
        DISTRO_NAME="${NAME:-Unknown}"
        DISTRO_VERSION="${VERSION_ID:-unknown}"
    else
        die "Cannot detect OS. /etc/os-release not found."
    fi

    case "$DISTRO_ID" in
        debian|ubuntu|linuxmint|pop|elementary|kali|raspbian)
            success "Detected: ${DISTRO_NAME} ${DISTRO_VERSION}"
            ;;
        *)
            warn "Unsupported distro '${DISTRO_NAME}'. Proceeding anyway, but issues may occur."
            ;;
    esac
}

# ── Python version check ──────────────────────────────────────────────────────
check_python() {
    local min_major=3
    local min_minor=9

    if command -v python3 &>/dev/null; then
        local ver
        ver=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
        local major minor
        IFS='.' read -r major minor <<<"$ver"
        if (( major > min_major || (major == min_major && minor >= min_minor) )); then
            success "Python ${ver} found."
            return 0
        fi
        warn "Python ${ver} is below minimum required ${min_major}.${min_minor}."
    fi

    info "Installing Python ${min_major}.${min_minor}+..."
    apt-get install -y "python${min_major}" "python${min_major}-pip" "python${min_major}-venv"
    success "Python installed."
}

# ── system packages ───────────────────────────────────────────────────────────
install_system_packages() {
    info "Updating package list..."
    apt-get update -qq

    info "Installing system dependencies..."
    apt-get install -y \
        curl \
        wget \
        git \
        build-essential \
        libssl-dev \
        libffi-dev \
        python3-dev \
        python3-pip \
        python3-venv \
        jq \
        ca-certificates \
        gnupg \
        lsb-release

    success "System packages installed."
}

# ── Ollama ─────────────────────────────────────────────────────────────────────
install_ollama() {
    if command -v ollama &>/dev/null; then
        success "Ollama is already installed ($(ollama --version 2>/dev/null || echo 'version unknown'))."
        return 0
    fi

    info "Installing Ollama (local LLM runner)..."
    curl -fsSL https://ollama.com/install.sh | sh
    success "Ollama installed."

    # Enable and start the Ollama service if systemd is available
    if command -v systemctl &>/dev/null; then
        systemctl enable ollama 2>/dev/null || true
        systemctl start  ollama 2>/dev/null || true
        success "Ollama service enabled and started."
    fi
}

# ── Python virtual environment + packages ────────────────────────────────────
install_python_packages() {
    local venv_dir="/opt/melvin/venv"

    info "Creating virtual environment at ${venv_dir}..."
    mkdir -p /opt/melvin
    python3 -m venv "${venv_dir}"

    # shellcheck source=/dev/null
    source "${venv_dir}/bin/activate"

    info "Upgrading pip..."
    pip install --upgrade pip --quiet

    if [[ -f "${PROJECT_ROOT}/requirements.txt" ]]; then
        info "Installing Python packages from requirements.txt..."
        pip install -r "${PROJECT_ROOT}/requirements.txt" --quiet
    else
        info "No requirements.txt found – installing base packages..."
        pip install \
            cryptography \
            requests \
            rich \
            textual \
            --quiet
    fi

    deactivate
    success "Python packages installed in ${venv_dir}."
}

# ── config directories ────────────────────────────────────────────────────────
setup_directories() {
    local real_user="${SUDO_USER:-$USER}"
    local real_home
    real_home=$(getent passwd "${real_user}" | cut -d: -f6)

    local config_dir="${real_home}/.config/melvin"
    local data_dir="${real_home}/.local/share/melvin/chats"

    info "Creating config and data directories..."
    mkdir -p "${config_dir}" "${data_dir}"
    chown -R "${real_user}:${real_user}" "${real_home}/.config/melvin" "${real_home}/.local/share/melvin"

    if [[ ! -f "${config_dir}/config.json" ]]; then
        cat > "${config_dir}/config.json" <<EOF
{
    "model": "llama3",
    "host": "127.0.0.1",
    "port": 11434,
    "chat_history_dir": "${data_dir}",
    "encryption_enabled": true,
    "log_level": "info"
}
EOF
        chown "${real_user}:${real_user}" "${config_dir}/config.json"
        success "Default config written to ${config_dir}/config.json"
    else
        info "Config file already exists – skipping."
    fi
}

# ── systemd service (optional) ────────────────────────────────────────────────
install_service() {
    if ! command -v systemctl &>/dev/null; then
        warn "systemd not detected – skipping service installation."
        return 0
    fi

    local service_file="/etc/systemd/system/melvin.service"
    local venv_dir="/opt/melvin/venv"

    info "Installing systemd service..."
    cat > "${service_file}" <<EOF
[Unit]
Description=Melvin God Mode – Local AI Assistant
After=network.target ollama.service
Wants=ollama.service

[Service]
Type=simple
User=${SUDO_USER:-$USER}
WorkingDirectory=${PROJECT_ROOT}
ExecStart=${venv_dir}/bin/python ${PROJECT_ROOT}/melvin.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    success "Service installed at ${service_file}."
    info "Run 'sudo systemctl enable --now melvin' to auto-start on boot."
}

# ── uninstall ─────────────────────────────────────────────────────────────────
uninstall() {
    warn "Uninstalling Melvin God Mode..."

    if command -v systemctl &>/dev/null; then
        systemctl stop  melvin 2>/dev/null || true
        systemctl disable melvin 2>/dev/null || true
        rm -f /etc/systemd/system/melvin.service
        systemctl daemon-reload
    fi

    rm -rf /opt/melvin

    success "Melvin God Mode has been removed."
    info "Note: Your config (~/.config/melvin) and chat history (~/.local/share/melvin) were NOT deleted."
    info "Remove them manually if you wish: rm -rf ~/.config/melvin ~/.local/share/melvin"
}

# ── main ──────────────────────────────────────────────────────────────────────
main() {
    banner
    require_root

    # Resolve the project root once and export for use by all sub-functions
    PROJECT_ROOT="$(dirname "$(dirname "$(realpath "$0")")")"
    export PROJECT_ROOT

    if [[ "${1:-}" == "--uninstall" ]]; then
        uninstall
        exit 0
    fi

    detect_distro
    install_system_packages
    check_python
    install_ollama
    install_python_packages
    setup_directories
    install_service

    echo
    echo -e "${BOLD}${GREEN}  ✔  Installation complete!${RESET}"
    echo
    echo -e "  Next steps:"
    echo -e "  1. Pull an AI model:  ${CYAN}ollama pull llama3${RESET}"
    echo -e "  2. Start Melvin:      ${CYAN}cd ${PROJECT_ROOT} && ./python-installer/installer.py${RESET}"
    echo
}

main "$@"
