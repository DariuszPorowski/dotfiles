#!/bin/bash
set -euo pipefail

export PATH="$HOME/.local/bin:$PATH"
export SSH_AUTH_SOCK="$HOME/.ssh/agent.sock"
if [[ -S "$SSH_AUTH_SOCK" ]] && SSH_AUTH_SOCK="$SSH_AUTH_SOCK" ssh-add -l >/dev/null 2>&1; then
  exit 0
fi
for dep in socat npiperelay; do
  if ! command -v "$dep" >/dev/null 2>&1; then
    echo "Cannot start WSL SSH relay: $dep is not installed." >&2
    exit 1
  fi
done
mkdir -p "$HOME/.ssh"
chmod 700 "$HOME/.ssh"
if [[ -e "$SSH_AUTH_SOCK" && ! -S "$SSH_AUTH_SOCK" ]]; then
  echo "Refusing to replace non-socket $SSH_AUTH_SOCK" >&2
  exit 1
fi
relay=(socat "UNIX-LISTEN:${SSH_AUTH_SOCK},fork,mode=0600" "EXEC:npiperelay -ei -s //./pipe/openssh-ssh-agent,nofork")
if ! pgrep --full --exact --uid="$UID" "${relay[*]}" >/dev/null; then
  rm -f -- "$SSH_AUTH_SOCK"
  umask 077
  setsid "${relay[@]}" </dev/null >/dev/null 2>"$HOME/.ssh/agent-relay.log" &
fi
for ((attempt = 0; attempt < 50; attempt++)); do
  [[ ! -S "$SSH_AUTH_SOCK" ]] || exit 0
  sleep 0.1
done
echo "WSL SSH relay did not create its socket; see ~/.ssh/agent-relay.log." >&2
exit 1
