#!/bin/sh

set -eu

BIN_DIR="${HOME}/.local/bin"

install_if_missing() {
  local name="$1"
  local install_url="$2"
  
  if ! command -v "$name" >/dev/null 2>&1; then
    echo "Installing $name to '${BIN_DIR}'" >&2
    curl -fsSL "$install_url" | bash -s -- -d "${BIN_DIR}"
  fi
}

# Install chezmoi
if ! chezmoi="$(command -v chezmoi)"; then
  chezmoi="${BIN_DIR}/chezmoi"
  echo "Installing chezmoi to '${chezmoi}'" >&2
  if command -v curl >/dev/null; then
    sh -c "$(curl -fsSL get.chezmoi.io)" -- -b "${BIN_DIR}"
  elif command -v wget >/dev/null; then
    sh -c "$(wget -qO- get.chezmoi.io)" -- -b "${BIN_DIR}"
  else
    echo "Error: curl or wget required" >&2
    exit 1
  fi
fi

# Install other tools
install_if_missing "oh-my-posh" "https://ohmyposh.dev/install.sh"
install_if_missing "aliae" "https://aliae.dev/install.sh"

# Apply chezmoi configuration
script_dir="$(cd -P -- "$(dirname -- "$(command -v -- "$0")")" && pwd -P)"
echo "Running 'chezmoi init --apply --source=${script_dir}'" >&2
exec "$chezmoi" init --apply --source="${script_dir}"
