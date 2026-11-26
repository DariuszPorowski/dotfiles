#!/bin/sh

set -eu

script_dir=$(CDPATH='' cd -P -- "$(dirname -- "$0")" && pwd -P)
bin_dir="$HOME/.local/bin"
export PATH="$PATH:$bin_dir"

if ! command -v chezmoi >/dev/null 2>&1; then
  # Digests from the upstream release's checksums.txt; update together.
  version=$(tr -d '\r' < "$script_dir/home/.chezmoiversion")
  case "$(uname -s)/$(uname -m)" in
    Linux/x86_64) arch=amd64; digest=5f2024119a1860f18f2243b892dd43a79f0fefe2ebef9786ee143f4d5fd69ccb ;;
    Linux/aarch64|Linux/arm64) arch=arm64; digest=bb1521dd02aff3967d61937213110e79ddd6e181e0856cf51e80dba01fda245f ;;
    Linux/i?86) arch=i386; digest=d0f956857f8bb3d4b63f0bf706c3bd7eb3fe5f7acc76df3470a7848bff74df28 ;;
    *) echo "Install chezmoi for this platform first." >&2; exit 1 ;;
  esac
  url="https://github.com/twpayne/chezmoi/releases/download/v$version/chezmoi_${version}_linux_${arch}.tar.gz"
  mkdir -p "$bin_dir"
  (
    tmp=$(mktemp -d "$bin_dir/.chezmoi.XXXXXXXX")
    trap 'rm -rf -- "$tmp"' EXIT
    trap 'exit 1' HUP INT TERM
    cd "$tmp"
    if command -v curl >/dev/null 2>&1; then
      curl -fsSL --proto '=https' --proto-redir '=https' -o archive "$url"
    elif command -v wget >/dev/null 2>&1; then
      wget -qO archive "$url"
    else
      echo "Install curl or wget to download chezmoi." >&2; exit 1
    fi
    printf '%s  archive\n' "$digest" | sha256sum -c -
    tar -xzf archive chezmoi
    chmod 755 chezmoi
    mv chezmoi "$bin_dir/chezmoi"
  )
fi

exec chezmoi init --source "$script_dir" --apply --error-on-conflict
