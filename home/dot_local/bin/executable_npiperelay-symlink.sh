#!/bin/bash

set -euo pipefail

CMD_EXE="/mnt/c/Windows/System32/cmd.exe"

# Determine the Windows username. WSL interop (running .exe files) may be
# unavailable in some contexts (e.g. under a systemd service), which surfaces
# as "Exec format error". Tolerate that and fall back gracefully.
get_windows_username() {
  local username=""

  if [ -x "$CMD_EXE" ]; then
    username="$("$CMD_EXE" /c "echo %username%" 2>/dev/null | tr -d '\r' || true)"
  fi

  if [ -z "$username" ] && command -v wslvar >/dev/null 2>&1; then
    username="$(wslvar USERNAME 2>/dev/null | tr -d '\r' || true)"
  fi

  echo "$username"
}

windowsUsername="$(get_windows_username)"

# Candidate locations for npiperelay.exe installed via WinGet (per-user and
# system-wide). When the username can't be resolved, fall back to globbing
# across all Windows user profiles.
npiperelayPaths=()
if [ -n "$windowsUsername" ]; then
  npiperelayPaths+=("/mnt/c/Users/$windowsUsername/AppData/Local/Microsoft/WinGet/Links/npiperelay.exe")
fi
npiperelayPaths+=(
  /mnt/c/Users/*/AppData/Local/Microsoft/WinGet/Links/npiperelay.exe
  "/mnt/c/Program Files/WinGet/Links/npiperelay.exe"
)

symlinkPath="/usr/local/bin/npiperelay"

pick_npiperelay() {
  local candidate

  for candidate in "${npiperelayPaths[@]}"; do
    if [ -f "$candidate" ]; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

main() {
  local target
  if ! target="$(pick_npiperelay)"; then
    echo "Error: npiperelay.exe not found in any known location." >&2
    echo "Checked:" >&2
    printf '  %s\n' "${npiperelayPaths[@]}" >&2
    exit 1
  fi

  # Ensure /usr/local/bin exists
  if [ ! -d "/usr/local/bin" ]; then
    sudo mkdir -p /usr/local/bin
  fi

  # If symlink exists and already points to target, do nothing
  if [ -L "$symlinkPath" ]; then
    currentTarget="$(readlink -f "$symlinkPath")"
    # Canonicalize Windows path via wslpath if possible
    if command -v wslpath >/dev/null 2>&1 && [[ "$target" == /mnt/c/* ]]; then
      targetCanonical="$(wslpath -u "$(wslpath -w "$target")")"
    else
      targetCanonical="$target"
    fi
    if [ "$currentTarget" = "$targetCanonical" ]; then
      echo "Symlink already exists: $symlinkPath -> $currentTarget"
      exit 0
    fi
  fi

  echo "Creating/Updating symlink: $symlinkPath -> $target"
  sudo ln -sf "$target" "$symlinkPath"
  echo "Done."
}

main "$@"
