#!/bin/sh
# Manual QEMU launcher. Not executed by the Windows reference acceptance run;
# tools/run_qemu.py is the tested path.
set -eu

ELF="${1:-build/minitos-k1.elf}"
QEMU="${QEMU_SYSTEM_ARM:-qemu-system-arm}"

if [ ! -f "$ELF" ]; then
    echo "Missing $ELF. Build first: python3 tools/build.py build" >&2
    exit 2
fi

exec "$QEMU" -M integratorcp -cpu arm1136 -m 128M -kernel "$ELF" \
    -display none -monitor none -serial stdio
