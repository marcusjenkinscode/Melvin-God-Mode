#!/usr/bin/env bash
# =============================================================================
#  node_join.sh — Join a node to the Melvin God Mode cluster
# =============================================================================
#  Usage:
#    ./node_join.sh [OPTIONS]
#
#  Options:
#    --master-host   <host>          Master node hostname/IP  (required)
#    --master-port   <port>          Master API port          (default: 8000)
#    --node-name     <name>          Friendly name for this node
#    --node-type     <worker|gpu>    Node type                (default: worker)
#    --ssh-tunnel                    Set up reverse SSH tunnel to master
#    --ollama-port   <port>          Local Ollama port        (default: 11434)
#    -h, --help                      Show this help message and exit
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------
_RED='\033[0;31m'
_GREEN='\033[0;32m'
_YELLOW='\033[1;33m'
_BLUE='\033[0;34m'
_CYAN='\033[0;36m'
_BOLD='\033[1m'
_RESET='\033[0m'

info()    { echo -e "${_BLUE}[INFO]${_RESET}  $*"; }
success() { echo -e "${_GREEN}[OK]${_RESET}    $*"; }
warn()    { echo -e "${_YELLOW}[WARN]${_RESET}  $*"; }
error()   { echo -e "${_RED}[ERROR]${_RESET} $*" >&2; }
die()     { error "$*"; exit 1; }
header()  { echo -e "\n${_BOLD}${_CYAN}$*${_RESET}"; }

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_DIR="${HOME}/.melvin/logs"
LOG_FILE="${LOG_DIR}/node_join_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "${LOG_DIR}"

log() {
    local level="$1"; shift
    local msg="$*"
    local ts
    ts="$(date '+%Y-%m-%d %H:%M:%S')"
    echo "[${ts}] [${level}] ${msg}" >> "${LOG_FILE}"
}

log_info()    { log "INFO"    "$*"; info    "$*"; }
log_success() { log "SUCCESS" "$*"; success "$*"; }
log_warn()    { log "WARN"    "$*"; warn    "$*"; }
log_error()   { log "ERROR"   "$*"; error   "$*"; }

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
MASTER_HOST=""
MASTER_PORT="8000"
NODE_NAME="$(hostname -s)"
NODE_TYPE="worker"
OLLAMA_PORT="11434"
SETUP_SSH_TUNNEL=false

# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------
usage() {
    cat <<EOF

${_BOLD}${_CYAN}Melvin God Mode — Node Join Script${_RESET}

${_BOLD}USAGE${_RESET}
  $0 [OPTIONS]

${_BOLD}OPTIONS${_RESET}
  --master-host  <host>         Master node hostname or IP  ${_YELLOW}[required]${_RESET}
  --master-port  <port>         Master API port             (default: ${MASTER_PORT})
  --node-name    <name>         Friendly node name          (default: hostname)
  --node-type    <worker|gpu>   Node type                   (default: ${NODE_TYPE})
  --ssh-tunnel                  Set up reverse SSH tunnel to master
  --ollama-port  <port>         Local Ollama port           (default: ${OLLAMA_PORT})
  -h, --help                    Show this help message and exit

${_BOLD}EXAMPLES${_RESET}
  $0 --master-host 192.168.1.10 --node-type gpu
  $0 --master-host melvin-master --master-port 9000 --node-name gpu-node-1 --node-type gpu --ssh-tunnel

${_BOLD}NOTES${_RESET}
  • Log file: ${LOG_FILE}
  • Ollama is installed automatically if not present.

EOF
}

# ---------------------------------------------------------------------------
# Argument Parsing
# ---------------------------------------------------------------------------
parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --master-host)   MASTER_HOST="${2:?'--master-host requires a value'}"; shift 2 ;;
            --master-port)   MASTER_PORT="${2:?'--master-port requires a value'}"; shift 2 ;;
            --node-name)     NODE_NAME="${2:?'--node-name requires a value'}"; shift 2 ;;
            --node-type)     NODE_TYPE="${2:?'--node-type requires a value'}"; shift 2 ;;
            --ollama-port)   OLLAMA_PORT="${2:?'--ollama-port requires a value'}"; shift 2 ;;
            --ssh-tunnel)    SETUP_SSH_TUNNEL=true; shift ;;
            -h|--help)       usage; exit 0 ;;
            *)               die "Unknown argument: $1  (run with --help for usage)" ;;
        esac
    done

    [[ -z "${MASTER_HOST}" ]] && die "--master-host is required. Run with --help for usage."
    [[ "${NODE_TYPE}" =~ ^(worker|gpu)$ ]] || die "--node-type must be 'worker' or 'gpu'."
}

# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------
command_exists() { command -v "$1" &>/dev/null; }

check_dependencies() {
    header "Checking dependencies…"
    local missing=()
    for cmd in curl jq; do
        if ! command_exists "${cmd}"; then
            missing+=("${cmd}")
        fi
    done
    if [[ ${#missing[@]} -gt 0 ]]; then
        log_warn "Installing missing tools: ${missing[*]}"
        if command_exists apt-get; then
            sudo apt-get update -q && sudo apt-get install -y -q "${missing[@]}"
        elif command_exists yum; then
            sudo yum install -y -q "${missing[@]}"
        elif command_exists brew; then
            brew install "${missing[@]}"
        else
            die "Cannot install ${missing[*]} — please install them manually."
        fi
    fi
    success "All required tools are present."
    log_success "Dependency check passed."
}

# ---------------------------------------------------------------------------
# Ollama Installation
# ---------------------------------------------------------------------------
install_ollama() {
    header "Checking Ollama installation…"
    if command_exists ollama; then
        local ver
        ver="$(ollama --version 2>/dev/null | head -1 || echo 'unknown')"
        log_success "Ollama already installed: ${ver}"
        return 0
    fi

    log_info "Ollama not found — installing…"
    if command_exists curl; then
        curl -fsSL https://ollama.ai/install.sh | sh
    else
        die "curl is required to install Ollama."
    fi

    if command_exists ollama; then
        local ver
        ver="$(ollama --version 2>/dev/null | head -1 || echo 'unknown')"
        log_success "Ollama installed successfully: ${ver}"
    else
        die "Ollama installation failed. Check ${LOG_FILE} for details."
    fi
}

# ---------------------------------------------------------------------------
# Start Ollama Service
# ---------------------------------------------------------------------------
start_ollama() {
    header "Starting Ollama service…"

    # systemd
    if command_exists systemctl && systemctl list-unit-files ollama.service &>/dev/null; then
        if systemctl is-active --quiet ollama; then
            log_success "Ollama service already running (systemd)."
        else
            sudo systemctl enable --now ollama
            log_success "Ollama service started (systemd)."
        fi
        return 0
    fi

    # Fallback: run as background process
    if pgrep -x ollama &>/dev/null; then
        log_success "Ollama process already running."
        return 0
    fi

    OLLAMA_HOST="0.0.0.0:${OLLAMA_PORT}" nohup ollama serve \
        >>"${LOG_DIR}/ollama.log" 2>&1 &
    OLLAMA_PID=$!
    sleep 2

    if kill -0 "${OLLAMA_PID}" 2>/dev/null; then
        log_success "Ollama started (PID ${OLLAMA_PID}, port ${OLLAMA_PORT})."
    else
        die "Failed to start Ollama. Check ${LOG_DIR}/ollama.log."
    fi
}

# ---------------------------------------------------------------------------
# Register with Master
# ---------------------------------------------------------------------------
get_local_ip() {
    # Prefer the IP used to reach the master
    local ip
    ip="$(ip route get "${MASTER_HOST}" 2>/dev/null | awk 'NR==1{for(i=1;i<=NF;i++) if($i=="src") print $(i+1)}')"
    [[ -z "${ip}" ]] && ip="$(hostname -I | awk '{print $1}')"
    echo "${ip}"
}

register_node() {
    header "Registering node with master (${MASTER_HOST}:${MASTER_PORT})…"

    local local_ip
    local_ip="$(get_local_ip)"
    local api_url="http://${MASTER_HOST}:${MASTER_PORT}/api/cluster/join"

    local payload
    payload="$(jq -n \
        --arg name       "${NODE_NAME}"  \
        --arg type       "${NODE_TYPE}"  \
        --arg host       "${local_ip}"   \
        --arg port       "${OLLAMA_PORT}" \
        --arg joined_at  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        '{name: $name, type: $type, host: $host, port: ($port | tonumber), joined_at: $joined_at}'
    )"

    log_info "Sending registration to ${api_url}…"
    log "INFO" "Payload: ${payload}"

    local response http_code
    response="$(curl -s -o /tmp/melvin_join_response.json -w "%{http_code}" \
        -X POST "${api_url}" \
        -H "Content-Type: application/json" \
        -d "${payload}" \
        --connect-timeout 10 \
        --max-time 30)" || {
        log_warn "Master unreachable at ${api_url} — node will operate in standalone mode."
        warn "Could not reach master. The node will function locally until connectivity is restored."
        return 0
    }

    http_code="${response}"
    if [[ "${http_code}" =~ ^2 ]]; then
        local node_id
        node_id="$(jq -r '.node_id // "unknown"' /tmp/melvin_join_response.json 2>/dev/null)"
        log_success "Registered successfully — node_id: ${node_id}"
        echo "${node_id}" > "${HOME}/.melvin/node_id"
        log "INFO" "Node ID saved to ${HOME}/.melvin/node_id"
    else
        log_warn "Master returned HTTP ${http_code}. Response: $(cat /tmp/melvin_join_response.json 2>/dev/null || echo 'empty')"
        warn "Registration returned HTTP ${http_code}. Check master logs."
    fi
}

# ---------------------------------------------------------------------------
# SSH Tunnel (optional)
# ---------------------------------------------------------------------------
setup_ssh_tunnel() {
    header "Setting up reverse SSH tunnel to ${MASTER_HOST}…"

    if ! command_exists ssh; then
        log_warn "ssh not found; skipping tunnel setup."
        return 0
    fi

    local remote_port=$(( OLLAMA_PORT + 10000 ))
    local tunnel_cmd="ssh -f -N -T -o StrictHostKeyChecking=accept-new \
        -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
        -R ${remote_port}:localhost:${OLLAMA_PORT} \
        ${MASTER_HOST}"

    log_info "Tunnel: remote port ${remote_port} → local Ollama :${OLLAMA_PORT}"
    eval "${tunnel_cmd}" && {
        log_success "Reverse SSH tunnel established (remote:${remote_port} → local:${OLLAMA_PORT})."
    } || {
        log_warn "SSH tunnel failed — continuing without tunnel."
    }

    # Persist tunnel via cron (runs every 5 minutes to re-establish if dropped)
    local cron_job="*/5 * * * * ${tunnel_cmd} 2>>${LOG_DIR}/ssh_tunnel.log"
    ( crontab -l 2>/dev/null | grep -qF "melvin-tunnel" ) || \
        ( crontab -l 2>/dev/null; echo "# melvin-tunnel"; echo "${cron_job}" ) | crontab -
    log_info "Cron entry added for tunnel auto-reconnect."
}

# ---------------------------------------------------------------------------
# Write Node Config
# ---------------------------------------------------------------------------
write_node_config() {
    header "Writing node configuration…"
    local config_dir="${HOME}/.melvin"
    mkdir -p "${config_dir}"

    cat > "${config_dir}/node.conf" <<EOF
# Melvin God Mode — Node Configuration
# Generated: $(date -u '+%Y-%m-%d %H:%M:%S UTC')

MELVIN_MASTER_HOST="${MASTER_HOST}"
MELVIN_MASTER_PORT="${MASTER_PORT}"
MELVIN_NODE_NAME="${NODE_NAME}"
MELVIN_NODE_TYPE="${NODE_TYPE}"
MELVIN_OLLAMA_PORT="${OLLAMA_PORT}"
EOF
    log_success "Config written to ${config_dir}/node.conf"
}

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print_summary() {
    echo
    echo -e "${_BOLD}${_GREEN}╔══════════════════════════════════════════════════╗${_RESET}"
    echo -e "${_BOLD}${_GREEN}║       Node successfully joined the cluster!      ║${_RESET}"
    echo -e "${_BOLD}${_GREEN}╚══════════════════════════════════════════════════╝${_RESET}"
    echo
    echo -e "  ${_BOLD}Node name  :${_RESET} ${NODE_NAME}"
    echo -e "  ${_BOLD}Node type  :${_RESET} ${NODE_TYPE}"
    echo -e "  ${_BOLD}Master     :${_RESET} ${MASTER_HOST}:${MASTER_PORT}"
    echo -e "  ${_BOLD}Ollama port:${_RESET} ${OLLAMA_PORT}"
    echo -e "  ${_BOLD}Log file   :${_RESET} ${LOG_FILE}"
    echo
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    echo
    echo -e "${_BOLD}${_CYAN}=================================================${_RESET}"
    echo -e "${_BOLD}${_CYAN}     Melvin God Mode — Node Join Script         ${_RESET}"
    echo -e "${_BOLD}${_CYAN}=================================================${_RESET}"

    parse_args "$@"
    log "INFO" "Starting node_join.sh — master=${MASTER_HOST}:${MASTER_PORT} name=${NODE_NAME} type=${NODE_TYPE}"

    check_dependencies
    install_ollama
    start_ollama
    register_node
    write_node_config

    if [[ "${SETUP_SSH_TUNNEL}" == "true" ]]; then
        setup_ssh_tunnel
    fi

    print_summary
    log "INFO" "node_join.sh completed successfully."
}

main "$@"
