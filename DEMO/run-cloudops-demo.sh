
#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

# ============================================================
# CloudOps no-domain synthetic demo installer and runner
#
# Supported distributions:
#   - Ubuntu
#   - Debian
#   - CentOS Stream
#   - Red Hat Enterprise Linux
#
# Default operation:
#   1. Detect the Linux distribution
#   2. Check Git, Docker, Compose, Python and PowerShell
#   3. Install missing dependencies
#   4. Replace podman-docker with Docker Engine when required
#   5. Clone or update CloudOps
#   6. Apply the demo_check.ps1 HTTP-404 compatibility fix
#   7. Start the synthetic demo
#   8. Create a temporary trycloudflare.com URL
# ============================================================

REPO_URL="https://github.com/cloudops-project/CloudOps.git"
INSTALL_DIR="${CLOUDOPS_DIR:-$HOME/CloudOps}"

CHECK_ONLY=false
INSTALL_ONLY=false
LOCAL_ONLY=false
SKIP_BUILD=false

MINIMUM_FREE_KB=$((4 * 1024 * 1024))
RECOMMENDED_FREE_KB=$((10 * 1024 * 1024))

POWERSHELL_VERSION="7.6.4"

POWERSHELL_DEB_URL="https://github.com/PowerShell/PowerShell/releases/download/v${POWERSHELL_VERSION}/powershell_${POWERSHELL_VERSION}-1.deb_amd64.deb"

POWERSHELL_RPM_URL="https://github.com/PowerShell/PowerShell/releases/download/v${POWERSHELL_VERSION}/powershell-${POWERSHELL_VERSION}-1.rh.x86_64.rpm"

BLUE='\033[1;34m'
GREEN='\033[1;32m'
YELLOW='\033[1;33m'
RED='\033[1;31m'
RESET='\033[0m'

log() {
    printf '\n%b[CloudOps]%b %s\n' "$BLUE" "$RESET" "$*"
}

success() {
    printf '%b[OK]%b %s\n' "$GREEN" "$RESET" "$*"
}

warning() {
    printf '%b[WARNING]%b %s\n' "$YELLOW" "$RESET" "$*" >&2
}

die() {
    printf '\n%b[ERROR]%b %s\n' "$RED" "$RESET" "$*" >&2
    exit 1
}

on_error() {
    local exit_code=$?
    local line_number=$1

    printf '\n%b[ERROR]%b Script failed at line %s with exit code %s.\n' \
        "$RED" "$RESET" "$line_number" "$exit_code" >&2

    exit "$exit_code"
}

trap 'on_error "$LINENO"' ERR

usage() {
    cat <<'USAGE'
CloudOps synthetic demo installer

Usage:
  ./run-cloudops-demo.sh [options]

Options:
  --check-only
      Show the OS and dependency versions, then exit.

  --install-only
      Install dependencies and clone/update CloudOps, but do not run it.

  --local-only
      Start the demo only on localhost without a public Quick Tunnel.

  --skip-build
      Reuse existing Docker images instead of rebuilding them.

  --help
      Show this help message.

Default:
  Check/install dependencies, clone/update CloudOps, reset the synthetic
  demo database, and create a temporary trycloudflare.com URL.

Examples:
  ./run-cloudops-demo.sh
  ./run-cloudops-demo.sh --check-only
  ./run-cloudops-demo.sh --install-only
  ./run-cloudops-demo.sh --local-only
  ./run-cloudops-demo.sh --skip-build
USAGE
}

for argument in "$@"; do
    case "$argument" in
        --check-only)
            CHECK_ONLY=true
            ;;
        --install-only)
            INSTALL_ONLY=true
            ;;
        --local-only)
            LOCAL_ONLY=true
            ;;
        --skip-build)
            SKIP_BUILD=true
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            die "Unknown option: $argument. Use --help."
            ;;
    esac
done

# ------------------------------------------------------------
# Detect Linux distribution
# ------------------------------------------------------------

[[ -f /etc/os-release ]] ||
    die "Cannot detect Linux distribution because /etc/os-release is missing."

# shellcheck disable=SC1091
source /etc/os-release

