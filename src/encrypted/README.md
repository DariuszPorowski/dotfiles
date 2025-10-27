# AGE

## Encrypt

```powershell
age --encrypt --armor --identity "${env:USERPROFILE}\personal.age" --output src\encrypted\azdo_microsoft.yaml.age src\encrypted\azdo_microsoft.yaml
```

```shell
age --encrypt --armor --identity "~/personal.age" --output src/encrypted/azdo_microsoft.yaml.age src/encrypted/azdo_microsoft.yaml
```

## Decrypt

```powershell
age --decrypt --identity "${env:USERPROFILE}\personal.age" src\encrypted\azdo_microsoft.yaml.age  > src\encrypted\azdo_microsoft.yaml
```

```shell
age --decrypt --identity "~/personal.age" src/encrypted/azdo_microsoft.yaml.age  > src/encrypted/azdo_microsoft.yaml
```
