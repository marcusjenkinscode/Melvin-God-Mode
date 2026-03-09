#!/usr/bin/env bash
# pull_models.sh — Pull Ollama models listed in models/models.txt
# Usage: ./pull_models.sh [--category <cat>] [--dry-run] [--timeout <secs>]
set -euo pipefail

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
MODELS_FILE="${REPO_ROOT}/models/models.txt"
LOG_FILE="/var/log/melvin-models.log"
TIMEOUT=300
CATEGORY=""
DRY_RUN=false

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
# Logging
# ---------------------------------------------------------------------------
_log() {
    local level="$1"; shift
    local msg="$*"
    local ts
    ts="$(date '+%Y-%m-%d %H:%M:%S')"
    echo "${ts} [${level}] ${msg}" >> "${LOG_FILE}" 2>/dev/null || true
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
        --category)
            CATEGORY="${2:?'--category requires a value'}"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --timeout)
            TIMEOUT="${2:?'--timeout requires a value (seconds)'}"
            shift 2
            ;;
        --models-file)
            MODELS_FILE="${2:?'--models-file requires a path'}"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [--category <name>] [--dry-run] [--timeout <secs>] [--models-file <path>]"
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
if [[ ! -f "${MODELS_FILE}" ]]; then
    error "Models file not found: ${MODELS_FILE}"
    exit 1
fi

if ! command -v ollama &>/dev/null; then
    error "ollama CLI not found in PATH"
    exit 1
fi

mkdir -p "$(dirname "${LOG_FILE}")" 2>/dev/null || true

# ---------------------------------------------------------------------------
# Parse models file
# ---------------------------------------------------------------------------
declare -a MODELS=()
current_category=""

while IFS= read -r line || [[ -n "${line}" ]]; do
    # Strip trailing whitespace
    line="${line%"${line##*[![:space:]]}"}"

    # Skip empty lines
    [[ -z "${line}" ]] && continue

    # Category header comment: # [category-name]
    if [[ "${line}" =~ ^#[[:space:]]*\[([^]]+)\] ]]; then
        current_category="${BASH_REMATCH[1]}"
        continue
    fi

    # Skip other comment lines
    [[ "${line}" =~ ^# ]] && continue

    # Apply category filter
    if [[ -n "${CATEGORY}" && "${current_category}" != "${CATEGORY}" ]]; then
        continue
    fi

    MODELS+=("${line}")
done < "${MODELS_FILE}"

TOTAL=${#MODELS[@]}

if [[ ${TOTAL} -eq 0 ]]; then
    warn "No models found${CATEGORY:+ in category '${CATEGORY}'}."
    exit 0
fi

# ---------------------------------------------------------------------------
# Pull loop
# ---------------------------------------------------------------------------
echo -e "\n${BOLD}╔══════════════════════════════════════╗${RESET}"
echo -e "${BOLD}║     MELVIN — Ollama Model Puller     ║${RESET}"
echo -e "${BOLD}╚══════════════════════════════════════╝${RESET}\n"

if [[ "${DRY_RUN}" == "true" ]]; then
    info "Dry-run mode — the following ${TOTAL} model(s) would be pulled:"
    for model in "${MODELS[@]}"; do
        echo -e "  ${YELLOW}→${RESET} ${model}"
    done
    exit 0
fi

info "Pulling ${TOTAL} model(s) (timeout=${TIMEOUT}s each)…"
_log INFO "Starting pull of ${TOTAL} model(s)"

declare -a FAILED=()
COUNT=0

for model in "${MODELS[@]}"; do
    COUNT=$(( COUNT + 1 ))
    echo -e "\n${BOLD}[${COUNT}/${TOTAL}]${RESET} Pulling ${CYAN}${model}${RESET}…"
    _log INFO "Pulling model ${COUNT}/${TOTAL}: ${model}"

    if timeout "${TIMEOUT}" ollama pull "${model}"; then
        success "Pulled: ${model}"
        _log OK "Pulled: ${model}"
    else
        error "Failed to pull: ${model}"
        FAILED+=("${model}")
    fi
done

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo -e "\n${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "${BOLD}Summary${RESET}"
echo -e "  Total:   ${TOTAL}"
echo -e "  ${GREEN}Success: $(( TOTAL - ${#FAILED[@]} ))${RESET}"
echo -e "  ${RED}Failed:  ${#FAILED[@]}${RESET}"

if [[ ${#FAILED[@]} -gt 0 ]]; then
    echo -e "\n${RED}Failed models:${RESET}"
    for m in "${FAILED[@]}"; do
        echo -e "  ${RED}✗${RESET} ${m}"
    done
    _log ERROR "Failed models: ${FAILED[*]}"
    exit 1
fi

echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}\n"
success "All models pulled successfully."
_log OK "All ${TOTAL} model(s) pulled."
