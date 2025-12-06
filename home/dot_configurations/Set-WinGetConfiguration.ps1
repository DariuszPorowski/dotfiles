<#
.SYNOPSIS
Validates and applies the yaml winget configuration to a Windows machine.

.DESCRIPTION
This script validates the winget configuration using winget's built-in validation capability, it runs any manual
installers required because of gaps or bugs in winget or DSC packages, and it applies the yaml configuration.
Admin rights are required to run this script because the Visual Studio 2022 configuration command will fail without
admin access instead of initiating a UAC prompt.

.PARAMETER YamlConfigFilePath
File path to the yaml configuration file to be applied by winget.

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
    [switch]$Sudo = $false
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Check for WinGet
if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    Write-Error 'WinGet is not installed.'
}

if ($Sudo) {
    if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        $currentProcess = Get-Process -Id $PID
        $argumentList = "-File `"$($MyInvocation.MyCommand.Path)`" -YamlConfigFilePath `"$YamlConfigFilePath`""
        if ($ValidateFirst) { $argumentList += " -ValidateFirst" }
        if ($Sudo) { $argumentList += " -Sudo" }

        Start-Process -FilePath $currentProcess.Path -Verb RunAs -ArgumentList $argumentList -Wait
        Exit
    }
}

winget configure --enable

if ($ValidateFirst) {
    Write-Host 'Validating WinGet configuration...'
    winget configure validate --file "$YamlConfigFilePath" --disable-interactivity
}

Write-Host "Starting WinGet configuration from $YamlConfigFilePath..."
winget configure --file "$YamlConfigFilePath" --accept-configuration-agreements --ignore-warnings --disable-interactivity

Write-Host 'WinGet configuration complete. A reboot may be required to finish setting up some apps like WSL or Docker Desktop.'
