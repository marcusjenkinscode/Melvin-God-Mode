#!/usr/bin/env bash
# update_models.sh — Update all currently installed Ollama models
# Usage: ./update_models.sh [--force]
set -euo pipefail

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
LOG_FILE="/var/log/melvin-models.log"
FORCE=false

# ---------------------------------------------------------------------------
# Colours
# ---------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------
_log() {
    local level="$1"; shift
    local ts
    ts="$(date '+%Y-%m-%d %H:%M:%S')"
    echo "${ts} [${level}] $*" >> "${LOG_FILE}" 2>/dev/null || true
}

info()    { echo -e "${CYAN}[INFO]${RESET}  $*"; _log INFO "$*"; }
success() { echo -e "${GREEN}[OK]${RESET}    $*"; _log OK "$*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; _log WARN "$*"; }
error()   { echo -e "${RED}[ERROR]${RESET} $*" >&2; _log ERROR "$*"; }

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --force)
            FORCE=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [--force]"
            echo "  --force   Re-pull every installed model regardless of current state"
            exit 0
            ;;
        *)
            error "Unknown argument: $1"
            exit 1
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Preflight checks
# ---------------------------------------------------------------------------
if ! command -v ollama &>/dev/null; then
    error "ollama CLI not found in PATH"
    exit 1
fi

mkdir -p "$(dirname "${LOG_FILE}")" 2>/dev/null || true

# ---------------------------------------------------------------------------
# Discover installed models
# ---------------------------------------------------------------------------
# `ollama list` output: NAME  ID  SIZE  MODIFIED
# Skip the header line and grab the first column.
mapfile -t INSTALLED < <(ollama list 2>/dev/null | tail -n +2 | awk '{print $1}' | grep -v '^$' || true)

TOTAL=${#INSTALLED[@]}

if [[ ${TOTAL} -eq 0 ]]; then
    warn "No models are currently installed."
    exit 0
fi

# ---------------------------------------------------------------------------
# Update loop
# ---------------------------------------------------------------------------
echo -e "\n${BOLD}╔══════════════════════════════════════╗${RESET}"
echo -e "${BOLD}║     MELVIN — Ollama Model Updater    ║${RESET}"
echo -e "${BOLD}╚══════════════════════════════════════╝${RESET}\n"

info "Found ${TOTAL} installed model(s). Starting update${FORCE:+' (force)'}…"
_log INFO "Updating ${TOTAL} installed model(s) (force=${FORCE})"

declare -a UPDATED=()
declare -a CURRENT=()
declare -a FAILED=()
COUNT=0

for model in "${INSTALLED[@]}"; do
    COUNT=$(( COUNT + 1 ))
    echo -e "\n${BOLD}[${COUNT}/${TOTAL}]${RESET} Updating ${CYAN}${model}${RESET}…"

    # Capture output to detect "up to date" messages
    tmpfile="$(mktemp)"
    if ollama pull "${model}" 2>&1 | tee "${tmpfile}"; then
        pull_output="$(cat "${tmpfile}")"
        rm -f "${tmpfile}"

        if echo "${pull_output}" | grep -qi "already up.to.date\|up to date\|nothing to pull"; then
            if [[ "${FORCE}" == "false" ]]; then
                info "${model} is already up to date — skipping"
                CURRENT+=("${model}")
                _log OK "Already current: ${model}"
                continue
            fi
        fi

        success "Updated: ${model}"
        UPDATED+=("${model}")
        _log OK "Updated: ${model}"
    else
        rm -f "${tmpfile}"
        error "Failed to update: ${model}"
        FAILED+=("${model}")
        _log ERROR "Failed: ${model}"
    fi
done

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo -e "\n${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "${BOLD}Update Summary${RESET}"
echo -e "  Checked:       ${TOTAL}"
echo -e "  ${GREEN}Updated:       ${#UPDATED[@]}${RESET}"
echo -e "  ${CYAN}Already current: ${#CURRENT[@]}${RESET}"
echo -e "  ${RED}Failed:        ${#FAILED[@]}${RESET}"

if [[ ${#UPDATED[@]} -gt 0 ]]; then
    echo -e "\n${GREEN}Updated models:${RESET}"
    for m in "${UPDATED[@]}"; do echo -e "  ${GREEN}↑${RESET} ${m}"; done
fi

if [[ ${#CURRENT[@]} -gt 0 ]]; then
    echo -e "\n${CYAN}Already up to date:${RESET}"
    for m in "${CURRENT[@]}"; do echo -e "  ${CYAN}✓${RESET} ${m}"; done
fi

if [[ ${#FAILED[@]} -gt 0 ]]; then
    echo -e "\n${RED}Failed models:${RESET}"
    for m in "${FAILED[@]}"; do echo -e "  ${RED}✗${RESET} ${m}"; done
    _log ERROR "Failed models: ${FAILED[*]}"
fi

echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}\n"

if [[ ${#FAILED[@]} -eq 0 ]]; then
    success "Model update complete."
    _log OK "Update complete. Updated=${#UPDATED[@]} Current=${#CURRENT[@]}"
else
    error "Update finished with ${#FAILED[@]} failure(s)."
    _log ERROR "Update finished with failures."
    exit 1
fi
