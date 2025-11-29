#{{ if .machine.windows }}
$packages = @(
    "JanDeDobbeleer.OhMyPosh"
    "JanDeDobbeleer.Aliae"
    "eza-community.eza"
    "BurntSushi.ripgrep.MSVC"
    "sharkdp.bat"
    "sxyazi.yazi"
)

foreach ($package in $packages) {
    winget install --id $package --exact --accept-source-agreements --accept-package-agreements --disable-interactivity
}
#{{ end -}}
