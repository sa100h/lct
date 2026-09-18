param([string]$OutputDirectory = ".keys")

$ErrorActionPreference = "Stop"
$resolved = [System.IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Path $resolved -Force | Out-Null
$private = Join-Path $resolved "jwt-private.pem"
$public = Join-Path $resolved "jwt-public.pem"
if ((Test-Path $private) -or (Test-Path $public)) {
    throw "JWT keys already exist in $resolved; refusing to overwrite them."
}

& openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -out $private
if ($LASTEXITCODE -ne 0) { throw "Failed to generate JWT private key." }
& openssl pkey -in $private -pubout -out $public
if ($LASTEXITCODE -ne 0) { throw "Failed to generate JWT public key." }
Write-Host "Generated JWT keys in $resolved"
