# Sourced only by the manually invoked guest helpers.
mount_point=/mnt/wsl/workspaces

die() { printf '%s\n' "$*" >&2; exit 1; }

require_uuid() {
  case $1 in ''|*[!0-9a-f-]*) die 'Expected the independently recorded lowercase filesystem UUID.' ;; esac
  printf '%s\n' "$1" | grep -Eq '^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$' ||
    die 'Expected the independently recorded filesystem UUID.'
}

verify_workspace() {
  # FSROOT also rejects a bind of a subdirectory of the expected filesystem.
  actual=$(sudo findmnt -rn -M "$mount_point" -o FSTYPE,LABEL,UUID,FSROOT) ||
    die "Cannot identify the mount at $mount_point. No link or permissions changed."
  [ "$actual" = "ext4 workspaces $1 /" ] ||
    die "Mount conflict: expected the root of ext4 workspaces UUID $1 at $mount_point. Nothing was detached."
}
