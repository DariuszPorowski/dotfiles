#!/bin/bash

set -euo pipefail

# Constants
readonly TOOL_NAME="fnm"
readonly INSTALL_SCRIPT_URL="https://fnm.vercel.app/install"

# Configuration (can be overridden by env)
VERSION="${1:-${VERSION:-latest}}"
INSTALL_DIR="${2:-${INSTALL_DIR:-}}"

# Logging helper
log() {
  echo "-> $*" >&2
}

# Error handling helper
die() {
  echo "X Error: $*" >&2
  exit "${2:-1}"
}

# Help message
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
  $0                         # Install latest
  $0 1.37.0                  # Install 1.37.0
  $0 1.37.0 ~/.local/fnm     # Install 1.37.0 to custom location
  VERSION=1.37.0 $0          # Install 1.37.0 via env
EOF
}

# Show help if requested
if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

# Normalize VERSION: empty/whitespace -> "latest", numeric -> add "v" prefix
if [[ -z "${VERSION//[[:space:]]/}" ]]; then
  VERSION="latest"
elif [[ "${VERSION}" != "latest" && "${VERSION}" =~ ^[0-9] ]]; then
  VERSION="v${VERSION}"
fi

# Determine install directory
if [[ -z "${INSTALL_DIR}" ]]; then
  INSTALL_DIR="${HOME}/.local/share/fnm"
fi

link_dir="$HOME/.local/bin"
mkdir -p -- "$INSTALL_DIR" "$link_dir"
bin="$(CDPATH='' cd -- "$INSTALL_DIR" && pwd -P)/$TOOL_NAME"
link="$(CDPATH='' cd -- "$link_dir" && pwd -P)/$TOOL_NAME"
previous=''
if [[ -L $link ]]; then
  previous=$(readlink "$link")
elif [[ -e $link && $link != "$bin" ]]; then
  die "Not replacing existing file: $link"
fi

if [[ $VERSION == latest || ! -x $bin ]] ||
   ! installed=$("$bin" --version) || [[ $installed != "fnm ${VERSION#v}" ]]; then
  unset GH_TOKEN GITHUB_TOKEN
  log "Installing $TOOL_NAME ($VERSION) to $INSTALL_DIR"
  if ! curl -fsSL --proto '=https' --tlsv1.3 "$INSTALL_SCRIPT_URL" |
    bash -s -- --skip-shell --install-dir "${bin%/*}" --release "$VERSION"; then
    die "Installation failed. Check version or network connection."
  fi
  installed=$("$bin" --version) || die "Installed binary failed to run: $bin"
  [[ $VERSION == latest || $installed == "fnm ${VERSION#v}" ]] || die "Expected $VERSION; got $installed"
fi
if [[ $link != "$bin" && $previous != "$bin" ]]; then
  ln -sfn -- "$bin" "$link"
fi

# Bash and Zsh source .commonrc. Fish loads conf.d even without a config.fish.
fish_dir="${XDG_CONFIG_HOME:-$HOME/.config}/fish"
hook="$fish_dir/conf.d/dotfiles-fnm.fish"
mkdir -p -- "${hook%/*}"
if [[ ! -e $hook && ! -L $hook ]]; then
  cat > "$hook" <<'FISH'
if status is-interactive; and test -x "$HOME/.local/bin/fnm"
    fish_add_path --move --path "$HOME/.local/bin"
    "$HOME/.local/bin/fnm" env --use-on-cd --version-file-strategy=recursive --shell fish | source
end
FISH
fi

# Remove only complete lines our earlier installers emitted; keep user hooks
# and even an unterminated last line unchanged.
migrate_fish() {
  local config=$1 line eol dir kept='' changed=0
  [[ -f $config ]] || return 0
  while :; do
    if IFS= read -r line; then eol=$'\n'; elif [[ -n $line ]]; then eol=''; else break; fi
    # shellcheck disable=SC2016 # Match the literal old hook, not its output.
    case $line in
      'eval "$(fnm env --use-on-cd --shell fish)"'|'fnm env --use-on-cd --shell fish | source')
        changed=1; continue ;;
    esac
    for dir in "$INSTALL_DIR" "${bin%/*}" "${previous%/*}" "$HOME/.local/share/fnm"; do
      if [[ -n $dir && ( $line == "export PATH=\$PATH:$dir" || $line == "fish_add_path '$dir'" ) ]]; then
        changed=1; continue 2
      fi
    done
    kept+="$line$eol"
  done < "$config"
  if (( changed )); then printf '%s' "$kept" > "$config"; fi
}
migrate_fish "$fish_dir/config.fish"
if [[ $fish_dir != "$HOME/.config/fish" ]]; then migrate_fish "$HOME/.config/fish/config.fish"; fi
log "Selected $installed at $bin. Restart your shell to activate it."
