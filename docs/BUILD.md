# Compilação e publicação

## Requisitos

- Windows 10 ou 11, 64 bits.
- Python 3.12 ou superior.
- Dependências de `requirements.txt`.
- PyInstaller e Pillow.

## Preparar o ambiente

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe -m pip install pyinstaller pillow
```

## Gerar o pacote

```powershell
.\build.ps1
```

O script cria:

- `dist/NetrunnerOverlay.exe`
- `release/NetrunnerOverlay-v1.0.0-windows-x64.zip`
- `release/SHA256SUMS.txt`

## Criar uma Release no GitHub

1. Confirme que todos os testes foram executados.
2. Faça commit das mudanças.
3. Crie e envie uma tag como `v1.0.0`.

```powershell
git tag v1.0.0
git push origin v1.0.0
```

O workflow `build-windows.yml` compila o aplicativo no Windows. Em uma tag `v*`, ele também cria a Release e anexa o ZIP e o arquivo de checksums.

## Alterar a versão

Ao preparar outra versão, atualize os valores em:

- `build.ps1`
- `version_info.txt`
- nomes de download citados no `README.md`

