############################################
# Import commonly used PowerShell modules
############################################

$modules = @(
    "Terminal-Icons",
    "PSReadLine",
    "Microsoft.WinGet.CommandNotFound"
)

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

############################################
# Quality of Life
############################################

function myip {
    curl ifconfig.me
}

############################################
# Initialize Tools
############################################

# Initialize Oh-My-Posh if installed
if (Get-Command oh-my-posh -ErrorAction SilentlyContinue) {
    $poshConfigPath = Join-Path "$env:USERPROFILE" '.oh-my-posh.json'
    if (Test-Path $poshConfigPath) {
        oh-my-posh init pwsh --config $poshConfigPath | Invoke-Expression
    }
    else {
        oh-my-posh init pwsh | Invoke-Expression
    }
}

# Initialize FNM if installed
if (Get-Command fnm -ErrorAction SilentlyContinue) {
    $fnmDir = 'X:\packages\fnm'
    if (Test-Path $fnmDir) {
        fnm env --fnm-dir=$fnmDir --shell powershell --use-on-cd --version-file-strategy=local | Out-String | Invoke-Expression
        fnm completions --fnm-dir=$fnmDir --shell powershell | Out-String | Invoke-Expression
    }
    else {
        fnm env --shell powershell --use-on-cd --version-file-strategy=local | Out-String | Invoke-Expression
        fnm completions --shell powershell | Out-String | Invoke-Expression
    }
}

# Initialize UV completion if installed
if (Get-Command uv -ErrorAction SilentlyContinue) {
    (& uv generate-shell-completion powershell) | Out-String | Invoke-Expression

    $uvPython = $(uv python find)
    if ($uvPython) {
        $uvPythonDir = Split-Path $uvPython
        $env:PATH = "$uvPythonDir;" + $env:PATH
    }
}

# Initialize UVX completion if installed
if (Get-Command uvx -ErrorAction SilentlyContinue) {
    (& uvx --generate-shell-completion powershell) | Out-String | Invoke-Expression
}

# Initialize Helm completion if installed
if (Get-Command helm -ErrorAction SilentlyContinue) {
    Invoke-Expression (helm completion powershell | Out-String)
}

# Initialize GitHub CLI completion if installed
if (Get-Command gh -ErrorAction SilentlyContinue) {
    Invoke-Expression (gh completion -s powershell | Out-String)
}
