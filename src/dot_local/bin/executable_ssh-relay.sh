# shellcheck disable=SC2148
if [ -f "$HOME/.ssh/agent.env" ]; then
  # shellcheck disable=SC1091
  source "$HOME/.ssh/agent.env"
  export SSH_AUTH_SOCK
fi
