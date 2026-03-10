#!/usr/bin/env bash
# =============================================================================
# Melvin God Mode – Debian Dependency Setup
# =============================================================================
# Installs only the system-level dependencies needed for Melvin God Mode.
# Useful for offline setups, custom deployments, or CI/CD pipelines.
#
# Usage:
#   sudo ./setup-dependencies.sh [--minimal]
#
#   --minimal   Install only the absolute minimum required packages.
# =============================================================================

set -euo pipefail

# ── colours ───────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
RESET='\033[0m'

info()    { echo -e "${CYAN}[INFO]${RESET}  $*"; }
success() { echo -e "${GREEN}[OK]${RESET}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
die()     { echo -e "${RED}[ERROR]${RESET} $*" >&2; exit 1; }

# ── root check ────────────────────────────────────────────────────────────────
[[ $EUID -ne 0 ]] && die "Must be run as root. Try: sudo ./setup-dependencies.sh"

# ── package lists ─────────────────────────────────────────────────────────────

# Packages always required
REQUIRED_PACKAGES=(
    python3
    python3-pip
    python3-venv
    python3-dev
    curl
    wget
    ca-certificates
    git
)

# Packages needed for building native Python extensions (cryptography, etc.)
BUILD_PACKAGES=(
    build-essential
    libssl-dev
    libffi-dev
    pkg-config
)

# Nice-to-have utilities
OPTIONAL_PACKAGES=(
    jq
    htop
    net-tools
    unzip
    gnupg
    lsb-release
)

# ── functions ─────────────────────────────────────────────────────────────────
update_apt() {
    info "Refreshing package lists..."
    apt-get update -qq
    success "Package lists updated."
}

install_packages() {
    local label="$1"
    shift
    local packages=("$@")

    info "Installing ${label} packages..."
    # Filter out already-installed packages for a clean install list
    local to_install=()
    for pkg in "${packages[@]}"; do
        if ! dpkg -l "${pkg}" &>/dev/null; then
            to_install+=("${pkg}")
        else
            info "  ${pkg} – already installed, skipping."
        fi
    done

    if [[ ${#to_install[@]} -eq 0 ]]; then
        success "All ${label} packages already present."
        return 0
    fi

    apt-get install -y "${to_install[@]}"
    success "${label} packages installed: ${to_install[*]}"
}

verify_python() {
    local ver
    ver=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')")
    local major minor
    IFS='.' read -r major minor _ <<<"$ver"

    if (( major < 3 || (major == 3 && minor < 9) )); then
        warn "Python ${ver} may be too old. Melvin requires Python 3.9+."
        warn "Consider upgrading: sudo apt-get install -y python3.X python3.X-pip python3.X-venv (replace X with the latest available version)"
    else
        success "Python ${ver} – OK."
    fi
}

check_disk_space() {
    local required_mb=2048  # 2 GB minimum
    local available_mb
    available_mb=$(df /opt --output=avail -BM | tail -1 | tr -d 'M ')

    if (( available_mb < required_mb )); then
        warn "Low disk space: ${available_mb} MB available, ${required_mb} MB recommended."
    else
        success "Disk space: ${available_mb} MB available – OK."
    fi
}

# ── main ──────────────────────────────────────────────────────────────────────
main() {
    local minimal=false
    for arg in "$@"; do
        [[ "$arg" == "--minimal" ]] && minimal=true
    done

    echo
    echo "  Melvin God Mode – Dependency Setup"
    echo "  ────────────────────────────────────"
    echo

    check_disk_space
    update_apt
    install_packages "required" "${REQUIRED_PACKAGES[@]}"

    if [[ "$minimal" != true ]]; then
        install_packages "build"    "${BUILD_PACKAGES[@]}"
        install_packages "optional" "${OPTIONAL_PACKAGES[@]}"
    fi

    verify_python

    echo
    success "All dependencies installed successfully."
    info "Run './install.sh' for the full Melvin God Mode setup."
    echo
}

main "$@"
