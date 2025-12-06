# Self-elevate the script if required
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    $currentProcess = Get-Process -Id $PID
    $argumentList = "-File `"$($MyInvocation.MyCommand.Path)`" $($MyInvocation.UnboundArguments)"
    Start-Process -FilePath $currentProcess.Path -Verb RunAs -ArgumentList $argumentList -Wait
    Exit
}

if (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'startup.env')) {
    . (Join-Path $PSScriptRoot 'startup.env')
}

# Set WSL_WORKSPACES_VHDX_FILE to a default value if not already set in the .env file.
if (-not $env:WSL_WORKSPACES_VHDX_FILE) {
    # The windows path to the workspace vhdx file. Default is $env:USERPROFILE\.wsl\workspaces.vhdx.
    $WSL_WORKSPACES_VHDX_FILE = Join-Path "$env:USERPROFILE" '.wsl' 'workspaces.vhdx'
}

# if file does not exist
if (-not (Test-Path -LiteralPath $WSL_WORKSPACES_VHDX_FILE)) {
    Write-Host "Creating new VHDX file at $WSL_WORKSPACES_VHDX_FILE..."
    $vhdx = New-VHD -Path "$WSL_WORKSPACES_VHDX_FILE" -Dynamic -SizeBytes 100GB
}
