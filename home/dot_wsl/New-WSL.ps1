<#
.SYNOPSIS
    Creates a new Ubuntu 26.04 LTS WSL instance with cloud-init.

.DESCRIPTION
    This script creates a new Ubuntu 26.04 LTS WSL instance by:
    - Downloading the checksum-pinned WSL image for the Windows OS architecture (if not already cached)
    - Configuring cloud-init with custom user data
    - Installing the instance to a specified location
    - Launching the instance for initial setup

.PARAMETER Name
    The name for the new WSL instance. This will be used as both the instance name
    and hostname in the WSL instance. Prefer a name such as ubuntu-dev: cloud-init
    also treats ubuntu-26.04.user-data and ubuntu-all.user-data as fallback files
    for other Ubuntu instances without their own user-data.

.PARAMETER Username
    Username for the new WSL user.
    Default: The Windows username to create a matching user in the WSL instance.

.PARAMETER GUI
    Provision a GUI-enabled instance. Installs a full XFCE desktop served over
    XRDP (connect via Remote Desktop to localhost:<Port>) in addition to the
    out-of-the-box WSLg support for individual Linux GUI apps.

.PARAMETER Port
    The TCP port XRDP listens on for the GUI instance. Defaults to 3390. Use a
    different port to avoid clashing with the Windows Remote Desktop service.
    Only used together with -GUI.

.PARAMETER Sparse
    Explicitly enable experimental sparse VHD support for this instance. Without
    this switch, WSL uses its global sparseVhd setting for new disks.

.PARAMETER VerifyOnly
    Launch the named instance if stopped and check its first-boot result and
    provisioned login/tools without reinstalling or replaying cloud-init.

.EXAMPLE
    .\New-WSL.ps1 -Name "ubuntu-dev"
    Creates a new WSL instance named "ubuntu-dev"

.EXAMPLE
    .\New-WSL.ps1 -Name "ubuntu-gui" -GUI
    Creates a new GUI-enabled WSL instance with an XFCE desktop over XRDP on the
    default port 3390

.EXAMPLE
    .\New-WSL.ps1 -Name "ubuntu-gui" -GUI -Port 3390
    Creates a new GUI-enabled WSL instance with XRDP listening on port 3390

.EXAMPLE
    .\New-WSL.ps1 -Name "general-dev" -VerifyOnly
    Checks the existing instance, including after Ubuntu disables cloud-init at the end of first boot.

.NOTES
    Requires x64 or ARM64 Windows, Virtual Machine Platform, a working hypervisor,
    and WSL 2 with --from-file support. If the host feature is missing, run
    wsl.exe --install --no-distribution as administrator and restart Windows.
    Run this script as the Windows user who should own the distro. On ARM64,
    PowerShell uses Canonical's stable classic snap and needs Snap Store access;
    on x64 it uses Microsoft's apt repository. Provisions new instances only.
    Leave WSL interop and Windows drive automount enabled so
    the WSL datasource can read %USERPROFILE%\.cloud-init\<Name>.user-data.
    Windows dotfiles setup preconfigures the current user's Ubuntu Insights
    opt-out, so new Ubuntu instances need not prompt for metrics consent.
    Ubuntu Pro agent policy, if present, can override individual cloud-init modules.
    Cloud-init documentation:
    - https://github.com/canonical/cloud-init/blob/main/doc/rtd/reference/datasources/wsl.rst#user-data-configuration
    - https://ubuntu.com/wsl/docs/stable/howto/cloud-init/
#>

param(
    [Parameter(Mandatory = $true)]
    [ValidateLength(1, 63)]
    [ValidatePattern('\A[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?)*\z')]
    [string]$Name,

    [Parameter(Mandatory = $false)]
    [ValidateNotNullOrEmpty()]
    [string]$Username = $env:USERNAME.ToLowerInvariant(),

    [Parameter(Mandatory = $false)]
    [switch]$GUI,

    [Parameter(Mandatory = $false)]
    [ValidateRange(1, 65535)]
    [int]$Port = 3390,

    [Parameter(Mandatory = $false)]
    [switch]$Sparse,

    [switch]$VerifyOnly
)

# Set strict error handling
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ($Name -match '^(?:CON|PRN|AUX|NUL|COM[0-9]|LPT[0-9])(?:\.|$)' -or $Name -eq 'default') {
    throw 'Choose a per-instance name that is not a reserved Windows or cloud-init filename.'
}
if ($Username -cnotmatch '^[a-z_][a-z0-9_-]{0,31}\z' -or $Username -eq 'root') {
    throw 'Supply -Username with a non-root Linux login name.'
}

#region Helpers

