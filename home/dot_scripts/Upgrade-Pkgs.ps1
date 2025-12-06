if (Get-Command winget -ErrorAction SilentlyContinue) {
    Write-Host 'UPDATING WINGET MACHINE PACKAGES'
    sudo winget upgrade --all --accept-package-agreements --accept-source-agreements --disable-interactivity --scope=machine

    Write-Host 'UPDATING WINGET USER PACKAGES'
    winget upgrade --all --accept-package-agreements --accept-source-agreements --disable-interactivity --scope=user
}

if (Get-Command uv -ErrorAction SilentlyContinue) {
    Write-Host 'UPDATING UV USER PACKAGES'
    uv tool upgrade --all
}

if (Get-Command scoop -ErrorAction SilentlyContinue) {
    Write-Host 'UPDATING SCOOP GLOBAL PACKAGES'
    sudo scoop update --all --global

    Write-Host 'UPDATING SCOOP USER PACKAGES'
    scoop update --all
}

if (Get-Command npm -ErrorAction SilentlyContinue) {
    Write-Host 'UPDATING NPM GLOBAL PACKAGES'
    sudo npm update --global

    Write-Host 'UPDATING NPM USER PACKAGES'
    npm update
}

if (Get-Command pnpm -ErrorAction SilentlyContinue) {
    Write-Host 'UPDATING PNPM GLOBAL PACKAGES'
    sudo pnpm update --global
}
