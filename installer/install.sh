#!/usr/bin/env bash
# =============================================================================
#  Melvin God Mode — Production Installer for Rocky Linux 9
#  /home/runner/work/Melvin-God-Mode/Melvin-God-Mode/installer/install.sh
# =============================================================================
set -euo pipefail

# ---------------------------------------------------------------------------
# Colour palette (tput with ANSI fallback)
# ---------------------------------------------------------------------------
if command -v tput &>/dev/null && tput setaf 1 &>/dev/null; then
    RED=$(tput setaf 1)
    GREEN=$(tput setaf 2)
    YELLOW=$(tput setaf 3)
    BLUE=$(tput setaf 4)
    CYAN=$(tput setaf 6)
    BOLD=$(tput bold)
    NC=$(tput sgr0)
else
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    BLUE='\033[0;34m'
    CYAN='\033[0;36m'
    BOLD='\033[1m'
    NC='\033[0m'
fi

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
readonly INSTALL_DIR="/opt/melvin"
readonly VENV_DIR="${INSTALL_DIR}/venv"
readonly LOG_FILE="/var/log/melvin-install.log"
readonly CONFIG_DIR="${INSTALL_DIR}/configs"
readonly SETTINGS_FILE="${CONFIG_DIR}/settings.yaml"
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
readonly CLEAN_FLAG="${1:-}"
readonly SERVICE_USER="melvin"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
exec 3>&1                        # save original stdout
mkdir -p "$(dirname "${LOG_FILE}")"
touch "${LOG_FILE}"

log() {
    local level="${1}"; shift
    local message="$*"
    local timestamp
    timestamp="$(date '+%Y-%m-%d %H:%M:%S')"
    printf '[%s] [%s] %s\n' "${timestamp}" "${level}" "${message}" >> "${LOG_FILE}"
}

info()    { log "INFO"    "$*"; printf '%b[INFO]%b  %s\n'    "${GREEN}"  "${NC}" "$*" >&3; }
warn()    { log "WARN"    "$*"; printf '%b[WARN]%b  %s\n'    "${YELLOW}" "${NC}" "$*" >&3; }
error()   { log "ERROR"   "$*"; printf '%b[ERROR]%b %s\n'    "${RED}"    "${NC}" "$*" >&3; }
section() { log "SECTION" "$*"; printf '\n%b%b==> %s%b\n'   "${BOLD}" "${CYAN}" "$*" "${NC}" >&3; }
success() { log "OK"      "$*"; printf '%b[OK]%b    %s\n'    "${GREEN}"  "${NC}" "$*" >&3; }

die() {
    error "$*"
    error "Installation failed. Check ${LOG_FILE} for details."
    exit 1
}

# ---------------------------------------------------------------------------
# Retry helper  — retry <attempts> <command> [args…]
# ---------------------------------------------------------------------------
retry() {
    local attempts="${1}"; shift
    local delay=5
    local attempt=1
    while true; do
        if "$@"; then
            return 0
        fi
        if (( attempt >= attempts )); then
            error "Command failed after ${attempts} attempts: $*"
            return 1
        fi
        warn "Attempt ${attempt}/${attempts} failed. Retrying in ${delay}s…"
        sleep "${delay}"
        (( attempt++ ))
        (( delay += 5 ))
    done
}

# ---------------------------------------------------------------------------
# OS detection — Rocky Linux 9 only
# ---------------------------------------------------------------------------
detect_os() {
    section "Detecting operating system"

    if [[ ! -f /etc/os-release ]]; then
        die "/etc/os-release not found. Cannot determine OS."
    fi

    # shellcheck source=/dev/null
    source /etc/os-release

    if [[ "${ID:-}" != "rocky" ]]; then
        die "This installer requires Rocky Linux. Detected: ${PRETTY_NAME:-unknown}"
    fi

    local major_version
    major_version="$(echo "${VERSION_ID:-0}" | cut -d. -f1)"
    if [[ "${major_version}" != "9" ]]; then
        die "Rocky Linux 9 is required. Detected version: ${VERSION_ID:-unknown}"
    fi

    success "Rocky Linux ${VERSION_ID} detected."
}