function Write-LogInfo {
    param (
        [Parameter(Mandatory = $true)]
        [string]$Message
    )
    Write-Host "$Message" -ForegroundColor Cyan
}

function Write-LogWarning {
    param (
        [Parameter(Mandatory = $true)]
        [string]$Message
    )
    Write-Host "$Message" -ForegroundColor Yellow
}

function Write-LogOK {
    param (
        [Parameter(Mandatory = $true)]
        [string]$Message
    )
    Write-Host "$Message" -ForegroundColor Green
}

function Read-CloudInitRecord([string]$Path) {
    $json = wsl.exe --distribution "$Name" --user root -- cat $Path
    if ($LASTEXITCODE -ne 0) { throw "Cannot verify first boot: $Path is missing or unreadable in '$Name'." }
    (ConvertFrom-Json -InputObject ($json -join "`n")).v1
}

function Assert-CloudInitProvisioned {
    $PSNativeCommandUseErrorActionPreference = $false
    $hint = "Run 'wsl -d $Name -u root -- cloud-init status --long'. For the saved run, inspect /var/lib/cloud/data/status.json and /var/log/cloud-init-output.log."
    $json = wsl.exe --distribution "$Name" --user root -- cloud-init status --wait --format=json
    $code = $LASTEXITCODE
    if ($code -notin 0, 2) { throw "cloud-init status failed (exit $code). $hint" }
    $status = ConvertFrom-Json -InputObject ($json -join "`n")
    $afterOobe = $status.status -ceq 'disabled' -and $status.boot_status_code -ceq 'disabled-by-marker-file'
    if (-not ($afterOobe -or $status.status -ceq 'done') -or
        ($status.datasource -cne 'wsl' -and -not ($afterOobe -and $status.datasource -ceq ''))) {
        throw "cloud-init did not complete with the WSL datasource. $hint"
    }

    # Ubuntu's OOBE writes cloud-init.disabled even after a failed run. result.json
    # is written at the end of modules-final; status.json retains per-stage warnings across boots.
    $result = Read-CloudInitRecord '/var/lib/cloud/data/result.json'
    if ($result.datasource -cne 'DataSourceWSL' -or $result.errors -isnot [array] -or $result.errors.Count) {
        throw "No successful WSL final-stage result for '$Name'. $hint"
    }
    $records = @($status)
    if ($afterOobe) {
        $saved = Read-CloudInitRecord '/var/lib/cloud/data/status.json'
        if ($saved.datasource -cne 'DataSourceWSL' -or -not ([double]$saved.'modules-final'.finished -gt 0)) {
            throw "Missing completed WSL final stage for '$Name'. $hint"
        }
        foreach ($stage in 'init-local', 'init', 'modules-config', 'modules-final') { $records += $saved.$stage }
    }

    $unit = 'systemd-networkd-wait-online.service'
    $maskedWait = "Failed to wait for network: Unexpected error while running command. Command: ['systemctl', 'start', '$unit'] Exit code: 1 Reason: - Stdout: Stderr: Failed to start ${unit}: Unit $unit is masked."
    $sawMaskedWait = $false
    foreach ($record in $records) {
        if ($record.errors -isnot [array] -or $record.errors.Count -or $null -eq $record.recoverable_errors) {
            throw "cloud-init recorded an error or incomplete status in '$Name'. $hint"
        }
        foreach ($group in $record.recoverable_errors.PSObject.Properties) {
            if ($group.Name -cne 'ERROR' -or $group.Value -isnot [array] -or -not $group.Value.Count) {
                throw "Unexpected cloud-init diagnostics in '$Name'. $hint"
            }
            foreach ($message in $group.Value) {
                if (($message -replace '\s+', ' ').Trim() -cne $maskedWait) {
                    throw "Unexpected recoverable cloud-init error in '$Name'. $hint"
                }
                $sawMaskedWait = $true
            }
        }
    }
    if ($code -eq 2 -and -not $sawMaskedWait) { throw "Unexplained degraded cloud-init result. $hint" }

    wsl.exe --distribution "$Name" --user "$Username" -- sh -c 'command -v task >/dev/null && { command -v pwsh >/dev/null || test -x /snap/bin/pwsh; }'
    if ($LASTEXITCODE -ne 0) { throw "Could not verify user '$Username', Task and PowerShell in '$Name'. $hint" }
    if ($sawMaskedWait) { Write-Warning "WSL's network wait unit was masked; the final stage and provisioned tools were verified." }
}

#endregion

if ($VerifyOnly) {
    Assert-CloudInitProvisioned
    Write-LogOK "First boot verified for '$Name'."
    return
}