OS_ID="${ID:-unknown}"
OS_VERSION="${VERSION_ID:-unknown}"
OS_NAME="${PRETTY_NAME:-$OS_ID}"

case "$OS_ID" in
    ubuntu)
        OS_FAMILY="apt"
        DOCKER_REPOSITORY_OS="ubuntu"
        MICROSOFT_REPOSITORY_OS="ubuntu"
        ;;

    debian)
        OS_FAMILY="apt"
        DOCKER_REPOSITORY_OS="debian"
        MICROSOFT_REPOSITORY_OS="debian"
        ;;

    centos)
        OS_FAMILY="rpm"
        DOCKER_REPOSITORY_OS="centos"
        MICROSOFT_REPOSITORY_OS="rhel"
        ;;

    rhel)
        OS_FAMILY="rpm"
        DOCKER_REPOSITORY_OS="rhel"
        MICROSOFT_REPOSITORY_OS="rhel"
        ;;

    *)
        die "Unsupported distribution: $OS_NAME. Supported: Ubuntu, Debian, CentOS Stream and RHEL."
        ;;
esac

# ------------------------------------------------------------
# Version and dependency checks
# ------------------------------------------------------------

show_command_version() {
    local name=$1
    shift

    printf '%-22s' "$name:"

    if "$@" >/tmp/cloudops-version-output 2>&1; then
        head -n 1 /tmp/cloudops-version-output
    else
        printf 'NOT INSTALLED OR NOT WORKING\n'
    fi

    rm -f /tmp/cloudops-version-output
}

docker_is_podman_shim() {
    command -v docker >/dev/null 2>&1 &&
        docker --version 2>&1 |
        grep -qiE 'podman|emulate docker'
}

docker_engine_available() {
    command -v docker >/dev/null 2>&1 &&
        ! docker_is_podman_shim
}

docker_compose_available() {
    docker_engine_available &&
        docker compose version >/dev/null 2>&1
}

show_versions() {
    echo
    echo "============================================================"
    echo " Operating system and dependency check"
    echo "============================================================"

    printf '%-22s%s\n' "Operating system:" "$OS_NAME"
    printf '%-22s%s\n' "Distribution ID:" "$OS_ID"
    printf '%-22s%s\n' "Distribution version:" "$OS_VERSION"
    printf '%-22s%s\n' "Architecture:" "$(uname -m)"
    printf '%-22s%s\n' "Kernel:" "$(uname -r)"

    echo

    show_command_version "Git" git --version

    if docker_is_podman_shim; then
        printf '%-22s%s\n' \
            "Docker:" \
            "PODMAN COMPATIBILITY SHIM DETECTED"

        printf '%-22s%s\n' \
            "Docker Compose:" \
            "NOT AVAILABLE"
    else
        show_command_version "Docker" docker --version
        show_command_version "Docker Compose" docker compose version
    fi

    show_command_version "Python" python3 --version
    show_command_version "PowerShell" pwsh --version

    echo "============================================================"
}

check_disk_space() {
    local available_kb
    local available_gib

    available_kb="$(df -Pk / | awk 'NR == 2 {print $4}')"

    available_gib="$(
        awk -v kb="$available_kb" \
            'BEGIN {printf "%.1f", kb / 1024 / 1024}'
    )"

    log "Disk-space check"

    printf 'Root filesystem free space: %s GiB\n' "$available_gib"

    if (( available_kb < MINIMUM_FREE_KB )); then
        die "At least 4 GiB of free root-filesystem space is required."
    fi

    if (( available_kb < RECOMMENDED_FREE_KB )); then
        warning "Less than 10 GiB is available. Docker builds may consume most remaining space."
    else
        success "Available disk space is acceptable."
    fi
}

show_versions

if [[ "$CHECK_ONLY" == true ]]; then
    exit 0
fi

[[ "$(id -u)" -eq 0 ]] ||
    die "Run this script as root, for example: sudo $0 $*"

check_disk_space

# ------------------------------------------------------------
# Base package installation
# ------------------------------------------------------------

apt_update_once=false

