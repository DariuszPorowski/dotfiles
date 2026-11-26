#!/bin/sh
set -eu
. "$(dirname "$0")/workspace-volume.sh"

[ "$#" -eq 1 ] || die 'Usage: vhdx-init.sh <recorded filesystem UUID>'
require_uuid "$1"
owner=${SUDO_USER:-$(id -un)}
if [ "$owner" = root ]; then
  echo "Run as the intended workspace owner, not from a root login." >&2
  exit 1
fi
verify_workspace "$1"
sudo chown "$owner:$(id -gn "$owner")" "$mount_point"
sudo chmod 2770 "$mount_point"