#region Path Configuration
# Template file containing cloud-init configuration with placeholders.
# The -GUI switch selects an independent, GUI-enabled config (XFCE + XRDP).
$cloudInitTmplName = if ($GUI) { 'Ubuntu-26.04-gui.user-data' } else { 'Ubuntu-26.04.user-data' }
$cloudInitConfigTmpl = Join-Path $PSScriptRoot "cloud-init\$cloudInitTmplName"

# Installation directory for this specific WSL instance
$installPath = Join-Path $env:LOCALAPPDATA "WSL\$Name"

# Shared directory for cached WSL images to avoid re-downloading
$imagesPath = Join-Path $env:LOCALAPPDATA 'WSL\.images'

# User's cloud-init configuration directory
$cloudInitDirPath = Join-Path $env:USERPROFILE '.cloud-init'

# Each SHA256SUMS is signed by Canonical in the corresponding release directory.
$release = '26.04.1'
$hostArch = [Runtime.InteropServices.RuntimeInformation]::OSArchitecture
switch ($hostArch) {
    'X64' {
        $imageArch = 'amd64'
        $releaseUrl = "https://releases.ubuntu.com/$release"
        $imageSha256 = '48d56724b5c8e60f24893e83e73bbb58c60b3ca22fba3da977075420acd54104'
    }
    'Arm64' {
        $imageArch = 'arm64'
        $releaseUrl = "https://cdimage.ubuntu.com/ubuntu/releases/$release/release"
        $imageSha256 = 'c7d893d7ccb291009e6096c5a946937337b6fd4c426f11b6541f6cd2bf894f7d'
    }
    default { throw "Unsupported Windows OS architecture: $hostArch. This WSL profile supports x64 and ARM64." }
}
$imageName = "ubuntu-$release-wsl-$imageArch.wsl"
$downloadUrl = "$releaseUrl/$imageName"
$imageFile = Join-Path $imagesPath $imageName
#endregion

#region Prerequisites Validation
Write-Verbose "Checking prerequisites..."

if (-not (Test-Path -LiteralPath $cloudInitConfigTmpl -PathType Leaf)) {
    throw "Cloud-init template not found at: $cloudInitConfigTmpl"
}
$landscapeConfig = Join-Path $env:USERPROFILE ".ubuntupro\.cloud-init\$Name.user-data"
if (Test-Path -LiteralPath $landscapeConfig -PathType Leaf) {
    throw "Landscape user-data takes precedence over this profile: $landscapeConfig. Choose a different instance name or provision through Landscape."
}
wsl.exe --status
if ($LASTEXITCODE -ne 0) {
    throw "WSL is not installed or not available. Please install WSL first."
}
$existingDistros = wsl.exe --list --quiet | ForEach-Object { $_.Replace("`0", '').Trim() }
if ($LASTEXITCODE -ne 0) { throw 'Unable to list WSL distributions.' }
if ($existingDistros -contains $Name) {
    throw "A WSL instance named '$Name' is already registered. Inspect it with 'wsl.exe --list --verbose'; it was not changed."
}
if (Test-Path -LiteralPath $installPath) {
    throw "The name '$Name' is not registered, but the installation path already exists: $installPath. Inspect it before retrying or choose another name. Nothing was removed."
}

# --status can report a default of 2 even when Windows cannot start a WSL 2 VM.
try {
    $feature = Get-CimInstance -ClassName Win32_OptionalFeature -Filter "Name='VirtualMachinePlatform'" -Property InstallState
    if ($feature -and $feature.InstallState -in 2, 3) {
        throw "Virtual Machine Platform is disabled or absent. Run 'wsl.exe --install --no-distribution' in an elevated PowerShell, restart Windows, then retry as your normal user."
    }
    $system = Get-CimInstance -ClassName Win32_ComputerSystem -Property HypervisorPresent
    if ($system -and $system.HypervisorPresent -is [bool] -and -not $system.HypervisorPresent) {
        throw "Windows reports no running hypervisor. Restart Windows if Virtual Machine Platform was just enabled. Otherwise check firmware virtualization and the hypervisor boot setting; a VM host must support and expose nested virtualization."
    }
}
catch [Microsoft.Management.Infrastructure.CimException] {
    Write-Warning "Could not query Windows virtualization prerequisites: $_. Continuing with WSL's own checks."
}
#endregion

[void][IO.Directory]::CreateDirectory($cloudInitDirPath)
[void][IO.Directory]::CreateDirectory($imagesPath)

