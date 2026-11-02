param(
    [string]$Elf = "build/minitos-k1.elf",
    [string]$Qemu = $env:QEMU_SYSTEM_ARM
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $Elf)) {
    throw "Missing $Elf. Build first: python tools/build.py build"
}

if (-not $Qemu) {
    $Qemu = (Get-Command qemu-system-arm -ErrorAction SilentlyContinue).Source
}
if (-not $Qemu) {
    $Candidate = Join-Path $env:ProgramFiles "qemu\qemu-system-arm.exe"
    if (Test-Path $Candidate) { $Qemu = $Candidate }
}
if (-not $Qemu) {
    throw "qemu-system-arm not found; set QEMU_SYSTEM_ARM"
}

Write-Host "Running $Elf on integratorcp/arm1136 (Ctrl+C to stop)"
& $Qemu -M integratorcp -cpu arm1136 -m 128M -kernel $Elf `
    -display none -monitor none -serial stdio
