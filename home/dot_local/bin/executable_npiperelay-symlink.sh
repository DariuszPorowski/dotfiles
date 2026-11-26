#!/bin/sh
set -eu

# Never install a system-wide link to a binary from another user's profile.
target=$(command -v npiperelay.exe || true)
if [ -z "$target" ]; then
  profile=$(cd /mnt/c && /mnt/c/Windows/System32/cmd.exe /d /c 'echo %USERPROFILE%' | tr -d '\r')
  target="$(wslpath -u "$profile")/AppData/Local/Microsoft/WinGet/Links/npiperelay.exe"
fi
if [ ! -x "$target" ]; then
  target="/mnt/c/Program Files/WinGet/Links/npiperelay.exe"
fi
if [ ! -x "$target" ]; then
  echo "Install npiperelay on Windows and make npiperelay.exe visible to this WSL user." >&2
  exit 1
fi
link="$HOME/.local/bin/npiperelay"
if [ -e "$link" ] && [ ! -L "$link" ]; then
  echo "Refusing to replace existing $link" >&2
  exit 1
fi
mkdir -p "$HOME/.local/bin"
ln -sfnT "$target" "$link"
