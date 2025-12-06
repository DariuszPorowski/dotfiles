#!/bin/bash

set -euo pipefail

# first check if /dev/sde exists and then do mkfs
if [[ -b /dev/sde ]]; then
  sudo mkfs.ext4 -m 0 -i 12000 -F -E "lazy_itable_init=1,lazy_journal_init=1,discard" -L workspaces /dev/sde
fi

# sudo fstrim -v /mnt/wsl/workspaces
# Import-Module Hyper-V
# Optimize-VHD -Path "$vhdxPath" -Mode Full
