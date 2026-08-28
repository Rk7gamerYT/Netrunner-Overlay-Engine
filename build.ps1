param(
    [string]$Python = "$PSScriptRoot\venv\Scripts\python.exe",
    [string]$Version = "1.0.0"
)

$ErrorActionPreference = "Stop"

$projectRoot = $PSScriptRoot
$buildDir = Join-Path $projectRoot "build"
$distDir = Join-Path $projectRoot "dist"
$releaseDir = Join-Path $projectRoot "release"
$packageDir = Join-Path $releaseDir "NetrunnerOverlay"
$zipPath = Join-Path $releaseDir "NetrunnerOverlay-v$Version-windows-x64.zip"
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
    # Evita que DLLs de ferramentas externas presentes no PATH (como Poppler/ICU)
    # sejam incorporadas por engano e entrem em conflito com o Qt no executável.
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
        --collect-all "TikTokLive" `
        --collect-all "pytchat" `
        --collect-all "pysher" `
        "main.py"

    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller encerrou com código $LASTEXITCODE."
    }

    New-Item -ItemType Directory -Path $packageDir -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $distDir "NetrunnerOverlay.exe") -Destination $packageDir
    Copy-Item -LiteralPath (Join-Path $projectRoot "README.md") -Destination $packageDir

    Compress-Archive -Path (Join-Path $packageDir "*") -DestinationPath $zipPath -CompressionLevel Optimal

    $exeHash = Get-FileHash -LiteralPath (Join-Path $distDir "NetrunnerOverlay.exe") -Algorithm SHA256
    $zipHash = Get-FileHash -LiteralPath $zipPath -Algorithm SHA256
    $checksumLines = @(
        "$($exeHash.Hash)  NetrunnerOverlay.exe",
        "$($zipHash.Hash)  $(Split-Path -Leaf $zipPath)"
    )
    Set-Content -LiteralPath (Join-Path $releaseDir "SHA256SUMS.txt") -Value $checksumLines -Encoding ascii
}
finally {
    $env:Path = $originalPath
    Pop-Location
}

Write-Host "Pacote criado em: $zipPath"
