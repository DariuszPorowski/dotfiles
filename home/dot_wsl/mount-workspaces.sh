#!/bin/sh
set -eu
. "$(dirname "$0")/workspace-volume.sh"
workspace_alias=/workspaces

usage() {
  printf '%s\n' \
    'First use: mount-workspaces.sh --attach-bare <absolute Windows VHDX path>' \
    'Compare lsblk before/after bare attachment. Independently confirm the new, empty whole disk.' \
    'Operator only: prepare whole-disk ext4 labeled workspaces and record its unique filesystem UUID.' \
    'Detach that exact host file with wsl.exe --unmount <Windows path> before the named mount.' \
    'Mount: mount-workspaces.sh <recorded UUID> [absolute Windows VHDX path]' \
    'Then run vhdx-init.sh <recorded UUID> as the intended owner. No helper formats a disk.'
}
case ${1:-} in
  -h|--help) usage; exit 0 ;;
  --attach-bare) [ "$#" -eq 2 ] || { usage >&2; exit 2; }; disk=$2 ;;
  *) [ "$#" -ge 1 ] && [ "$#" -le 2 ] || { usage >&2; exit 2; }
     require_uuid "$1"
     disk=${2-${WSL_WORKSPACES_VHDX_FILE:-}}
     if [ -z "$disk" ]; then
       profile=$(cd /mnt/c && cmd.exe /d /c 'echo %USERPROFILE%')
       disk="$(printf '%s' "$profile" | tr -d '\r')\\.wsl\\workspaces.vhdx"
     fi ;;
esac
case $disk in [A-Za-z]:\\*|\\\\*) ;; *) die 'Expected an absolute Windows VHDX path.' ;; esac
if [ "$1" = --attach-bare ]; then
  wsl.exe --mount --vhd "$disk" --bare
  usage
  exit 0
fi

if ! mountpoint -q "$mount_point"; then
  wsl.exe --mount --vhd "$disk" --name workspaces
fi
verify_workspace "$1"
if [ -L "$workspace_alias" ] && [ "$(readlink -f -- "$workspace_alias")" = "$mount_point" ]; then
  exit 0
fi
if [ -e "$workspace_alias" ] || [ -L "$workspace_alias" ]; then
  die "Existing $workspace_alias does not point to $mount_point; it was not changed."
fi
# -T prevents creating a link *inside* a concurrently created directory.
sudo ln -sT -- "$mount_point" "$workspace_alias"
