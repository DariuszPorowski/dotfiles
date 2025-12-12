#!/bin/bash

set -euo pipefail

DEVICE="/dev/sde"
MOUNT_POINT="/mnt/wsl/workspaces"

# If the device exists, format it only when it doesn't already have a filesystem.
if [[ -b "${DEVICE}" ]]; then
  if ! blkid -o value -s TYPE "${DEVICE}" >/dev/null 2>&1; then
    sudo mkfs.ext4 -m 0 -i 12000 -F -E "lazy_itable_init=1,lazy_journal_init=1,discard" -L workspaces "${DEVICE}"
  fi
fi

# After init, ensure all users (no sudo) can read/write on the volume.
if [[ -d "${MOUNT_POINT}" ]] && grep -qs " ${MOUNT_POINT} " /proc/mounts; then
  # Ensure shared group ownership and group inheritance for new files.
  # Prefer the invoking user when run via sudo; otherwise fall back to the common first user (uid 1000).
  OWNER_USER="${SUDO_USER:-}"
  if [[ -z "$OWNER_USER" ]] || [[ "$OWNER_USER" == "root" ]]; then
    OWNER_USER="$(getent passwd 1000 | cut -d: -f1 || true)"
  fi
  if [[ -z "$OWNER_USER" ]]; then
    OWNER_USER="root"
  fi

  sudo chown "${OWNER_USER}:users" "${MOUNT_POINT}"
  # 2 = setgid; 777 = rwx for all. (No sticky bit -> users can delete each other's files.)
  sudo chmod 2777 "${MOUNT_POINT}"
fi

# sudo fstrim -v /mnt/wsl/workspaces
# Import-Module Hyper-V
# Optimize-VHD -Path "$vhdxPath" -Mode Full