# ---------------------------------------------------------------------------
# Root check
# ---------------------------------------------------------------------------
check_root() {
    if [[ "${EUID}" -ne 0 ]]; then
        die "This installer must be run as root (or via sudo)."
    fi
}

# ---------------------------------------------------------------------------
# Clean / uninstall
# ---------------------------------------------------------------------------
clean_installation() {
    section "Removing existing Melvin God Mode installation"

    systemctl stop melvin-webui melvin-healer 2>/dev/null || true
    systemctl disable melvin-webui melvin-healer 2>/dev/null || true
    rm -f /etc/systemd/system/melvin-webui.service
    rm -f /etc/systemd/system/melvin-healer.service
    systemctl daemon-reload 2>/dev/null || true

    rm -rf "${INSTALL_DIR}"
    rm -f /usr/local/bin/melvin
    rm -rf /var/log/melvin

    if id "${SERVICE_USER}" &>/dev/null; then
        userdel "${SERVICE_USER}" 2>/dev/null || true
        info "Removed service user '${SERVICE_USER}'."
    fi

    success "Clean complete."
}

# ---------------------------------------------------------------------------
# EPEL
# ---------------------------------------------------------------------------
install_epel() {
    section "Installing EPEL release"
    if rpm -q epel-release &>/dev/null; then
        info "EPEL already installed — skipping."
        return 0
    fi
    retry 3 dnf install -y epel-release
    retry 3 dnf config-manager --set-enabled crb 2>/dev/null || true
    success "EPEL installed."
}

# ---------------------------------------------------------------------------
# System packages
# ---------------------------------------------------------------------------
install_system_deps() {
    section "Installing system dependencies"

    local packages=(
        git curl wget
        python3 python3-pip python3-devel
        gcc gcc-c++ make cmake
        openssl-devel libffi-devel zlib-devel
        bzip2-devel readline-devel sqlite-devel
        net-tools nmap
        figlet
        portaudio-devel espeak
        jq htop iotop iftop
    )

    # Packages that may only be available via EPEL or third-party repos
    local optional_packages=(
        masscan nikto gobuster amass ffuf
        dnsenum dnsrecon whatweb toilet
    )

    info "Updating package cache…"
    retry 3 dnf makecache --quiet

    info "Installing core packages…"
    retry 3 dnf install -y "${packages[@]}"

    info "Installing optional/EPEL packages (best-effort)…"
    for pkg in "${optional_packages[@]}"; do
        if dnf install -y "${pkg}" &>>"${LOG_FILE}"; then
            success "  ${pkg}"
        else
            warn "  ${pkg} not available — skipping."
        fi
    done

    # python3-venv is a separate package on RHEL-family
    if ! python3 -m venv --help &>/dev/null; then
        retry 3 dnf install -y python3-virtualenv 2>/dev/null || \
            pip3 install virtualenv
    fi

    success "System dependencies installed."
}

# ---------------------------------------------------------------------------
# Docker CE
# ---------------------------------------------------------------------------
install_docker() {
    section "Installing Docker CE"

    if command -v docker &>/dev/null && docker --version &>/dev/null; then
        info "Docker already installed ($(docker --version)) — skipping."
    else
        info "Adding Docker CE repository…"
        retry 3 dnf config-manager \
            --add-repo https://download.docker.com/linux/centos/docker-ce.repo

        info "Installing Docker CE packages…"
        retry 3 dnf install -y docker-ce docker-ce-cli containerd.io \
            docker-buildx-plugin docker-compose-plugin
    fi

    info "Enabling and starting Docker service…"
    systemctl enable --now docker

    if ! systemctl is-active --quiet docker; then
        die "Docker service failed to start."
    fi

    success "Docker CE is running."
}

