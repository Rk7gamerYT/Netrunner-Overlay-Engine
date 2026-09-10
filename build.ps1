param(
    [string]$Python = "$PSScriptRoot\venv\Scripts\python.exe",
    [string]$Version = "1.2.8",
    [string]$Repository = $env:GITHUB_REPOSITORY
)

$ErrorActionPreference = "Stop"

$projectRoot = $PSScriptRoot
$buildDir = Join-Path $projectRoot "build"
$distDir = Join-Path $projectRoot "dist"
$releaseDir = Join-Path $projectRoot "release"
$endpointSource = Join-Path $projectRoot ".build-update-endpoint.txt"
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
    if ($Repository) {
        Set-Content -LiteralPath $endpointSource -Value "https://github.com/$Repository/releases/latest/download/latest.json" -Encoding ascii
    }
    else {
        Set-Content -LiteralPath $endpointSource -Value "" -Encoding ascii
    }

    # Evita que DLLs de ferramentas externas presentes no PATH sejam
    # incorporadas por engano ao executável.
    $env:Path = (($originalPath -split ";") | Where-Object {
        $_ -and $_ -notmatch "codex-runtimes" -and $_ -notmatch "poppler[\\/]Library[\\/]bin"
    }) -join ";"

    # Evita o stub autoextraivel/comprimido do --onefile. Esse stub e um
    # padrao comum de falsos positivos em engines heuristicas; o Inno
    # Setup ja empacota a pasta inteira de forma transparente.
    # Nuitka gera um standalone nativo, sem o bootloader/archive do
    # PyInstaller que provocou o alerta heuristico Wacatac.
    & $pythonCommand -m nuitka `
        --mode=standalone `
        --windows-console-mode=disable `
        --assume-yes-for-downloads `
        --remove-output `
        --output-dir="$distDir" `
        --output-filename=NetrunnerOverlay.exe `
        --windows-icon-from-ico="$projectRoot\assets\netrunner.ico" `
        --company-name="Netrunner" `
        --product-name="Netrunner Overlay Engine" `
        --file-description="Netrunner Overlay Engine" `
        --file-version=$Version.0 `
        --product-version=$Version `
        --include-data-dir="$projectRoot\assets=assets" `
        --include-data-dir="$projectRoot\ui=ui" `
        --include-data-files="$endpointSource=update_endpoint.txt" `
        --include-package=TikTokLive `
        --include-package=pytchat `
        --include-package=pysher `
        --nofollow-import-to=PyQt6 `
        --nofollow-import-to=PySide6 `
        --nofollow-import-to=webview.platforms.android `
        --noinclude-data-files=webview/lib/pywebview-android.jar `
        "main.py"

    if ($LASTEXITCODE -ne 0) {
        throw "Nuitka encerrou com código $LASTEXITCODE."
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

    # Assinatura Authenticode e feita antes do hash. Sem certificado, a build
    # continua reproduzivel, mas o aviso e explicito: checksum nao substitui
    # identidade do publicador e nao remove alertas de reputacao.
    if ($env:NETRUNNER_SIGNING_CERTIFICATE) {
        & (Join-Path $projectRoot "tools\sign-release.ps1") `
            -Installer $installerPath `
            -CertificatePath $env:NETRUNNER_SIGNING_CERTIFICATE
        if ($LASTEXITCODE -ne 0) {
            throw "A assinatura Authenticode do instalador falhou."
        }
    }

    # Alternativa portatil: o executavel Nuitka isolado passou limpo no
    # VirusTotal, enquanto alguns modelos heurísticos penalizam o bootstrap
    # do instalador. O ZIP preserva a arvore standalone sem executar setup.
    $portablePath = Join-Path $releaseDir "NetrunnerOverlay-Portable-v$Version-windows-x64.zip"
    Compress-Archive `
        -Path (Join-Path $distDir "main.dist\*") `
        -DestinationPath $portablePath `
        -CompressionLevel Optimal

    $installerHash = Get-FileHash -LiteralPath $installerPath -Algorithm SHA256
    $portableHash = Get-FileHash -LiteralPath $portablePath -Algorithm SHA256
    $checksumLines = @(
        "$($installerHash.Hash)  $(Split-Path -Leaf $installerPath)",
        "$($portableHash.Hash)  $(Split-Path -Leaf $portablePath)"
    )
    Set-Content -LiteralPath (Join-Path $releaseDir "SHA256SUMS.txt") -Value $checksumLines -Encoding ascii
    if ($Repository) {
        $manifest = [ordered]@{
            version = $Version
            download_url = "https://github.com/$Repository/releases/download/v$Version/$(Split-Path -Leaf $installerPath)"
            sha256 = $installerHash.Hash.ToLowerInvariant()
            notes_url = "https://github.com/$Repository/releases/tag/v$Version"
        }
        $manifest | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $releaseDir "latest.json") -Encoding utf8
    }
}
finally {
    $env:Path = $originalPath
    if (Test-Path -LiteralPath $endpointSource) {
        Remove-Item -LiteralPath $endpointSource -Force
    }
    Pop-Location
}

Write-Host "Instalador criado em: $installerPath"
Write-Host "Pacote portátil criado em: $portablePath"
if ($Repository) {
    Write-Host "Manifesto de atualização criado em: $(Join-Path $releaseDir 'latest.json')"
}
if (-not $env:NETRUNNER_SIGNING_CERTIFICATE) {
    Write-Warning "Build sem assinatura Authenticode. Defina NETRUNNER_SIGNING_CERTIFICATE para distribuir."
}
