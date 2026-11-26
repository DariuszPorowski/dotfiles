[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$Path = $(if ($env:WSL_WORKSPACES_VHDX_FILE) { $env:WSL_WORKSPACES_VHDX_FILE } else { Join-Path $HOME '.wsl\workspaces.vhdx' })
)

$ErrorActionPreference = 'Stop'
$Path = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Path)
if (Test-Path -LiteralPath $Path) { throw "Refusing to overwrite existing disk: $Path" }
if (-not $PSCmdlet.ShouldProcess($Path, 'Create a blank 100 GB dynamic workspace VHDX')) { return }
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    $currentProcess = Get-Process -Id $PID
    $child = Start-Process -FilePath $currentProcess.Path -Verb RunAs -ArgumentList "-NoProfile -File `"$PSCommandPath`" -Path `"$Path`"" -Wait -PassThru
    exit $child.ExitCode
}
New-VHD -Path $Path -Dynamic -SizeBytes 100GB
Write-Host 'Blank disk created. Use mount-workspaces.sh --attach-bare with this path for manual first-use preparation.'
