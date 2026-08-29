param(
    [string]$Python = "$PSScriptRoot\venv\Scripts\python.exe",
    [string]$Version = "1.2.0"
)

$ErrorActionPreference = "Stop"

$projectRoot = $PSScriptRoot
$buildDir = Join-Path $projectRoot "build"
$distDir = Join-Path $projectRoot "dist"
$releaseDir = Join-Path $projectRoot "release"
$originalPath = $env:Path

if (Test-Path -LiteralPath $Python) {
    $pythonCommand = (Resolve-Path -LiteralPath $Python).Path
}
else {
    $resolvedPython = Get-Command $Python -ErrorAction SilentlyContinue

    if (-not $resolvedPython) {
        throw "Python não encontrado em: $Python"
    }

    $pythonCommand = $resolvedPython.Source
}

foreach ($target in @($buildDir, $distDir, $releaseDir)) {
    if (Test-Path -LiteralPath $target) {
        Remove-Item -LiteralPath $target -Recurse -Force
    }
}

Push-Location $projectRoot

try {
    # Evita que DLLs de ferramentas externas presentes no PATH sejam
    # incorporadas por engano ao executável.
    $env:Path = (($originalPath -split ";") | Where-Object {
        $_ -and $_ -notmatch "codex-runtimes" -and $_ -notmatch "poppler[\\/]Library[\\/]bin"
    }) -join ";"

    & $pythonCommand -m PyInstaller `
        --noconfirm `
        --clean `
        --onefile `
        --windowed `
        --name "NetrunnerOverlay" `
        --icon "assets\netrunner.ico" `
        --version-file "version_info.txt" `
        --add-data "assets\netrunner.ico;assets" `
        --add-data "assets\netrunner.png;assets" `
        --add-data "assets\platforms;assets\platforms" `
        --add-data "ui\dashboard.html;ui" `
        --exclude-module "PyQt6" `
        --exclude-module "PySide6" `
        --collect-all "webview" `
        --collect-all "TikTokLive" `
        --collect-all "pytchat" `
        --collect-all "pysher" `
        "main.py"

    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller encerrou com código $LASTEXITCODE."
    }

    $isccCandidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        "C:\Program Files\Inno Setup 6\ISCC.exe"
    )
    $iscc = $isccCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if (-not $iscc) {
        throw "Inno Setup 6 não encontrado. Instale-o antes de gerar o instalador."
    }

    & $iscc `
        "/DAppVersion=$Version" `
        "/DProjectRoot=$projectRoot" `
        "/DOutputDir=$releaseDir" `
        (Join-Path $projectRoot "installer\NetrunnerOverlay.iss")

    if ($LASTEXITCODE -ne 0) {
        throw "Inno Setup encerrou com código $LASTEXITCODE."
    }

    $installerPath = Join-Path $releaseDir "NetrunnerOverlay-Setup-v$Version-windows-x64.exe"
    $installerHash = Get-FileHash -LiteralPath $installerPath -Algorithm SHA256
    $checksumLines = @(
        "$($installerHash.Hash)  $(Split-Path -Leaf $installerPath)"
    )
    Set-Content -LiteralPath (Join-Path $releaseDir "SHA256SUMS.txt") -Value $checksumLines -Encoding ascii
}
finally {
    $env:Path = $originalPath
    Pop-Location
}

Write-Host "Instalador criado em: $installerPath"
