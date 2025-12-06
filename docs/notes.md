# NOTES

Just something that I often forget

---

## GPG

- Export keys

  ```sh
  # Public key
  gpg --output public-key.pgp --armor --export example@example.com
  # Private key
  gpg --output private-key.pgp --armor --export-secret-key example@example.com
  ```

- Import _(for both public and private keys)_

  ```sh
  gpg --import the-key.gpg
  ```

- Trust a key

  ```sh
  gpg --list-signatures
  ```

  ```sh
  gpg --edit-key {key-id}
  # trust
  # 5
  # quit
  ```

- Start gpg-agent and keyboxd (with task scheduler!)

  ```sh
  gpgconf --launch gpg-agent
  gpgconf --launch keyboxd
  ```
