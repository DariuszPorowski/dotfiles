# shellcheck disable=SC2148
if [ -f "$HOME/.ssh/agent.env" ]; then
  # shellcheck disable=SC1091
  . "$HOME/.ssh/agent.env"
  if [ -n "$SSH_AUTH_SOCK" ]; then
    export SSH_AUTH_SOCK
  fi
fi
