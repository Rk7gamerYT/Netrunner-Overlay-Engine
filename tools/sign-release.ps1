param(
    [Parameter(Mandatory = $true)]
    [string]$Installer,

    [Parameter(Mandatory = $true)]
    [string]$CertificatePath,

    [string]$TimestampUrl = "http://timestamp.digicert.com"
)

$ErrorActionPreference = "Stop"

$signtool = @(
    (Get-Command signtool.exe -ErrorAction SilentlyContinue).Source,
    "C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\signtool.exe"
) | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1

if (-not $signtool) { throw "signtool.exe não foi encontrado. Instale o Windows SDK." }
if (-not (Test-Path -LiteralPath $Installer)) { throw "Instalador não encontrado: $Installer" }
if (-not (Test-Path -LiteralPath $CertificatePath)) { throw "Certificado PFX não encontrado: $CertificatePath" }

$password = Read-Host "Senha do certificado PFX" -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($password)
try {
    $plainPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    & $signtool sign /fd SHA256 /td SHA256 /tr $TimestampUrl /f $CertificatePath /p $plainPassword $Installer
    if ($LASTEXITCODE -ne 0) { throw "signtool falhou ao assinar o instalador." }
}
finally {
    if ($bstr -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
    $plainPassword = $null
}

& $signtool verify /pa /v $Installer
if ($LASTEXITCODE -ne 0) { throw "A verificação Authenticode falhou." }
Write-Host "Assinatura verificada: $Installer"
