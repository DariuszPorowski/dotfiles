# Editing encrypted profiles

On a trusted personal workstation, run this from the repository root with the
personal chezmoi configuration initialized:

```sh
chezmoi edit-encrypted home/encrypted/azdo_microsoft.yaml.age
```

The command opens a temporary decrypted copy and re-encrypts it when the
editor exits. Use an editor that waits until you finish, and avoid persistent
editor backups, swap files or cloud sync for decrypted data. Do not redirect
plaintext into the working tree or add `personal.age` to Git.
