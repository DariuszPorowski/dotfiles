# Dotfiles

Uses [chezmoi](https://www.chezmoi.io/) as the dotfile manager.

## AGE key

Set AGE key

### 1Password CLI

```sh
op read op://personal/age/key > ~/personal.age
```

### PowerShell

```pwsh
# Prevent saving further history in this session (optional)
Set-PSReadLineOption -HistorySaveStyle SaveNothing

$plain = Read-Host 'Paste AGE private key (not saved to history)'
Set-Content -Path $HOME/personal.age -Value $plain -NoNewline
Remove-Variable plain
```

### Bash

Paste then Ctrl+D (the key itself is never on a command line):

```sh
cat > ~/personal.age
# paste key
# Ctrl+D
```

Optionally make sure only you can read it:

```sh
chmod 600 ~/personal.age
```

## Linux

Init with CURL

```sh
sh -c "$(curl -fsLS get.chezmoi.io)" -- init DariuszPorowski --apply
```

Init with WGET

```sh
sh -c "$(wget -qO- get.chezmoi.io)" -- init DariuszPorowski --apply
```

Some of the scripts require `sudo`.

## Windows

Install chezmoi in an elevated shell.

```pwsh
winget install twpayne.chezmoi
```

Init

```pwsh
chezmoi init DariuszPorowski --apply
```

Init with PS

```pwsh
iex "&{$(irm 'https://get.chezmoi.io/ps1')} -- init DariuszPorowski --apply"
```
