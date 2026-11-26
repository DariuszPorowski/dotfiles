#!/bin/bash
set -euo pipefail

if [[ ${1:-} == -h || ${1:-} == --help ]]; then
  echo "Usage: $0 [VERSION|latest] [INSTALL_DIR] (installs under INSTALL_DIR/go)"
  exit 0
fi
version=${1:-${VERSION:-latest}}
if [[ -z ${version//[[:space:]]/} ]]; then version=latest; fi
prefix=${2:-${INSTALL_DIR:-}}
if [[ -z $prefix ]]; then
  if (( EUID == 0 )); then prefix=/usr/local; else prefix="$HOME/.local"; fi
fi
mkdir -p -- "$prefix"
prefix=$(CDPATH='' cd -- "$prefix" && pwd -P)
target="$prefix/go"
if [[ -L $target || ( -e $target && ( ! -f $target/VERSION || ! -x $target/bin/go ) ) ]]; then
  echo "Refusing to replace non-Go installation at $target" >&2; exit 1
fi

matches_release() {
  local actual
  [[ -f $1/VERSION && $(head -n 1 "$1/VERSION") == "$2" ]] &&
    actual=$(GOTOOLCHAIN=local "$1/bin/go" version) &&
    [[ $actual == "go version $2 "* ]]
}

select_sdk() {
  # Store data, not shell code. Managed Bash and Zsh read this same preference.
  local choice="${XDG_STATE_HOME:-$HOME/.local/state}/dotfiles/go-root"
  if [[ ! -f $choice || $(<"$choice") != "$target" ]]; then
    mkdir -p -- "${choice%/*}"
    printf '%s\n' "$target" > "$choice"
  fi
  printf 'Selected %s in %s. Restart your shell to refresh PATH.\n' "$1" "$target"
}

if [[ $version != latest ]] && matches_release "$target" "go${version#go}"; then
  select_sdk "go${version#go}"
  exit 0
fi

case $(uname -m) in
  x86_64|amd64) arch=amd64 ;;
  aarch64|arm64) arch=arm64 ;;
  armv7l|armv6l) arch=armv6l ;;
  i386|i686) arch=386 ;;
  *) echo "Unsupported Go architecture" >&2; exit 1 ;;
esac

stage=$(mktemp -d "$prefix/.go-install.XXXXXXXX")
# Keep the previous installation for recovery if interrupted during replacement.
trap 'if [[ ! -e "$stage/previous" ]]; then rm -rf -- "$stage"; fi' EXIT
metadata='https://go.dev/dl/?mode=json'
if [[ $version != latest ]]; then metadata+='&include=all'; fi
curl -fsSL --proto '=https' --proto-redir '=https' -o "$stage/releases" "$metadata"
read -r release archive digest < <(
  jq -er --arg version "go${version#go}" --arg arch "$arch" '
    (if $version == "golatest" then .[0] else first(.[] | select(.version == $version)) end)
    | .version as $release | .files[] | select(.os=="linux" and .arch==$arch and .kind=="archive")
    | [$release, .filename, .sha256] | @tsv' "$stage/releases"
) || { echo "No Linux $arch release found for Go $version" >&2; exit 1; }

if ! matches_release "$target" "$release"; then
  curl -fsSL --proto '=https' --proto-redir '=https' -o "$stage/archive" "https://go.dev/dl/$archive"
  (cd "$stage" && printf '%s  archive\n' "$digest" | sha256sum -c - && tar -xzf archive)
  matches_release "$stage/go" "$release" || { echo "Archive does not run as $release" >&2; exit 1; }
  if [[ -e $target ]]; then mv -T -- "$target" "$stage/previous"; fi
  if ! mv -T -- "$stage/go" "$target"; then
    if [[ -d $stage/previous ]]; then mv -T -- "$stage/previous" "$target"; fi
    exit 1
  fi
  if [[ -d $stage/previous ]]; then rm -rf -- "$stage/previous"; fi
fi

select_sdk "$release"
