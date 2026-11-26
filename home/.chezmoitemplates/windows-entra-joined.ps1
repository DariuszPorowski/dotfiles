$dsreg = Join-Path ([Environment]::SystemDirectory) 'dsregcmd.exe'
if (Test-Path -LiteralPath $dsreg -PathType Leaf) {
    # Return only the device join flag, not tenant, device or user identifiers.
    $field = @(& $dsreg /status 2>$null | Select-String '^\s*AzureAdJoined\s*:\s*(YES|NO)\s*$')
    if ($LASTEXITCODE -eq 0 -and $field.Count -eq 1) {
        return $field[0].Matches[0].Groups[1].Value.ToUpperInvariant()
    }
}
'UNKNOWN'