# ---------------------------------------------------------------------------
# Ollama
# ---------------------------------------------------------------------------
install_ollama() {
    section "Installing Ollama"

    if command -v ollama &>/dev/null; then
        info "Ollama already installed ($(ollama --version 2>/dev/null || echo 'unknown version')) — skipping."
        return 0
    fi

    info "Downloading and running Ollama installer…"
    local installer_script
    installer_script="$(mktemp /tmp/ollama-install.XXXXXX.sh)"
    trap 'rm -f "${installer_script}"' RETURN

    retry 3 curl -fsSL https://ollama.ai/install.sh -o "${installer_script}"
    chmod +x "${installer_script}"
    bash "${installer_script}" 2>&1 | tee -a "${LOG_FILE}"

    if ! command -v ollama &>/dev/null; then
        die "Ollama installation failed — binary not found after install."
    fi

    # Enable ollama service if the installer registered one
    if systemctl list-unit-files ollama.service &>/dev/null; then
        systemctl enable --now ollama 2>/dev/null || true
    fi

    success "Ollama installed: $(ollama --version 2>/dev/null || echo 'ok')"
}

# ---------------------------------------------------------------------------
# Python virtual environment
# ---------------------------------------------------------------------------
create_virtualenv() {
    section "Creating Python virtual environment"

    mkdir -p "${INSTALL_DIR}"

    if [[ -d "${VENV_DIR}" ]]; then
        info "Virtual environment already exists — recreating."
        rm -rf "${VENV_DIR}"
    fi

    python3 -m venv "${VENV_DIR}" || \
        python3 -m virtualenv "${VENV_DIR}" || \
        die "Failed to create virtual environment."

    # Upgrade pip inside venv
    retry 3 "${VENV_DIR}/bin/pip" install --upgrade pip setuptools wheel

    success "Virtual environment created at ${VENV_DIR}."
}

# ---------------------------------------------------------------------------
# Python packages
# ---------------------------------------------------------------------------
install_python_packages() {
    section "Installing Python packages"

    local pip="${VENV_DIR}/bin/pip"

    # Core web / API
    local web_packages=(
        flask flask-socketio flask-cors
        fastapi "uvicorn[standard]"
        aiohttp requests
    )

    # AI / LLM
    local ai_packages=(
        langchain langchain-community langgraph
        openai anthropic
        "sentence-transformers"
        transformers
        torch
    )

    # Vector databases
    local vector_packages=(
        chromadb qdrant-client weaviate-client
    )

    # Utilities
    local util_packages=(
        psutil gputil
        docker
        pyyaml click rich
        pyttsx3 pyaudio speechrecognition
    )

    info "Installing web/API packages…"
    retry 3 "${pip}" install "${web_packages[@]}"

    info "Installing AI/LLM packages (this may take a while)…"
    retry 3 "${pip}" install "${ai_packages[@]}"

    info "Installing vector-database clients…"
    retry 3 "${pip}" install "${vector_packages[@]}"

    info "Installing utility packages…"
    retry 3 "${pip}" install "${util_packages[@]}"

    success "Python packages installed."
}

# ---------------------------------------------------------------------------
# Copy project files
# ---------------------------------------------------------------------------
copy_project_files() {
    section "Copying project files to ${INSTALL_DIR}"

    mkdir -p "${INSTALL_DIR}"

    local dirs_to_copy=(
        agents ascii autocode cli cluster configs dashboard
        docker docs healing memory models scripts voice webui
    )

    for d in "${dirs_to_copy[@]}"; do
        local src="${PROJECT_ROOT}/${d}"
        if [[ -d "${src}" ]]; then
            cp -r "${src}" "${INSTALL_DIR}/"
            info "  Copied ${d}/"
        else
            warn "  Source directory not found: ${src} — skipping."
        fi
    done

    # Copy top-level files
    for f in README.md LICENSE; do
        [[ -f "${PROJECT_ROOT}/${f}" ]] && cp "${PROJECT_ROOT}/${f}" "${INSTALL_DIR}/" || true
    done

    success "Project files copied."
}

