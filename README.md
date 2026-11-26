---
title: Dotfiles
description: Personal Windows, WSL and Linux dotfiles managed with chezmoi.
---

## Setup

Use [chezmoi](https://www.chezmoi.io/) 2.74.2 or newer. On Windows, use WinGet
1.11+ and run chezmoi from a **non-elevated** PowerShell 7 terminal. Setup
installs stable Microsoft DSC 3.2+ from the Store; approve UAC for machine settings.

```powershell
winget install --id Microsoft.PowerShell --exact
winget install --id twpayne.chezmoi --exact
```

### Restore the age key

Before `chezmoi init`, restore the **existing** key from 1Password (`op://personal/age/key`).
A new key cannot decrypt these dotfiles. Skip this step in dev containers or if the key
is already in place. Keep `personal.age` outside the repo and cloud-synced folders.

On **Windows (PowerShell 7)**, create a private file before writing the key:

```powershell
$key = Join-Path $HOME 'personal.age'
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
New-Item -ItemType File -Path $key -ErrorAction Stop | Out-Null &&
    icacls.exe $key /inheritance:r /grant:r "*${sid}:(F)" &&
    op read 'op://personal/age/key' | Set-Content -LiteralPath $key -Encoding utf8NoBOM
```

If `op` is unavailable:

```powershell
$key = Join-Path $HOME 'personal.age'
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
New-Item -ItemType File -Path $key -ErrorAction Stop | Out-Null &&
    icacls.exe $key /inheritance:r /grant:r "*${sid}:(F)" &&
    Read-Host -MaskInput 'Paste the age secret key line' | Set-Content -LiteralPath $key -Encoding utf8NoBOM
```

On **Linux (including WSL) or macOS**, use the signed-in 1Password CLI:

```sh
op read --file-mode 0600 --out-file "$HOME/personal.age" 'op://personal/age/key'
```

Without `op`, run the following in Bash or Zsh, paste the key, then press Enter and Ctrl+D:

```sh
(umask 077; set -C; trap 'stty echo' EXIT; stty -echo && cat > "$HOME/personal.age")
```

### Initialize

At `chezmoi init`, `auto` selects work package feeds on Entra-joined Windows
devices (including hybrid joined), and personal feeds elsewhere. Adding a work
account alone does not count. Set `DOTFILES_PROFILE` to `work`, `personal`, or
`auto` before init to change a remembered choice. WSL does not probe Windows.
Windows work setup uses Intune's `azure-powershell` repository for PowerShell modules and WinGet DSC resources.

```sh
chezmoi init DariuszPorowski --apply
```

On Linux or WSL, `sh ./install.sh` also works from this checkout.
For signed commits, enable the 1Password SSH agent on the host.
For the PowerShell extension's console in VS Code, keep `powershell.enableProfileLoading` enabled.

When Podman is on `PATH`, new shells map `docker` to `podman` and `docker-compose`
to `podman compose`. Compose needs an installed provider such as `podman-compose`.
Fresh Windows installs request all-users Podman. Existing installs, including repairs, keep their original scope.
Shared installs can also provide `docker` to scripts without replacing an existing Docker executable.

## Update

```sh
chezmoi update
```
