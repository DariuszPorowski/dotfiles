#!/bin/sh
# Existing guests can still invoke this Windows-side filename as root at boot.
printf '%s\n' 'Remove the old startup.sh command from /etc/wsl.conf. Use mount-workspaces.sh manually; nothing was mounted.' >&2