# ---------------------------------------------------------------------------
# Permissions and symlinks
# ---------------------------------------------------------------------------
configure_permissions() {
    section "Configuring permissions and symlinks"

    # Make all Python entry-points executable
    find "${INSTALL_DIR}" -name "*.py" -exec grep -l "^#!/" {} \; \
        | xargs -r chmod +x

    # CLI entry point
    local cli_script="${INSTALL_DIR}/cli/melvin"
    if [[ -f "${cli_script}" ]]; then
        chmod +x "${cli_script}"
        ln -sf "${cli_script}" /usr/local/bin/melvin
        success "Symlink: /usr/local/bin/melvin -> ${cli_script}"
    elif [[ -f "${INSTALL_DIR}/cli/melvin.py" ]]; then
        chmod +x "${INSTALL_DIR}/cli/melvin.py"
        ln -sf "${INSTALL_DIR}/cli/melvin.py" /usr/local/bin/melvin
        success "Symlink: /usr/local/bin/melvin -> ${INSTALL_DIR}/cli/melvin.py"
    else
        warn "CLI entry point not found — /usr/local/bin/melvin not created."
    fi

    # Restrict ownership to the service user
    chown -R "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}"
    chmod -R 755 "${INSTALL_DIR}"
    # Configs may contain secrets — limit to owner-read
    chmod 750 "${CONFIG_DIR}"
    chmod 640 "${SETTINGS_FILE}" 2>/dev/null || true

    success "Permissions configured."
}

# ---------------------------------------------------------------------------
# Service user
# ---------------------------------------------------------------------------
create_service_user() {
    section "Creating service user '${SERVICE_USER}'"

    if id "${SERVICE_USER}" &>/dev/null; then
        info "User '${SERVICE_USER}' already exists — skipping."
    else
        useradd --system --no-create-home \
            --shell /sbin/nologin \
            --comment "Melvin God Mode service account" \
            "${SERVICE_USER}"
        success "User '${SERVICE_USER}' created."
    fi

    # Grant Docker access so the healer can manage containers
    if getent group docker &>/dev/null; then
        usermod -aG docker "${SERVICE_USER}"
        info "Added '${SERVICE_USER}' to the docker group."
    fi
}


create_default_config() {
    section "Creating default configuration"

    mkdir -p "${CONFIG_DIR}"

    if [[ -f "${SETTINGS_FILE}" ]]; then
        info "settings.yaml already exists — not overwriting."
        return 0
    fi

    local secret_key
    secret_key="$(python3 -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null || \
                  openssl rand -hex 32 2>/dev/null || \
                  echo "CHANGE_ME_$(date +%s%N | sha256sum | head -c 32)")"

    # Only write the default if the file was not already copied from the
    # project sources.  If configs/settings.yaml was shipped in the repo it
    # will have been copied by copy_project_files().
    if [[ ! -f "${SETTINGS_FILE}" ]]; then
        cat > "${SETTINGS_FILE}" <<YAML
# Melvin God Mode — default runtime configuration
# Auto-generated by installer on $(date).  Edit as needed.

system:
  name: "Melvin God Mode"
  version: "1.0.0"
  base_dir: "/opt/melvin"
  log_dir: "/var/log/melvin"
  data_dir: "/opt/melvin/data"

ollama:
  host: "127.0.0.1"
  port: 11434
  timeout: 120
  max_retries: 3

webui:
  host: "0.0.0.0"
  port: 5000
  debug: false
  # Generated randomly at install time.  Rotate by re-running the installer
  # or replacing this value manually.
  secret_key: "${secret_key}"

database:
  type: "chromadb"
  path: "/opt/melvin/data/chromadb"
  collection_name: "melvin_memory"

agents:
  max_concurrent: 4
  timeout: 300
  retry_attempts: 3
  log_level: "INFO"

cluster:
  # Replace placeholder addresses with real node IPs/hostnames.
  nodes:
    - name: "node-1"
      host: "192.168.1.10"
      port: 7001
  sync_interval: 30

gpu:
  scheduler_interval: 10
  max_jobs_per_gpu: 2
  memory_threshold: 0.85

voice:
  enabled: false
  language: "en-US"
  sample_rate: 16000
  chunk_size: 1024

healing:
  check_interval: 60
  restart_attempts: 3
  notification_webhook: ""

security:
  # Set api_key_required: true before exposing to any network.
  api_key_required: false
  rate_limit: 100
  allowed_hosts:
    - "localhost"
    - "127.0.0.1"

models:
  default_model: "llama3"
  embedding_model: "nomic-embed-text"
  max_context_length: 8192

logging:
  level: "INFO"
  format: "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
  max_size_mb: 100
  backup_count: 5
YAML
        success "Default settings.yaml written to ${SETTINGS_FILE}."
    fi
}

