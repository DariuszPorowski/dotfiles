#!/bin/bash

set -euo pipefail

# Constants
readonly GITHUB_OWNER="jqlang"
readonly GITHUB_REPO="jq"
readonly TOOL_NAME="jq"

# Configuration (can be overridden by env)
VERSION="${1:-${VERSION:-latest}}"
INSTALL_DIR="${2:-${INSTALL_DIR:-}}"

tempDir=""

log() {
  echo "-> $*" >&2
}

die() {
  echo "X Error: $*" >&2
  exit "${2:-1}"
}
usage() {
  cat <<EOF
Usage: $0 [VERSION] [INSTALL_DIR]

Positional arguments:
  VERSION           Version to install (default: latest)
  INSTALL_DIR       Custom install directory

Environment variables:
  VERSION           Desired version (default: latest)
  INSTALL_DIR       Install directory override

Examples:
  $0                      # Install latest
  $0 1.8.1                # Install 1.8.1
  $0 jq-1.8.1             # Install jq-1.8.1 tag
  $0 1.8.1 ~/.local/bin   # Install 1.8.1 to ~/.local/bin
EOF
}

cleanup() {
  if [[ -n "${tempDir}" && -d "${tempDir}" ]]; then
    rm -rf "${tempDir}"
  fi
}
trap cleanup EXIT INT TERM

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

# Normalize VERSION: empty/whitespace -> "latest"
if [[ -z "${VERSION//[[:space:]]/}" ]]; then
  VERSION="latest"
fi

# Determine install directory
if [[ -z "${INSTALL_DIR}" ]]; then
  if [[ "${EUID}" -eq 0 ]]; then
    INSTALL_DIR="/usr/local/bin"
  else
    INSTALL_DIR="${HOME}/.local/bin"
  fi
fi

command -v curl >/dev/null 2>&1 || die "Missing required dependency: curl"

if [[ ! -d "${INSTALL_DIR}" ]]; then
  mkdir -p "${INSTALL_DIR}" || die "Cannot create install directory ${INSTALL_DIR}"
fi

# Detect OS/arch (Linux only)
os="$(uname -s | tr '[:upper:]' '[:lower:]')"
[[ "${os}" == "linux" ]] || die "Unsupported OS: ${os} (this installer is for Linux binaries)"

archRaw="$(uname -m)"
case "${archRaw}" in
  x86_64 | amd64) arch="amd64" ;;
  arm64 | aarch64) arch="arm64" ;;
  armv7l) arch="armhf" ;;
  armv6l) arch="armel" ;;
  i386 | i686) arch="i386" ;;
  riscv64) arch="riscv64" ;;
  s390x) arch="s390x" ;;
  *) die "Unsupported architecture: ${archRaw}" ;;
esac

# Determine download URL
if [[ "${VERSION}" == "latest" ]]; then
  downloadUrl="https://github.com/${GITHUB_OWNER}/${GITHUB_REPO}/releases/latest/download/${TOOL_NAME}-linux-${arch}"
else
  tag="${VERSION}"
  if [[ "${tag}" =~ ^v[0-9] ]]; then
    tag="${tag#v}"
  fi
  if [[ "${tag}" =~ ^[0-9] ]]; then
    tag="${TOOL_NAME}-${tag}"
  fi
  downloadUrl="https://github.com/${GITHUB_OWNER}/${GITHUB_REPO}/releases/download/${tag}/${TOOL_NAME}-linux-${arch}"
fi

log "Installing ${TOOL_NAME} (${VERSION}) to ${INSTALL_DIR}"
log "Downloading ${downloadUrl}"

tempDir="$(mktemp -d)" || die "Failed to create temp directory"

binPath="${tempDir}/${TOOL_NAME}"
if ! curl -fsSL --proto '=https' --tlsv1.2 "${downloadUrl}" -o "${binPath}"; then
  die "Download failed (${downloadUrl}). Check version or network connection."
fi

chmod 0755 "${binPath}" || die "Failed to set permissions"

log "Installing binary"

# Set ownership if running as root
if [[ "${EUID}" -eq 0 ]]; then
  chown root:0 "${binPath}" || die "Failed to set ownership"
fi

install -Dm0755 "${binPath}" "${INSTALL_DIR}/${TOOL_NAME}" || die "Failed to install binary"

log "✓ Successfully installed ${TOOL_NAME} to ${INSTALL_DIR}/${TOOL_NAME}"

"${INSTALL_DIR}/${TOOL_NAME}" --version >/dev/null 2>&1 || die "Installed binary failed to run (${INSTALL_DIR}/${TOOL_NAME})"
