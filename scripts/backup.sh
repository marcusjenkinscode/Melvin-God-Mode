#!/usr/bin/env bash
# backup.sh — Backup and restore Melvin God Mode data
# Usage: ./backup.sh [--restore <backup_file>] [--keep <n>]
set -euo pipefail

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
BACKUP_DIR="/opt/melvin/backups"
LOG_FILE="/var/log/melvin-backup.log"
KEEP=7
RESTORE_FILE=""

# Sources to back up (space-separated; adjusted paths for non-root installs)
BACKUP_SOURCES=(
    "/opt/melvin/configs"
    "/opt/melvin/data/chroma"
    "/opt/melvin/data/knowledge"
    "/opt/melvin/logs"
)

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
die()     { error "$*"; exit 1; }

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --restore)
            RESTORE_FILE="${2:?'--restore requires a backup file path'}"
            shift 2
            ;;
        --keep)
            KEEP="${2:?'--keep requires a number'}"
            shift 2
            ;;
        --backup-dir)
            BACKUP_DIR="${2:?'--backup-dir requires a path'}"
            shift 2
            ;;
        -h|--help)
            cat <<EOF
Usage: $0 [OPTIONS]

Options:
  --restore <file>   Restore from the specified backup archive
  --keep <n>         Number of backups to retain (default: ${KEEP})
  --backup-dir <dir> Backup destination directory (default: ${BACKUP_DIR})
  -h, --help         Show this help message
EOF
            exit 0
            ;;
        *)
            die "Unknown argument: $1"
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
ensure_dir() {
    local dir="$1"
    mkdir -p "${dir}" || die "Cannot create directory: ${dir}"
}

# ---------------------------------------------------------------------------
# Restore mode
# ---------------------------------------------------------------------------
do_restore() {
    local archive="${RESTORE_FILE}"

    [[ -f "${archive}" ]] || die "Backup file not found: ${archive}"

    echo -e "\n${BOLD}╔══════════════════════════════════════╗${RESET}"
    echo -e "${BOLD}║     MELVIN — Restore from Backup     ║${RESET}"
    echo -e "${BOLD}╚══════════════════════════════════════╝${RESET}\n"

    info "Restoring from: ${archive}"
    _log INFO "Restore started from ${archive}"

    # Safety snapshot before overwriting
    local safety_ts
    safety_ts="$(date '+%Y%m%d_%H%M%S')"
    local safety_archive="${BACKUP_DIR}/pre_restore_${safety_ts}.tar.gz"
    info "Creating safety backup before restore → ${safety_archive}"
    do_backup_internal "${safety_archive}"

    # Extract to filesystem root (archive paths are absolute)
    info "Extracting archive…"
    tar -xzf "${archive}" -C / || die "Extraction failed"

    success "Restore complete."
    _log OK "Restore complete from ${archive}"
}

# ---------------------------------------------------------------------------
# Backup helpers
# ---------------------------------------------------------------------------
do_backup_internal() {
    local out_file="$1"
    local -a existing_sources=()

    for src in "${BACKUP_SOURCES[@]}"; do
        if [[ -e "${src}" ]]; then
            existing_sources+=("${src}")
        else
            warn "Source not found (skipped): ${src}"
        fi
    done

    if [[ ${#existing_sources[@]} -eq 0 ]]; then
        warn "No backup sources exist — nothing to archive."
        return 0
    fi

    # Strip leading slash so tar stores absolute paths cleanly
    tar -czf "${out_file}" \
        --ignore-failed-read \
        --warning=no-file-changed \
        "${existing_sources[@]}" 2>/dev/null || {
            # tar exits 1 when files changed during backup; treat as warning
            warn "tar exited with non-zero status (files may have changed during backup)"
        }
}

rotate_backups() {
    local dir="${BACKUP_DIR}"
    local keep="${KEEP}"

    # List backups oldest-first; delete beyond the keep limit
    mapfile -t old_backups < <(
        find "${dir}" -maxdepth 1 -name 'melvin_backup_*.tar.gz' \
            -printf '%T@ %p\n' 2>/dev/null \
            | sort -n | head -n -"${keep}" | awk '{print $2}'
    )

    for f in "${old_backups[@]}"; do
        info "Removing old backup: $(basename "${f}")"
        rm -f "${f}"
        _log INFO "Removed old backup: ${f}"
    done
}

# ---------------------------------------------------------------------------
# Main backup mode
# ---------------------------------------------------------------------------
do_backup() {
    local ts
    ts="$(date '+%Y%m%d_%H%M%S')"
    local archive="${BACKUP_DIR}/melvin_backup_${ts}.tar.gz"

    ensure_dir "${BACKUP_DIR}"
    ensure_dir "$(dirname "${LOG_FILE}")" 2>/dev/null || true

    echo -e "\n${BOLD}╔══════════════════════════════════════╗${RESET}"
    echo -e "${BOLD}║       MELVIN — Backup Engine         ║${RESET}"
    echo -e "${BOLD}╚══════════════════════════════════════╝${RESET}\n"

    info "Backup started → ${archive}"
    _log INFO "Backup started: ${archive}"

    info "Sources:"
    for src in "${BACKUP_SOURCES[@]}"; do
        local indicator="${RED}✗ (missing)${RESET}"
        [[ -e "${src}" ]] && indicator="${GREEN}✓${RESET}"
        echo -e "  ${indicator} ${src}"
    done

    do_backup_internal "${archive}"

    local size
    size="$(du -sh "${archive}" 2>/dev/null | cut -f1 || echo '?')"
    success "Backup created: $(basename "${archive}") (${size})"
    _log OK "Backup created: ${archive} size=${size}"

    info "Rotating backups (keeping last ${KEEP})…"
    rotate_backups

    local count
    count="$(find "${BACKUP_DIR}" -maxdepth 1 -name 'melvin_backup_*.tar.gz' | wc -l)"
    info "Current backup count: ${count}"

    echo -e "\n${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
    success "Backup complete."
    _log OK "Backup run finished."
}

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if [[ -n "${RESTORE_FILE}" ]]; then
    do_restore
else
    do_backup
fi
