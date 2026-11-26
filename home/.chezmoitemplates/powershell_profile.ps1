############################################
# Init
############################################

if ([Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT) {
    # VS Code can outlive a WinGet install. Keep its process PATH first and add missing user entries.
    & {
        $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
        if (-not $userPath) { return }
        $entries = @($env:Path -split ';' | Where-Object { $_ })
        foreach ($dir in ([Environment]::ExpandEnvironmentVariables($userPath) -split ';')) {
            if (-not [string]::IsNullOrWhiteSpace($dir) -and $dir -notin $entries) {
                $entries += $dir
            }
        }
        $env:Path = $entries -join ';'
    }
}

$psType = 'pwsh'
{{- if and (not .machine.windows) (not .machine.ephemeral) (eq (get .machine "profile") "work") }}
if (-not (Test-Path Env:COREPACK_NPM_REGISTRY)) {
    $env:COREPACK_NPM_REGISTRY = '{{ trimSuffix "/" .packageFeeds.node }}'
}
{{- end }}
if ($PSVersionTable.PSEdition -eq 'Desktop') {
    $psType = 'powershell'
}

############################################
# Import commonly used PowerShell modules
############################################

$modules = @(
    "Terminal-Icons",
    "PSReadLine"
)
if ($PSVersionTable.PSVersion -ge [version]'7.4' -and $IsWindows -and
    (Get-Command winget.exe -CommandType Application -ErrorAction SilentlyContinue)) {
    $modules += "Microsoft.WinGet.CommandNotFound"
}

foreach ($module in $modules) {
    if (Get-Module -ListAvailable -Name $module) {
        Import-Module $module
    }
}

############################################
# Unix-like command aliases for PowerShell
############################################

function unzip ($file) {
    Write-Output("Extracting", $file, "to", $pwd)
    $fullFile = Get-ChildItem -Path $pwd -Filter $file | ForEach-Object { $_.FullName }
    Expand-Archive -Path $fullFile -DestinationPath $pwd
}

function grep($regex, $dir) {
    if ($dir) {
        Get-ChildItem $dir | select-string $regex
        return
    }
    $input | select-string $regex
}

function sed($file, $find, $replace) {
    (Get-Content $file).replace("$find", $replace) | Set-Content $file
}

function which($name) {
    Get-Command $name | Select-Object -ExpandProperty Definition
}

function printenv() {
    Get-ChildItem Env: | Sort-Object Name
}

############################################
# Quality of Life
############################################

function myip {
    Invoke-RestMethod -Uri 'https://ifconfig.me/ip'
}

############################################
# Initialize Tools
############################################

# Initialize Aliae if installed
if (Get-Command aliae -ErrorAction SilentlyContinue) {
    aliae init "$psType" | Invoke-Expression
}
if ($podman = Get-Command podman -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1) {
    Set-Alias -Name docker -Value $podman.Source
    function docker-compose {
        if ($MyInvocation.ExpectingInput) { $input | docker compose @args }
        else { docker compose @args }
    }
}

# Initialize Oh-My-Posh if installed
if (Get-Command oh-my-posh -ErrorAction SilentlyContinue) {
    $poshConfigPath = Join-Path $HOME '.oh-my-posh.json'
    if (Test-Path $poshConfigPath) {
        oh-my-posh init "$psType" --config $poshConfigPath | Invoke-Expression
    }
    else {
        oh-my-posh init "$psType" | Invoke-Expression
    }
}

# Initialize mise if installed
if (Get-Command mise -ErrorAction SilentlyContinue) {
    (&mise activate pwsh) | Out-String | Invoke-Expression
}

# Initialize FNM if installed
if (Get-Command fnm -ErrorAction SilentlyContinue) {
    fnm env --shell powershell --use-on-cd --version-file-strategy=recursive | Out-String | Invoke-Expression
    fnm completions --shell powershell | Out-String | Invoke-Expression
}

# Initialize Chezmoi completion if installed
if (Get-Command chezmoi -ErrorAction SilentlyContinue) {
    chezmoi completion powershell | Out-String | Invoke-Expression
}

# Initialize UV completion if installed
if (Get-Command uv -ErrorAction SilentlyContinue) {
    uv generate-shell-completion powershell | Out-String | Invoke-Expression

    $uvPython = uv python find --no-python-downloads 2>$null
    if ($LASTEXITCODE -eq 0 -and $uvPython) {
        $uvPythonDir = Split-Path $uvPython
        $separator = [IO.Path]::PathSeparator
        if ($uvPythonDir -notin ($env:PATH -split [regex]::Escape($separator))) {
            $env:PATH = "$uvPythonDir$separator$env:PATH"
        }
    }
}

# Initialize UVX completion if installed
if (Get-Command uvx -ErrorAction SilentlyContinue) {
    uvx --generate-shell-completion powershell | Out-String | Invoke-Expression
}

# Initialize Helm completion if installed
if (Get-Command helm -ErrorAction SilentlyContinue) {
    helm completion powershell | Out-String | Invoke-Expression
}

# Initialize GitHub CLI completion if installed
if (Get-Command gh -ErrorAction SilentlyContinue) {
    gh completion --shell powershell | Out-String | Invoke-Expression
}
