# Pinned ARM bare-metal toolchain for MinitOS K1.
#
# The download is large (~320 MiB). The script is idempotent: if the pinned
# toolchain is already present it exits without downloading again.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts/fetch-toolchain.ps1
#   $env:MINITOS_ARM_BIN = "$env:LOCALAPPDATA\Tools\xpack-arm-none-eabi-gcc-15.2.1-1.1\bin"

$ErrorActionPreference = "Stop"

$Version = "15.2.1-1.1"
$Sha256 = "bae6a3d1667697ce750c3b13d6d26d80973ecedc2cc87bf04869e83447fd93ea"
$Name = "xpack-arm-none-eabi-gcc-$Version"
$Root = Join-Path $env:LOCALAPPDATA "Tools"
$Dest = Join-Path $Root $Name
$Gcc = Join-Path $Dest "bin\arm-none-eabi-gcc.exe"
$Zip = Join-Path $env:TEMP "$Name-win32-x64.zip"
$Url = "https://github.com/xpack-dev-tools/arm-none-eabi-gcc-xpack/releases/download/v$Version/$Name-win32-x64.zip"

if (Test-Path $Gcc) {
    Write-Host "ARM toolchain already installed: $Dest"
    Write-Host "MINITOS_ARM_BIN=$Dest\bin"
    exit 0
}

if (-not (Test-Path $Zip)) {
    Write-Host "Downloading $Url"
    Invoke-WebRequest -Uri $Url -OutFile $Zip -UseBasicParsing
}

$Actual = (Get-FileHash $Zip -Algorithm SHA256).Hash.ToLowerInvariant()
if ($Actual -ne $Sha256) {
    throw "SHA256 mismatch for $Zip`nexpected $Sha256`nactual   $Actual"
}

New-Item -ItemType Directory -Force -Path $Root | Out-Null
Write-Host "Extracting to $Root"
tar.exe -xf $Zip -C $Root

if (-not (Test-Path $Gcc)) {
    throw "toolchain extraction did not produce $Gcc"
}

Write-Host "ARM toolchain installed: $Dest"
Write-Host "Set this in the current shell:"
Write-Host "  `$env:MINITOS_ARM_BIN = `"$Dest\bin`""
