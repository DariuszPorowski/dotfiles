if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    $currentProcess = Get-Process -Id $PID
    $argumentList = "-File `"$($MyInvocation.MyCommand.Path)`" $($MyInvocation.UnboundArguments)"
    Start-Process -FilePath $currentProcess.Path -Verb RunAs -ArgumentList $argumentList -Wait
    Exit
}

Write-Host 'APPLYING WINGET CONFIGURATION'

$scriptPath = Join-Path $env:USERPROFILE '.configurations' 'Set-WinGetConfiguration.ps1'
$config = Join-Path $env:USERPROFILE '.configurations' 'os.dsc.yaml'
& $scriptPath -YamlConfigFilePath "$config" -ValidateFirst

$config = Join-Path $env:USERPROFILE '.configurations' 'core-pkgs.dsc.yaml'
& $scriptPath -YamlConfigFilePath "$config" -ValidateFirst
