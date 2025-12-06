#!/bin/bash

# This script is used to start the npiperelay.exe process which forwards the ssh-agent socket to the Windows side

# Only print messages when running in an interactive terminal
_log() {
  [[ -t 1 ]] && echo "$@"
}

# Set the socket location for SSH agent forwarding
export SSH_AUTH_SOCK="$HOME/.ssh/agent.sock"

# Create the necessary directory if it doesn't exist
mkdir -p "$(dirname "$SSH_AUTH_SOCK")"

# Write the SSH_AUTH_SOCK value to a file
echo "SSH_AUTH_SOCK=$SSH_AUTH_SOCK" >"$HOME/.ssh/agent.env"

# Define the piperelay command as an array
piperelay=(socat "UNIX-LISTEN:${SSH_AUTH_SOCK},fork" "EXEC:npiperelay -ei -s //./pipe/openssh-ssh-agent,nofork")

# Check if the SSH agent forwarding process is already running
if ! pgrep --full --exact --uid="${UID}" "${piperelay[*]}" >/dev/null; then
  # Remove existing socket if it exists
  rm -f "$SSH_AUTH_SOCK"

  _log "Starting SSH-Agent relay..."
  # Start the SSH-Agent relay in the background with a new session
  setsid "${piperelay[@]}" >/dev/null 2>&1 &
else
  _log "SSH-Agent relay is already running."
fi
