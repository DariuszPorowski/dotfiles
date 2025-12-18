############################################
# Init
############################################

$psType = 'pwsh'
if ($PSVersionTable.PSEdition -eq 'Desktop') {
    $psType = 'powershell'
}

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

function printenv() {
    Get-ChildItem Env: | Sort-Object Name
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

# Initialize Aliae if installed
if (Get-Command aliae -ErrorAction SilentlyContinue) {
    aliae init "$psType" | Invoke-Expression
}

# Initialize Oh-My-Posh if installed
if (Get-Command oh-my-posh -ErrorAction SilentlyContinue) {
    $poshConfigPath = Join-Path "$env:USERPROFILE" '.oh-my-posh.json'
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

    $uvPython = $(uv python find)
    if ($uvPython) {
        $uvPythonDir = Split-Path $uvPython
        $env:PATH = "$uvPythonDir;" + $env:PATH
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
