<#
.SYNOPSIS
Validates and applies the yaml winget configuration to a Windows machine.

.DESCRIPTION
Runs WinGet configuration in the calling terminal. Resources that need administrator rights can declare
securityContext: elevated in the manifest. WinGetPackage inventory runs as the signed-in user.

.PARAMETER YamlConfigFilePath
File path to the yaml configuration file to be applied by winget.

.PARAMETER WorkCatalogUri
Expected URI of the trusted azure-powershell repository used by work manifests.

.PARAMETER RequireStandardUser
Stop if the calling PowerShell is elevated, so user-scoped resources run as the signed-in user.

.PARAMETER TestNativeDsc
Test the native settings document with the stable DSC processor. Apply only if a resource differs.

.EXAMPLE
Set-WinGetConfiguration.ps1 -YamlConfigFilePath ".\configurations.winget"
#>

param (
    [Parameter(
        Mandatory = $true,
        HelpMessage = 'Path to the WinGet configuration file'
    )]
    [ValidateNotNullOrEmpty()]
    [string]$YamlConfigFilePath,
    [switch]$ValidateFirst = $false,
    [switch]$RequireStandardUser,
    [switch]$TestNativeDsc,
    [uri]$WorkCatalogUri
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ($RequireStandardUser -and
    ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'This WinGet configuration requires a non-elevated session. Open a normal PowerShell terminal and rerun chezmoi apply.'
}

if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    Write-Error 'WinGet is not installed.'
}

function Assert-WinGetSuccess([string]$Stage, [int]$Code) {
    if ($Code -ne 0) {
        $message = "WinGet {0} failed for '{1}': {2} (0x{2:X8})." -f $Stage, $YamlConfigFilePath, $Code
        if ($Stage -eq 'apply' -and $Code -eq -1978286075) {
            $message += " To see which units failed without reapplying, run 'winget configure list', then 'winget configure list --history <ID>' for this run. Check the nonzero results and their details."
        }
        throw $message
    }
}

function Test-OnlyPrivateCatalogWarning([object[]]$Lines) {
    # S_FALSE also covers missing resources. Accept only complete unit/advisory pairs, never the exit code alone.
    $advisory = 'The configuration unit is not available publicly; ensure that anyone who will use this configuration has access to it.'
    $header = '^[A-Za-z][A-Za-z0-9_.-]*(?:\uD83D\uDEE1\uFE0F?)?(?: +\[[A-Za-z0-9_.-]+\])?$'
    $expectAdvisory = $false
    $seen = $false
    foreach ($line in $Lines) {
        if ($line -isnot [string]) { return $false }
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        if ($expectAdvisory) {
            if ($line.Trim() -cne $advisory) { return $false }
            $seen = $true
        } elseif ($line.TrimEnd() -cnotmatch $header) {
            return $false
        }
        $expectAdvisory = -not $expectAdvisory
    }
    return $seen -and -not $expectAdvisory
}

# Handle native exit codes here even when the caller enabled PowerShell 7's native error preference.
$PSNativeCommandUseErrorActionPreference = $false
if ($WorkCatalogUri) {
    # Check the applying account's registration without changing it.
    $repo = Get-PSRepository -Name 'azure-powershell' -ErrorAction Stop
    if ($repo.InstallationPolicy -ne 'Trusted' -or
        ([string]$repo.SourceLocation).TrimEnd('/') -cne $WorkCatalogUri.AbsoluteUri.TrimEnd('/')) {
        throw "WinGet work configuration requires the trusted azure-powershell repository at $WorkCatalogUri."
    }
}
if ($TestNativeDsc) {
    # WinGet resolves this stable Store alias independently of PATH.
    $dsc = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'Microsoft\WindowsApps\Microsoft.DesiredStateConfiguration_8wekyb3d8bbwe\dsc.exe'
    if (-not (Test-Path -LiteralPath $dsc -PathType Leaf)) {
        throw 'Install stable Microsoft DSC (winget install --id 9NVTPZWRC6KQ --exact --source msstore) and retry.'
    }
    $version = & $dsc --version
    if ($LASTEXITCODE -ne 0 -or $version -notmatch '^dsc (\d+\.\d+\.\d+)$' -or [version]$Matches[1] -lt [version]'3.2.0') {
        throw "Windows setup requires stable DSC 3.2 or later; found '$version'. Update Microsoft DSC from the Store and retry."
    }
    Write-Host "Testing native DSC settings in '$YamlConfigFilePath'..."
    # Drift is expected before apply; a nonzero exit indicates a processor or resource error.
    $json = & $dsc config test --file $YamlConfigFilePath --output-format json
    if ($LASTEXITCODE -ne 0) { throw "DSC preflight failed for '$YamlConfigFilePath' (exit $LASTEXITCODE)." }
    $test = ConvertFrom-Json -InputObject ($json -join "`n")
    if ($test.hadErrors -isnot [bool] -or $test.hadErrors -or -not $test.results.Count) {
        throw "No successful DSC test results for '$YamlConfigFilePath'."
    }
    $states = foreach ($unit in $test.results) {
        if ($unit.result.inDesiredState -isnot [bool]) { throw "Invalid DSC test result for '$YamlConfigFilePath'." }
        $unit.result.inDesiredState
    }
    if ($states -notcontains $false) { return }
}

winget configure --enable
Assert-WinGetSuccess 'enable' $LASTEXITCODE

if ($ValidateFirst -and -not $TestNativeDsc) {
    Write-Host 'Validating WinGet configuration...'
    if ($WorkCatalogUri) {
        # WinGet writes UTF-8 unit headers (including the elevation shield), also under Windows PowerShell 5.1.
        $encoding = [Console]::OutputEncoding
        try {
            [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
            $lines = @()
            winget configure validate --file "$YamlConfigFilePath" --disable-interactivity --no-vt 2>&1 | Tee-Object -Variable lines
            $code = $LASTEXITCODE
        } finally {
            [Console]::OutputEncoding = $encoding
        }
        if ($code -eq 1 -and (Test-OnlyPrivateCatalogWarning $lines)) {
            Write-Warning 'Continuing: validation reported only the expected private catalog visibility advisory.'
        } else {
            Assert-WinGetSuccess 'validation' $code
        }
    } else {
        winget configure validate --file "$YamlConfigFilePath" --disable-interactivity
        Assert-WinGetSuccess 'validation' $LASTEXITCODE
    }
}

Write-Host "Starting WinGet configuration from $YamlConfigFilePath..."
winget configure --file "$YamlConfigFilePath" --accept-configuration-agreements --disable-interactivity
Assert-WinGetSuccess 'apply' $LASTEXITCODE

Write-Host 'WinGet configuration complete. A reboot may be required to finish setting up WSL.'
