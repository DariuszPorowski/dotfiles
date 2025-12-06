#!/bin/bash

set -eo pipefail

# This command executes upon wsl startup. It must be configured in the /etc/wsl.conf file on the distribution, like this:
#
# [boot]
# command="<path to script>/.wsl/startup.sh"

# Windows paths are not available in this script, so they are defined here.
WSL_EXE="/mnt/c/Windows/System32/wsl.exe"
CMD_EXE="/mnt/c/Windows/System32/cmd.exe"

# Provide the ability to source an .env file to override the default values and provide additional logic.
# NOTE: This sourced file must have LF line endings, not CRLF, or the mount command will fail.
if [[ -f "$(dirname "$0")/startup.env" ]]; then
  # shellcheck disable=SC1091
  source "$(dirname "$0")/startup.env"
fi

# Set WSL_WORKSPACES_VHDX_FILE to a default value if not already set in the .env file.
if [[ -z "${WSL_WORKSPACES_VHDX_FILE}" ]]; then
  # The windows path to the workspace vhdx file. Default is %userprofile%\.wsl\workspace.vhdx.
  WSL_WORKSPACES_VHDX_FILE=$($CMD_EXE /c "echo %userprofile%\.wsl\workspaces.vhdx")
  # Remove the trailing carriage return character from the Windows path.
  WSL_WORKSPACES_VHDX_FILE=$(echo "${WSL_WORKSPACES_VHDX_FILE}" | tr -d '\r')
fi

# Check on the Windows side if the vhdx file exists. If not, silently exit.
if ! $CMD_EXE /c "if exist ${WSL_WORKSPACES_VHDX_FILE} (exit 0) else (exit 1)"; then
  exit 0
fi

if [[ ! -d /mnt/wsl/workspaces ]]; then
  $WSL_EXE --mount --name workspaces --vhd "${WSL_WORKSPACES_VHDX_FILE}"
fi

if [[ -d /mnt/wsl/workspaces ]] && [[ ! -d /workspaces ]]; then
  ln -s /mnt/wsl/workspaces /workspaces
fi
