#!/usr/bin/env bash
# =============================================================================
# Melvin God Mode – Debian Interactive Configuration
# =============================================================================
# Guides the user through post-install configuration:
#   • Choosing / pulling an AI model via Ollama
#   • Setting chat history storage path
#   • Enabling/disabling encryption
#   • Configuring host & port for the Ollama API
#
# Usage:
#   ./configure.sh          (run as the target user, NOT as root)
# =============================================================================

set -euo pipefail

# ── colours ───────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
BOLD='\033[1m'
RESET='\033[0m'

info()    { echo -e "${CYAN}[INFO]${RESET}  $*"; }
success() { echo -e "${GREEN}[OK]${RESET}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
ask()     { echo -e "${BOLD}${CYAN}  ➜  $*${RESET}"; }

CONFIG_DIR="${HOME}/.config/melvin"
CONFIG_FILE="${CONFIG_DIR}/config.json"
DATA_DIR="${HOME}/.local/share/melvin/chats"

# ── helpers ───────────────────────────────────────────────────────────────────
prompt_default() {
    # prompt_default "Question text" "default_value"
    local question="$1"
    local default="$2"
    local reply

    ask "${question} [${default}]: "
    read -r reply
    echo "${reply:-$default}"
}

prompt_yesno() {
    # prompt_yesno "Question text" "y|n"
    local question="$1"
    local default="${2:-y}"
    local reply

    ask "${question} (y/n) [${default}]: "
    read -r reply
    reply="${reply:-$default}"
    [[ "${reply,,}" == "y" || "${reply,,}" == "yes" ]]
}

write_config() {
    local model="$1"
    local host="$2"
    local port="$3"
    local chat_dir="$4"
    local encryption="$5"
    local log_level="$6"

    mkdir -p "${CONFIG_DIR}"

    # Use jq if available for safe JSON generation; fall back to printf otherwise.
    if command -v jq &>/dev/null; then
        jq -n \
            --arg     model       "${model}" \
            --arg     host        "${host}" \
            --argjson port        "${port}" \
            --argjson enc         "${encryption}" \
            --arg     chat_dir    "${chat_dir}" \
            --arg     log_level   "${log_level}" \
            '{model: $model, host: $host, port: $port,
              chat_history_dir: $chat_dir,
              encryption_enabled: $enc,
              log_level: $log_level}' \
            > "${CONFIG_FILE}"
    else
        # Fall back: values are tightly controlled by the script, so this is safe.
        printf '{\n    "model": "%s",\n    "host": "%s",\n    "port": %s,\n    "chat_history_dir": "%s",\n    "encryption_enabled": %s,\n    "log_level": "%s"\n}\n' \
            "${model}" "${host}" "${port}" "${chat_dir}" "${encryption}" "${log_level}" \
            > "${CONFIG_FILE}"
    fi

    success "Configuration written to ${CONFIG_FILE}"
}

select_model() {
    echo
    echo -e "  ${BOLD}Available Ollama models (popular choices):${RESET}"
    echo "  ┌─────────────────────────────────────────────────────────────┐"
    echo "  │  1) llama3          – Meta LLaMA 3 8B (recommended)         │"
    echo "  │  2) llama3:70b      – Meta LLaMA 3 70B (needs 40 GB+ RAM)   │"
    echo "  │  3) mistral         – Mistral 7B (fast, lightweight)         │"
    echo "  │  4) gemma2          – Google Gemma 2 9B                      │"
    echo "  │  5) phi3            – Microsoft Phi-3 Mini (very fast)        │"
    echo "  │  6) codellama       – Meta Code LLaMA (coding tasks)         │"
    echo "  │  7) (custom)        – Enter a custom model name              │"
    echo "  └─────────────────────────────────────────────────────────────┘"
    echo

    ask "Select a model [1-7] or press Enter for llama3: "
    read -r choice

    case "${choice:-1}" in
        1) echo "llama3" ;;
        2) echo "llama3:70b" ;;
        3) echo "mistral" ;;
        4) echo "gemma2" ;;
        5) echo "phi3" ;;
        6) echo "codellama" ;;
        7)
            ask "Enter custom model name (e.g. llama3:latest): "
            read -r custom_model
            echo "${custom_model:-llama3}"
            ;;
        *) echo "llama3" ;;
    esac
}

pull_model() {
    local model="$1"

    if ! command -v ollama &>/dev/null; then
        warn "Ollama not found in PATH – skipping model pull."
        warn "Pull the model manually later: ollama pull ${model}"
        return 0
    fi

    if prompt_yesno "Pull model '${model}' now? (requires internet, may take a while)" "y"; then
        info "Pulling ${model}..."
        ollama pull "${model}"
        success "Model '${model}' ready."
    else
        info "Skipping model pull. Run 'ollama pull ${model}' when ready."
    fi
}

# ── main ──────────────────────────────────────────────────────────────────────
main() {
    echo
    echo -e "  ${BOLD}${CYAN}Melvin God Mode – Configuration Wizard${RESET}"
    echo "  ─────────────────────────────────────────"
    echo

    # 1. Model selection
    CHOSEN_MODEL=$(select_model)
    success "Model selected: ${CHOSEN_MODEL}"

    # 2. Ollama host/port
    echo
    OLLAMA_HOST=$(prompt_default "Ollama API host" "127.0.0.1")
    OLLAMA_PORT=$(prompt_default "Ollama API port" "11434")

    # 3. Chat history location
    echo
    CHAT_DIR=$(prompt_default "Chat history directory" "${DATA_DIR}")
    mkdir -p "${CHAT_DIR}"
    success "Chat directory: ${CHAT_DIR}"

    # 4. Encryption
    echo
    if prompt_yesno "Enable AES-256 encryption for stored chat history?" "y"; then
        ENCRYPTION_ENABLED="true"
        success "Encryption enabled."
    else
        ENCRYPTION_ENABLED="false"
        warn "Encryption disabled – chat logs will be stored as plain JSON."
    fi

    # 5. Log level
    echo
    echo -e "  ${BOLD}Log level:${RESET}  debug | info | warning | error"
    LOG_LEVEL=$(prompt_default "Log level" "info")

    # Write config
    echo
    write_config "${CHOSEN_MODEL}" "${OLLAMA_HOST}" "${OLLAMA_PORT}" "${CHAT_DIR}" "${ENCRYPTION_ENABLED}" "${LOG_LEVEL}"

    # Optionally pull model
    pull_model "${CHOSEN_MODEL}"

    echo
    echo -e "  ${BOLD}${GREEN}✔  Configuration complete!${RESET}"
    echo
    echo -e "  Config file:  ${CYAN}${CONFIG_FILE}${RESET}"
    echo -e "  Chat history: ${CYAN}${CHAT_DIR}${RESET}"
    echo
}

main "$@"