# ---------------------------------------------------------------------------
# Systemd services
# ---------------------------------------------------------------------------
configure_systemd() {
    section "Configuring systemd services"

    local log_dir="/var/log/melvin"
    mkdir -p "${log_dir}"

    # ---- melvin-webui -------------------------------------------------------
    cat > /etc/systemd/system/melvin-webui.service <<EOF
[Unit]
Description=Melvin God Mode — Web UI
After=network.target docker.service ollama.service
Wants=docker.service

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${INSTALL_DIR}
Environment="PATH=${VENV_DIR}/bin:/usr/local/bin:/usr/bin:/bin"
Environment="PYTHONPATH=${INSTALL_DIR}"
ExecStart=${VENV_DIR}/bin/python ${INSTALL_DIR}/webui/app.py
Restart=on-failure
RestartSec=10
NoNewPrivileges=true
PrivateTmp=true
StandardOutput=append:${log_dir}/webui.log
StandardError=append:${log_dir}/webui-error.log

[Install]
WantedBy=multi-user.target
EOF

    # ---- melvin-healer ------------------------------------------------------
    cat > /etc/systemd/system/melvin-healer.service <<EOF
[Unit]
Description=Melvin God Mode — Container Healer
After=network.target docker.service
Requires=docker.service

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${INSTALL_DIR}
Environment="PATH=${VENV_DIR}/bin:/usr/local/bin:/usr/bin:/bin"
Environment="PYTHONPATH=${INSTALL_DIR}"
ExecStart=${VENV_DIR}/bin/python ${INSTALL_DIR}/healing/container_healer.py
Restart=on-failure
RestartSec=15
NoNewPrivileges=true
PrivateTmp=true
StandardOutput=append:${log_dir}/healer.log
StandardError=append:${log_dir}/healer-error.log

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable melvin-webui melvin-healer

    success "systemd services registered and enabled."
    info "Start with: systemctl start melvin-webui melvin-healer"
}

# ---------------------------------------------------------------------------
# Firewall
# ---------------------------------------------------------------------------
configure_firewall() {
    section "Configuring firewall (best-effort)"

    if ! command -v firewall-cmd &>/dev/null; then
        warn "firewalld not found — skipping firewall configuration."
        return 0
    fi

    if ! systemctl is-active --quiet firewalld; then
        warn "firewalld is not running — skipping."
        return 0
    fi

    local ports=(5000/tcp 11434/tcp 7001/tcp)
    for p in "${ports[@]}"; do
        firewall-cmd --permanent --add-port="${p}" 2>>"${LOG_FILE}" || true
    done
    firewall-cmd --reload 2>>"${LOG_FILE}" || true

    success "Firewall rules applied."
}

# ---------------------------------------------------------------------------
# SELinux
# ---------------------------------------------------------------------------
configure_selinux() {
    section "Adjusting SELinux context"

    if ! command -v getenforce &>/dev/null; then
        warn "SELinux tools not found — skipping."
        return 0
    fi

    local mode
    mode="$(getenforce)"
    info "SELinux mode: ${mode}"

    if [[ "${mode}" == "Enforcing" ]]; then
        # Allow the web UI to bind to a non-standard port
        if command -v semanage &>/dev/null; then
            semanage port -a -t http_port_t -p tcp 5000 2>>"${LOG_FILE}" || \
                semanage port -m -t http_port_t -p tcp 5000 2>>"${LOG_FILE}" || \
                warn "Could not update SELinux port context for 5000/tcp."
        fi

        # Relabel the install directory
        if command -v restorecon &>/dev/null; then
            restorecon -Rv "${INSTALL_DIR}" >>"${LOG_FILE}" 2>&1 || true
        fi
    fi

    success "SELinux configuration done."
}