#region Image Download
# Keep the lock filename stable. Closing the handle releases it even after a failed download.
try {
    $lock = [IO.File]::Open("$imageFile.lock", 'OpenOrCreate', 'ReadWrite', 'None')
}
catch [IO.IOException] {
    throw "Cannot lock the image cache. If another installer is downloading, retry after it finishes: $_"
}
try {
    if ([IO.File]::Exists($imageFile) -and (Get-FileHash -LiteralPath $imageFile -Algorithm SHA256).Hash -ne $imageSha256) {
        $quarantine = "$imageFile.$([guid]::NewGuid()).invalid"
        [IO.File]::Move($imageFile, $quarantine)
        Write-Warning "Moved the invalid cached image to $quarantine."
    }
    if (-not [IO.File]::Exists($imageFile)) {
        $partial = "$imageFile.$([guid]::NewGuid()).part"
        try {
            Write-LogInfo "Downloading Ubuntu $release LTS WSL image from $downloadUrl..."
            Invoke-WebRequest -Uri $downloadUrl -OutFile $partial -UseBasicParsing
            if ((Get-FileHash -LiteralPath $partial -Algorithm SHA256).Hash -ne $imageSha256) {
                throw 'Downloaded Ubuntu image checksum mismatch. No image was cached or installed.'
            }
            [IO.File]::Move($partial, $imageFile)
        }
        finally { [IO.File]::Delete($partial) }
    }
}
finally { $lock.Dispose() }
#endregion

#region Cloud-Init Configuration
Write-Verbose "Preparing cloud-init configuration..."

try {
    $cloudInitConfig = [IO.File]::ReadAllText($cloudInitConfigTmpl)
    $cloudInitConfig = $cloudInitConfig.Replace('__USERNAME__', $Username)
    $cloudInitConfig = $cloudInitConfig.Replace('__HOSTNAME__', $Name)
    $cloudInitConfig = $cloudInitConfig.Replace('__RDP_PORT__', [string]$Port)
}
catch {
    throw "Failed to process cloud-init template: $_"
}

# Publish complete bytes without replacement. Only an identical file is safe to reuse on retry.
$cloudInitConfigFile = Join-Path $cloudInitDirPath "$Name.user-data"
$pending = "$cloudInitConfigFile.$([guid]::NewGuid()).part"
try {
    [IO.File]::WriteAllText($pending, $cloudInitConfig)
    try { [IO.File]::Move($pending, $cloudInitConfigFile) }
    catch [IO.IOException] {
        if (-not [IO.File]::Exists($cloudInitConfigFile)) { throw }
        if ((Get-FileHash -LiteralPath $pending).Hash -ne (Get-FileHash -LiteralPath $cloudInitConfigFile).Hash) {
            throw "Conflicting cloud-init configuration: $cloudInitConfigFile. Nothing was replaced."
        }
        Write-Verbose "Reusing matching cloud-init configuration at $cloudInitConfigFile"
    }
}
finally { [IO.File]::Delete($pending) }
#endregion

#region Instance Installation
Write-LogInfo "Installing WSL instance '$Name'..."

try {
    wsl.exe --install --from-file "$imageFile" --name "$Name" --location "$installPath" --version 2 --no-launch
    if ($LASTEXITCODE -ne 0) {
        throw "WSL installation failed with exit code: $LASTEXITCODE"
    }
    Write-LogOK "Instance installed successfully."
}
catch {
    throw "Failed to install WSL instance: $_"
}
#endregion

#region Sparse VHD
if ($Sparse) {
    Write-LogInfo "Enabling sparse VHD support for '$Name' (unsafe)..."
    Write-LogWarning "Sparse VHD support is experimental and can risk data corruption."
    try {
        wsl.exe --terminate "$Name"
        if ($LASTEXITCODE -ne 0) { throw "wsl --terminate returned $LASTEXITCODE" }
        wsl.exe --manage "$Name" --set-sparse true --allow-unsafe
        if ($LASTEXITCODE -ne 0) { throw "wsl --manage --set-sparse returned $LASTEXITCODE" }
        Write-LogOK "Sparse VHD enabled for '$Name'."
    }
    catch {
        Write-Warning "Could not enable sparse VHD for '$Name': $_. Continuing first boot; do not reinstall."
    }
}
#endregion

#region Initial Launch
Write-LogInfo "Launching WSL instance '$Name' for initial setup..."
Write-LogWarning "Cloud-init will configure the system on first boot. This may take a few minutes."

Assert-CloudInitProvisioned
Write-LogOK "WSL instance '$Name' has been successfully created and configured!"
Write-LogInfo "You can access it anytime using: wsl -d $Name"
if ($GUI) {
    Write-LogInfo "Set an XRDP password: wsl -d $Name -u root -- passwd $Username"
}
#endregion
