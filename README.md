# MinitOS K1 — ARMv6 kernel bring-up

Independent implementation of the MinitOS K1 stage: a freestanding, 32-bit
little-endian ARMv6 kernel that boots on the QEMU `integratorcp` machine with
an ARM1136 CPU and prints a banner through a real PL011 UART driver.

K0 was used only as an input for analysis. The K0 tree was not modified and no
K0 source file is reused verbatim by this implementation.

## Verified result

The acceptance sequence was executed on 2026-11-02 with QEMU 11.1.0 and
GCC 15.2.1:

```text
MINITOS KERNEL STARTED
board: integratorcp
uart: pl011 @ 0x16000000
cpu midr: 0x4117b363
idle
```

| Criterion | Result |
|---|---|
| ELF32 little-endian ARM image built | **PASS** |
| Entry point checked against the vector table and linker symbols | **PASS** |
| QEMU machine/CPU is `integratorcp` / `arm1136` | **PASS** |
| Kernel actually executes (not merely loads) | **PASS** |
| `MINITOS KERNEL STARTED` visible on UART | **PASS** |
| Repeated clean builds are byte-identical | **PASS** |
| Samsung Galaxy Gio / MSM7227 execution | **NOT RUN** |

See [docs/K1_ACCEPTANCE.md](docs/K1_ACCEPTANCE.md) for the full evidence and
[docs/ASSUMPTIONS_AND_LIMITATIONS.md](docs/ASSUMPTIONS_AND_LIMITATIONS.md) for
everything that is *not* verified.

## Platform boundary

This kernel targets QEMU's **ARM Integrator/CP** reference machine only.

- Load address `0x00010000` is a QEMU reference layout, **not** a Galaxy Gio
  load address.
- UART0 at `0x16000000` is the **QEMU Integrator/CP** PL011, **not** a
  verified MSM7227 peripheral address.
- The Gio boot chain, SDRAM map, bootloader protocol and peripheral map are
  unknown here and are deliberately not assumed.
- Do not flash this image to a phone.

The independent board layer exists so a future Gio port can add a different
board descriptor and boot path without rewriting the kernel core.

## What K1 implements

- ARMv6 reset path in assembly with an 8-entry exception vector table.
- Deterministic Supervisor-mode entry, private 16 KiB boot stack and BSS clear.
- Board description with only verified QEMU Integrator/CP facts.
- Polled PL011 UART driver (8N1, 115200, FIFO, no interrupts).
- Console facade with `\n` → CRLF translation and hexadecimal formatting.
- CPU MIDR read through CP15 so the ARM1136 model is proven at runtime.
- Freestanding C11 kernel, no libc, no libgcc, no host runtime.
- Reproducible Python build driver, linker script, ELF checker and QEMU
  runtime harness.

## What K1 intentionally does not implement

Interrupt handling, exception recovery, MMU, caches setup, timers, physical
memory allocator, scheduler, framebuffer, application environment, UART RX,
DMA or real-hardware support. The vector table and module boundaries are
prepared for those stages, but no placeholder claims functionality.

## Quick start

### 1. Toolchain

The reference toolchain is pinned:

- xPack GNU Arm Embedded GCC **15.2.1-1.1**
- archive SHA-256
  `bae6a3d1667697ce750c3b13d6d26d80973ecedc2cc87bf04869e83447fd93ea`

On Windows:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/fetch-toolchain.ps1
$env:MINITOS_ARM_BIN = "$env:LOCALAPPDATA\Tools\xpack-arm-none-eabi-gcc-15.2.1-1.1\bin"
```

On other hosts, install an `arm-none-eabi-gcc` toolchain and either put it on
`PATH` or set `MINITOS_ARM_BIN` to its `bin` directory. The build driver also
accepts `ARM_GCC_BIN`.

### 2. Build and check

```sh
python tools/build.py build
python tools/build.py verify --no-build
python tools/verify_platform.py
python tools/run_qemu.py
python tools/build.py repro
```

Run the complete sequence (and copy evidence into `docs/evidence/`):

```sh
python tools/acceptance.py --evidence
```

With GNU Make available, the same operations are wrapped as:

```sh
make build verify platform run repro acceptance
```

### 3. Manual QEMU run

```sh
qemu-system-arm -M integratorcp -cpu arm1136 -m 128M \
    -kernel build/minitos-k1.elf -display none -monitor none -serial stdio
```

or on Windows:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run-qemu.ps1
```

The kernel never exits; stop QEMU with Ctrl+C. The automated harness waits for
the banner and terminates QEMU itself.

## Build outputs

`build/` contains:

| File | Purpose |
|---|---|
| `minitos-k1.elf` | ELF32 ARM executable loaded by QEMU |
| `minitos-k1.bin` | flat binary of the loadable image |
| `minitos-k1.map` | linker map |
| `disassembly.txt` | ARM disassembly |
| `readelf-*.txt` | ELF header, segments, sections, symbols, attributes |
| `sizes.txt`, `sizes-all.txt` | size reports |
| `memory-usage.txt` | linker memory-region usage |
| `SHA256SUMS.txt` | artifact hashes |
| `serial.log` | raw UART output from the runtime test |
| `runtime-evidence.txt` | runtime checks and serial output |
| `qemu-mtree.txt` | live QEMU memory map from QMP |
| `repro.txt` | double-build hash comparison |
| `acceptance.txt` | full acceptance log |

## Project layout

```text
minitos-k1/
├── include/minitos/          public kernel interfaces and board constants
├── src/
│   ├── arch/armv6/           start.S, CPSR/CP15 primitives
│   ├── board/                board descriptor (integratorcp)
│   ├── drivers/              PL011 UART driver
│   └── kernel/               console facade and kernel_main
├── linker/integratorcp.ld    link layout and memory budget
├── tools/                    build, ELF check, QEMU platform/runtime tests
├── scripts/                  manual toolchain and QEMU launchers
├── docs/                     architecture, decisions, platform, acceptance
└── Makefile                  thin wrapper over tools/build.py
```

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — boot flow, memory layout,
  module contracts and extension points.
- [docs/PLATFORM_INTEGRATORCP.md](docs/PLATFORM_INTEGRATORCP.md) — verified
  QEMU machine map, PL011 programming model and load contract.
- [docs/K0_ANALYSIS.md](docs/K0_ANALYSIS.md) — what K0 actually contains and
  which assumptions K1 rejects.
- [docs/DECISIONS.md](docs/DECISIONS.md) — engineering decision journal.
- [docs/ASSUMPTIONS_AND_LIMITATIONS.md](docs/ASSUMPTIONS_AND_LIMITATIONS.md) —
  explicit unverified assumptions and limits.
- [docs/K1_ACCEPTANCE.md](docs/K1_ACCEPTANCE.md) — acceptance matrix and
  evidence with exact commands and hashes.
- [docs/evidence/](docs/evidence/) — raw captured evidence.

## Reproducibility

`tools/build.py repro` performs two independent clean builds and compares the
SHA-256 of both the ELF and the flat binary. Byte-identical output was observed
on the reference host with the pinned toolchain. Cross-host and cross-toolchain
byte identity is **not** claimed; the compiler version is part of the build
definition.