# ---------------------------------------------------------------------------
# Completion banner
# ---------------------------------------------------------------------------
print_banner() {
    local version="1.0.0"
    printf '\n%b' "${CYAN}"
    cat <<'BANNER'
  __  __   _____  _      __  __  _____  _   _
 |  \/  | | ____|| |    \ \/ / |_   _|| \ | |
 | |\/| | |  _|  | |     \  /    | |  |  \| |
 | |  | | | |___ | |___  /  \    | |  | |\  |
 |_|  |_| |_____||_____|/_/\_\   |_|  |_| \_|

   ___  ___  ____     __  __  ___  ____  _____
  / __|/ _ \|  _ \   |  \/  |/ _ \|  _ \| ____|
 | (_ | (_) | | | |  | |\/| | | | | | | |  _|
  \___|\___/|_| |_|  |_|  |_|\___/|_| |_|_____|

BANNER
    printf '%b' "${NC}"
    printf '%b%bMelvin God Mode v%s — Installation Complete!%b\n\n' \
        "${BOLD}" "${GREEN}" "${version}" "${NC}"
    printf '  %-22s %b%s%b\n' "Install directory:"  "${CYAN}" "${INSTALL_DIR}"          "${NC}"
    printf '  %-22s %b%s%b\n' "Virtual env:"        "${CYAN}" "${VENV_DIR}"              "${NC}"
    printf '  %-22s %b%s%b\n' "Config file:"        "${CYAN}" "${SETTINGS_FILE}"         "${NC}"
    printf '  %-22s %b%s%b\n' "Log file:"           "${CYAN}" "${LOG_FILE}"              "${NC}"
    printf '  %-22s %b%s%b\n' "Web UI service:"     "${CYAN}" "melvin-webui.service"     "${NC}"
    printf '  %-22s %b%s%b\n' "Healer service:"     "${CYAN}" "melvin-healer.service"    "${NC}"
    printf '\n'
    printf '%bNext steps:%b\n' "${YELLOW}" "${NC}"
    printf '  1. Edit  %b%s%b  and set your API keys / secrets.\n' \
        "${CYAN}" "${SETTINGS_FILE}" "${NC}"
    printf '  2. Run   %bsystemctl start melvin-webui melvin-healer%b\n' "${GREEN}" "${NC}"
    printf '  3. Visit %bhttp://$(hostname -I | awk '"'"'{print $1}'"'"'):5000%b\n' "${BLUE}" "${NC}"
    printf '  4. Use   %bmelvin --help%b  for CLI commands.\n\n' "${GREEN}" "${NC}"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    # Redirect all stderr to log as well
    exec 2> >(tee -a "${LOG_FILE}" >&2)

    printf '\n%b%b Melvin God Mode Installer%b\n' "${BOLD}" "${CYAN}" "${NC}"
    info "Installer started at $(date)"
    info "Project root: ${PROJECT_ROOT}"
    info "Install dir:  ${INSTALL_DIR}"
    info "Log file:     ${LOG_FILE}"

    check_root
    detect_os

    if [[ "${CLEAN_FLAG}" == "--clean" ]]; then
        clean_installation
        info "Clean complete. Re-run without --clean to install."
        exit 0
    fi

    # Ensure log dir is writable by the service user
    local log_dir="/var/log/melvin"
    mkdir -p "${log_dir}"
    chown "${SERVICE_USER}:${SERVICE_USER}" "${log_dir}"

    install_epel
    install_system_deps
    install_docker
    install_ollama
    create_virtualenv
    install_python_packages
    copy_project_files
    create_service_user
    configure_permissions
    create_default_config
    configure_systemd
    configure_firewall
    configure_selinux

    print_banner

    info "Installation completed successfully at $(date)"
}

main "$@"