apt_update() {
    if [[ "$apt_update_once" == false ]]; then
        log "Updating APT package metadata"

        export DEBIAN_FRONTEND=noninteractive
        apt-get update

        apt_update_once=true
    fi
}

install_base_dependencies() {
    log "Checking basic dependencies"

    if [[ "$OS_FAMILY" == "apt" ]]; then
        apt_update

        apt-get install -y \
            ca-certificates \
            curl \
            git \
            gnupg \
            python3 \
            wget
    else
        dnf install -y \
            ca-certificates \
            curl \
            dnf-plugins-core \
            git \
            python3 \
            wget
    fi

    success "Basic dependencies are installed."
}

# ------------------------------------------------------------
# Docker installation
# ------------------------------------------------------------

remove_apt_docker_conflicts() {
    local conflicts=(
        docker.io
        docker-compose
        docker-compose-v2
        docker-doc
        podman-docker
        containerd
        runc
    )

    local installed=()
    local package

    for package in "${conflicts[@]}"; do
        if dpkg-query -W -f='${Status}' "$package" 2>/dev/null |
            grep -q 'install ok installed'; then

            installed+=("$package")
        fi
    done

    if (( ${#installed[@]} > 0 )); then
        log "Removing conflicting Docker packages"

        apt-get remove -y "${installed[@]}"
    fi
}

remove_rpm_docker_conflicts() {
    local conflicts=(
        podman-docker
        docker
        docker-client
        docker-client-latest
        docker-common
        docker-latest
        docker-latest-logrotate
        docker-logrotate
        docker-engine
    )

    local installed=()
    local package

    for package in "${conflicts[@]}"; do
        if rpm -q "$package" >/dev/null 2>&1; then
            installed+=("$package")
        fi
    done

    if (( ${#installed[@]} > 0 )); then
        log "Removing conflicting Docker packages or Podman compatibility shims"

        dnf remove -y "${installed[@]}"

        hash -r
    fi
}

install_docker_apt() {
    remove_apt_docker_conflicts
    apt_update

    log "Adding the official Docker repository"

    install -m 0755 -d /etc/apt/keyrings

    curl -fsSL \
        "https://download.docker.com/linux/${DOCKER_REPOSITORY_OS}/gpg" \
        -o /etc/apt/keyrings/docker.asc

    chmod a+r /etc/apt/keyrings/docker.asc

    local codename

    if [[ "$OS_ID" == "ubuntu" ]]; then
        codename="${UBUNTU_CODENAME:-${VERSION_CODENAME:-}}"
    else
        codename="${VERSION_CODENAME:-}"
    fi

    [[ -n "$codename" ]] ||
        die "Could not determine the distribution codename."

    cat > /etc/apt/sources.list.d/docker.sources <<DOCKER_SOURCE
Types: deb
URIs: https://download.docker.com/linux/${DOCKER_REPOSITORY_OS}
Suites: ${codename}
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
DOCKER_SOURCE

    apt_update_once=false
    apt_update

    log "Installing Docker Engine, Buildx and Docker Compose"

    apt-get install -y \
        docker-ce \
        docker-ce-cli \
        containerd.io \
        docker-buildx-plugin \
        docker-compose-plugin
}

install_docker_rpm() {
    remove_rpm_docker_conflicts

    log "Adding the official Docker repository"

    dnf install -y dnf-plugins-core

    local repository_file="/etc/yum.repos.d/docker-ce.repo"

    if [[ ! -f "$repository_file" ]]; then
        dnf config-manager --add-repo \
            "https://download.docker.com/linux/${DOCKER_REPOSITORY_OS}/docker-ce.repo"
    fi

    log "Installing Docker Engine, Buildx and Docker Compose"

    dnf install -y \
        docker-ce \
        docker-ce-cli \
        containerd.io \
        docker-buildx-plugin \
        docker-compose-plugin
}

install_docker() {
    if docker_engine_available &&
       docker_compose_available; then

        success "Docker Engine and Docker Compose are already installed."
    else
        if docker_is_podman_shim; then
            warning "Podman Docker compatibility shim detected."

            warning "The shim will be removed, but existing Podman images and volumes will not be deleted."
        fi

        if [[ "$OS_FAMILY" == "apt" ]]; then
            install_docker_apt
        else
            install_docker_rpm
        fi
    fi

    log "Starting Docker Engine"

    systemctl enable --now docker

    docker info >/dev/null ||
        die "Docker was installed but the Docker daemon is unavailable."

    docker compose version >/dev/null ||
        die "Docker Compose was installed but cannot be executed."

    success "Docker Engine and Docker Compose are working."
}

# ------------------------------------------------------------
# PowerShell installation
# ------------------------------------------------------------

install_powershell_apt() {
    local temporary_directory
    local microsoft_package
    local architecture

    temporary_directory="$(mktemp -d)"
    microsoft_package="$temporary_directory/packages-microsoft-prod.deb"

    log "Adding the Microsoft package repository"

    if curl -fsSL \
        "https://packages.microsoft.com/config/${MICROSOFT_REPOSITORY_OS}/${OS_VERSION}/packages-microsoft-prod.deb" \
        -o "$microsoft_package"; then

        dpkg -i "$microsoft_package"

        apt_update_once=false
        apt_update

        if apt-get install -y powershell; then
            rm -rf "$temporary_directory"
            return
        fi
    fi

    warning "Microsoft repository installation failed."

    warning "Trying the PowerShell universal Debian package."

    architecture="$(dpkg --print-architecture)"

    [[ "$architecture" == "amd64" ]] ||
        die "Automatic PowerShell fallback currently supports amd64 only. Detected: $architecture"

    curl -fsSL \
        "$POWERSHELL_DEB_URL" \
        -o "$temporary_directory/powershell.deb"

    if ! dpkg -i "$temporary_directory/powershell.deb"; then
        apt-get install -f -y
    fi

    rm -rf "$temporary_directory"
}

install_powershell_rpm() {
    local major_version
    local temporary_directory
    local microsoft_package

    major_version="${OS_VERSION%%.*}"
    temporary_directory="$(mktemp -d)"
    microsoft_package="$temporary_directory/packages-microsoft-prod.rpm"

    log "Adding the Microsoft package repository"

    if curl -fsSL \
        "https://packages.microsoft.com/config/rhel/${major_version}/packages-microsoft-prod.rpm" \
        -o "$microsoft_package"; then

        rpm -Uvh --replacepkgs "$microsoft_package"

        if dnf install -y powershell; then
            rm -rf "$temporary_directory"
            return
        fi
    fi

    warning "Microsoft repository installation failed."

    warning "Trying the PowerShell universal RHEL package."

    [[ "$(uname -m)" == "x86_64" ]] ||
        die "Automatic PowerShell RPM fallback currently supports x86_64 only."

    dnf install -y "$POWERSHELL_RPM_URL"

    rm -rf "$temporary_directory"
}

install_powershell() {
    if command -v pwsh >/dev/null 2>&1; then
        success "PowerShell is already installed."
        return
    fi

    log "Installing PowerShell"

    if [[ "$OS_FAMILY" == "apt" ]]; then
        install_powershell_apt
    else
        install_powershell_rpm
    fi

    command -v pwsh >/dev/null 2>&1 ||
        die "PowerShell installation completed, but pwsh was not found."

    success "PowerShell is installed."
}

# ------------------------------------------------------------
# Install dependencies
# ------------------------------------------------------------

install_base_dependencies
install_docker
install_powershell

log "Installed dependency versions"

show_versions

# ------------------------------------------------------------
# CloudOps repository preparation
# ------------------------------------------------------------

restore_known_demo_check_patch_before_update() {
    cd "$INSTALL_DIR"

    # Remove the backup created during the original manual troubleshooting.
    rm -f scripts/demo_check.ps1.bak

    local tracked_changes
    local untracked_files

    tracked_changes="$(
        {
            git diff --name-only
            git diff --cached --name-only
        } |
        sed '/^$/d' |
        sort -u
    )"

    untracked_files="$(
        git ls-files --others --exclude-standard |
        sed '/^$/d' |
        sort -u
    )"

    if [[ -z "$tracked_changes" &&
          -z "$untracked_files" ]]; then

        return
    fi

    if [[ "$tracked_changes" == "scripts/demo_check.ps1" &&
          -z "$untracked_files" ]] &&
       grep -Fq -- "-SkipHttpErrorCheck" scripts/demo_check.ps1; then

        log "Restoring the known local demo-check compatibility patch before updating"

        git restore \
            --source=HEAD \
            --staged \
            --worktree \
            scripts/demo_check.ps1

        return
    fi

    echo
    git status --short

    die "The existing CloudOps repository has unexpected local changes. Preserve or remove them before updating."
}

prepare_repository() {
    if [[ -d "$INSTALL_DIR/.git" ]]; then
        log "Existing CloudOps repository found at $INSTALL_DIR"

        cd "$INSTALL_DIR"

        local current_origin
        current_origin="$(git remote get-url origin 2>/dev/null || true)"

        [[ "$current_origin" == "$REPO_URL" ]] ||
            die "$INSTALL_DIR is not connected to the expected CloudOps repository."

        restore_known_demo_check_patch_before_update

        log "Updating the CloudOps main branch"

        git fetch origin main
        git switch main
        git pull --ff-only origin main

    elif [[ -e "$INSTALL_DIR" ]]; then
        die "$INSTALL_DIR exists but is not a Git repository."

    else
        log "Cloning the CloudOps main branch"

        git clone \
            --branch main \
            --single-branch \
            "$REPO_URL" \
            "$INSTALL_DIR"

        cd "$INSTALL_DIR"
    fi

    success "CloudOps repository is ready."

    echo
    git status --short --branch
    git log -1 --oneline
}

# ------------------------------------------------------------
# Apply the verified demo_check.ps1 compatibility fix
# ------------------------------------------------------------

apply_demo_check_fix() {
    cd "$INSTALL_DIR"

    log "Checking demo_check.ps1 HTTP-error compatibility"

    python3 - <<'PY'
from pathlib import Path

path = Path("scripts/demo_check.ps1")

if not path.is_file():
    raise SystemExit("scripts/demo_check.ps1 was not found.")

content = path.read_text(encoding="utf-8")

old = (
    '$openapi = Invoke-WebRequest -UseBasicParsing '
    '-Uri "http://localhost:5173/api/v1/openapi.json" '
    '-TimeoutSec 20 -ErrorAction SilentlyContinue'
)

new = (
    '$openapi = Invoke-WebRequest -UseBasicParsing '
    '-Uri "http://localhost:5173/api/v1/openapi.json" '
    '-TimeoutSec 20 -SkipHttpErrorCheck'
)

if new in content:
    print("demo_check.ps1 compatibility fix is already applied.")

elif old in content:
    content = content.replace(old, new, 1)
    path.write_text(content, encoding="utf-8")

    print("demo_check.ps1 compatibility fix applied.")

else:
    raise SystemExit(
        "Expected OpenAPI check was not found. "
        "The upstream script may have changed; refusing an unsafe patch."
    )
PY

    grep -n -- "openapi.json" scripts/demo_check.ps1

    if ! grep -Fq -- "-SkipHttpErrorCheck" scripts/demo_check.ps1; then
        die "The demo_check.ps1 compatibility patch was not applied correctly."
    fi

    # Parse the PowerShell file without executing it.
    pwsh -NoProfile -Command '
        $tokens = $null
        $errors = $null

        [System.Management.Automation.Language.Parser]::ParseFile(
            "'"$INSTALL_DIR"'/scripts/demo_check.ps1",
            [ref]$tokens,
            [ref]$errors
        ) | Out-Null

        if ($errors.Count -gt 0) {
            $errors | ForEach-Object { Write-Error $_ }
            exit 1
        }
    '

    success "demo_check.ps1 compatibility patch passed PowerShell parsing."
}

prepare_repository
apply_demo_check_fix

if [[ "$INSTALL_ONLY" == true ]]; then
    echo
    success "Dependency installation and repository preparation completed."

    echo "CloudOps directory: $INSTALL_DIR"
    exit 0
fi

check_disk_space

# ------------------------------------------------------------
# Diagnostics
# ------------------------------------------------------------

show_demo_diagnostics() {
    cd "$INSTALL_DIR"

    warning "Collecting CloudOps container diagnostics"

    docker compose \
        -f compose.demo.yml \
        --profile tunnel \
        ps || true

    docker compose \
        -f compose.demo.yml \
        logs \
        --no-color \
        --tail=100 \
        api \
        web \
        postgres \
        job-worker \
        scheduler-worker || true

    docker compose \
        -f compose.demo.yml \
        --profile tunnel \
        logs \
        --no-color \
        --tail=100 \
        cloudflared || true
}

# ------------------------------------------------------------
# Start CloudOps demo
# ------------------------------------------------------------

run_demo() {
    cd "$INSTALL_DIR"

    local powershell_arguments=(
        -NoProfile
        -File
        ./scripts/demo_bootstrap.ps1
        -Reset
    )

    if [[ "$LOCAL_ONLY" == false ]]; then
        powershell_arguments+=(-Tunnel)
    fi

    if [[ "$SKIP_BUILD" == true ]]; then
        powershell_arguments+=(-SkipBuild)
    fi

    log "Starting the CloudOps synthetic demo"

    if [[ "$LOCAL_ONLY" == true ]]; then
        warning "Local-only mode selected. No public Cloudflare URL will be created."
    else
        echo "A temporary trycloudflare.com URL will be created."
        echo "The public URL changes whenever the tunnel restarts."
    fi

    if ! pwsh "${powershell_arguments[@]}"; then
        show_demo_diagnostics

        die "CloudOps demo startup failed. Review the diagnostics printed above."
    fi

    log "Running final container status"

    docker compose \
        -f compose.demo.yml \
        --profile tunnel \
        ps

    echo
    echo "============================================================"
    echo " CloudOps synthetic demo"
    echo "============================================================"

    echo
    echo "Local application:"
    echo "  http://localhost:5173"

    echo
    echo "Mailpit:"
    echo "  http://localhost:8025"

    echo
    echo "Demo login:"
    echo "  Email    : owner@cloudops-demo.testmail.com"
    echo "  Password : CloudOps-Demo-Password-123!"

    if [[ "$LOCAL_ONLY" == false ]]; then
        local temporary_url

        temporary_url="$(
            docker compose \
                -f compose.demo.yml \
                --profile tunnel \
                logs \
                --no-color \
                cloudflared 2>/dev/null |
                grep -Eo \
                    'https://[-a-z0-9]+\.trycloudflare\.com' |
                tail -n 1 ||
                true
        )"

        echo
        echo "Temporary public URL:"

        if [[ -n "$temporary_url" ]]; then
            echo "  $temporary_url"
        else
            echo "  The URL was not automatically extracted."
            echo "  Check the cloudflared logs with the command below."
        fi
    fi

    echo
    echo "Check services:"
    echo "  cd \"$INSTALL_DIR\""
    echo "  docker compose -f compose.demo.yml --profile tunnel ps"

    echo
    echo "View the tunnel URL and logs:"
    echo "  docker compose -f compose.demo.yml --profile tunnel logs --tail=100 cloudflared"

    echo
    echo "Show only the temporary public URL:"
    echo "  docker compose -f compose.demo.yml --profile tunnel logs --no-color cloudflared | grep -Eo 'https://[-a-z0-9]+\\.trycloudflare\\.com' | tail -1"

    echo
    echo "Stop everything while preserving demo data:"
    echo "  docker compose -f compose.demo.yml --profile tunnel down"

    echo
    echo "Stop everything and delete demo data:"
    echo "  docker compose -f compose.demo.yml --profile tunnel down -v"

    echo
    echo "Restart later without rebuilding images:"
    echo "  pwsh -NoProfile -File ./scripts/demo_bootstrap.ps1 -Reset -Tunnel -SkipBuild"

    echo
    echo "Important:"
    echo "  Do not run ./cloudops.sh up without a domain."
    echo "  That command is for the stable named-tunnel deployment."

    echo
    echo "============================================================"
}

run_demo
