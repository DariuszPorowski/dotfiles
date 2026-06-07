<#
.SYNOPSIS
    Creates a dynamically expanding VHDX file used as a shared WSL workspaces disk.

.DESCRIPTION
    Provisions a 100 GB dynamic VHDX at the location defined by the
    WSL_WORKSPACES_VHDX_FILE environment variable (set via startup.env), or at
    the default path %USERPROFILE%\.wsl\workspaces.vhdx when not set.

    The script self-elevates to Administrator because New-VHD requires the
    Hyper-V module and elevated privileges. If a VHDX already exists at the
    target path, the script asks for confirmation before overwriting it so an
    existing disk is never replaced unintentionally.

.EXAMPLE
    .\New-VHDX.ps1
    Creates the VHDX at the default (or configured) path, prompting first if a
    file already exists.

.NOTES
    Set WSL_WORKSPACES_VHDX_FILE in startup.env to override the output path.
#>

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

# If the file already exists, confirm before overwriting so an existing disk is
# never replaced unintentionally.
if (Test-Path -LiteralPath $WSL_WORKSPACES_VHDX_FILE) {
    Write-Warning "A VHDX file already exists at $WSL_WORKSPACES_VHDX_FILE."
    $response = Read-Host 'Overwrite it? This permanently deletes the existing file. [y/N]'
    if ($response -notmatch '^[Yy]') {
        Write-Host 'Keeping the existing VHDX file. No changes made.'
        Exit
    }
    Write-Host "Removing existing VHDX file at $WSL_WORKSPACES_VHDX_FILE..."
    Remove-Item -LiteralPath $WSL_WORKSPACES_VHDX_FILE -Force
}

Write-Host "Creating new VHDX file at $WSL_WORKSPACES_VHDX_FILE..."
New-VHD -Path "$WSL_WORKSPACES_VHDX_FILE" -Dynamic -SizeBytes 100GB
